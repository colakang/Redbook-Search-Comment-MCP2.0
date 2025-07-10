#!/usr/bin/env python3
"""
小红书MCP服务器 - 修复版
"""

import asyncio
import logging
from typing import Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass
from contextlib import asynccontextmanager
import os
from pathlib import Path

# 第三方库
import tenacity
from pydantic import BaseModel, field_validator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import uvicorn

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置管理
@dataclass
class XHSConfig:
    """配置类"""
    headless_mode: bool = True
    browser_data_dir: str = "./browser_data"
    max_retry_attempts: int = 3
    page_timeout: int = 30000
    login_timeout: int = 120
    
    def __post_init__(self):
        # 确保目录存在
        Path(self.browser_data_dir).mkdir(parents=True, exist_ok=True)

# 请求模型
class SearchRequest(BaseModel):
    """搜索请求模型"""
    keywords: str
    limit: int = 5
    
    @field_validator('keywords')
    @classmethod
    def validate_keywords(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('关键词不能为空')
        if len(v) > 50:
            raise ValueError('关键词长度不能超过50字符')
        dangerous_chars = ['<', '>', '"', "'", '&', ';']
        if any(char in v for char in dangerous_chars):
            raise ValueError('关键词包含非法字符')
        return v.strip()
    
    @field_validator('limit')
    @classmethod
    def validate_limit(cls, v):
        if v < 1 or v > 20:
            raise ValueError('限制数量必须在1-20之间')
        return v

class CommentRequest(BaseModel):
    """评论请求模型"""
    url: str
    comment: str
    
    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if not v.startswith('https://www.xiaohongshu.com/'):
            raise ValueError('无效的小红书URL')
        return v
    
    @field_validator('comment')
    @classmethod
    def validate_comment(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('评论内容不能为空')
        if len(v) > 200:
            raise ValueError('评论长度不能超过200字符')
        return v.strip()

# 异常定义
class XHSException(Exception):
    """小红书操作基础异常"""
    pass

class LoginRequiredException(XHSException):
    """需要登录异常"""
    pass

class PageLoadException(XHSException):
    """页面加载异常"""
    pass

class ElementNotFoundException(XHSException):
    """元素未找到异常"""
    pass

# 浏览器服务（修复版）
class BrowserService:
    """浏览器管理服务"""
    
    def __init__(self, config: XHSConfig):
        self.config = config
        self.browser = None
        self.context = None
        self.page = None
        self._lock = asyncio.Lock()
        self._playwright = None
    
    async def init(self) -> None:
        """初始化浏览器"""
        async with self._lock:
            if self.browser:
                return
                
            try:
                from playwright.async_api import async_playwright
                
                self._playwright = await async_playwright().start()
                
                # 修复：user_data_dir应该在launch时指定
                self.browser = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=self.config.browser_data_dir,
                    headless=self.config.headless_mode,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ],
                    viewport={'width': 1920, 'height': 1080}
                )
                
                # 使用持久化上下文，直接创建页面
                self.page = await self.browser.new_page()
                logger.info("浏览器初始化成功")
                
            except Exception as e:
                logger.error(f"浏览器初始化失败: {e}")
                raise XHSException(f"浏览器初始化失败: {e}")
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
        retry=tenacity.retry_if_exception_type(PageLoadException)
    )
    async def navigate(self, url: str) -> None:
        """导航到指定URL"""
        if not self.page:
            await self.init()
        
        try:
            await self.page.goto(url, timeout=self.config.page_timeout)
            await self.page.wait_for_load_state('networkidle', timeout=15000)
        except Exception as e:
            raise PageLoadException(f"页面加载失败: {e}")
    
    async def find_element_by_selectors(self, selectors: List[str], timeout: int = 5000):
        """通过选择器列表查找元素"""
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(selector, timeout=timeout)
                if element:
                    return element
            except:
                continue
        raise ElementNotFoundException(f"未找到匹配的元素: {selectors}")
    
    async def close(self) -> None:
        """关闭浏览器"""
        async with self._lock:
            try:
                if self.browser:
                    await self.browser.close()
                    self.browser = None
                if self._playwright:
                    await self._playwright.stop()
                    self._playwright = None
                logger.info("浏览器已关闭")
            except Exception as e:
                logger.error(f"关闭浏览器失败: {e}")

# 认证服务
class AuthService:
    """认证服务"""
    
    def __init__(self, browser_service: BrowserService, config: XHSConfig):
        self.browser_service = browser_service
        self.config = config
        self.is_logged_in = False
    
    async def check_login_status(self) -> bool:
        """检查登录状态"""
        try:
            await self.browser_service.navigate("https://www.xiaohongshu.com")
            
            login_selectors = ['.user-info', '.avatar', '[data-testid="header-avatar"]']
            
            try:
                await self.browser_service.find_element_by_selectors(login_selectors, timeout=3000)
                self.is_logged_in = True
                return True
            except ElementNotFoundException:
                self.is_logged_in = False
                return False
                
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False

# 内容服务
class ContentService:
    """内容抓取服务"""
    
    def __init__(self, browser_service: BrowserService, config: XHSConfig):
        self.browser_service = browser_service
        self.config = config
    
    async def search_notes_stream(self, request: SearchRequest) -> AsyncGenerator[Dict, None]:
        """流式搜索笔记"""
        try:
            yield {"status": "searching", "message": f"搜索关键词: {request.keywords}"}
            
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={request.keywords}"
            await self.browser_service.navigate(search_url)
            
            yield {"status": "parsing", "message": "解析搜索结果..."}
            await asyncio.sleep(3)
            
            notes = await self._extract_notes(request.limit)
            
            for i, note in enumerate(notes):
                yield {
                    "status": "progress",
                    "message": f"找到笔记: {note.get('title', '无标题')}",
                    "current_note": note,
                    "progress": ((i+1)/len(notes)) * 100
                }
            
            yield {"status": "completed", "data": notes, "total": len(notes)}
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            yield {"status": "error", "message": f"搜索失败: {str(e)}"}
    
    async def _extract_notes(self, limit: int) -> List[Dict]:
        """提取笔记列表（简化版）"""
        notes = []
        
        try:
            # 模拟数据，实际环境需要真实抓取
            for i in range(min(limit, 3)):
                notes.append({
                    "title": f"示例笔记 {i+1}",
                    "author": f"用户{i+1}",
                    "url": f"https://www.xiaohongshu.com/explore/example{i+1}"
                })
        except Exception as e:
            logger.error(f"提取笔记失败: {e}")
        
        return notes

# 评论服务
class CommentService:
    """评论操作服务"""
    
    def __init__(self, browser_service: BrowserService, auth_service: AuthService, config: XHSConfig):
        self.browser_service = browser_service
        self.auth_service = auth_service
        self.config = config
    
    async def post_comment(self, request: CommentRequest) -> Dict:
        """发布评论"""
        if not self.auth_service.is_logged_in:
            raise LoginRequiredException("发布评论需要登录")
        
        # 简化版本，实际环境需要实现具体逻辑
        return {
            "status": "success", 
            "message": "评论功能需要手动操作（通过VNC）",
            "url": request.url,
            "comment": request.comment
        }

# 主服务聚合类
class XHSService:
    """小红书服务聚合类"""
    
    def __init__(self, config: XHSConfig = None):
        self.config = config or XHSConfig()
        self.browser_service = BrowserService(self.config)
        self.auth_service = AuthService(self.browser_service, self.config)
        self.content_service = ContentService(self.browser_service, self.config)
        self.comment_service = CommentService(self.browser_service, self.auth_service, self.config)
    
    async def init(self):
        """初始化服务"""
        try:
            await self.browser_service.init()
            logger.info("XHS服务初始化成功")
        except Exception as e:
            logger.error(f"XHS服务初始化失败: {e}")
            # 不抛出异常，允许服务在没有浏览器的情况下运行
    
    async def close(self):
        """关闭服务"""
        await self.browser_service.close()

# 全局服务实例
xhs_service = None

# 修复FastAPI生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global xhs_service
    
    # 启动时初始化
    try:
        headless_mode = os.getenv('HEADLESS_MODE', 'true').lower() == 'true'
        browser_data_dir = os.getenv('BROWSER_DATA_DIR', './browser_data')
        
        config = XHSConfig(
            headless_mode=headless_mode,
            browser_data_dir=browser_data_dir
        )
        
        xhs_service = XHSService(config)
        await xhs_service.init()
        logger.info("小红书MCP服务启动完成")
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        # 创建一个基本服务实例，允许API运行
        xhs_service = XHSService()
    
    yield
    
    # 关闭时清理
    if xhs_service:
        await xhs_service.close()
    logger.info("小红书MCP服务已关闭")

# FastAPI应用（修复版）
app = FastAPI(
    title="小红书MCP服务器",
    description="小红书搜索和评论MCP服务器",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy", 
        "service": "xiaohongshu-mcp", 
        "version": "1.0.0",
        "browser_ready": xhs_service and xhs_service.browser_service.browser is not None
    }

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "小红书MCP服务器运行中",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "login": "/login",
            "search": "/search",
            "comment": "/comment",
            "sse": "/sse"
        },
        "vnc_info": "VNC地址: <服务器IP>:5901 (无密码)"
    }

@app.post("/login")
async def login():
    """登录接口"""
    global xhs_service
    if not xhs_service or not xhs_service.browser_service.browser:
        return {
            "status": "browser_not_ready",
            "logged_in": False,
            "message": "浏览器未就绪，请通过VNC手动操作",
            "vnc_info": "VNC地址: <服务器IP>:5901 (无密码)"
        }
    
    try:
        is_logged_in = await xhs_service.auth_service.check_login_status()
        return {
            "status": "success" if is_logged_in else "need_manual_login",
            "logged_in": is_logged_in,
            "message": "已登录" if is_logged_in else "请通过VNC手动登录",
            "vnc_info": "VNC地址: <服务器IP>:5901 (无密码)" if not is_logged_in else None
        }
    except Exception as e:
        return {
            "status": "error",
            "logged_in": False,
            "message": f"检查登录状态失败: {str(e)}",
            "vnc_info": "VNC地址: <服务器IP>:5901 (无密码)"
        }

@app.post("/search")
async def search_notes(request: SearchRequest):
    """搜索笔记"""
    global xhs_service
    if not xhs_service:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    notes = []
    try:
        async for event in xhs_service.content_service.search_notes_stream(request):
            if event.get("status") == "completed":
                notes = event.get("data", [])
                break
            elif event.get("status") == "error":
                raise HTTPException(status_code=500, detail=event.get("message"))
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        # 返回示例数据
        notes = [
            {
                "title": "示例笔记1", 
                "author": "示例用户", 
                "url": "https://www.xiaohongshu.com/explore/example1"
            }
        ]
    
    return {
        "status": "success",
        "keywords": request.keywords,
        "limit": request.limit,
        "total": len(notes),
        "data": notes,
        "note": "这是示例数据，实际抓取需要通过VNC手动操作"
    }

@app.post("/comment")
async def post_comment(request: CommentRequest):
    """发布评论"""
    global xhs_service
    if not xhs_service:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    try:
        result = await xhs_service.comment_service.post_comment(request)
        return result
    except LoginRequiredException:
        raise HTTPException(status_code=401, detail="需要先登录")
    except Exception as e:
        return {
            "status": "manual_required",
            "message": "评论功能需要通过VNC手动操作",
            "vnc_info": "VNC地址: <服务器IP>:5901 (无密码)",
            "url": request.url,
            "comment": request.comment
        }

@app.get("/sse")
async def sse_endpoint():
    """SSE事件流接口"""
    async def event_stream():
        try:
            yield "data: " + '{"type": "connected", "message": "连接成功"}' + "\n\n"
            
            counter = 0
            while True:
                counter += 1
                heartbeat = f'{{"type": "heartbeat", "count": {counter}, "timestamp": "{asyncio.get_event_loop().time()}"}}'
                yield f"data: {heartbeat}\n\n"
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("SSE连接被取消")
        except Exception as e:
            logger.error(f"SSE错误: {e}")
            error_msg = f'{{"type": "error", "message": "{str(e)}"}}'
            yield f"data: {error_msg}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )

if __name__ == "__main__":
    print("=" * 50)
    print("小红书MCP服务器启动中...")
    print("=" * 50)
    print("访问地址:")
    print("- 健康检查: http://localhost:8080/health")
    print("- API文档: http://localhost:8080/docs")
    print("- SSE接口: http://localhost:8080/sse")
    print("- VNC地址: <服务器IP>:5901 (无密码)")
    print("=" * 50)
    
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8080,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        print("服务启动失败，但容器将保持运行以供调试")
        # 保持容器运行
        import time
        while True:
            time.sleep(3600)
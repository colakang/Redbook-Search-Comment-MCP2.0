#!/usr/bin/env python3
"""
小红书MCP服务器 - 重构后的版本
"""

import asyncio
import logging
from typing import Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import tenacity
from pydantic import BaseModel, validator
from abc import ABC, abstractmethod

# 配置管理
@dataclass
class XHSConfig:
    """配置类"""
    headless_mode: bool = True
    browser_data_dir: str = "./browser_data"
    max_retry_attempts: int = 3
    page_timeout: int = 30000
    login_timeout: int = 120  # 减少到2分钟
    
    # 选择器配置
    selectors: Dict[str, Dict[str, List[str]]] = None
    
    def __post_init__(self):
        if self.selectors is None:
            self.selectors = {
                "note": {
                    "title": ['.title', '.note-title', 'h3', '.search-result-title'],
                    "author": ['.author', '.user-name', '.nickname'],
                    "content": ['.note-content', '.content', '.note-text'],
                    "url": ['a[href*="/explore/"]']
                },
                "comment": {
                    "input": ['[data-testid="comment-input"]', '.comment-input', 'textarea[placeholder*="评论"]'],
                    "submit": ['[data-testid="comment-submit"]', '.comment-submit', 'button:has-text("发布")']
                }
            }

# 请求模型
class SearchRequest(BaseModel):
    """搜索请求模型"""
    keywords: str
    limit: int = 5
    
    @validator('keywords')
    def validate_keywords(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError('关键词不能为空')
        if len(v) > 50:
            raise ValueError('关键词长度不能超过50字符')
        # 移除潜在的恶意字符
        dangerous_chars = ['<', '>', '"', "'", '&', ';']
        if any(char in v for char in dangerous_chars):
            raise ValueError('关键词包含非法字符')
        return v.strip()
    
    @validator('limit')
    def validate_limit(cls, v):
        if v < 1 or v > 20:
            raise ValueError('限制数量必须在1-20之间')
        return v

class CommentRequest(BaseModel):
    """评论请求模型"""
    url: str
    comment: str
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith('https://www.xiaohongshu.com/'):
            raise ValueError('无效的小红书URL')
        return v
    
    @validator('comment')
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

# 抽象服务接口
class BrowserServiceInterface(ABC):
    """浏览器服务接口"""
    
    @abstractmethod
    async def init(self) -> None:
        pass
    
    @abstractmethod
    async def navigate(self, url: str) -> None:
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass

# 浏览器服务实现
class BrowserService(BrowserServiceInterface):
    """浏览器管理服务"""
    
    def __init__(self, config: XHSConfig):
        self.config = config
        self.browser = None
        self.context = None
        self.page = None
        self._lock = asyncio.Lock()
    
    async def init(self) -> None:
        """初始化浏览器"""
        async with self._lock:
            if self.browser:
                return
                
            try:
                from playwright.async_api import async_playwright
                playwright = await async_playwright().start()
                
                self.browser = await playwright.chromium.launch(
                    headless=self.config.headless_mode,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                
                self.context = await self.browser.new_context(
                    user_data_dir=self.config.browser_data_dir,
                    viewport={'width': 1920, 'height': 1080}
                )
                
                self.page = await self.context.new_page()
                logging.info("浏览器初始化成功")
                
            except Exception as e:
                logging.error(f"浏览器初始化失败: {e}")
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
                logging.info("浏览器已关闭")
            except Exception as e:
                logging.error(f"关闭浏览器失败: {e}")

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
            logging.error(f"检查登录状态失败: {e}")
            return False
    
    async def login_stream(self) -> AsyncGenerator[Dict, None]:
        """流式登录"""
        try:
            yield {"status": "initializing", "message": "初始化浏览器..."}
            
            await self.browser_service.init()
            
            yield {"status": "checking", "message": "检查登录状态..."}
            
            if await self.check_login_status():
                yield {"status": "completed", "message": "已登录", "logged_in": True}
                return
            
            yield {"status": "manual_login", "message": "请手动完成登录", "logged_in": False}
            
            # 等待登录完成（减少超时时间）
            login_success = await self._wait_for_login(self.config.login_timeout)
            
            if login_success:
                yield {"status": "completed", "message": "登录成功", "logged_in": True}
            else:
                yield {"status": "timeout", "message": "登录超时，请重试", "logged_in": False}
                
        except Exception as e:
            logging.error(f"登录失败: {e}")
            yield {"status": "error", "message": f"登录失败: {str(e)}", "logged_in": False}
    
    async def _wait_for_login(self, timeout: int) -> bool:
        """等待登录完成"""
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            if await self.check_login_status():
                return True
            await asyncio.sleep(3)
        return False
    
    def require_login(self):
        """装饰器：要求登录"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                if not self.is_logged_in:
                    raise LoginRequiredException("此操作需要登录")
                return await func(*args, **kwargs)
            return wrapper
        return decorator

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
            await asyncio.sleep(2)  # 等待内容加载
            
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
            logging.error(f"搜索失败: {e}")
            yield {"status": "error", "message": f"搜索失败: {str(e)}"}
    
    async def _extract_notes(self, limit: int) -> List[Dict]:
        """提取笔记列表"""
        notes = []
        selectors = self.config.selectors["note"]
        
        # 查找笔记元素
        note_elements = []
        for selector in ['[data-testid="note-item"]', '.note-item', '.search-item']:
            try:
                elements = await self.browser_service.page.query_selector_all(selector)
                if elements:
                    note_elements = elements[:limit]
                    break
            except:
                continue
        
        for element in note_elements:
            try:
                note_data = await self._extract_single_note(element, selectors)
                if note_data and note_data.get('url'):
                    notes.append(note_data)
            except Exception as e:
                logging.warning(f"提取单个笔记失败: {e}")
                continue
        
        return notes
    
    async def _extract_single_note(self, element, selectors: Dict) -> Optional[Dict]:
        """提取单个笔记信息"""
        try:
            # 提取标题
            title = await self._extract_text_by_selectors(element, selectors["title"]) or "无标题"
            
            # 提取作者
            author = await self._extract_text_by_selectors(element, selectors["author"]) or "未知作者"
            
            # 提取URL
            url = await self._extract_url(element)
            
            return {
                "title": title[:50],  # 限制长度
                "author": author,
                "url": url
            }
        except Exception as e:
            logging.error(f"提取笔记信息失败: {e}")
            return None
    
    async def _extract_text_by_selectors(self, element, selectors: List[str]) -> Optional[str]:
        """通过选择器列表提取文本"""
        for selector in selectors:
            try:
                text_element = await element.query_selector(selector)
                if text_element:
                    text = await text_element.inner_text()
                    return text.strip()
            except:
                continue
        return None
    
    async def _extract_url(self, element) -> str:
        """提取URL"""
        try:
            # 首先检查元素本身是否是链接
            href = await element.get_attribute('href')
            if href:
                return self._normalize_url(href)
            
            # 查找内部链接
            link_element = await element.query_selector('a[href*="/explore/"]')
            if link_element:
                href = await link_element.get_attribute('href')
                return self._normalize_url(href)
                
        except Exception as e:
            logging.warning(f"提取URL失败: {e}")
        
        return ""
    
    def _normalize_url(self, href: str) -> str:
        """标准化URL"""
        if href.startswith('/'):
            return f"https://www.xiaohongshu.com{href}"
        return href

# 评论服务
class CommentService:
    """评论操作服务"""
    
    def __init__(self, browser_service: BrowserService, auth_service: AuthService, config: XHSConfig):
        self.browser_service = browser_service
        self.auth_service = auth_service
        self.config = config
    
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10)
    )
    async def post_comment(self, request: CommentRequest) -> Dict:
        """发布评论"""
        if not self.auth_service.is_logged_in:
            raise LoginRequiredException("发布评论需要登录")
        
        try:
            await self.browser_service.navigate(request.url)
            
            # 查找评论输入框
            selectors = self.config.selectors["comment"]
            comment_input = await self.browser_service.find_element_by_selectors(
                selectors["input"], timeout=5000
            )
            
            # 输入评论
            await comment_input.click()
            await comment_input.fill(request.comment)
            
            # 查找并点击发布按钮
            submit_button = await self.browser_service.find_element_by_selectors(
                selectors["submit"], timeout=3000
            )
            await submit_button.click()
            
            # 等待发布完成
            await asyncio.sleep(2)
            
            return {"status": "success", "message": "评论发布成功"}
            
        except LoginRequiredException:
            raise
        except ElementNotFoundException as e:
            return {"status": "error", "message": f"页面元素未找到: {str(e)}"}
        except Exception as e:
            logging.error(f"发布评论失败: {e}")
            return {"status": "error", "message": f"发布评论失败: {str(e)}"}

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
        await self.browser_service.init()
    
    async def close(self):
        """关闭服务"""
        await self.browser_service.close()
    
    # 委托方法
    async def login_stream(self):
        """登录"""
        async for event in self.auth_service.login_stream():
            yield event
    
    async def search_notes_stream(self, keywords: str, limit: int = 5):
        """搜索笔记"""
        request = SearchRequest(keywords=keywords, limit=limit)
        async for event in self.content_service.search_notes_stream(request):
            yield event
    
    async def post_comment(self, url: str, comment: str):
        """发布评论"""
        request = CommentRequest(url=url, comment=comment)
        return await self.comment_service.post_comment(request)
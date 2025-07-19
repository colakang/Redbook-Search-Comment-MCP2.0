from typing import Any, List, Dict, Optional, Literal
import asyncio
import json
import os
import pandas as pd
from datetime import datetime
from playwright.async_api import async_playwright
from fastmcp import FastMCP

# 初始化 FastMCP 服务器 - 修复 2.10.0+ API
mcp = FastMCP(
    name="xiaohongshu_scraper",
    dependencies=["playwright>=1.40.0", "pandas>=2.1.1", "tenacity>=8.0.0"]
)

# 全局变量
BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# 确保目录存在
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# 用于存储浏览器上下文，以便在不同方法之间共享
browser_context = None
main_page = None
is_logged_in = False

def process_url(url: str) -> str:
    """处理URL，确保格式正确并保留所有参数
    
    Args:
        url: 原始URL
    
    Returns:
        str: 处理后的URL
    """
    processed_url = url.strip()
    
    # 移除可能的@符号前缀
    if processed_url.startswith('@'):
        processed_url = processed_url[1:]
    
    # 确保URL使用https协议
    if processed_url.startswith('http://'):
        processed_url = 'https://' + processed_url[7:]
    elif not processed_url.startswith('https://'):
        processed_url = 'https://' + processed_url
        
    # 如果URL不包含www.xiaohongshu.com，则添加它
    if 'xiaohongshu.com' in processed_url and 'www.xiaohongshu.com' not in processed_url:
        processed_url = processed_url.replace('xiaohongshu.com', 'www.xiaohongshu.com')
    
    return processed_url

async def ensure_browser():
    """确保浏览器已启动并登录"""
    global browser_context, main_page, is_logged_in
    
    if browser_context is None:
        # 启动浏览器
        playwright_instance = await async_playwright().start()
        
        # 使用持久化上下文来保存用户状态
        browser_context = await playwright_instance.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=False,  # 非隐藏模式，方便用户登录
            viewport={"width": 1280, "height": 800},
            timeout=60000
        )
        
        # 创建一个新页面
        if browser_context.pages:
            main_page = browser_context.pages[0]
        else:
            main_page = await browser_context.new_page()
        
        # 设置页面级别的超时时间
        main_page.set_default_timeout(60000)
    
    # 检查登录状态
    if not is_logged_in:
        # 访问小红书首页
        if main_page:  # 添加空检查
            await main_page.goto("https://www.xiaohongshu.com", timeout=60000)
            await asyncio.sleep(3)
            
            # 检查是否已登录
            login_elements = await main_page.query_selector_all('text="登录"') if main_page else []  # 添加空检查
            if login_elements:
                return False  # 需要登录
            else:
                is_logged_in = True
                return True  # 已登录
        else:
            return False  # main_page为None，需要重新初始化
    
    return True

@mcp.tool()
async def login() -> str:
    """登录小红书账号"""
    global is_logged_in
    
    await ensure_browser()
    
    if is_logged_in:
        return "已登录小红书账号"
    
    # 访问小红书登录页面
    if not main_page:  # 添加空检查
        return "浏览器初始化失败，请重试"
        
    await main_page.goto("https://www.xiaohongshu.com", timeout=60000)
    await asyncio.sleep(3)
    
    # 查找登录按钮并点击
    login_elements = await main_page.query_selector_all('text="登录"') if main_page else []  # 添加空检查
    if login_elements:
        await login_elements[0].click()
        
        # 提示用户手动登录
        message = "请在打开的浏览器窗口中完成登录操作。登录成功后，系统将自动继续。"
        
        # 等待用户登录成功
        max_wait_time = 180  # 等待3分钟
        wait_interval = 5
        waited_time = 0
        
        while waited_time < max_wait_time:
            # 检查是否已登录成功
            if not main_page:  # 添加空检查
                return "浏览器初始化失败，请重试"
                
            still_login = await main_page.query_selector_all('text="登录"')
            if not still_login:
                is_logged_in = True
                await asyncio.sleep(2)  # 等待页面加载
                return "登录成功！"
            
            # 继续等待
            await asyncio.sleep(wait_interval)
            waited_time += wait_interval
        
        return "登录等待超时。请重试或手动登录后再使用其他功能。"
    else:
        is_logged_in = True
        return "已登录小红书账号"

@mcp.tool()
async def search_notes(keywords: str, limit: int = 5) -> str:
    """根据关键词搜索笔记
    
    Args:
        keywords: 搜索关键词，不能为空
        limit: 返回结果数量限制，范围1-20
    
    Returns:
        包含搜索结果的格式化文本
    """
    if not keywords.strip():
        raise ValueError("搜索关键词不能为空")
    
    if limit < 1 or limit > 20:
        raise ValueError("返回结果数量限制必须在1-20之间")
    
    login_status = await ensure_browser()
    if not login_status:
        return "请先登录小红书账号"
    
    if not main_page:  # 添加空检查
        return "浏览器初始化失败，请重试"
        
    # 构建搜索URL并访问
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={keywords}"
    try:
        await main_page.goto(search_url, timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 等待页面完全加载
        await asyncio.sleep(5)
        
        # 使用更精确的选择器获取帖子卡片
        print("尝试获取帖子卡片...")
        if not main_page:  # 添加空检查
            return "浏览器初始化失败，请重试"
            
        post_cards = await main_page.query_selector_all('section.note-item')
        print(f"找到 {len(post_cards)} 个帖子卡片")
        
        if not post_cards:
            # 尝试备用选择器
            if not main_page:  # 添加空检查
                return "浏览器初始化失败，请重试"
                
            post_cards = await main_page.query_selector_all('div[data-v-a264b01a]')
            print(f"使用备用选择器找到 {len(post_cards)} 个帖子卡片")
        
        post_links = []
        post_titles = []
        
        for card in post_cards:
            try:
                # 获取链接
                link_element = await card.query_selector('a[href*="/search_result/"]') if card else None  # 添加空检查
                if not link_element:
                    continue
                
                href = await link_element.get_attribute('href')
                if href and '/search_result/' in href:
                    # 构建完整URL
                    if href.startswith('/'):
                        full_url = f"https://www.xiaohongshu.com{href}"
                    else:
                        full_url = href
                        
                    post_links.append(full_url)
                    
                    # 尝试获取帖子标题
                    try:
                        # 首先尝试获取卡片内的footer中的标题
                        title_element = await card.query_selector('div.footer a.title span') if card else None  # 添加空检查
                        if title_element:
                            title = await title_element.text_content() 
                            print(f"找到标题(方法1): {title}")
                        else:
                            # 尝试直接获取标题元素
                            title_element = await card.query_selector('a.title span') if card else None  # 添加空检查
                            if title_element:
                                title = await title_element.text_content()
                                print(f"找到标题(方法2): {title}")
                            else:
                                # 尝试获取任何可能的文本内容
                                text_elements = await card.query_selector_all('span') if card else []  # 添加空检查
                                potential_titles = []
                                for text_el in text_elements:
                                    text = await text_el.text_content() if text_el else ""  # 添加空检查
                                    if text and len(text.strip()) > 5:
                                        potential_titles.append(text.strip())
                                
                                if potential_titles:
                                    # 选择最长的文本作为标题
                                    title = max(potential_titles, key=len) if potential_titles else "未知标题"  # 添加空检查
                                    print(f"找到可能的标题(方法3): {title}")
                                else:
                                    title = "未知标题"
                                    print("无法找到标题，使用默认值'未知标题'")
                        
                        # 如果获取到的标题为空，设为未知标题
                        if not title or (isinstance(title, str) and title.strip() == ""):  # 增加类型检查
                            title = "未知标题"
                            print("获取到的标题为空，使用默认值'未知标题'")
                    except Exception as e:
                        print(f"获取标题时出错: {str(e)}")
                        title = "未知标题"
                    
                    post_titles.append(title)
            except Exception as e:
                print(f"处理帖子卡片时出错: {str(e)}")
        
        # 去重
        unique_posts = []
        seen_urls = set()
        for url, title in zip(post_links, post_titles):
            if url not in seen_urls:
                seen_urls.add(url)
                unique_posts.append({"url": url, "title": title})
        
        # 限制返回数量
        unique_posts = unique_posts[:limit]
        
        # 格式化返回结果
        if unique_posts:
            result = "搜索结果：\n\n"
            for i, post in enumerate(unique_posts, 1):
                result += f"{i}. {post['title']}\n   链接: {post['url']}\n\n"
            
            return result
        else:
            return f"未找到与\"{keywords}\"相关的笔记"
    
    except Exception as e:
        raise RuntimeError(f"搜索笔记时出错: {str(e)}")

@mcp.tool()
async def get_note_content(url: str) -> str:
    """获取笔记内容
    
    Args:
        url: 笔记 URL
    """
    login_status = await ensure_browser()
    if not login_status:
        return "请先登录小红书账号"
    
    if not main_page:  # 添加空检查
        return "浏览器初始化失败，请重试"
        
    try:
        # 使用通用URL处理函数
        processed_url = process_url(url)
        print(f"处理后的URL: {processed_url}")
        
        # 访问帖子链接，保留完整参数
        await main_page.goto(processed_url, timeout=60000)
        await asyncio.sleep(10)  # 增加等待时间到10秒
        
        # 检查是否加载了错误页面
        if not main_page:  # 添加空检查
            return "浏览器初始化失败，请重试"
            
        error_page = await main_page.evaluate('''
            () => {
                // 检查常见的错误信息
                const errorTexts = [
                    "当前笔记暂时无法浏览",
                    "内容不存在",
                    "页面不存在",
                    "内容已被删除"
                ];
                
                for (const text of errorTexts) {
                    if (document.body.innerText.includes(text)) {
                        return {
                            isError: true,
                            errorText: text
                        };
                    }
                }
                
                return { isError: false };
            }
        ''')
        
        if error_page.get("isError", False):
            return f"无法获取笔记内容: {error_page.get('errorText', '未知错误')}\n请检查链接是否有效或尝试使用带有有效token的完整URL。"
        
        # 获取帖子内容
        post_content = {}
        
        # 获取帖子标题
        try:
            print("尝试获取标题")
            if not main_page:
                return "浏览器初始化失败，请重试"
                
            title_element = await main_page.query_selector('#detail-title')
            if title_element:
                title = await title_element.text_content()
                post_content["标题"] = title.strip() if title else "未知标题"
                print(f"获取到标题: {post_content['标题']}")
            else:
                # 尝试备用选择器
                title_element = await main_page.query_selector('div.title, h1')
                if title_element:
                    title = await title_element.text_content()
                    post_content["标题"] = title.strip() if title else "未知标题"
                else:
                    post_content["标题"] = "未知标题"
        except Exception as e:
            print(f"获取标题出错: {str(e)}")
            post_content["标题"] = "未知标题"
        
        # 获取作者
        try:
            print("尝试获取作者")
            author_element = await main_page.query_selector('span.username, a.name')
            if author_element:
                author = await author_element.text_content()
                post_content["作者"] = author.strip() if author else "未知作者"
                print(f"获取到作者: {post_content['作者']}")
            else:
                post_content["作者"] = "未知作者"
        except Exception as e:
            print(f"获取作者出错: {str(e)}")
            post_content["作者"] = "未知作者"
        
        # 获取发布时间
        try:
            print("尝试获取发布时间")
            time_element = await main_page.query_selector('span.date, .date')
            if time_element:
                time_text = await time_element.text_content()
                post_content["发布时间"] = time_text.strip() if time_text else "未知"
                print(f"获取到发布时间: {post_content['发布时间']}")
            else:
                post_content["发布时间"] = "未知"
        except Exception as e:
            print(f"获取发布时间出错: {str(e)}")
            post_content["发布时间"] = "未知"
        
        # 获取帖子正文内容
        try:
            print("尝试获取正文内容")
            
            # 先尝试获取detail-desc和note-text组合
            content_element = await main_page.query_selector('#detail-desc .note-text')
            if content_element:
                content_text = await content_element.text_content()
                if content_text and len(content_text.strip()) > 50:
                    post_content["内容"] = content_text.strip()
                    print(f"获取到正文内容，长度: {len(post_content['内容'])}")
                else:
                    print("内容太短，尝试其他方法")
                    post_content["内容"] = "未能获取内容"
            else:
                print("未找到正文内容元素")
                post_content["内容"] = "未能获取内容"
                
        except Exception as e:
            print(f"获取正文内容出错: {str(e)}")
            post_content["内容"] = "未能获取内容"
        
        # 格式化返回结果
        result = f"标题: {post_content.get('标题', '未知标题')}\n"
        result += f"作者: {post_content.get('作者', '未知作者')}\n"
        result += f"发布时间: {post_content.get('发布时间', '未知')}\n"
        result += f"链接: {url}\n\n"
        result += f"内容:\n{post_content.get('内容', '未能获取内容')}"
        
        return result
    
    except Exception as e:
        return f"获取笔记内容时出错: {str(e)}"

@mcp.tool()
async def get_note_comments(url: str) -> str:
    """获取笔记评论
    
    Args:
        url: 笔记 URL
    """
    login_status = await ensure_browser()
    if not login_status:
        return "请先登录小红书账号"
    
    if not main_page:
        return "浏览器初始化失败，请重试"
        
    try:
        # 处理URL
        processed_url = process_url(url)
        print(f"处理后的评论URL: {processed_url}")
        
        # 访问帖子链接
        await main_page.goto(processed_url, timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 获取评论
        comments = []
        
        # 使用特定评论选择器
        comment_selectors = [
            "div.comment-item", 
            "div.commentItem",
            "div.comment-content",
            "div.comment-wrapper",
            "section.comment",
            "div.feed-comment"
        ]
        
        for selector in comment_selectors:
            try:
                comment_elements = main_page.locator(selector)
                if comment_elements:
                    count = await comment_elements.count()
                    if count > 0:
                        for i in range(min(count, 10)):  # 限制最多获取10条评论
                            try:
                                comment_element = comment_elements.nth(i)
                                if not comment_element:
                                    continue
                                    
                                # 提取评论者名称
                                username = "未知用户"
                                username_selectors = ["span.user-name", "a.name", "div.username", "span.nickname"]
                                for username_selector in username_selectors:
                                    try:
                                        username_el = comment_element.locator(username_selector).first
                                        if username_el and await username_el.count() > 0:
                                            username_text = await username_el.text_content()
                                            if username_text:
                                                username = username_text.strip()
                                                break
                                    except Exception:
                                        continue
                                
                                # 提取评论内容
                                content = "未知内容"
                                content_selectors = ["div.content", "p.content", "div.text", "span.content"]
                                for content_selector in content_selectors:
                                    try:
                                        content_el = comment_element.locator(content_selector).first
                                        if content_el and await content_el.count() > 0:
                                            content_text = await content_el.text_content()
                                            if content_text:
                                                content = content_text.strip()
                                                break
                                    except Exception:
                                        continue
                                
                                # 提取评论时间
                                time_location = "未知时间"
                                time_selectors = ["span.time", "div.time", "span.date", "div.date"]
                                for time_selector in time_selectors:
                                    try:
                                        time_el = comment_element.locator(time_selector).first
                                        if time_el and await time_el.count() > 0:
                                            time_text = await time_el.text_content()
                                            if time_text:
                                                time_location = time_text.strip()
                                                break
                                    except Exception:
                                        continue
                                
                                # 如果内容有足够长度且找到用户名，添加评论
                                if username != "未知用户" and content != "未知内容" and len(content) > 2:
                                    comments.append({
                                        "用户名": username,
                                        "内容": content,
                                        "时间": time_location
                                    })
                            except Exception as e:
                                print(f"处理单个评论出错: {str(e)}")
                                continue
                        
                        # 如果找到了评论，就不继续尝试其他选择器了
                        if comments:
                            break
            except Exception as e:
                print(f"处理评论选择器出错: {str(e)}")
                continue
        
        # 格式化返回结果
        if comments:
            result = f"共获取到 {len(comments)} 条评论：\n\n"
            for i, comment in enumerate(comments, 1):
                result += f"{i}. {comment['用户名']}（{comment['时间']}）: {comment['内容']}\n\n"
            return result
        else:
            return "未找到任何评论，可能是帖子没有评论或评论区无法访问。"
    
    except Exception as e:
        return f"获取评论时出错: {str(e)}"

@mcp.tool()
async def analyze_note(url: str) -> str:
    """获取并分析笔记内容，返回笔记的详细信息供AI生成评论
    
    Args:
        url: 笔记 URL，必须是有效的小红书链接
        
    Returns:
        JSON格式的字符串，包含笔记的详细分析信息
    """
    if not url or not url.strip():
        raise ValueError("笔记URL不能为空")
    
    if "xiaohongshu.com" not in url:
        raise ValueError("必须是有效的小红书链接")
    
    login_status = await ensure_browser()
    if not login_status:
        raise RuntimeError("请先登录小红书账号")
    
    try:
        # 处理URL
        processed_url = process_url(url)
        
        # 直接调用get_note_content获取笔记内容
        note_content_result = await get_note_content(processed_url)
        
        # 检查是否获取成功
        if note_content_result.startswith("请先登录") or note_content_result.startswith("无法获取笔记内容") or note_content_result.startswith("获取笔记内容时出错"):
            raise RuntimeError(note_content_result)
        
        # 解析获取到的笔记内容
        content_lines = note_content_result.strip().split('\n')
        post_content = {}
        
        # 提取标题、作者、发布时间和内容
        for i, line in enumerate(content_lines):
            if line.startswith("标题:"):
                post_content["标题"] = line.replace("标题:", "").strip()
            elif line.startswith("作者:"):
                post_content["作者"] = line.replace("作者:", "").strip()
            elif line.startswith("发布时间:"):
                post_content["发布时间"] = line.replace("发布时间:", "").strip()
            elif line.startswith("内容:"):
                # 内容可能有多行，获取剩余所有行
                content_text = "\n".join(content_lines[i+1:]).strip()
                post_content["内容"] = content_text
                break
        
        # 简单分词和领域检测
        import re
        words = re.findall(r'\w+', f"{post_content.get('标题', '')} {post_content.get('内容', '')}")
        
        # 使用常见的热门领域关键词
        domain_keywords = {
            "美妆": ["口红", "粉底", "眼影", "护肤", "美妆", "化妆", "保湿", "精华", "面膜"],
            "穿搭": ["穿搭", "衣服", "搭配", "时尚", "风格", "单品", "衣橱", "潮流"],
            "美食": ["美食", "好吃", "食谱", "餐厅", "小吃", "甜点", "烘焙", "菜谱"],
            "旅行": ["旅行", "旅游", "景点", "出行", "攻略", "打卡", "度假", "酒店"],
            "母婴": ["宝宝", "母婴", "育儿", "儿童", "婴儿", "辅食", "玩具"],
            "数码": ["数码", "手机", "电脑", "相机", "智能", "设备", "科技"],
            "家居": ["家居", "装修", "家具", "设计", "收纳", "布置", "家装"],
            "健身": ["健身", "运动", "瘦身", "减肥", "训练", "塑形", "肌肉"],
            "AI": ["AI", "人工智能", "大模型", "编程", "开发", "技术", "Claude", "GPT"]
        }
        
        # 检测帖子可能属于的领域
        detected_domains = []
        for domain, domain_keys in domain_keywords.items():
            for key in domain_keys:
                if key.lower() in post_content.get("标题", "").lower() or key.lower() in post_content.get("内容", "").lower():
                    detected_domains.append(domain)
                    break
        
        # 如果没有检测到明确的领域，默认为生活方式
        if not detected_domains:
            detected_domains = ["生活"]
        
        # 返回分析结果
        result = {
            "url": url,
            "标题": post_content.get("标题", "未知标题"),
            "作者": post_content.get("作者", "未知作者"),
            "内容": post_content.get("内容", "未能获取内容"),
            "领域": detected_domains,
            "关键词": list(set(words))[:20]  # 取前20个不重复的词作为关键词
        }
        
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        raise RuntimeError(f"分析笔记内容时出错: {str(e)}")

@mcp.tool()
async def post_smart_comment(url: str, comment_type: Literal["引流", "点赞", "咨询", "专业"] = "引流") -> str:
    """
    根据帖子内容发布智能评论，增加曝光并引导用户关注或私聊

    Args:
        url: 笔记 URL，必须是有效的小红书链接
        comment_type: 评论类型，可选值:
                     "引流" - 引导用户关注或私聊
                     "点赞" - 简单互动获取好感
                     "咨询" - 以问题形式增加互动
                     "专业" - 展示专业知识建立权威

    Returns:
        JSON格式的字符串，包含笔记信息和评论指导
    """
    if not url or not url.strip():
        raise ValueError("笔记URL不能为空")
    
    if "xiaohongshu.com" not in url:
        raise ValueError("必须是有效的小红书链接")
    
    # 处理URL
    processed_url = process_url(url)
    
    # 获取笔记内容
    note_info = await analyze_note(processed_url)
    
    if "error" in note_info:
        raise RuntimeError(note_info["error"])
    
    # 评论类型指导
    comment_guides = {
        "引流": '生成一条表达认同并引导互动的评论。可以提到自己也在研究相关内容，或表达希望进一步交流的意愿。',
        "点赞": '生成一条简短的赞美评论，表达对内容的喜爱和支持。',
        "咨询": '生成一条提问式评论，针对笔记内容询问更多细节或相关信息。',
        "专业": '生成一条展示专业知识的评论，针对笔记内容提供专业见解或补充信息。'
    }
    
    # 返回结构化的JSON结果
    result = {
        "note_info": note_info,
        "comment_type": comment_type,
        "comment_guide": comment_guides.get(comment_type, ""),
        "url": url,
        "message": "请根据笔记内容和评论类型指南，生成一条自然、相关的评论。"
    }
    
    return json.dumps(result, ensure_ascii=False, indent=2)

@mcp.tool()
async def post_comment(url: str, comment: str) -> str:
    """发布评论到指定笔记
    
    Args:
        url: 笔记 URL，必须是有效的小红书链接
        comment: 要发布的评论内容，不能为空
    
    Returns:
        评论发布结果的描述
    """
    if not url or not url.strip():
        raise ValueError("笔记URL不能为空")
    
    if not comment or not comment.strip():
        raise ValueError("评论内容不能为空")
    
    if "xiaohongshu.com" not in url:
        raise ValueError("必须是有效的小红书链接")
    
    if len(comment.strip()) > 500:
        raise ValueError("评论内容过长，请控制在500字符以内")
    
    login_status = await ensure_browser()
    if not login_status:
        raise RuntimeError("请先登录小红书账号，才能发布评论")
    
    if not main_page:
        raise RuntimeError("浏览器初始化失败，请重试")
    
    try:
        # 处理URL
        processed_url = process_url(url)
        print(f"处理后的评论URL: {processed_url}")
        
        # 访问帖子链接
        await main_page.goto(processed_url, timeout=60000)
        await asyncio.sleep(5)  # 等待页面加载
        
        # 定位评论输入框
        comment_input = None
        input_selectors = [
            'div[contenteditable="true"]',
            'textarea[placeholder*="说点什么"]',
            'input[placeholder*="说点什么"]'
        ]
        
        # 尝试常规选择器
        for selector in input_selectors:
            try:
                element = await main_page.query_selector(selector)
                if element and await element.is_visible():
                    await element.scroll_into_view_if_needed()
                    await asyncio.sleep(1)
                    comment_input = element
                    break
            except Exception as e:
                print(f"定位评论输入框时出错: {str(e)}")
                continue
        
        if not comment_input:
            raise RuntimeError("未能找到评论输入框，无法发布评论")
        
        # 输入评论内容
        await comment_input.click()
        await asyncio.sleep(1)
        
        await main_page.keyboard.type(comment.strip())
        await asyncio.sleep(1)
        
        # 发送评论
        send_success = False
        
        # 尝试点击发送按钮
        try:
            send_button = await main_page.query_selector('button:has-text("发送")')
            if send_button and await send_button.is_visible():
                await send_button.click()
                await asyncio.sleep(2)
                send_success = True
        except Exception as e:
            print(f"点击发送按钮出错: {str(e)}")
        
        # 如果失败，尝试使用Enter键
        if not send_success:
            try:
                await main_page.keyboard.press("Enter")
                await asyncio.sleep(2)
                send_success = True
            except Exception as e:
                print(f"使用Enter键发送出错: {str(e)}")
        
        if send_success:
            return f"已成功发布评论：{comment.strip()}"
        else:
            raise RuntimeError("发布评论失败，请检查评论内容或网络连接")
    
    except Exception as e:
        if "ValueError" in str(type(e)) or "RuntimeError" in str(type(e)):
            raise
        else:
            raise RuntimeError(f"发布评论时出错: {str(e)}")

# 添加健康检查工具
@mcp.tool()
async def health_check() -> str:
    """健康检查工具，验证服务是否正常运行
    
    Returns:
        JSON格式的健康状态信息
    """
    health_status = {
        "status": "healthy", 
        "service": "xiaohongshu_mcp",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }
    return json.dumps(health_status, ensure_ascii=False, indent=2)

# 添加状态检查工具
@mcp.tool()
async def status_check() -> str:
    """状态检查工具，获取服务详细状态信息
    
    Returns:
        JSON格式的状态信息
    """
    global browser_context, main_page, is_logged_in
    
    status = {
        "browser_initialized": browser_context is not None,
        "page_available": main_page is not None,
        "logged_in": is_logged_in,
        "timestamp": datetime.now().isoformat(),
        "browser_data_dir": BROWSER_DATA_DIR
    }
    return json.dumps(status, ensure_ascii=False, indent=2)

# 添加浏览器状态检查工具
@mcp.tool()
async def browser_status() -> str:
    """浏览器状态检查工具，获取浏览器详细状态
    
    Returns:
        JSON格式的浏览器状态信息
    """
    global browser_context, main_page, is_logged_in
    
    status = {
        "browser_context_active": browser_context is not None,
        "main_page_active": main_page is not None,
        "is_logged_in": is_logged_in,
        "timestamp": datetime.now().isoformat()
    }
    
    if browser_context:
        try:
            pages = browser_context.pages
            status["page_count"] = len(pages)
            status["context_closed"] = browser_context.closed if hasattr(browser_context, 'closed') else False
        except Exception as e:
            status["browser_error"] = str(e)
    
    return json.dumps(status, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # 使用 Streamable HTTP 模式运行 MCP 服务器（推荐方式）
    print("启动小红书MCP服务器 (Streamable HTTP模式)...")
    print("健康检查工具: health_check")
    print("状态检查工具: status_check") 
    print("浏览器状态工具: browser_status")
    
    # 从环境变量获取配置
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8080"))
    log_level = os.getenv("FASTMCP_LOG_LEVEL", "INFO")
    
    print(f"启动服务在 {host}:{port}/mcp")
    print(f"日志级别: {log_level}")
    
    # 使用最新的 streamable-http 传输方式
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path="/mcp",
        log_level=log_level.lower()
    )
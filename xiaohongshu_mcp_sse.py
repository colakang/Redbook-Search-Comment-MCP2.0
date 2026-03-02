"""
小红书 MCP Server — Streamable HTTP 模式
Claude Desktop 可直接通过 URL 连接，无需 proxy。

claude_desktop_config.json 配置：
{
  "mcpServers": {
    "xiaohongshu": {
      "url": "http://<docker-host-ip>:8080/mcp/"
    }
  }
}
"""

import asyncio
import base64
import json
import os
import re
from typing import Any

from mcp.types import ImageContent
from playwright.async_api import async_playwright
from fastmcp import FastMCP

mcp = FastMCP("xiaohongshu")

BROWSER_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_data")
os.makedirs(BROWSER_DATA_DIR, exist_ok=True)

browser_context = None
main_page = None
is_logged_in = False


# ─── 内部工具 ────────────────────────────────────────────────────────────────

def _ok(data: dict) -> dict:
    return {"ok": True, **data}

def _err(msg: str) -> dict:
    return {"ok": False, "error": msg}

def _process_url(url: str) -> str:
    url = url.strip().lstrip("@")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url
    if "xiaohongshu.com" in url and "www.xiaohongshu.com" not in url:
        url = url.replace("xiaohongshu.com", "www.xiaohongshu.com")
    return url

async def _ensure_browser() -> bool:
    global browser_context, main_page, is_logged_in
    if browser_context is None:
        pw = await async_playwright().start()
        browser_context = await pw.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            timeout=60000,
        )
        main_page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()
        main_page.set_default_timeout(60000)

    if not is_logged_in and main_page:
        await main_page.goto("https://www.xiaohongshu.com", timeout=60000)
        await asyncio.sleep(3)
        login_els = await main_page.query_selector_all('text="登录"')
        if login_els:
            return False
        is_logged_in = True

    return True

async def _check_error_page() -> str | None:
    """返回错误文本，或 None 表示页面正常"""
    if not main_page:
        return "浏览器未就绪"
    result = await main_page.evaluate("""
        () => {
            const errors = ["当前笔记暂时无法浏览","内容不存在","页面不存在","内容已被删除"];
            for (const t of errors) {
                if (document.body.innerText.includes(t)) return t;
            }
            return null;
        }
    """)
    return result


# ─── Tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
async def login() -> dict:
    """登录小红书账号（扫码登录）"""
    global is_logged_in
    await _ensure_browser()

    if is_logged_in:
        return _ok({"message": "已登录"})
    if not main_page:
        return _err("浏览器初始化失败")

    await main_page.goto("https://www.xiaohongshu.com", timeout=60000)
    await asyncio.sleep(3)

    els = await main_page.query_selector_all('text="登录"')
    if not els:
        is_logged_in = True
        return _ok({"message": "已登录"})

    await els[0].click()
    for _ in range(36):  # 最多等 3 分钟
        await asyncio.sleep(5)
        still = await main_page.query_selector_all('text="登录"')
        if not still:
            is_logged_in = True
            return _ok({"message": "登录成功"})

    return _err("登录超时，请重试")


@mcp.tool()
async def search_notes(keywords: str, limit: int = 5) -> dict:
    """
    搜索小红书笔记。

    Args:
        keywords: 搜索关键词
        limit: 返回结果数量，1-20，默认 5
    """
    if not keywords.strip():
        return _err("关键词不能为空")
    limit = max(1, min(limit, 20))

    if not await _ensure_browser():
        return _err("请先登录")
    if not main_page:
        return _err("浏览器未就绪")

    url = f"https://www.xiaohongshu.com/search_result?keyword={keywords}"
    try:
        await main_page.goto(url, timeout=60000)
        await asyncio.sleep(5)

        cards = await main_page.query_selector_all("section.note-item")
        if not cards:
            cards = await main_page.query_selector_all("div[data-v-a264b01a]")

        seen, results = set(), []
        for card in cards:
            if len(results) >= limit:
                break
            try:
                link_el = await card.query_selector('a[href*="/search_result/"]')
                if not link_el:
                    continue
                href = await link_el.get_attribute("href")
                if not href or "/search_result/" not in href:
                    continue
                full_url = f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href
                if full_url in seen:
                    continue
                seen.add(full_url)

                title_el = await card.query_selector("div.footer a.title span") or await card.query_selector("a.title span")
                title = (await title_el.text_content()).strip() if title_el else "未知标题"
                results.append({"title": title, "url": full_url})
            except Exception:
                continue

        if results:
            return _ok({"count": len(results), "notes": results})
        return _err(f"未找到与"{keywords}"相关的笔记")

    except Exception as e:
        return _err(f"搜索出错: {e}")


@mcp.tool()
async def get_note_content(url: str) -> dict:
    """
    获取笔记的标题、作者、正文和图片链接。

    Args:
        url: 小红书笔记链接
    """
    if not url or "xiaohongshu.com" not in url:
        return _err("无效的小红书链接")
    if not await _ensure_browser():
        return _err("请先登录")
    if not main_page:
        return _err("浏览器未就绪")

    try:
        processed = _process_url(url)
        await main_page.goto(processed, timeout=60000)
        await asyncio.sleep(8)

        err = await _check_error_page()
        if err:
            return _err(err)

        # 标题
        title = "未知标题"
        for sel in ["#detail-title", "div.title", "h1"]:
            el = await main_page.query_selector(sel)
            if el:
                t = await el.text_content()
                if t and t.strip():
                    title = t.strip()
                    break

        # 作者
        author = "未知作者"
        for sel in ["span.username", "a.name"]:
            el = await main_page.query_selector(sel)
            if el:
                t = await el.text_content()
                if t and t.strip():
                    author = t.strip()
                    break

        # 正文
        content = ""
        for sel in ["#detail-desc .note-text", "#detail-desc", "div.desc"]:
            el = await main_page.query_selector(sel)
            if el:
                t = await el.text_content()
                if t and len(t.strip()) > 10:
                    content = t.strip()
                    break

        # 图片 URL（小红书图床）
        images = await main_page.evaluate("""
            () => {
                const imgs = Array.from(document.querySelectorAll(
                    '.note-content img, .media-container img, swiper-slide img, .carousel img'
                ));
                return [...new Set(imgs.map(i => i.src).filter(s => s && s.startsWith('http')))];
            }
        """)

        return _ok({
            "title": title,
            "author": author,
            "url": url,
            "content": content or "未能获取正文",
            "images": images or [],
        })

    except Exception as e:
        return _err(f"获取笔记出错: {e}")


@mcp.tool()
async def get_note_comments(url: str) -> dict:
    """
    获取笔记的评论列表（用户名、内容、时间）。

    Args:
        url: 小红书笔记链接
    """
    if not url or "xiaohongshu.com" not in url:
        return _err("无效的小红书链接")
    if not await _ensure_browser():
        return _err("请先登录")
    if not main_page:
        return _err("浏览器未就绪")

    try:
        processed = _process_url(url)
        await main_page.goto(processed, timeout=60000)
        await asyncio.sleep(5)

        err = await _check_error_page()
        if err:
            return _err(err)

        # 滚动加载评论
        for _ in range(8):
            await main_page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(1)
            for btn_text in ["查看更多评论", "展开更多评论", "加载更多"]:
                try:
                    btn = main_page.locator(f"text={btn_text}").first
                    if await btn.count() > 0 and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(2)
                except Exception:
                    pass

        comments = []

        # 方法一：CSS 选择器
        for sel in ["div.comment-item", "div.commentItem", "div.comment-content", "div.feed-comment"]:
            elements = main_page.locator(sel)
            count = await elements.count()
            if count == 0:
                continue

            for i in range(count):
                try:
                    el = elements.nth(i)

                    user = "未知用户"
                    for usel in ["span.user-name", "a.name", "div.username", "span.nickname"]:
                        uel = el.locator(usel).first
                        if await uel.count() > 0:
                            t = await uel.text_content()
                            if t and t.strip():
                                user = t.strip()
                                break

                    text = ""
                    for csel in ["div.content", "p.content", "div.text", "div.comment-text"]:
                        cel = el.locator(csel).first
                        if await cel.count() > 0:
                            t = await cel.text_content()
                            if t and t.strip():
                                text = t.strip()
                                break

                    if not text:
                        full = await el.text_content()
                        if full:
                            text = full.replace(user, "").strip() if user != "未知用户" else full.strip()

                    time_val = ""
                    for tsel in ["span.time", "div.time", "span.date", "time"]:
                        tel = el.locator(tsel).first
                        if await tel.count() > 0:
                            t = await tel.text_content()
                            if t and t.strip():
                                time_val = t.strip()
                                break

                    if user != "未知用户" and text and len(text) > 2:
                        comments.append({"user": user, "text": text, "time": time_val})
                except Exception:
                    continue

            if comments:
                break

        # 方法二：用户链接兜底
        if not comments:
            user_links = main_page.locator('a[href*="/user/profile/"]')
            for i in range(await user_links.count()):
                try:
                    uel = user_links.nth(i)
                    user = (await uel.text_content() or "").strip()
                    sibling_text = await main_page.evaluate("""
                        (el) => {
                            let sib = el.nextElementSibling;
                            while (sib) {
                                const t = sib.textContent.trim();
                                if (t) return t;
                                sib = sib.nextElementSibling;
                            }
                            const p = el.parentElement;
                            if (!p) return null;
                            return p.textContent.replace(el.textContent, '').trim() || null;
                        }
                    """, uel)
                    if user and sibling_text:
                        comments.append({"user": user, "text": sibling_text, "time": ""})
                except Exception:
                    continue

        if comments:
            return _ok({"count": len(comments), "comments": comments})
        return _ok({"count": 0, "comments": [], "note": "该笔记暂无评论或评论区无法访问"})

    except Exception as e:
        return _err(f"获取评论出错: {e}")


@mcp.tool()
async def analyze_note(url: str) -> dict:
    """
    分析笔记内容，提取领域标签和关键词，供生成评论使用。

    Args:
        url: 小红书笔记链接
    """
    if not url or "xiaohongshu.com" not in url:
        return _err("无效的小红书链接")

    result = await get_note_content(url)
    if not result.get("ok"):
        return result

    title = result["title"]
    content = result["content"]
    combined = f"{title} {content}"

    domain_map = {
        "美妆": ["口红", "粉底", "眼影", "护肤", "美妆", "化妆", "保湿", "精华", "面膜"],
        "穿搭": ["穿搭", "衣服", "搭配", "时尚", "风格", "单品", "潮流"],
        "美食": ["美食", "好吃", "食谱", "餐厅", "小吃", "甜点", "烘焙"],
        "旅行": ["旅行", "旅游", "景点", "攻略", "打卡", "度假", "酒店"],
        "母婴": ["宝宝", "母婴", "育儿", "儿童", "婴儿", "辅食"],
        "数码": ["数码", "手机", "电脑", "相机", "智能", "科技"],
        "家居": ["家居", "装修", "家具", "设计", "收纳", "家装"],
        "健身": ["健身", "运动", "瘦身", "减肥", "训练", "塑形"],
        "AI":   ["AI", "人工智能", "大模型", "编程", "Claude", "GPT", "开发"],
    }

    domains = [d for d, keys in domain_map.items() if any(k.lower() in combined.lower() for k in keys)]
    keywords = list(set(re.findall(r"[\w\u4e00-\u9fff]+", combined)))[:20]

    return _ok({
        "url": url,
        "title": title,
        "author": result["author"],
        "content": content,
        "images": result.get("images", []),
        "domains": domains or ["生活"],
        "keywords": keywords,
    })


@mcp.tool()
async def post_smart_comment(url: str, comment_type: str = "引流") -> dict:
    """
    分析笔记并生成评论指导，Claude 根据返回内容生成评论后调用 post_comment 发布。

    Args:
        url: 小红书笔记链接
        comment_type: 评论类型 — 引流 / 点赞 / 咨询 / 专业
    """
    guides = {
        "引流": "认同内容，引导私信互动，结尾加"欢迎私信"或"有问题找我聊"，≤30字",
        "点赞": "简短赞美，提及作者或领域，≤20字",
        "咨询": "以"请问博主"开头，针对内容提具体问题，≤30字",
        "专业": "以"从专业角度"开头，补充专业见解，≤30字",
    }
    if comment_type not in guides:
        return _err(f"comment_type 需为：{', '.join(guides.keys())}")

    note = await analyze_note(url)
    if not note.get("ok"):
        return note

    return _ok({
        "note": note,
        "type": comment_type,
        "guide": guides[comment_type],
        "url": url,
        "instruction": "根据 note 内容和 guide 直接生成评论，然后调用 post_comment 发布，无需确认",
    })


@mcp.tool()
async def post_comment(url: str, comment: str) -> dict:
    """
    发布评论到指定笔记。

    Args:
        url: 小红书笔记链接
        comment: 评论内容（≤500字）
    """
    if not url or "xiaohongshu.com" not in url:
        return _err("无效的小红书链接")
    comment = comment.strip()
    if not comment:
        return _err("评论内容不能为空")
    if len(comment) > 500:
        return _err("评论过长，请控制在500字以内")

    if not await _ensure_browser():
        return _err("请先登录")
    if not main_page:
        return _err("浏览器未就绪")

    try:
        processed = _process_url(url)
        await main_page.goto(processed, timeout=60000)
        await asyncio.sleep(5)

        err = await _check_error_page()
        if err:
            return _err(err)

        # 找评论输入框
        input_el = None
        for sel in ['div[contenteditable="true"]', 'textarea[placeholder*="说点什么"]']:
            el = await main_page.query_selector(sel)
            if el and await el.is_visible():
                await el.scroll_into_view_if_needed()
                input_el = el
                break

        if not input_el:
            # JS 兜底：滚动到底部后再找
            await main_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            for sel in ['div[contenteditable="true"]']:
                el = await main_page.query_selector(sel)
                if el and await el.is_visible():
                    input_el = el
                    break

        if not input_el:
            return _err("未找到评论输入框")

        await input_el.click()
        await asyncio.sleep(0.5)
        await main_page.keyboard.type(comment)
        await asyncio.sleep(1)

        # 发送
        sent = False
        btn = await main_page.query_selector('button:has-text("发送")')
        if btn and await btn.is_visible():
            await btn.click()
            await asyncio.sleep(2)
            sent = True

        if not sent:
            await main_page.keyboard.press("Enter")
            await asyncio.sleep(2)
            sent = True

        if sent:
            return _ok({"comment": comment, "message": "评论已发布"})
        return _err("发布失败，请检查网络或登录状态")

    except Exception as e:
        return _err(f"发布评论出错: {e}")


@mcp.tool()
async def take_screenshot() -> list:
    """
    截取当前浏览器画面，返回图片给 LLM 查看（用于调试页面状态）。
    """
    if not main_page:
        return [{"type": "text", "text": json.dumps(_err("浏览器未启动"))}]

    try:
        buf = await main_page.screenshot(type="jpeg", quality=70, full_page=False)
        b64 = base64.b64encode(buf).decode()
        return [ImageContent(type="image", data=b64, mimeType="image/jpeg")]
    except Exception as e:
        return [{"type": "text", "text": json.dumps(_err(f"截图失败: {e}"))}]


# ─── 入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8080"))
    print(f"启动小红书 MCP Server → http://{host}:{port}/mcp/")
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path="/mcp/",
    )

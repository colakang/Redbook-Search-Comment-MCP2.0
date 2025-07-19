#!/usr/bin/env python3
"""
小红书MCP服务器客户端连接示例
使用 streamable-http 传输方式连接到服务器
"""

import asyncio
import json
from typing import Dict, Any
import httpx


class XiaohongshuMCPClient:
    """小红书MCP客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.mcp_endpoint = f"{base_url}/mcp"
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """调用MCP工具"""
        if arguments is None:
            arguments = {}
            
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = await self.client.post(
                self.mcp_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"HTTP错误: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"error": f"请求失败: {str(e)}"}
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        return await self.call_tool("health_check")
    
    async def status_check(self) -> Dict[str, Any]:
        """状态检查"""
        return await self.call_tool("status_check")
    
    async def browser_status(self) -> Dict[str, Any]:
        """浏览器状态检查"""
        return await self.call_tool("browser_status")
    
    async def login(self) -> Dict[str, Any]:
        """登录小红书"""
        return await self.call_tool("login")
    
    async def search_notes(self, keywords: str, limit: int = 5) -> Dict[str, Any]:
        """搜索笔记"""
        return await self.call_tool("search_notes", {
            "keywords": keywords,
            "limit": limit
        })
    
    async def get_note_content(self, url: str) -> Dict[str, Any]:
        """获取笔记内容"""
        return await self.call_tool("get_note_content", {"url": url})
    
    async def get_note_comments(self, url: str) -> Dict[str, Any]:
        """获取笔记评论"""
        return await self.call_tool("get_note_comments", {"url": url})
    
    async def analyze_note(self, url: str) -> Dict[str, Any]:
        """分析笔记"""
        return await self.call_tool("analyze_note", {"url": url})
    
    async def post_smart_comment(self, url: str, comment_type: str = "引流") -> Dict[str, Any]:
        """智能评论分析"""
        return await self.call_tool("post_smart_comment", {
            "url": url,
            "comment_type": comment_type
        })
    
    async def post_comment(self, url: str, comment: str) -> Dict[str, Any]:
        """发布评论"""
        return await self.call_tool("post_comment", {
            "url": url,
            "comment": comment
        })
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


async def main():
    """示例用法"""
    client = XiaohongshuMCPClient("http://localhost:8080")
    
    try:
        print("=== 小红书MCP客户端测试 ===\n")
        
        # 1. 健康检查
        print("1. 健康检查...")
        result = await client.health_check()
        print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
        
        # 2. 状态检查
        print("2. 状态检查...")
        result = await client.status_check()
        print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
        
        # 3. 浏览器状态
        print("3. 浏览器状态...")
        result = await client.browser_status()
        print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
        
        # 4. 登录检查
        print("4. 检查登录状态...")
        result = await client.login()
        print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
        
        # 5. 搜索示例（如果已登录）
        if not ("error" in result or "请先登录" in str(result)):
            print("5. 搜索笔记...")
            result = await client.search_notes("美食", limit=3)
            print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}\n")
        
        print("=== 测试完成 ===")
        
    except Exception as e:
        print(f"客户端测试失败: {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
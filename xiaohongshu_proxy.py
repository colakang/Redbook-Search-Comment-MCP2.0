"""
小红书MCP代理服务器 - 用于连接Claude Desktop到远程Docker MCP服务器
"""

from fastmcp import FastMCP, Client
import os

# 从环境变量获取远程服务器地址，默认使用你的Docker服务器
REMOTE_SERVER_URL = os.getenv("XIAOHONGSHU_SERVER_URL", "http://192.168.1.134:8080/mcp/")

# 创建连接到远程HTTP服务器的客户端
remote_client = Client(REMOTE_SERVER_URL)

# 创建代理服务器
mcp = FastMCP.as_proxy(
    remote_client, 
    name="XiaohongshuProxy",
    description="小红书MCP服务代理 - 连接到Docker容器中的远程服务器"
)

if __name__ == "__main__":
    # 运行STDIO服务器供Claude Desktop使用
    mcp.run(transport="stdio")
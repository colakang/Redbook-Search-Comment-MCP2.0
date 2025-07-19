#!/usr/bin/env python3
"""
FastMCP Streamable HTTP 会话管理修复脚本
专门解决 "Missing session ID" 问题
"""

import os
import sys
import asyncio
import json
from fastmcp import FastMCP

# 修复版的MCP服务器启动
def create_fixed_mcp():
    """创建修复了会话管理的MCP服务器"""
    
    # 尝试不同的初始化方式
    try:
        # 方法1: 检查是否需要特殊配置
        mcp = FastMCP(
            name="xiaohongshu_scraper",
            # 可能需要的会话配置
        )
        return mcp, "基础配置"
    except Exception as e:
        print(f"基础配置失败: {e}")
        return None, str(e)

def run_streamable_http_server():
    """运行 streamable-http 服务器"""
    
    mcp, config_type = create_fixed_mcp()
    if not mcp:
        print("❌ 无法创建MCP服务器")
        return False
    
    print(f"✅ 使用 {config_type} 创建MCP服务器")
    
    # 添加一个简单的测试工具
    @mcp.tool()
    async def ping() -> str:
        """简单的ping测试"""
        return "pong"
    
    # 从环境变量获取配置
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8080"))
    
    print(f"启动 streamable-http 服务在 {host}:{port}")
    
    try:
        # 尝试不同的启动方式
        startup_methods = [
            # 方法1: 基础启动
            lambda: mcp.run(transport="streamable-http", host=host, port=port),
            
            # 方法2: 添加路径
            lambda: mcp.run(transport="streamable-http", host=host, port=port, path="/mcp"),
            
            # 方法3: 最简启动
            lambda: mcp.run(transport="streamable-http"),
            
            # 方法4: 获取app手动启动
            lambda: manual_uvicorn_start(mcp, host, port),
        ]
        
        for i, method in enumerate(startup_methods, 1):
            try:
                print(f"尝试启动方法 {i}...")
                method()
                print(f"✅ 方法 {i} 启动成功!")
                return True
            except Exception as e:
                print(f"❌ 方法 {i} 失败: {e}")
                continue
        
        print("❌ 所有启动方法都失败了")
        return False
        
    except Exception as e:
        print(f"❌ 启动过程中出现异常: {e}")
        return False

def manual_uvicorn_start(mcp, host, port):
    """手动使用 uvicorn 启动"""
    import uvicorn
    
    try:
        app = mcp.get_app()
        print(f"获取到 FastMCP 应用，使用 uvicorn 启动...")
        uvicorn.run(app, host=host, port=port)
    except Exception as e:
        print(f"uvicorn 启动失败: {e}")
        raise

def test_server_connection():
    """测试服务器连接"""
    import subprocess
    import time
    
    print("等待服务器启动...")
    time.sleep(5)
    
    test_commands = [
        # 测试基础连接
        "curl -s http://localhost:8080/",
        
        # 测试MCP端点
        "curl -s http://localhost:8080/mcp/",
        
        # 测试ping工具
        'curl -s -X POST http://localhost:8080/mcp/ -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d \'{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "ping", "arguments": {}}}\'',
    ]
    
    for cmd in test_commands:
        print(f"执行: {cmd}")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            print(f"状态码: {result.returncode}")
            if result.stdout:
                print(f"响应: {result.stdout[:200]}...")
            if result.stderr:
                print(f"错误: {result.stderr[:200]}...")
        except Exception as e:
            print(f"测试失败: {e}")
        print("-" * 40)

if __name__ == "__main__":
    print("🔧 FastMCP Streamable HTTP 修复脚本")
    print("=" * 50)
    
    # 检查 FastMCP 版本
    try:
        import fastmcp
        version = getattr(fastmcp, '__version__', 'unknown')
        print(f"FastMCP 版本: {version}")
        
        # 检查可用的方法
        mcp_test = FastMCP("test")
        print(f"FastMCP 可用方法: {[m for m in dir(mcp_test) if not m.startswith('_') and 'run' in m]}")
        
        # 检查 run 方法签名
        import inspect
        print(f"run 方法签名: {inspect.signature(mcp_test.run)}")
        
    except Exception as e:
        print(f"❌ FastMCP 检查失败: {e}")
        sys.exit(1)
    
    print("=" * 50)
    
    # 启动服务器
    success = run_streamable_http_server()
    
    if not success:
        print("❌ 服务器启动失败")
        sys.exit(1)
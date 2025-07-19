#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中... (Streamable HTTP模式)"
echo "==================================="

# 设置环境变量
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=/dev/null

# 清理旧进程和锁文件
cleanup_processes() {
    echo "清理进程和锁文件..."
    pkill -f Xvfb 2>/dev/null || true
    pkill -f fluxbox 2>/dev/null || true
    pkill -f x11vnc 2>/dev/null || true
    pkill -f chrome 2>/dev/null || true
    pkill -f chromium 2>/dev/null || true
    pkill -f python 2>/dev/null || true
    
    # 清理X11锁文件
    rm -f /tmp/.X*-lock 2>/dev/null || true
    
    # 清理Chrome锁文件
    rm -f /app/browser_data/SingletonLock 2>/dev/null || true
    rm -f /app/browser_data/SingletonSocket 2>/dev/null || true
    rm -f /app/browser_data/SingletonCookie* 2>/dev/null || true
    
    sleep 2
}

cleanup_processes

# 创建必要目录
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

mkdir -p /app/browser_data
chmod 755 /app/browser_data

mkdir -p /app/logs
chmod 755 /app/logs

# 启动Xvfb
echo "启动虚拟显示服务器..."
Xvfb :0 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset -nolisten tcp >/dev/null 2>&1 &
XVFB_PID=$!

# 等待Xvfb启动
sleep 3
if ! xdpyinfo -display :0 >/dev/null 2>&1; then
    echo "错误: Xvfb启动失败"
    exit 1
fi
echo "✓ Xvfb启动成功 (PID: $XVFB_PID)"

# 启动窗口管理器
echo "启动窗口管理器..."
fluxbox >/dev/null 2>&1 &
FLUXBOX_PID=$!
sleep 2
echo "✓ Fluxbox启动完成 (PID: $FLUXBOX_PID)"

# 启动VNC服务器
if [ "$VNC_MODE" = "true" ]; then
    echo "启动VNC服务器..."
    
    x11vnc \
        -display :0 \
        -forever \
        -nopw \
        -rfbport 5900 \
        -shared \
        -quiet \
        -bg \
        -noxrecord \
        -noxfixes \
        -noxdamage
    
    sleep 2
    
    if pgrep -f x11vnc >/dev/null; then
        VNC_PID=$(pgrep -f x11vnc)
        echo "✓ VNC服务器启动成功 (PID: $VNC_PID)"
        echo "VNC地址: <服务器IP>:5901 (无密码)"
    else
        echo "✗ VNC服务器启动失败"
        exit 1
    fi
    
    # 创建Chrome启动脚本（供VNC中手动使用）
    echo "创建Chrome启动脚本..."
    cat > /usr/local/bin/start-chrome << 'EOF'
#!/bin/bash
export DISPLAY=:0

# 清理Chrome锁文件
rm -f /app/browser_data/SingletonLock 2>/dev/null || true
rm -f /app/browser_data/SingletonSocket 2>/dev/null || true
rm -f /app/browser_data/SingletonCookie* 2>/dev/null || true

# 启动Chrome
google-chrome-stable \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-web-security \
    --no-first-run \
    --no-default-browser-check \
    --user-data-dir=/app/browser_data \
    --window-size=1920,1080 \
    --start-maximized \
    "https://www.xiaohongshu.com" \
    2>/dev/null &

echo "Chrome启动中..."
EOF
    chmod +x /usr/local/bin/start-chrome
    
    # 创建桌面快捷方式
    mkdir -p /root/Desktop
    cat > /root/Desktop/Chrome.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Chrome浏览器
Comment=启动Chrome访问小红书
Exec=/usr/local/bin/start-chrome
Icon=google-chrome
Terminal=false
Categories=Network;WebBrowser;
EOF
    chmod +x /root/Desktop/Chrome.desktop
    
    echo "✓ Chrome启动脚本已创建"
    echo "  在VNC桌面上双击Chrome图标启动浏览器"
    echo "  或在终端中运行: start-chrome"
    
    # 创建MCP服务状态检查脚本
    cat > /usr/local/bin/check-mcp << 'EOF'
#!/bin/bash
echo "检查MCP服务状态..."

# 检查MCP服务是否运行
if pgrep -f "python.*xiaohongshu_mcp_sse.py" >/dev/null; then
    echo "✓ MCP服务进程运行中"
    
    # 测试MCP健康检查工具
    echo "测试健康检查工具..."
    curl -X POST http://localhost:8080/mcp \
      -H 'Content-Type: application/json' \
      -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
          "name": "health_check",
          "arguments": {}
        }
      }' 2>/dev/null || echo "健康检查工具调用失败"
else
    echo "✗ MCP服务进程未运行"
fi
EOF
    chmod +x /usr/local/bin/check-mcp
fi

echo "==================================="
echo "环境启动完成!"
echo "MCP服务(HTTP): http://<服务器IP>:8080/mcp"
echo "健康检查工具: health_check"
echo "状态检查工具: status_check"
echo "浏览器状态工具: browser_status"
if [ "$VNC_MODE" = "true" ]; then
echo "VNC地址: <服务器IP>:5901 (无密码)"
fi
echo ""
echo "使用说明:"
echo "1. 通过VNC连接到桌面 (如果启用)"
echo "2. 双击桌面上的Chrome图标启动浏览器"
echo "3. 在浏览器中登录小红书账号"
echo "4. 使用HTTP API进行搜索和评论操作"
echo "   - 端点: http://服务器IP:8080/mcp"
echo "   - 健康检查: 调用health_check工具"
echo "==================================="

# 清理函数
cleanup() {
    echo "正在关闭服务..."
    
    # 关闭所有Chrome进程
    pkill -f chrome 2>/dev/null || true
    pkill -f chromium 2>/dev/null || true
    
    # 关闭Python应用
    pkill -f python 2>/dev/null || true
    
    # 关闭VNC
    if [ ! -z "$VNC_PID" ] && kill -0 "$VNC_PID" 2>/dev/null; then
        kill $VNC_PID 2>/dev/null || true
    fi
    pkill -f x11vnc 2>/dev/null || true
    
    # 关闭窗口管理器
    if [ ! -z "$FLUXBOX_PID" ] && kill -0 "$FLUXBOX_PID" 2>/dev/null; then
        kill $FLUXBOX_PID 2>/dev/null || true
    fi
    pkill -f fluxbox 2>/dev/null || true
    
    # 关闭Xvfb
    if [ ! -z "$XVFB_PID" ] && kill -0 "$XVFB_PID" 2>/dev/null; then
        kill $XVFB_PID 2>/dev/null || true
    fi
    pkill -f Xvfb 2>/dev/null || true
    
    echo "服务清理完成"
    exit 0
}

# 信号处理
trap cleanup SIGTERM SIGINT

# 等待一会儿让所有服务稳定启动
sleep 3

# 启动MCP服务器
echo "启动MCP Streamable HTTP服务器..."
cd /app

# 检查Python文件是否存在
if [ ! -f "xiaohongshu_mcp_sse.py" ]; then
    echo "错误: xiaohongshu_mcp_sse.py 文件不存在"
    echo "请确保文件已正确复制到容器中"
    exit 1
fi

# 启动Python应用，并将日志输出到文件
python xiaohongshu_mcp_sse.py 2>&1 | tee /app/logs/mcp_server.log &
MCP_PID=$!

# 等待服务启动
echo "等待MCP服务启动..."
sleep 10

# 检查MCP服务是否正常启动 - 通过检查进程而不是HTTP端点
for i in {1..30}; do
    if pgrep -f "python.*xiaohongshu_mcp_sse.py" >/dev/null; then
        echo "✓ MCP Streamable HTTP服务启动成功 (PID: $MCP_PID)"
        echo "✓ 进程检查通过"
        
        # 尝试调用健康检查工具
        echo "测试健康检查工具..."
        sleep 5  # 等待服务完全就绪
        if curl -X POST http://localhost:8080/mcp \
          -H 'Content-Type: application/json' \
          -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "health_check", "arguments": {}}}' \
          >/dev/null 2>&1; then
            echo "✓ 健康检查工具响应正常"
        else
            echo "⚠ 健康检查工具暂时无响应，但服务正在启动"
        fi
        break
    elif [ $i -eq 30 ]; then
        echo "✗ MCP服务启动失败或进程检查超时"
        echo "查看日志:"
        tail -20 /app/logs/mcp_server.log
        exit 1
    else
        echo "等待MCP服务启动... ($i/30)"
        sleep 2
    fi
done

echo "==================================="
echo "🚀 小红书MCP服务器已启动 (Streamable HTTP模式)"
echo "==================================="
echo "服务地址: http://0.0.0.0:8080/mcp"
echo "健康检查: 调用health_check工具"
echo "状态检查: 调用status_check工具"
echo "浏览器状态: 调用browser_status工具"
if [ "$VNC_MODE" = "true" ]; then
echo "VNC访问: <服务器IP>:5901"
fi
echo ""
echo "测试命令:"
echo "  健康检查: curl -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -d '{\"jsonrpc\": \"2.0\", \"id\": 1, \"method\": \"tools/call\", \"params\": {\"name\": \"health_check\", \"arguments\": {}}}'"
echo "  状态检查: curl -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -d '{\"jsonrpc\": \"2.0\", \"id\": 2, \"method\": \"tools/call\", \"params\": {\"name\": \"status_check\", \"arguments\": {}}}'"
echo "==================================="

# 保持容器运行，同时监控MCP进程
while true; do
    if ! kill -0 $MCP_PID 2>/dev/null; then
        echo "MCP服务进程已停止，重启中..."
        python xiaohongshu_mcp_sse.py 2>&1 | tee -a /app/logs/mcp_server.log &
        MCP_PID=$!
        sleep 5
    fi
    
    # 定期输出状态
    if [ $(($(date +%s) % 300)) -eq 0 ]; then
        echo "$(date): MCP服务运行中 (PID: $MCP_PID)"
        if [ "$VNC_MODE" = "true" ]; then
            echo "VNC可访问: <服务器IP>:5901"
        fi
    fi
    
    sleep 10
done
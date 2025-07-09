#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
echo "==================================="

# 设置环境变量
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=/dev/null

# 启动Xvfb虚拟显示
echo "启动虚拟显示..."
Xvfb :0 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 3

# 启动窗口管理器
echo "启动窗口管理器..."
fluxbox &
FLUXBOX_PID=$!
sleep 2

# 根据VNC_MODE决定是否启动VNC
if [ "$VNC_MODE" = "true" ]; then
    echo "启动VNC服务器..."
    x11vnc -display :0 -forever -usepw -rfbport 5900 -shared -noxrecord -noxfixes -noxdamage &
    VNC_PID=$!
    sleep 2
    
    echo "==================================="
    echo "VNC服务器已启动"
    echo "VNC地址: <服务器IP>:5901"
    echo "VNC密码: xhstools"
    echo "==================================="
    
    # 在VNC模式下启动Chrome（供手动操作）
    echo "启动Chrome浏览器（VNC模式）..."
    
    # 检查Chrome是否存在
    if command -v google-chrome-stable >/dev/null 2>&1; then
        CHROME_CMD="google-chrome-stable"
    elif command -v google-chrome >/dev/null 2>&1; then
        CHROME_CMD="google-chrome"
    elif command -v chromium >/dev/null 2>&1; then
        CHROME_CMD="chromium"
    else
        echo "警告: 未找到Chrome浏览器，使用Playwright的Chromium"
        CHROME_CMD="/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
    fi
    
    # 启动Chrome
    $CHROME_CMD \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --disable-software-rasterizer \
        --disable-background-timer-throttling \
        --disable-backgrounding-occluded-windows \
        --disable-renderer-backgrounding \
        --remote-debugging-port=9222 \
        --user-data-dir=/app/browser_data \
        --window-size=1920,1080 \
        --start-maximized \
        "https://www.xiaohongshu.com" >/dev/null 2>&1 &
    CHROME_PID=$!
    
    if [ $? -eq 0 ]; then
        echo "Chrome浏览器启动成功 (PID: $CHROME_PID)"
    else
        echo "Chrome浏览器启动失败，但VNC仍可用"
    fi
fi

# 等待服务启动
sleep 3

# 显示服务信息
echo "==================================="
echo "服务信息:"
echo "MCP SSE服务地址: http://<服务器IP>:8080/sse"
if [ "$VNC_MODE" = "true" ]; then
    echo "VNC地址: <服务器IP>:5901"
    echo "VNC密码: xhstools"
fi
echo "健康检查: http://<服务器IP>:8080/health"
echo "==================================="

# 清理函数
cleanup() {
    echo "正在关闭服务..."
    if [ ! -z "$CHROME_PID" ] && kill -0 "$CHROME_PID" 2>/dev/null; then
        echo "关闭Chrome浏览器..."
        kill $CHROME_PID 2>/dev/null
        sleep 2
        # 强制结束Chrome进程
        pkill -f chrome 2>/dev/null
    fi
    if [ ! -z "$VNC_PID" ] && kill -0 "$VNC_PID" 2>/dev/null; then
        echo "关闭VNC服务器..."
        kill $VNC_PID 2>/dev/null
    fi
    if [ ! -z "$FLUXBOX_PID" ] && kill -0 "$FLUXBOX_PID" 2>/dev/null; then
        echo "关闭窗口管理器..."
        kill $FLUXBOX_PID 2>/dev/null
    fi
    if [ ! -z "$XVFB_PID" ] && kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "关闭虚拟显示..."
        kill $XVFB_PID 2>/dev/null
    fi
    exit 0
}

# 设置信号处理
trap cleanup SIGTERM SIGINT

# 启动主应用
echo "启动小红书MCP SSE服务器..."
cd /app
python xiaohongshu_mcp_sse.py

# 如果主应用退出，执行清理
cleanup
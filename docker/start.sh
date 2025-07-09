#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
echo "==================================="

# 设置环境变量
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=/dev/null

# 清理旧进程
pkill -f Xvfb 2>/dev/null || true
pkill -f fluxbox 2>/dev/null || true
pkill -f x11vnc 2>/dev/null || true
pkill -f chrome 2>/dev/null || true
rm -f /tmp/.X*-lock 2>/dev/null || true
sleep 2

# 创建X11目录
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# 启动Xvfb
echo "启动虚拟显示服务器..."
Xvfb :0 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset >/dev/null 2>&1 &
XVFB_PID=$!

# 等待Xvfb启动
sleep 3
if ! xdpyinfo -display :0 >/dev/null 2>&1; then
    echo "错误: Xvfb启动失败"
    exit 1
fi
echo "✓ Xvfb启动成功"

# 启动窗口管理器
echo "启动窗口管理器..."
fluxbox >/dev/null 2>&1 &
FLUXBOX_PID=$!
sleep 2

# 启动VNC服务器
if [ "$VNC_MODE" = "true" ]; then
    echo "启动VNC服务器..."
    
    # 启动x11vnc
    x11vnc -display :0 -forever -nopw -rfbport 5900 -shared -quiet -bg
    
    sleep 2
    
    if pgrep -f x11vnc >/dev/null; then
        echo "✓ VNC服务器启动成功"
        echo "VNC地址: <服务器IP>:5901 (无密码)"
    else
        echo "✗ VNC服务器启动失败"
        exit 1
    fi
    
    # 启动Chrome
    echo "启动Chrome浏览器..."
    if command -v google-chrome-stable >/dev/null 2>&1; then
        google-chrome-stable \
            --no-sandbox \
            --disable-dev-shm-usage \
            --disable-gpu \
            --user-data-dir=/app/browser_data \
            --window-size=1920,1080 \
            --start-maximized \
            "https://www.xiaohongshu.com" >/dev/null 2>&1 &
        
        CHROME_PID=$!
        sleep 2
        
        if kill -0 $CHROME_PID 2>/dev/null; then
            echo "✓ Chrome启动成功"
        else
            echo "⚠ Chrome启动失败，但VNC可用"
        fi
    fi
fi

echo "==================================="
echo "服务启动完成!"
echo "MCP服务: http://<服务器IP>:8080"
echo "VNC地址: <服务器IP>:5901"
echo "==================================="

# 清理函数
cleanup() {
    echo "正在关闭服务..."
    [ ! -z "$CHROME_PID" ] && kill $CHROME_PID 2>/dev/null
    pkill -f x11vnc 2>/dev/null || true
    [ ! -z "$FLUXBOX_PID" ] && kill $FLUXBOX_PID 2>/dev/null
    [ ! -z "$XVFB_PID" ] && kill $XVFB_PID 2>/dev/null
    exit 0
}

trap cleanup SIGTERM SIGINT

# 启动Python应用
echo "启动MCP服务..."
cd /app
python xiaohongshu_mcp_sse.py

cleanup
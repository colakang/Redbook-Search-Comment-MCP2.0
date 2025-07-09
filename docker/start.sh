#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
echo "==================================="

# 设置环境变量
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=/dev/null

# 清理函数
cleanup() {
    echo "清理进程..."
    pkill -f Xvfb 2>/dev/null || true
    pkill -f fluxbox 2>/dev/null || true
    pkill -f x11vnc 2>/dev/null || true
    pkill -f chrome 2>/dev/null || true
    rm -f /tmp/.X*-lock 2>/dev/null || true
    rm -f /tmp/.X11-unix/X* 2>/dev/null || true
    sleep 2
}

# 初始清理
cleanup

# 创建X11目录
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# 启动Xvfb
echo "启动虚拟显示服务器..."
Xvfb :0 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset >/dev/null 2>&1 &
XVFB_PID=$!

# 等待Xvfb启动
sleep 5
if ! xdpyinfo -display :0 >/dev/null 2>&1; then
    echo "错误: Xvfb启动失败"
    exit 1
fi
echo "✓ Xvfb启动成功"

# 启动窗口管理器
echo "启动窗口管理器..."
fluxbox >/dev/null 2>&1 &
FLUXBOX_PID=$!
sleep 3

# 启动VNC（如果启用）
if [ "$VNC_MODE" = "true" ]; then
    echo "启动VNC服务器..."
    
    # 创建VNC目录
    mkdir -p /root/.vnc
    
    # 简单的VNC密码设置
    echo "xhstools" > /tmp/vncpass
    if command -v vncpasswd >/dev/null 2>&1; then
        cat /tmp/vncpass | vncpasswd -f > /root/.vnc/passwd
        chmod 600 /root/.vnc/passwd
        rm /tmp/vncpass
        VNC_AUTH="-usepw"
        echo "✓ VNC密码设置成功"
    else
        echo "⚠ vncpasswd未找到，使用无密码模式"
        VNC_AUTH="-nopw"
    fi
    
    # 启动x11vnc
    x11vnc -display :0 -forever $VNC_AUTH -rfbport 5900 -shared -quiet -bg -o /tmp/x11vnc.log
    
    sleep 3
    
    if pgrep -f x11vnc >/dev/null; then
        echo "==================================="
        echo "✓ VNC服务器启动成功!"
        echo "VNC地址: <服务器IP>:5901"
        if [ "$VNC_AUTH" = "-usepw" ]; then
            echo "VNC密码: xhstools"
        else
            echo "VNC无密码（仅测试用）"
        fi
        echo "==================================="
    else
        echo "✗ VNC启动失败"
        cat /tmp/x11vnc.log 2>/dev/null || echo "无VNC日志"
        exit 1
    fi
    
    # 启动Chrome
    echo "启动Chrome浏览器..."
    if command -v google-chrome-stable >/dev/null 2>&1; then
        google-chrome-stable \
            --no-sandbox \
            --disable-dev-shm-usage \
            --disable-gpu \
            --remote-debugging-port=9222 \
            --user-data-dir=/app/browser_data \
            --window-size=1920,1080 \
            --start-maximized \
            "https://www.xiaohongshu.com" >/dev/null 2>&1 &
        CHROME_PID=$!
        sleep 3
        if kill -0 $CHROME_PID 2>/dev/null; then
            echo "✓ Chrome启动成功"
        else
            echo "⚠ Chrome启动失败"
        fi
    fi
fi

# 显示服务信息
echo "==================================="
echo "服务信息:"
echo "MCP服务: http://<服务器IP>:8080/sse"
if [ "$VNC_MODE" = "true" ]; then
    echo "VNC地址: <服务器IP>:5901"
fi
echo "健康检查: http://<服务器IP>:8080/health"
echo "==================================="

# 退出时清理
final_cleanup() {
    echo "关闭服务..."
    [ ! -z "$CHROME_PID" ] && kill $CHROME_PID 2>/dev/null
    [ ! -z "$VNC_PID" ] && kill $VNC_PID 2>/dev/null
    [ ! -z "$FLUXBOX_PID" ] && kill $FLUXBOX_PID 2>/dev/null
    [ ! -z "$XVFB_PID" ] && kill $XVFB_PID 2>/dev/null
    cleanup
    exit 0
}

trap final_cleanup SIGTERM SIGINT

# 启动主应用
echo "启动Python应用..."
cd /app
python xiaohongshu_mcp_sse.py

final_cleanup
#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
echo "==================================="

# 设置环境变量
export DISPLAY=:0
export DBUS_SESSION_BUS_ADDRESS=/dev/null

# 清理旧进程
cleanup_processes() {
    pkill -f Xvfb 2>/dev/null || true
    pkill -f fluxbox 2>/dev/null || true
    pkill -f x11vnc 2>/dev/null || true
    pkill -f chrome 2>/dev/null || true
    pkill -f chromium 2>/dev/null || true
    rm -f /tmp/.X*-lock 2>/dev/null || true
    sleep 2
}

cleanup_processes

# 创建X11目录
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

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
    
    # 启动x11vnc，增强兼容性
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
    
    # 检查VNC状态
    if pgrep -f x11vnc >/dev/null; then
        VNC_PID=$(pgrep -f x11vnc)
        echo "✓ VNC服务器启动成功 (PID: $VNC_PID)"
        echo "VNC地址: <服务器IP>:5901 (无密码)"
    else
        echo "✗ VNC服务器启动失败"
        exit 1
    fi
    
    # 启动Chrome（改进版）
    echo "启动Chrome浏览器..."
    
    # 检查Chrome可用性
    CHROME_CMD=""
    if command -v google-chrome-stable >/dev/null 2>&1; then
        CHROME_CMD="google-chrome-stable"
    elif command -v google-chrome >/dev/null 2>&1; then
        CHROME_CMD="google-chrome"
    elif command -v chromium-browser >/dev/null 2>&1; then
        CHROME_CMD="chromium-browser"
    elif command -v chromium >/dev/null 2>&1; then
        CHROME_CMD="chromium"
    fi
    
    if [ ! -z "$CHROME_CMD" ]; then
        echo "找到浏览器: $CHROME_CMD"
        
        # 创建Chrome数据目录
        mkdir -p /app/browser_data
        chmod 755 /app/browser_data
        
        # 启动Chrome，增强参数
        DISPLAY=:0 $CHROME_CMD \
            --no-sandbox \
            --disable-dev-shm-usage \
            --disable-gpu \
            --disable-software-rasterizer \
            --disable-background-timer-throttling \
            --disable-backgrounding-occluded-windows \
            --disable-renderer-backgrounding \
            --disable-features=VizDisplayCompositor \
            --disable-extensions \
            --disable-plugins \
            --disable-web-security \
            --disable-features=TranslateUI \
            --no-first-run \
            --no-default-browser-check \
            --user-data-dir=/app/browser_data \
            --window-size=1920,1080 \
            --start-maximized \
            "https://www.xiaohongshu.com" \
            >/dev/null 2>&1 &
        
        CHROME_PID=$!
        sleep 3
        
        # 检查Chrome状态
        if kill -0 $CHROME_PID 2>/dev/null && pgrep -f "$CHROME_CMD" >/dev/null; then
            echo "✓ Chrome启动成功 (PID: $CHROME_PID)"
        else
            echo "⚠ Chrome启动失败，但VNC可用于手动启动"
            echo "  可以通过VNC手动打开浏览器"
            CHROME_PID=""
        fi
    else
        echo "⚠ 未找到Chrome浏览器，请通过VNC手动操作"
    fi
fi

echo "==================================="
echo "服务启动完成!"
echo "MCP服务: http://<服务器IP>:8080"
echo "VNC地址: <服务器IP>:5901 (无密码)"
echo "API文档: http://<服务器IP>:8080/docs"
echo "==================================="

# 清理函数
cleanup() {
    echo "正在关闭服务..."
    
    # 关闭Chrome
    if [ ! -z "$CHROME_PID" ] && kill -0 "$CHROME_PID" 2>/dev/null; then
        kill $CHROME_PID 2>/dev/null || true
    fi
    pkill -f chrome 2>/dev/null || true
    pkill -f chromium 2>/dev/null || true
    
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

# 启动Python应用
echo "启动MCP服务..."
cd /app

# 确保目录权限正确
chmod 755 /app
chmod -R 755 /app/browser_data 2>/dev/null || true

# 启动Python应用，增加错误处理
python xiaohongshu_mcp_sse.py || {
    echo "Python应用启动失败，但保持容器运行用于调试"
    echo "请检查VNC连接: <服务器IP>:5901"
    
    # 保持容器运行，方便调试
    while true; do
        echo "$(date): 容器保持运行中，VNC地址: <服务器IP>:5901"
        sleep 300  # 每5分钟输出一次状态
    done
}

cleanup
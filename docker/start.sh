#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
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
fi

echo "==================================="
echo "服务启动完成!"
echo "MCP服务: http://<服务器IP>:8080"
echo "VNC地址: <服务器IP>:5901 (无密码)"
echo "API文档: http://<服务器IP>:8080/docs"
echo ""
echo "使用说明:"
echo "1. 通过VNC连接到桌面"
echo "2. 双击桌面上的Chrome图标启动浏览器"
echo "3. 在浏览器中登录小红书账号"
echo "4. 使用API进行搜索和评论操作"
echo "==================================="

# 清理函数
cleanup() {
    echo "正在关闭服务..."
    
    # 关闭所有Chrome进程
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

# 启动Python应用
python xiaohongshu_mcp_sse.py || {
    echo "Python应用启动失败，但保持容器运行用于调试"
    echo "VNC地址: <服务器IP>:5901 (无密码)"
    
    # 保持容器运行
    while true; do
        echo "$(date): 容器运行中，请通过VNC操作"
        sleep 300
    done
}

cleanup
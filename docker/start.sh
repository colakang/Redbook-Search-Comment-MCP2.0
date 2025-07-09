#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中（无头服务器模式）..."
echo "==================================="

# 检测是否为无头服务器环境
check_headless_environment() {
    echo "检测服务器环境..."
    
    # 检查是否有DISPLAY环境变量指向宿主机
    if [ ! -z "$DISPLAY" ] && [ "$DISPLAY" != ":0" ]; then
        echo "检测到外部DISPLAY环境变量: $DISPLAY"
        echo "在无头服务器上重置为容器内部显示"
    fi
    
    # 检查宿主机X11状态（仅用于日志记录）
    if [ -S /tmp/.X11-unix/X0 ]; then
        echo "注意: 检测到宿主机X11套接字，但将使用容器内部X11"
    else
        echo "确认: 宿主机为无头服务器环境，将创建容器内部X11"
    fi
}

# 容器内部X11环境设置
setup_container_x11() {
    echo "设置容器内部X11环境..."
    
    # 强制使用容器内部显示
    export DISPLAY=:0
    export DBUS_SESSION_BUS_ADDRESS=/dev/null
    
    # 创建容器内部X11目录
    mkdir -p /tmp/.X11-unix
    chmod 1777 /tmp/.X11-unix
    
    # 清理任何遗留的X11文件
    rm -f /tmp/.X*-lock 2>/dev/null || true
    rm -f /tmp/.X11-unix/X* 2>/dev/null || true
    
    echo "容器X11环境设置完成"
}

# 清理函数
cleanup() {
    echo "清理容器内部进程..."
    
    # 只清理容器内的进程
    pkill -9 -f "Xvfb.*:0" 2>/dev/null || true
    pkill -9 -f "fluxbox" 2>/dev/null || true
    pkill -9 -f "x11vnc.*:0" 2>/dev/null || true
    pkill -9 -f "chrome" 2>/dev/null || true
    
    # 清理容器内X11文件
    rm -f /tmp/.X*-lock 2>/dev/null || true
    rm -f /tmp/.X11-unix/X* 2>/dev/null || true
    
    sleep 2
    echo "容器清理完成"
}

# 启动容器专用Xvfb
start_container_xvfb() {
    echo "启动容器内部Xvfb服务器..."
    
    # 使用最适合无头服务器的Xvfb配置
    Xvfb :0 \
        -screen 0 1920x1080x24 \
        -ac \
        +extension GLX \
        +extension RANDR \
        +extension RENDER \
        -noreset \
        -nolisten tcp \
        -nolisten unix \
        -dpi 96 \
        -fbdir /var/tmp \
        >/dev/null 2>&1 &
    
    XVFB_PID=$!
    echo "Xvfb进程ID: $XVFB_PID"
    
    # 等待Xvfb完全启动
    echo "等待Xvfb服务器启动..."
    for i in {1..30}; do
        if xdpyinfo -display :0 >/dev/null 2>&1; then
            echo "✓ Xvfb服务器启动成功"
            return 0
        fi
        if ! kill -0 $XVFB_PID 2>/dev/null; then
            echo "✗ Xvfb进程意外退出"
            return 1
        fi
        sleep 1
        echo "  等待中... ($i/30)"
    done
    
    echo "✗ Xvfb启动超时"
    return 1
}

# 启动窗口管理器
start_window_manager() {
    echo "启动轻量级窗口管理器..."
    
    # 使用最小配置的fluxbox
    DISPLAY=:0 fluxbox >/dev/null 2>&1 &
    FLUXBOX_PID=$!
    
    sleep 3
    
    if kill -0 $FLUXBOX_PID 2>/dev/null; then
        echo "✓ Fluxbox启动成功"
    else
        echo "⚠ Fluxbox启动失败，但X11仍可用"
    fi
}

# 启动VNC服务器
start_vnc_server() {
    echo "启动VNC服务器..."
    
    # 优化无头服务器的VNC配置
    x11vnc \
        -display :0 \
        -forever \
        -usepw \
        -rfbport 5900 \
        -shared \
        -noxrecord \
        -noxfixes \
        -noxdamage \
        -noxinerama \
        -quiet \
        -bg \
        -o /tmp/x11vnc.log \
        -logappend
    
    sleep 3
    
    # 验证VNC启动
    if pgrep -f "x11vnc.*:0" >/dev/null; then
        VNC_PID=$(pgrep -f "x11vnc.*:0")
        echo "==================================="
        echo "✓ VNC服务器启动成功!"
        echo "VNC地址: <服务器IP>:5901"
        echo "VNC密码: xhstools"
        echo "VNC进程ID: $VNC_PID"
        echo "==================================="
        return 0
    else
        echo "✗ VNC服务器启动失败"
        echo "VNC日志内容:"
        cat /tmp/x11vnc.log 2>/dev/null || echo "无日志文件"
        return 1
    fi
}

# 启动浏览器
start_browser() {
    echo "启动Chrome浏览器..."
    
    # 检查Chrome可用性
    if command -v google-chrome-stable >/dev/null 2>&1; then
        CHROME_CMD="google-chrome-stable"
    elif command -v google-chrome >/dev/null 2>&1; then
        CHROME_CMD="google-chrome"
    elif command -v chromium >/dev/null 2>&1; then
        CHROME_CMD="chromium"
    else
        echo "⚠ 未找到Chrome浏览器"
        return 1
    fi
    
    # 无头服务器优化的Chrome配置
    DISPLAY=:0 $CHROME_CMD \
        --no-sandbox \
        --disable-dev-shm-usage \
        --disable-gpu \
        --disable-software-rasterizer \
        --disable-background-timer-throttling \
        --disable-backgrounding-occluded-windows \
        --disable-renderer-backgrounding \
        --disable-features=TranslateUI \
        --disable-extensions \
        --disable-plugins \
        --remote-debugging-port=9222 \
        --user-data-dir=/app/browser_data \
        --window-size=1920,1080 \
        --start-maximized \
        "https://www.xiaohongshu.com" >/dev/null 2>&1 &
    
    CHROME_PID=$!
    sleep 3
    
    if kill -0 $CHROME_PID 2>/dev/null; then
        echo "✓ Chrome浏览器启动成功 (PID: $CHROME_PID)"
    else
        echo "⚠ Chrome浏览器启动失败，但VNC仍可用"
        CHROME_PID=""
    fi
}

# 主要流程
main() {
    # 错误处理
    set -e
    trap 'echo "启动过程中发生错误"; cleanup; exit 1' ERR
    
    # 1. 环境检测
    check_headless_environment
    
    # 2. 初始清理
    cleanup
    
    # 3. 设置容器X11环境
    setup_container_x11
    
    # 4. 启动Xvfb
    if ! start_container_xvfb; then
        echo "Xvfb启动失败，退出"
        exit 1
    fi
    
    # 5. 启动窗口管理器
    start_window_manager
    
    # 6. 根据配置启动VNC
    if [ "$VNC_MODE" = "true" ]; then
        if ! start_vnc_server; then
            echo "VNC启动失败，退出"
            exit 1
        fi
        
        # 7. 启动浏览器
        start_browser
    fi
    
    # 8. 显示服务信息
    echo "==================================="
    echo "服务状态摘要:"
    echo "✓ Xvfb虚拟显示服务器: 运行中"
    echo "✓ VNC远程桌面服务: 端口5901"
    echo "✓ MCP服务接口: 端口8080"
    echo ""
    echo "连接信息:"
    echo "VNC地址: <服务器IP>:5901"
    echo "VNC密码: xhstools"
    echo "MCP地址: http://<服务器IP>:8080/sse"
    echo "健康检查: http://<服务器IP>:8080/health"
    echo "==================================="
}

# 清理函数（用于退出）
final_cleanup() {
    echo "正在关闭所有容器内服务..."
    
    # 关闭Chrome
    if [ ! -z "$CHROME_PID" ] && kill -0 "$CHROME_PID" 2>/dev/null; then
        kill $CHROME_PID 2>/dev/null
    fi
    pkill -f chrome 2>/dev/null || true
    
    # 关闭VNC
    if [ ! -z "$VNC_PID" ] && kill -0 "$VNC_PID" 2>/dev/null; then
        kill $VNC_PID 2>/dev/null
    fi
    pkill -f x11vnc 2>/dev/null || true
    
    # 关闭窗口管理器
    if [ ! -z "$FLUXBOX_PID" ] && kill -0 "$FLUXBOX_PID" 2>/dev/null; then
        kill $FLUXBOX_PID 2>/dev/null
    fi
    pkill -f fluxbox 2>/dev/null || true
    
    # 关闭Xvfb
    if [ ! -z "$XVFB_PID" ] && kill -0 "$XVFB_PID" 2>/dev/null; then
        kill $XVFB_PID 2>/dev/null
    fi
    pkill -f Xvfb 2>/dev/null || true
    
    # 清理容器内文件
    rm -f /tmp/.X*-lock /tmp/.X11-unix/X* 2>/dev/null || true
    
    echo "容器服务清理完成"
    exit 0
}

# 设置信号处理
trap final_cleanup SIGTERM SIGINT

# 执行主流程
main

# 启动Python应用
echo "启动小红书MCP服务器..."
cd /app

# 依赖检查
python -c "import tenacity; print('✓ tenacity')" || {
    echo "✗ tenacity模块未安装"
    final_cleanup
    exit 1
}

echo "启动主应用..."
python xiaohongshu_mcp_sse.py

# 退出时清理
final_cleanup
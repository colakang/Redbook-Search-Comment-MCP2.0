#!/bin/bash

echo "==================================="
echo "小红书MCP服务器启动中..."
echo "==================================="

# 错误处理
set -e
trap 'echo "错误发生在第$LINENO行"; cleanup; exit 1' ERR

# 清理函数
cleanup() {
    echo "执行清理操作..."
    
    # 强制杀死所有相关进程
    pkill -9 -f "Xvfb" 2>/dev/null || true
    pkill -9 -f "fluxbox" 2>/dev/null || true
    pkill -9 -f "x11vnc" 2>/dev/null || true
    pkill -9 -f "chrome" 2>/dev/null || true
    
    # 清理X11相关文件
    rm -rf /tmp/.X*-lock /tmp/.X11-unix/* 2>/dev/null || true
    
    # 等待进程完全退出
    sleep 2
    
    echo "清理完成"
}

# 查找可用的显示端口
find_available_display() {
    for i in {0..10}; do
        if ! ls /tmp/.X${i}-lock >/dev/null 2>&1; then
            echo $i
            return
        fi
    done
    echo "0"  # 默认返回0
}

# 初始清理
echo "初始清理环境..."
cleanup

# 设置环境变量
DISPLAY_NUM=$(find_available_display)
export DISPLAY=:$DISPLAY_NUM
export DBUS_SESSION_BUS_ADDRESS=/dev/null

echo "使用显示端口: $DISPLAY_NUM"

# 创建必要的目录
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

# 启动Xvfb虚拟显示
echo "启动虚拟显示服务器..."
Xvfb :$DISPLAY_NUM \
    -screen 0 1920x1080x24 \
    -ac \
    +extension GLX \
    +render \
    -noreset \
    -nolisten tcp \
    -dpi 96 \
    >/dev/null 2>&1 &

XVFB_PID=$!
echo "Xvfb PID: $XVFB_PID"

# 等待并验证Xvfb启动
echo "等待虚拟显示服务器启动..."
for i in {1..30}; do
    if xdpyinfo -display :$DISPLAY_NUM >/dev/null 2>&1; then
        echo "虚拟显示服务器启动成功"
        break
    fi
    if ! kill -0 $XVFB_PID 2>/dev/null; then
        echo "错误: Xvfb进程意外退出"
        exit 1
    fi
    sleep 1
    echo "等待中... ($i/30)"
done

# 最终验证
if ! xdpyinfo -display :$DISPLAY_NUM >/dev/null 2>&1; then
    echo "错误: 虚拟显示服务器启动失败"
    exit 1
fi

# 启动窗口管理器
echo "启动窗口管理器..."
DISPLAY=:$DISPLAY_NUM fluxbox >/dev/null 2>&1 &
FLUXBOX_PID=$!
sleep 3

# 验证窗口管理器
if ! kill -0 $FLUXBOX_PID 2>/dev/null; then
    echo "警告: Fluxbox可能启动失败，但继续运行"
fi

# 根据VNC_MODE决定是否启动VNC
if [ "$VNC_MODE" = "true" ]; then
    echo "启动VNC服务器..."
    
    # 启动x11vnc
    x11vnc \
        -display :$DISPLAY_NUM \
        -forever \
        -usepw \
        -rfbport 5900 \
        -shared \
        -noxrecord \
        -noxfixes \
        -noxdamage \
        -quiet \
        -bg \
        -o /tmp/x11vnc.log
    
    # 等待VNC启动
    sleep 3
    
    # 检查VNC是否启动成功
    if pgrep -f "x11vnc.*:$DISPLAY_NUM" >/dev/null; then
        VNC_PID=$(pgrep -f "x11vnc.*:$DISPLAY_NUM")
        echo "==================================="
        echo "VNC服务器启动成功!"
        echo "VNC地址: <服务器IP>:5901"
        echo "VNC密码: xhstools"
        echo "显示端口: :$DISPLAY_NUM"
        echo "VNC PID: $VNC_PID"
        echo "==================================="
    else
        echo "错误: VNC服务器启动失败"
        echo "VNC日志:"
        cat /tmp/x11vnc.log 2>/dev/null || echo "无VNC日志"
        exit 1
    fi
    
    # 在VNC模式下启动Chrome
    echo "启动Chrome浏览器..."
    
    # 检查Chrome命令
    if command -v google-chrome-stable >/dev/null 2>&1; then
        CHROME_CMD="google-chrome-stable"
    elif command -v google-chrome >/dev/null 2>&1; then
        CHROME_CMD="google-chrome"
    elif command -v chromium >/dev/null 2>&1; then
        CHROME_CMD="chromium"
    else
        echo "警告: 未找到Chrome浏览器"
        CHROME_CMD=""
    fi
    
    if [ ! -z "$CHROME_CMD" ]; then
        DISPLAY=:$DISPLAY_NUM $CHROME_CMD \
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
        sleep 2
        
        if kill -0 $CHROME_PID 2>/dev/null; then
            echo "Chrome浏览器启动成功 (PID: $CHROME_PID)"
        else
            echo "Chrome浏览器启动失败，但VNC可用"
            CHROME_PID=""
        fi
    fi
fi

# 显示服务信息
echo "==================================="
echo "服务信息:"
echo "MCP SSE服务地址: http://<服务器IP>:8080/sse"
if [ "$VNC_MODE" = "true" ]; then
    echo "VNC地址: <服务器IP>:5901"
    echo "VNC密码: xhstools"
    echo "显示端口: :$DISPLAY_NUM"
fi
echo "健康检查: http://<服务器IP>:8080/health"
echo "==================================="

# 增强的清理函数（用于退出时）
final_cleanup() {
    echo "正在关闭所有服务..."
    
    # 关闭Chrome
    if [ ! -z "$CHROME_PID" ] && kill -0 "$CHROME_PID" 2>/dev/null; then
        echo "关闭Chrome浏览器..."
        kill $CHROME_PID 2>/dev/null
        sleep 2
    fi
    pkill -f chrome 2>/dev/null || true
    
    # 关闭VNC
    if [ ! -z "$VNC_PID" ] && kill -0 "$VNC_PID" 2>/dev/null; then
        echo "关闭VNC服务器..."
        kill $VNC_PID 2>/dev/null
    fi
    pkill -f x11vnc 2>/dev/null || true
    
    # 关闭窗口管理器
    if [ ! -z "$FLUXBOX_PID" ] && kill -0 "$FLUXBOX_PID" 2>/dev/null; then
        echo "关闭窗口管理器..."
        kill $FLUXBOX_PID 2>/dev/null
    fi
    pkill -f fluxbox 2>/dev/null || true
    
    # 关闭虚拟显示
    if [ ! -z "$XVFB_PID" ] && kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "关闭虚拟显示..."
        kill $XVFB_PID 2>/dev/null
    fi
    pkill -f Xvfb 2>/dev/null || true
    
    # 清理文件
    rm -rf /tmp/.X*-lock /tmp/.X11-unix/* 2>/dev/null || true
    
    echo "所有服务已关闭"
    exit 0
}

# 设置信号处理
trap final_cleanup SIGTERM SIGINT

# 启动主应用
echo "启动小红书MCP SSE服务器..."
cd /app

# 检查Python依赖
echo "检查关键依赖..."
python -c "import tenacity; print('✓ tenacity')" || {
    echo "✗ tenacity模块未安装"
    final_cleanup
    exit 1
}

python -c "import playwright; print('✓ playwright')" || {
    echo "✗ playwright模块未安装"
    final_cleanup
    exit 1
}

echo "所有依赖检查通过，启动主应用..."

# 启动主应用
python xiaohongshu_mcp_sse.py

# 如果主应用退出，执行清理
final_cleanup
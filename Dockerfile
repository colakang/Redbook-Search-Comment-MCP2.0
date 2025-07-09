FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖和浏览器 + VNC组件
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    # VNC和虚拟显示支持
    xvfb \
    x11vnc \
    fluxbox \
    dbus-x11 \
    # 实用工具
    curl \
    procps \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置VNC密码
RUN mkdir -p /root/.vnc && \
    echo "xhstools" | vncpasswd -f > /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# 复制项目文件
COPY requirements.txt .
COPY xiaohongshu_mcp_sse.py .
COPY docker/ ./docker/

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 安装Playwright浏览器
RUN playwright install chromium --with-deps

# 创建必要的目录
RUN mkdir -p browser_data data logs

# 设置启动脚本权限
RUN chmod +x docker/start.sh

# 暴露端口
EXPOSE 8080 5900

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 使用启动脚本
CMD ["./docker/start.sh"]
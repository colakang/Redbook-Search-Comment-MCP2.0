FROM python:3.11-slim

WORKDIR /app

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    # 基础工具
    wget \
    gnupg \
    ca-certificates \
    curl \
    procps \
    psmisc \
    # Chrome依赖
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
    # X11和VNC支持
    xvfb \
    x11vnc \
    x11-utils \
    x11-xserver-utils \
    fluxbox \
    dbus-x11 \
    # 字体支持
    fonts-wqy-zenhei \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# 创建X11目录并设置权限
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix

# 设置VNC密码
RUN mkdir -p /root/.vnc && \
    echo "xhstools" | vncpasswd -f > /root/.vnc/passwd && \
    chmod 600 /root/.vnc/passwd

# 复制requirements.txt并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 验证关键依赖
RUN python -c "import tenacity; print('✓ tenacity 安装成功')" && \
    python -c "import playwright; print('✓ playwright 安装成功')" && \
    python -c "import fastapi; print('✓ fastapi 安装成功')"

# 安装Playwright浏览器
RUN playwright install chromium --with-deps

# 复制应用文件
COPY xiaohongshu_mcp_sse.py .
COPY .env .
COPY docker/ ./docker/

# 创建必要的目录并设置权限
RUN mkdir -p browser_data data logs && \
    chmod -R 755 /app && \
    chmod +x docker/start.sh

# 暴露端口
EXPOSE 8080 5900

# 健康检查
#HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
#    CMD pgrep -f x11vnc >/dev/null && curl -f http://localhost:8080/health || exit 1

# 使用改进的启动脚本
CMD ["./docker/start.sh"]
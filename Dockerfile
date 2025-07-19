FROM python:3.11-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0
ENV DBUS_SESSION_BUS_ADDRESS=/dev/null

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    curl \
    procps \
    psmisc \
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
    xvfb \
    x11vnc \
    x11-utils \
    x11-xserver-utils \
    fluxbox \
    dbus-x11 \
    fonts-wqy-zenhei \
    fonts-noto-cjk \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 安装 Google Chrome
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# 创建必要的目录
RUN mkdir -p /tmp/.X11-unix && \
    chmod 1777 /tmp/.X11-unix

RUN mkdir -p /root/.vnc

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 验证关键依赖安装
RUN python -c "import tenacity; print('tenacity OK')" && \
    python -c "import playwright; print('playwright OK')" && \
    python -c "import fastapi; print('fastapi OK')" && \
    python -c "import fastmcp; print('fastmcp OK')"

# 安装 Playwright 浏览器
RUN playwright install chromium --with-deps

# 复制应用文件 - 注意文件名匹配
COPY xiaohongshu_mcp_sse.py .
COPY .env .
COPY docker/ ./docker/

# 创建目录并设置权限
RUN mkdir -p browser_data data logs && \
    chmod -R 755 /app && \
    chmod +x docker/start.sh

# 暴露端口
EXPOSE 8080 5900

# 添加健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# 启动命令
CMD ["./docker/start.sh"]
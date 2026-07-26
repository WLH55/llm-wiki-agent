# 纯后端运行时镜像（不内嵌前端构建）
FROM python:3.11-slim

WORKDIR /app

# Debian 官方源偶发 502 时回退到阿里云镜像，便于国内网络构建
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g; s|https://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org|https://mirrors.aliyun.com|g; s|https://deb.debian.org|https://mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libpq-dev \
      gcc \
      curl; \
    rm -rf /var/lib/apt/lists/*

# Python 依赖（先拷 pyproject.toml 利用层缓存）
COPY pyproject.toml ./

# 拷贝后端源码
COPY app/ ./app/

# 安装 Python 包（app/ 已拷贝，pip install . 可以打包）
# 国内网络优先走阿里云 PyPI 镜像，降低 files.pythonhosted.org 超时概率
RUN pip install --no-cache-dir \
      -i https://mirrors.aliyun.com/pypi/simple/ \
      --trusted-host mirrors.aliyun.com \
      .

# Playwright Python 包不包含浏览器；镜像中安装 Chromium 及其系统依赖
# 国内网络优先走 npmmirror，降低 cdn.playwright.dev 超时/断连概率
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
RUN python -m playwright install --with-deps chromium

# Alembic 迁移文件
COPY alembic.ini ./
COPY alembic/ ./alembic/

EXPOSE 8000

# 启动时自动跑 alembic upgrade（worker 容器由 compose command 覆盖）
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

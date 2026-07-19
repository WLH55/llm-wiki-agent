# ===== Stage 1: 构建前端（Vite + React） =====
FROM node:20-alpine AS frontend-build

WORKDIR /build

# 先拷 package.json 利用层缓存
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

# 拷源码并构建（输出 /build/dist/）
COPY frontend/ ./
RUN npm run build


# ===== Stage 2: 后端运行时 =====
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖（先拷 pyproject.toml 利用层缓存）
COPY backend/pyproject.toml ./

# 拷贝后端源码
COPY backend/app/ ./app/

# 拷贝前端构建产物（FastAPI StaticFiles 托管）
COPY --from=frontend-build /build/dist/ ./static/dist/

# 安装 Python 包（app/ 已拷贝，pip install . 可以打包）
RUN pip install --no-cache-dir .

# Playwright Python 包不包含浏览器；镜像中安装 Chromium 及其系统依赖
RUN python -m playwright install --with-deps chromium

# Alembic 迁移文件
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/

EXPOSE 8000

# 启动时自动跑 alembic upgrade（worker 容器不跑这条 CMD，docker-compose 用 command 覆盖）
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

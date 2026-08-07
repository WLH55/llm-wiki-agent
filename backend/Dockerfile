# syntax=docker/dockerfile:1

# =============================================================================
# LLM Wiki Agent - Backend 生产镜像
# 设计规范参考 WeKnora docker/Dockerfile.app：
#   * 多阶段构建：builder 装依赖/浏览器，runtime 只留运行所需
#   * 非 root 用户运行 + gosu 降权（entrypoint 修复 bind-mount 属主后降权）
#   * 构建参数注入版本/提交信息，apt/pip 镜像源可配置（国内加速）
#   * 镜像内不挂源码：生产用构建产物；开发模式前后端在本机运行（见 docker-compose.dev.yml 说明）
# =============================================================================

# ---------------- Stage 1: builder（依赖 + Playwright Chromium） ----------------
FROM python:3.11-slim AS builder

# 构建参数：国内镜像源（留空走官方源）
ARG APT_MIRROR_ARG
ARG PIP_INDEX_ARG

# 先切 apt 源（若指定），再装构建依赖
RUN set -eux; \
    if [ -n "${APT_MIRROR_ARG:-}" ]; then \
        sed -i "s@deb.debian.org@${APT_MIRROR_ARG:-}@g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends gcc libpq-dev curl; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 依赖层缓存：先拷 pyproject.toml 与 app 包，再 pip install（利用 BuildKit 层缓存）
COPY pyproject.toml ./
COPY app/ ./app/

# 独立 venv：运行时整目录拷贝，避免污染系统 Python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 安装项目依赖（含 playwright 包；浏览器本体在下一步）
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ${PIP_INDEX_ARG:+--index-url $PIP_INDEX_ARG} .

# 下载 Playwright Chromium + 系统依赖（npmmirror 加速，可经构建参数覆盖）
ARG PLAYWRIGHT_DOWNLOAD_HOST_ARG=https://npmmirror.com/mirrors/playwright
ENV PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST_ARG}
RUN python -m playwright install --with-deps chromium

# ---------------- Stage 2: runtime（非 root 运行） ----------------
FROM python:3.11-slim AS runtime

ARG APT_MIRROR_ARG
# 版本/构建信息注入（compose 构建参数传入）
ARG VERSION_ARG=latest
ARG COMMIT_ID_ARG=unknown
ARG BUILD_TIME_ARG=unknown

ENV TZ=Asia/Shanghai \
    VERSION=${VERSION_ARG} \
    COMMIT_ID=${COMMIT_ID_ARG} \
    BUILD_TIME=${BUILD_TIME_ARG} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# 非 root 用户（参考 WeKnora：useradd appuser）
RUN useradd -m -s /bin/bash appuser

# apt 镜像源（若指定）+ 运行时依赖：
#   curl          -> 健康检查
#   gosu          -> entrypoint 降权执行
#   libpq5        -> asyncpg 运行库（构建期 libpq-dev 只在 builder）
#   tzdata        -> 时区支持
RUN set -eux; \
    if [ -n "${APT_MIRROR_ARG:-}" ]; then \
        sed -i "s@deb.debian.org@${APT_MIRROR_ARG:-}@g" /etc/apt/sources.list.d/debian.sources; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends tzdata ca-certificates curl gosu libpq5; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 拷贝 venv、Playwright 浏览器缓存与源码
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.cache/ms-playwright /home/appuser/.cache/ms-playwright
COPY --from=builder /build/app ./app
COPY alembic.ini ./
COPY alembic/ ./alembic/

# Playwright 系统运行库（浏览器本体已从 builder 拷贝，这里只装 OS 依赖）
RUN /opt/venv/bin/python -m playwright install-deps chromium

# 数据/日志目录（开发环境会被 bind-mount 覆盖，属主由 entrypoint 修复）
RUN mkdir -p /app/logs /app/storage && \
    chown -R appuser:appuser /app /home/appuser/.cache/ms-playwright

# 入口：修复属主 -> 降权 -> 执行业务命令（参考 WeKnora scripts/docker-entrypoint.sh）
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 注意：后端配置默认 PORT=8000，但 Docker 内统一 8008（与 compose 端口映射/健康检查一致）
EXPOSE 8008

# 启动时先跑 Alembic 迁移再起 uvicorn（与现有 Dockerfile 行为一致）
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8008"]

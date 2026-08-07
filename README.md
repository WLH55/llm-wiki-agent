# LLM Wiki 3.0

MVP P1 Batch 1: RAG 基础闭环（pgvector halfvec 多维度 + BM25 + RRF 融合 + 中文分词）。

## 架构

| 服务 | 镜像 | 用途 |
|------|------|------|
| postgres | postgres:16 + pgvector + zhparser（自定义构建） | 主数据库 + 向量检索 + 中文分词 |
| redis | redis:7-alpine | Dramatiq 任务队列 + 流处理 |
| minio | minio/minio | 原始文档对象存储 |
| backend | python:3.11-slim（多阶段构建，非 root 运行） | FastAPI + uvicorn |
| task-worker | 同 backend 镜像 | Dramatiq 队列消费者 |
| frontend | nginx:1.27-alpine（多阶段构建） | 前端静态资源 + /api 反代 |

## 快速启动（开发模式）

参考 WeKnora 开发规范：`docker-compose.dev.yml` 只启动基础设施，backend / frontend 在本机运行（热更新）。

```bash
cp .env.example .env
cp backend/.env.example backend/.env.dev
# 编辑 backend/.env.dev，填入 EMBEDDING_API_KEY 等

make dev-start        # 启动基础设施（postgres/redis/minio）

# 新终端 1：本地后端（http://localhost:8008）
cd backend
python -m venv .venv          # 首次
.venv/Scripts/Activate        # Windows PowerShell
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload

# 新终端 2：本地前端（http://localhost:5173，/api 代理到 localhost:8008）
cd frontend
npm install
npm run dev
```

本机连接地址（`backend/.env.dev` 已对齐）：Postgres `localhost:5432`、Redis `localhost:6380`、MinIO `localhost:9000` / 控制台 `localhost:9001`。

## 生产部署

```bash
cp .env.example .env
cp backend/.env.example backend/.env.prod
# 编辑 .env 与 backend/.env.prod，替换所有 CHANGE_ME / 默认凭据
make prod-up   # = docker compose up -d --build
```

生产 compose（docker-compose.yml）特点（参考 WeKnora 规范）：

- 所有服务由 Dockerfile 构建，无源码挂载；非 root 用户运行（gosu 降权）
- 每个服务带 healthcheck，`depends_on` 使用 `service_healthy`
- 命名卷持久化 + `restart: unless-stopped`
- 镜像源（apt/pip/Playwright）可配置，便于国内网络构建

> 国内网络提示：本机直连 deb.debian.org / pypi.org 可能超时或返回 502，建议在 .env 中配置：
>
> ```bash
> APT_MIRROR_ARG=mirrors.aliyun.com
> PIP_INDEX_ARG=https://mirrors.aliyun.com/pypi/simple/
> ```

> 首次构建后端镜像需下载 Playwright Chromium（约 150MB+），耗时较长属正常。


## 访问入口

- 前端：http://localhost:5173（开发）/ http://localhost:80（生产）
- API 文档：http://localhost:8008/docs
- 健康检查：http://localhost:8008/health
- MinIO 控制台：http://localhost:9001

## 常用命令

| 命令 | 作用 |
|------|------|
| `make dev-start` | 启动基础设施（postgres/redis/minio） |
| `make dev-app` | 本机启动后端（需激活 backend/.venv） |
| `make dev-frontend` | 本机启动前端 Vite |
| `make dev-stop` / `make dev-logs` / `make dev-status` | 停止 / 跟踪日志 / 查看基础设施状态 |
| `make prod-up` / `make prod-down` | 构建并启动 / 停止生产环境 |
| `make migrate` | 本地跑 Alembic 迁移（需激活 backend/.venv） |
| `make test` | 本地跑 pytest（需激活 backend/.venv） |
| `make psql` | 进 Postgres 容器 psql |
| `make redis-cli` | 进 Redis 容器 cli |

## 开发

### 后端本地开发（不用 Docker）

```bash
cd backend
python -m venv .venv
.venv/Scripts/Activate  # Windows PowerShell
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

### 前端本地开发（Vite dev server）

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173，代理 /api → http://localhost:8008
```

## 文档

- 设计文档：`mydocs/`
- Spec（本批次）：`mydocs/specs/2026-07-10_00-11_mvp-p1-batch1-rag-foundation.md`
- ADR：`mydocs/context/docs/adr/`

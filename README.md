# LLM Wiki 3.0

MVP P1 Batch 1: RAG 基础闭环（pgvector halfvec 多维度 + BM25 + RRF 融合 + 中文分词）。

## 架构

7 个服务（无 frontend 容器、无 nginx 容器）：

| 服务 | 镜像 | 用途 |
|------|------|------|
| postgres | postgres:16 + pgvector + zhparser（自定义） | 主数据库 + 向量检索 + 中文分词 |
| redis | redis:7-alpine | Taskiq Redis Streams 传输层 |
| minio | minio/minio | 原始文档对象存储 |
| backend | python:3.11-slim（含前端静态托管） | FastAPI + uvicorn |
| outbox-publisher | 同 backend 镜像 | 可靠发布 PostgreSQL Outbox |
| task-worker-shared | 同 backend 镜像 | Taskiq 默认队列消费者 |
| task-worker-critical | 同 backend 镜像 | Taskiq critical 队列消费者 |

## 快速启动

```bash
cp .env.example .env
# 编辑 .env，填入 EMBEDDING_API_KEY（SiliconFlow）
make up
make logs
```

## 访问入口

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 前端搜索页：http://localhost:8000/search（阶段 7 后可用）
- MinIO 控制台：http://localhost:9001

## 常用命令

| 命令 | 作用 |
|------|------|
| `make up` | 构建并启动所有服务 |
| `make down` | 停止所有服务 |
| `make logs` | 跟踪日志 |
| `make migrate` | 跑 Alembic 迁移 |
| `make test` | 跑 pytest |
| `make shell` | 进 backend 容器 shell |
| `make psql` | 连 Postgres psql |

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
npm run dev  # http://localhost:5173，代理 /api → http://localhost:8000
```

## 文档

- 设计文档：`mydocs/`
- Spec（本批次）：`mydocs/specs/2026-07-10_00-11_mvp-p1-batch1-rag-foundation.md`
- ADR：`mydocs/context/docs/adr/`

# =============================================================================
# LLM Wiki Agent Makefile
# 开发模式参考 WeKnora：dev compose 只起基础设施，backend/frontend 在本机运行
#   make dev-start      -> 启动基础设施（postgres/redis/minio）
#   make dev-app        -> 本机启动后端（需先激活 backend/.venv）
#   make dev-frontend   -> 本机启动前端 Vite
#   make prod-up        -> 容器化生产部署（docker-compose.yml）
# =============================================================================

COMPOSE_DEV = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.yml

.PHONY: help up down dev-start dev-stop dev-logs dev-status dev-app dev-frontend prod-up prod-down build logs ps migrate test shell psql redis-cli

help:
	@echo "LLM Wiki Agent"
	@echo ""
	@echo "开发模式（基础设施容器 + 前后端本机运行）："
	@echo "  dev-start       启动基础设施（postgres/redis/minio）"
	@echo "  dev-stop        停止基础设施"
	@echo "  dev-logs        跟踪基础设施日志"
	@echo "  dev-status      查看基础设施状态"
	@echo "  dev-app         本机启动后端（需激活 backend/.venv）"
	@echo "  dev-frontend    本机启动前端（cd frontend && npm run dev）"
	@echo ""
	@echo "生产部署（全部容器化）："
	@echo "  prod-up         构建并启动生产栈"
	@echo "  prod-down       停止生产栈"
	@echo ""
	@echo "常用："
	@echo "  migrate         本地跑 Alembic 迁移（需激活 backend/.venv）"
	@echo "  test            本地跑 pytest（需激活 backend/.venv）"
	@echo "  psql            进入 Postgres"
	@echo "  redis-cli       进入 Redis"

# 兼容旧入口
up: dev-start

down: dev-stop

# ---------------- 开发模式：基础设施 ----------------

dev-start:
	$(COMPOSE_DEV) up -d

dev-stop:
	$(COMPOSE_DEV) down

dev-logs:
	$(COMPOSE_DEV) logs -f

dev-status:
	$(COMPOSE_DEV) ps

# ---------------- 开发模式：本机运行前后端 ----------------

dev-app:
	cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8008 --reload

dev-frontend:
	cd frontend && npm run dev

# ---------------- 生产部署 ----------------

prod-up:
	$(COMPOSE_PROD) up -d --build

prod-down:
	$(COMPOSE_PROD) down

build:
	$(COMPOSE_PROD) build

# ---------------- 常用工具（本地后端需先激活 backend/.venv） ----------------

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest

shell:
	cd backend && bash

psql:
	$(COMPOSE_DEV) exec postgres psql -U "$${POSTGRES_USER:-llmwiki}" -d "$${POSTGRES_DB:-llmwiki}"

redis-cli:
	$(COMPOSE_DEV) exec redis redis-cli -a "$${REDIS_PASSWORD:-llmwiki}"

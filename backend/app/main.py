"""
FastAPI 应用入口

沿用脚手架 create_app() 模式 + 全局异常 + CORS；扩展：
- lifespan 占位调用 ensure_bootstrap_owner（阶段 3 实现）
- 移除 example router 注册
- 加 SPA fallback（FastAPI StaticFiles 托管前端，无 nginx）
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings, setup_logging
from app.config.exceptions import register_exception_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    setup_logging()

    logger.info(f"应用启动: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"运行环境: {settings.ENVIRONMENT}")
    logger.info(f"调试模式: {settings.DEBUG}")

    # 阶段 3: 启动时确保 bootstrap owner 存在
    try:
        from app.auth.bootstrap import ensure_bootstrap_owner
        from app.database import async_session_factory

        async with async_session_factory() as db:
            await ensure_bootstrap_owner(db)
    except Exception as e:
        logger.error(f"ensure_bootstrap_owner 失败: {e}", exc_info=True)

    yield

    logger.info("应用关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # ========== 配置中间件 ==========
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOW_ORIGINS,
        allow_credentials=settings.ALLOW_CREDENTIALS,
        allow_methods=settings.ALLOW_METHODS,
        allow_headers=settings.ALLOW_HEADERS,
    )

    # 缓存请求体中间件（用于异常日志记录）
    @app.middleware("http")
    async def cache_request_body(request: Request, call_next):
        content_type = request.headers.get("content-type", "").lower()
        if request.method in ("POST", "PUT", "PATCH") and not content_type.startswith(
            "multipart/form-data"
        ):
            try:
                body = await request.body()
                if body:
                    request.state.body = body.decode("utf-8")
            except Exception:
                pass
        return await call_next(request)

    # ========== 注册全局异常处理器 ==========
    register_exception_handlers(app)

    # ========== 注册路由 ==========
    from app.auth.routes import router as auth_router
    from app.routers.document import router as document_router
    from app.routers.kb import router as kb_router
    from app.routers.search import router as search_router

    app.include_router(auth_router, prefix="/api")  # /api/auth/*
    app.include_router(kb_router, prefix=settings.API_PREFIX)  # /api/v1/kb
    app.include_router(document_router, prefix=settings.API_PREFIX)  # /api/v1/kb/{id}/documents
    app.include_router(search_router, prefix=settings.API_PREFIX)  # /api/v1/kb/{id}/search

    # ========== 健康检查 ==========
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # ========== SPA 静态托管（无 nginx） ==========
    dist_dir: Path = settings.FRONTEND_DIST_DIR
    assets_dir: Path = dist_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            """SPA 路由回退: /api/* 之外的路径返回 index.html"""
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            index_file = dist_dir / "index.html"
            if not index_file.exists():
                raise HTTPException(status_code=404, detail="Frontend not built")
            return FileResponse(str(index_file))
    else:
        logger.warning(f"前端构建产物不存在: {dist_dir}（阶段 7 后才构建；当前仅 API 可用）")

    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )

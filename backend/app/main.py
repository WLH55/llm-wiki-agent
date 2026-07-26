"""
FastAPI 应用入口

沿用脚手架 create_app() 模式 + 全局异常 + CORS；扩展：
- lifespan 启动时 ensure_bootstrap_owner
- 仅提供 API；前端由独立 frontend 服务/容器托管
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, setup_logging
from app.web.exception_handlers import register_exception_handlers

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    setup_logging()
    logger.info(f"应用启动: {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"运行环境: {settings.ENVIRONMENT}")
    logger.info(f"调试模式: {settings.DEBUG}")
    # 启动时确保 bootstrap owner 存在
    try:
        from app.auth.service.bootstrap import ensure_bootstrap_owner
        from app.models.database import async_session_factory
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
    from app.auth.api.routes import router as auth_router
    from app.knowledge_bases.api.routes import router as kb_router
    from app.parsers.api.routes import engines_router, router as document_router
    from app.search.api.routes import router as search_router
    app.include_router(auth_router, prefix="/api")  # /api/auth/*
    app.include_router(kb_router, prefix=settings.API_PREFIX)  # /api/v1/kb
    app.include_router(engines_router, prefix=settings.API_PREFIX)  # /api/v1/parsers/engines
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

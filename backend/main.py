from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from infra.config import settings
from infra.logging import setup_logging
from middleware.exception_handler import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from middleware.request_id import RequestIDMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    from api.v1.health import router as health_router
    from api.v1.projects import router as projects_router
    from api.v1.jobs import router as jobs_router
    from api.v1.parse import router as parse_router
    from api.v1.models import router as models_router
    from api.v1.generate import router as generate_router
    from api.v1.generate import episode_router
    from api.v1.scenes import router as scenes_episode_router
    from api.v1.scenes import scenes_router
    from api.v1.characters import router as characters_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(parse_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(generate_router, prefix="/api/v1")
    app.include_router(episode_router, prefix="/api/v1")
    app.include_router(scenes_episode_router, prefix="/api/v1")
    app.include_router(scenes_router, prefix="/api/v1")
    app.include_router(characters_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def root_health():
        return {"status": "ok"}

    return app


app = create_app()

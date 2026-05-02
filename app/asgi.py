"""Application implementation - ASGI."""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from app.config import config
from app.models.exception import HttpException
from app.router import root_api_router
from app.utils import utils


def exception_handler(request: Request, e: HttpException):
    return JSONResponse(
        status_code=e.status_code,
        content=utils.get_response(e.status_code, e.data, e.message),
    )


def validation_exception_handler(request: Request, e: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content=utils.get_response(
            status=400, data=e.errors(), message="field required"
        ),
    )


def get_application() -> FastAPI:
    """Initialize FastAPI application.

    Returns:
       FastAPI: Application object instance.

    """
    instance = FastAPI(
        title=config.project_name,
        description=config.project_description,
        version=config.project_version,
        debug=False,
    )
    instance.include_router(root_api_router)
    instance.add_exception_handler(HttpException, exception_handler)
    instance.add_exception_handler(RequestValidationError, validation_exception_handler)
    return instance


app = get_application()

# Configures the CORS middleware for the FastAPI app
cors_allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
origins = cors_allowed_origins_str.split(",") if cors_allowed_origins_str else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

task_dir = utils.task_dir()
app.mount(
    "/tasks", StaticFiles(directory=task_dir, html=True, follow_symlink=True), name=""
)

public_dir = utils.public_dir()
app.mount("/", StaticFiles(directory=public_dir, html=True), name="")


@app.on_event("shutdown")
def shutdown_event():
    logger.info("shutdown event")


@app.on_event("startup")
def startup_event():
    logger.info("startup event")
    # Spec 014: production-guard + per-tenant storage backfill.
    from app.middleware.jwt_auth import verify_production_safety
    verify_production_safety()
    _maybe_backfill_uploads_to_tenant_layout()


def _maybe_backfill_uploads_to_tenant_layout() -> None:
    """Spec 014 FR-020: migrate flat storage/uploads/<uuid>.<ext> →
    storage/uploads/<demo-tenant-id>/<uuid>.<ext> on first startup after
    Step 2 lands. Idempotent — re-running skips files already in a
    tenant subdir.
    """
    import os
    import shutil

    uploads_dir = utils.storage_dir("uploads", create=True)
    if not os.path.isdir(uploads_dir):
        return

    legacy_files = [
        f for f in os.listdir(uploads_dir)
        if os.path.isfile(os.path.join(uploads_dir, f))
    ]
    if not legacy_files:
        return

    target_tenant = os.environ.get("LAYER2_DEMO_TENANT_ID", "demo-tenant-001")
    target_dir = os.path.join(uploads_dir, target_tenant)
    os.makedirs(target_dir, exist_ok=True)

    moved = 0
    for f in legacy_files:
        src = os.path.join(uploads_dir, f)
        dst = os.path.join(target_dir, f)
        if not os.path.exists(dst):
            try:
                shutil.move(src, dst)
                moved += 1
            except OSError as exc:
                logger.warning(f"backfill failed for {f}: {exc}")
    if moved:
        logger.info(f"spec 014 backfill: moved {moved} uploads to {target_tenant}/")

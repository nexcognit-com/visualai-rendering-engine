"""Application configuration - root APIRouter.

Defines all FastAPI application endpoints.

Resources:
    1. https://fastapi.tiangolo.com/tutorial/bigger-applications

"""

from fastapi import APIRouter

from app.controllers.v1 import bgm, llm, uploads, video

root_api_router = APIRouter()
# v1
root_api_router.include_router(video.router)
root_api_router.include_router(llm.router)
# VisualAI additions (spec 009 + 010)
root_api_router.include_router(uploads.router)
root_api_router.include_router(bgm.router)

from typing import Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from app.controllers.v1.base import new_router
from app.models.schema import (
    VideoScriptRequest,
    VideoScriptResponse,
    VideoTermsRequest,
    VideoTermsResponse,
)
from app.services import llm
from app.utils import utils

# authentication dependency
# router = new_router(dependencies=[Depends(base.verify_token)])
router = new_router()


@router.post(
    "/scripts",
    response_model=VideoScriptResponse,
    summary="Create a script for the video",
)
def generate_video_script(request: Request, body: VideoScriptRequest):
    video_script = llm.generate_script(
        video_subject=body.video_subject,
        language=body.video_language,
        paragraph_number=body.paragraph_number,
    )
    response = {"video_script": video_script}
    return utils.get_response(200, response)


@router.post(
    "/terms",
    response_model=VideoTermsResponse,
    summary="Generate video terms based on the video script",
)
def generate_video_terms(request: Request, body: VideoTermsRequest):
    video_terms = llm.generate_terms(
        video_subject=body.video_subject,
        video_script=body.video_script,
        amount=body.amount,
    )
    response = {"video_terms": video_terms}
    return utils.get_response(200, response)


# Spec 006/013 follow-up — Polish preview.
# Lets the wizard preview the polished script before committing to a render,
# without dispatching a task / consuming any state. Pure llm.polish_script wrapper.


class PolishPreviewRequest(BaseModel):
    brief: str = Field(..., description="Creator's rough brief or bullet points.")
    video_subject: Optional[str] = Field(
        default="", description="Optional product/topic context (e.g. enriched URL scrape)."
    )
    duration_seconds: Optional[int] = Field(
        default=20, ge=5, le=120, description="Target voiceover duration."
    )
    language: Optional[str] = Field(default="en")


@router.post(
    "/scripts/polish-preview",
    summary="Preview a polished script (no render dispatch)",
)
def polish_preview(request: Request, body: PolishPreviewRequest):
    if not body.brief or not body.brief.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Brief is required.",
                "error_code": "polish_brief_required",
            },
        )
    try:
        polished = llm.polish_script(
            brief=body.brief.strip(),
            video_subject=(body.video_subject or "").strip(),
            duration_seconds=body.duration_seconds or 20,
            language=body.language or "en",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": str(exc),
                "error_code": "polish_failed",
            },
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "detail": f"Polish service error: {exc}",
                "error_code": "polish_failed",
            },
        )
    return utils.get_response(200, {"polished_script": polished})

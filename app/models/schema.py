import os
import warnings
from enum import Enum
from typing import Any, List, Literal, Optional, Union

import pydantic
from pydantic import BaseModel, Field, model_validator

from app.config import config

# 忽略 Pydantic 的特定警告
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Field name.*shadows an attribute in parent.*",
)


class VideoConcatMode(str, Enum):
    random = "random"
    sequential = "sequential"


class VideoTransitionMode(str, Enum):
    none = None
    shuffle = "Shuffle"
    fade_in = "FadeIn"
    fade_out = "FadeOut"
    slide_in = "SlideIn"
    slide_out = "SlideOut"


class VideoAspect(str, Enum):
    landscape = "16:9"
    portrait = "9:16"
    square = "1:1"

    def to_resolution(self):
        if self == VideoAspect.landscape.value:
            return 1920, 1080
        elif self == VideoAspect.portrait.value:
            return 1080, 1920
        elif self == VideoAspect.square.value:
            return 1080, 1080
        return 1080, 1920


class _Config:
    arbitrary_types_allowed = True


@pydantic.dataclasses.dataclass(config=_Config)
class MaterialInfo:
    provider: str = "pexels"
    url: str = ""
    duration: int = 0


class VideoParams(BaseModel):
    """
    {
      "video_subject": "",
      "video_aspect": "横屏 16:9（西瓜视频）",
      "voice_name": "女生-晓晓",
      "bgm_name": "random",
      "font_name": "STHeitiMedium 黑体-中",
      "text_color": "#FFFFFF",
      "font_size": 60,
      "stroke_color": "#000000",
      "stroke_width": 1.5
    }
    """

    video_subject: str
    video_script: str = ""  # Script used to generate the video
    # Spec 015: Agent Mode dispatch. Default "short" preserves Step-1/2
    # behavior (Mode 2 — Short Marketing Video). "faceless" routes Mode 5
    # (topic-driven generic stock — Pexels permitted). "product_shoot" is
    # rejected at the controller boundary (Mode 1 lives in Layer 2 + 2.5,
    # never reaches Layer 3) — the literal includes it so the schema covers
    # all five-mode-set members ever seen on the API.
    # Spec 016 widens the literal with "long" — Mode 3 Long-Form Video
    # (16:9 YouTube, 2-5 min). Layer 2 builds the script + B-roll list
    # upstream; Layer 3 assembles per the long_form mode registry entry.
    mode: Literal["short", "faceless", "product_shoot", "long"] = "short"

    # Spec 017 — Visual-relevance pipeline. Layer 2.5 may pre-resolve each
    # narration segment to a specific clip URL (semantically aligned via
    # Twelve Labs embed re-ranking, with Kling fallback when stock fails).
    # When provided, these flow into the visuals.json sidecar so material.py
    # bypasses Pixabay/NanoBanana entirely. Both fields are optional —
    # absence = legacy auto-stock dispatch.
    pre_signed_clip_urls: Optional[List[str]] = None
    # Per-segment metadata (text, visual_prompt, target_seconds, provenance,
    # verifier_score). Length matches pre_signed_clip_urls; index N's URL
    # plays during segment N's narration. Stored verbatim in the sidecar
    # for asset-audit traceability.
    segments: Optional[list] = None
    # Spec 013: explicit script-handling mode. None = legacy behavior:
    # empty video_script → auto path; non-empty → verbatim. "auto"/"verbatim"
    # are explicit flavors of those two; "polish" sends the user-typed text
    # to llm.polish_script and uses the LLM's output as the spoken script.
    script_mode: Optional[Literal["auto", "verbatim", "polish"]] = None
    # Spec 013: preserved creator brief — populated only when
    # script_mode == "polish". Original input is kept for provenance even
    # though video_script gets overwritten with the polished output.
    script_brief: Optional[str] = None
    video_terms: Optional[str | list] = None  # Keywords used to generate the video
    video_aspect: Optional[VideoAspect] = VideoAspect.portrait.value
    video_concat_mode: Optional[VideoConcatMode] = VideoConcatMode.random.value
    video_transition_mode: Optional[VideoTransitionMode] = None
    video_clip_duration: Optional[int] = 5
    video_count: Optional[int] = 1

    video_source: Optional[str] = "pexels"
    video_materials: Optional[List[MaterialInfo]] = (
        None  # Materials used to generate the video
    )
    
    custom_audio_file: Optional[str] = None  # Custom audio file path, will ignore video_script and disable subtitle
    video_language: Optional[str] = ""  # auto detect

    voice_name: Optional[str] = ""
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.0
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2

    subtitle_enabled: Optional[bool] = True
    subtitle_position: Optional[str] = config.ui.get("subtitle_position", "bottom")  # top, bottom, center, custom
    custom_position: float = config.ui.get("custom_position", 70.0)
    font_name: Optional[str] = "STHeitiMedium.ttc"
    text_fore_color: Optional[str] = "#FFFFFF"
    text_background_color: Union[bool, str] = True

    font_size: int = 60
    stroke_color: Optional[str] = "#000000"
    stroke_width: float = 1.5
    n_threads: Optional[int] = 2
    paragraph_number: Optional[int] = 1

    # Spec 014: tenant context. Required at runtime when
    # LAYER3_REQUIRE_TENANT_CONTEXT=true (production default after Step 2).
    # JWT middleware injects these from claims into the request body before
    # Pydantic parsing so production controllers always see them populated.
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None

    # Spec 006: visuals source mode. None preserves legacy behavior (Pexels-only
    # auto path — every existing render). "auto" is an explicit flavor of legacy.
    # "user_uploaded" routes through material.download_videos's new branch that
    # converts uploaded image paths into Ken Burns clips.
    # "hybrid" (Clarifications 2026-05-03) interleaves user uploads with
    # Pexels + Pixabay setting footage; see FR-022..FR-025.
    visuals_mode: Optional[Literal["auto", "user_uploaded", "hybrid"]] = None

    # Spec 006: filesystem path to the user's uploaded model image. Optional
    # even when visuals_mode == "user_uploaded" (model is optional per FR-003).
    # Path MUST resolve under storage/uploads/.
    uploaded_model_path: Optional[str] = None

    # Spec 006: ordered list of paths to user's uploaded product images.
    # 1–3 entries required when visuals_mode == "user_uploaded".
    uploaded_product_paths: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_visuals(self) -> "VideoParams":
        # Both user_uploaded and hybrid modes require uploads + path checks.
        # Auto + None skip validation entirely.
        if self.visuals_mode not in ("user_uploaded", "hybrid"):
            return self
        if not self.uploaded_product_paths:
            raise ValueError("no_product_assets")
        if len(self.uploaded_product_paths) > 3:
            raise ValueError("too_many_product_assets")
        for p in self.uploaded_product_paths:
            _require_under_uploads(p)
        if self.uploaded_model_path:
            _require_under_uploads(self.uploaded_model_path)
        return self

    @model_validator(mode="after")
    def _validate_tenant_context(self) -> "VideoParams":
        """Spec 014: enforce tenant context when production-flag is set.

        Read at validate-time so tests can monkey-patch without restart.
        Defaults to false in dev so legacy callers continue to work during
        the Step 1 → Step 2 transition window.
        """
        if not _require_tenant_context():
            return self
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError("tenant_id_required")
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id_required")
        return self


def _require_tenant_context() -> bool:
    return os.environ.get("LAYER3_REQUIRE_TENANT_CONTEXT", "false").lower() in (
        "true", "1", "yes",
    )


def _require_under_uploads(path: str) -> None:
    """Reject any path that doesn't resolve under storage/uploads/.

    Step 1 single-user means a basic path-traversal guard; Step 2 will scope
    further to ``storage/uploads/<tenant_id>/`` via the same helper.
    """
    uploads_dir = os.path.realpath(os.path.join(os.getcwd(), "storage", "uploads"))
    real = os.path.realpath(path) if os.path.isabs(path) else os.path.realpath(
        os.path.join(os.getcwd(), path)
    )
    if not real.startswith(uploads_dir + os.sep) and real != uploads_dir:
        raise ValueError("path_outside_uploads")


class SubtitleRequest(BaseModel):
    video_script: str
    video_language: Optional[str] = ""
    voice_name: Optional[str] = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.2
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2
    subtitle_position: Optional[str] = config.ui.get("subtitle_position", "bottom")
    font_name: Optional[str] = "STHeitiMedium.ttc"
    text_fore_color: Optional[str] = "#FFFFFF"
    text_background_color: Union[bool, str] = True
    font_size: int = 60
    stroke_color: Optional[str] = "#000000"
    stroke_width: float = 1.5
    video_source: Optional[str] = "local"
    subtitle_enabled: Optional[str] = "true"


class AudioRequest(BaseModel):
    video_script: str
    video_language: Optional[str] = ""
    voice_name: Optional[str] = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.2
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2
    video_source: Optional[str] = "local"


class VideoScriptParams:
    """
    {
      "video_subject": "春天的花海",
      "video_language": "",
      "paragraph_number": 1
    }
    """

    video_subject: Optional[str] = "春天的花海"
    video_language: Optional[str] = ""
    paragraph_number: Optional[int] = 1


class VideoTermsParams:
    """
    {
      "video_subject": "",
      "video_script": "",
      "amount": 5
    }
    """

    video_subject: Optional[str] = "春天的花海"
    video_script: Optional[str] = (
        "春天的花海，如诗如画般展现在眼前。万物复苏的季节里，大地披上了一袭绚丽多彩的盛装。金黄的迎春、粉嫩的樱花、洁白的梨花、艳丽的郁金香……"
    )
    amount: Optional[int] = 5


class BaseResponse(BaseModel):
    status: int = 200
    message: Optional[str] = "success"
    data: Any = None


class TaskVideoRequest(VideoParams, BaseModel):
    pass


class TaskQueryRequest(BaseModel):
    pass


class VideoScriptRequest(VideoScriptParams, BaseModel):
    pass


class VideoTermsRequest(VideoTermsParams, BaseModel):
    pass


######################################################################################################
######################################################################################################
######################################################################################################
######################################################################################################
class TaskResponse(BaseResponse):
    class TaskResponseData(BaseModel):
        task_id: str

    data: TaskResponseData

    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"task_id": "6c85c8cc-a77a-42b9-bc30-947815aa0558"},
            },
        }


class TaskQueryResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "state": 1,
                    "progress": 100,
                    "videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/final-1.mp4"
                    ],
                    "combined_videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/combined-1.mp4"
                    ],
                },
            },
        }


class TaskDeletionResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "state": 1,
                    "progress": 100,
                    "videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/final-1.mp4"
                    ],
                    "combined_videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/combined-1.mp4"
                    ],
                },
            },
        }


class VideoScriptResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "video_script": "春天的花海，是大自然的一幅美丽画卷。在这个季节里，大地复苏，万物生长，花朵争相绽放，形成了一片五彩斑斓的花海..."
                },
            },
        }


class VideoTermsResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"video_terms": ["sky", "tree"]},
            },
        }


class BgmRetrieveResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "files": [
                        {
                            "name": "output013.mp3",
                            "size": 1891269,
                            "file": "/MoneyPrinterTurbo/resource/songs/output013.mp3",
                        }
                    ]
                },
            },
        }


class BgmUploadResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"file": "/MoneyPrinterTurbo/resource/songs/example.mp3"},
            },
        }

class VideoMaterialRetrieveResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "files": [
                        {
                            "name": "example.mp4",
                            "size": 12345678,
                            "file": "/MoneyPrinterTurbo/resource/videos/example.mp4",
                        }
                    ]
                },
            },
        }

class VideoMaterialUploadResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "file": "/MoneyPrinterTurbo/resource/videos/example.mp4",
                },
            },
        }
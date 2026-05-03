import hashlib
import json
import os
import random
import tempfile
import threading
from os import path
from typing import List, Optional
from urllib.parse import urlencode

import requests
from loguru import logger
from moviepy.video.io.VideoFileClip import VideoFileClip

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect, VideoConcatMode
from app.utils import utils

# Thread-safe counter for API key rotation
_api_key_counter = 0
_api_key_lock = threading.Lock()


def get_api_key(cfg_key: str):
    api_keys = config.app.get(cfg_key)
    if not api_keys:
        raise ValueError(
            f"\n\n##### {cfg_key} is not set #####\n\nPlease set it in the config.toml file: {config.config_file}\n\n"
            f"{utils.to_json(config.app)}"
        )

    # if only one key is provided, return it
    if isinstance(api_keys, str):
        return api_keys

    global _api_key_counter
    with _api_key_lock:
        _api_key_counter += 1
        return api_keys[_api_key_counter % len(api_keys)]


def search_videos_pexels(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)
    video_orientation = aspect.name
    video_width, video_height = aspect.to_resolution()
    api_key = get_api_key("pexels_api_keys")
    headers = {
        "Authorization": api_key,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    }
    # Build URL
    params = {"query": search_term, "per_page": 20, "orientation": video_orientation}
    query_url = f"https://api.pexels.com/videos/search?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url,
            headers=headers,
            proxies=config.proxy,
            verify=False,
            timeout=(30, 60),
        )
        response = r.json()
        video_items = []
        if "videos" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["videos"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["video_files"]
            # loop through each url to determine the best quality
            for video in video_files:
                w = int(video["width"])
                h = int(video["height"])
                if w == video_width and h == video_height:
                    item = MaterialInfo()
                    item.provider = "pexels"
                    item.url = video["link"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def search_videos_pixabay(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    aspect = VideoAspect(video_aspect)

    video_width, video_height = aspect.to_resolution()

    api_key = get_api_key("pixabay_api_keys")
    # Build URL
    params = {
        "q": search_term,
        "video_type": "all",  # Accepted values: "all", "film", "animation"
        "per_page": 50,
        "key": api_key,
    }
    query_url = f"https://pixabay.com/api/videos/?{urlencode(params)}"
    logger.info(f"searching videos: {query_url}, with proxies: {config.proxy}")

    try:
        r = requests.get(
            query_url, proxies=config.proxy, verify=False, timeout=(30, 60)
        )
        response = r.json()
        video_items = []
        if "hits" not in response:
            logger.error(f"search videos failed: {response}")
            return video_items
        videos = response["hits"]
        # loop through each video in the result
        for v in videos:
            duration = v["duration"]
            # check if video has desired minimum duration
            if duration < minimum_duration:
                continue
            video_files = v["videos"]
            # loop through each url to determine the best quality
            for video_type in video_files:
                video = video_files[video_type]
                w = int(video["width"])
                # h = int(video["height"])
                if w >= video_width:
                    item = MaterialInfo()
                    item.provider = "pixabay"
                    item.url = video["url"]
                    item.duration = duration
                    video_items.append(item)
                    break
        return video_items
    except Exception as e:
        logger.error(f"search videos failed: {str(e)}")

    return []


def save_video(video_url: str, save_dir: str = "") -> str:
    if not save_dir:
        save_dir = utils.storage_dir("cache_videos")

    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    url_without_query = video_url.split("?")[0]
    url_hash = utils.md5(url_without_query)
    video_id = f"vid-{url_hash}"
    video_path = f"{save_dir}/{video_id}.mp4"

    # if video already exists, return the path
    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        logger.info(f"video already exists: {video_path}")
        return video_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    # if video does not exist, download it
    with open(video_path, "wb") as f:
        f.write(
            requests.get(
                video_url,
                headers=headers,
                proxies=config.proxy,
                verify=False,
                timeout=(60, 240),
            ).content
        )

    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        clip = None
        try:
            clip = VideoFileClip(video_path)
            duration = clip.duration
            fps = clip.fps
            if duration > 0 and fps > 0:
                return video_path
        except Exception as e:
            logger.warning(f"invalid video file: {video_path} => {str(e)}")
            try:
                os.remove(video_path)
            except Exception:
                pass
        finally:
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass
    return ""


def download_videos(
    task_id: str,
    search_terms: List[str],
    source: str = "pexels",
    video_aspect: VideoAspect = VideoAspect.portrait,
    video_contact_mode: VideoConcatMode = VideoConcatMode.random,
    audio_duration: float = 0.0,
    max_clip_duration: int = 5,
) -> List[str]:
    # ============================================================================
    # USER POLICY (set by Amr 2026-05-03, refined to MIXED — see chat log):
    #
    #   1. Pexels is EXCLUDED. Pexels' relevance ranking returned random clips
    #      (American flags, snowflakes, hand-on-keyboard) for niche tech queries
    #      like "AI bounding boxes overlay". Never call search_videos_pexels
    #      from the auto path.
    #   2. URL detected in topic → MIXED Pixabay video + NanoBanana stills,
    #      interleaved (P-N-P-N-...). This gives the video real motion from
    #      Pixabay clips AND on-prompt AI hero shots from NanoBanana, without
    #      going all-AI. URLs signal product-specific intent so we want some
    #      AI-generated imagery in the mix; but real motion is essential to
    #      avoid the "slideshow" feel.
    #   3. No URL → Pixabay only. Real-motion stock B-roll for general topics
    #      like "Mediterranean diet" / "productivity tips" where Pixabay's
    #      inventory is solid.
    #
    # To change this policy: edit the dispatch block immediately after this
    # comment. The Pexels code path (search_videos_pexels) is intentionally
    # left in the file so it can be re-enabled by changing the dispatcher,
    # but should NOT be called from the auto path.
    # ============================================================================
    # Spec 006: short-circuit on a visuals.json sidecar written by the video
    # controller before render dispatch. When present + visuals_mode is
    # "user_uploaded", we replace the Pexels fetch entirely with Ken Burns
    # clips built from user-uploaded images. The sidecar pattern preserves
    # task.py's existing call signature (debt #5 line count unchanged).
    sidecar = _read_visuals_sidecar(task_id)

    # Spec 015 / Step 3 (FR-022): Layer 2 may pre-mint pre-signed URLs into
    # the sidecar instead of letting Layer 3 call Pexels/Pixabay directly.
    # When pre_signed_clip_urls is non-null + non-empty, fetch from those
    # URLs. (Layer 2's URL-population path lands in Step 3.5; today the field
    # is null for Mode 2 + Mode 5, which fall through to existing logic.)
    if sidecar:
        pre_signed = sidecar.get("pre_signed_clip_urls")
        if pre_signed:
            return _download_from_pre_signed_urls(task_id, pre_signed)

    if sidecar and sidecar.get("visuals_mode") == "user_uploaded":
        return _build_clips_from_uploads(
            task_id=task_id,
            model_path=sidecar.get("uploaded_model_path"),
            product_paths=sidecar.get("uploaded_product_paths") or [],
            audio_duration=audio_duration,
            video_aspect=video_aspect,
        )
    if sidecar and sidecar.get("visuals_mode") == "hybrid":
        return _build_clips_hybrid(
            task_id=task_id,
            model_path=sidecar.get("uploaded_model_path"),
            product_paths=sidecar.get("uploaded_product_paths") or [],
            audio_duration=audio_duration,
            video_aspect=video_aspect,
            max_clip_duration=max_clip_duration,
            setting_tag=sidecar.get("setting_tag") or "general",
            setting_queries=sidecar.get("stock_queries") or [],
        )

    # Spec 015 / Step 3 (FR-023, soft form): warn when a non-faceless mode
    # hits the direct Pexels/Pixabay call path. Mode 2 Auto + hybrid retain
    # this path as residual debt #3 awaiting Step 3.5; Mode 5 is the
    # constitution Principle IV permitted exception. Step 3.5 flips the
    # warning to a hard RuntimeError once Layer 2 owns the stock-fetch flow.
    sidecar_mode = (sidecar or {}).get("mode") if sidecar else None
    if sidecar_mode and sidecar_mode != "faceless":
        logger.warning(
            f"material.principle_iv_soft_warning: mode={sidecar_mode!r} hitting "
            "direct Pexels/Pixabay path. Constitution Principle IV will require "
            "this to route through Layer 2 pre-signed URLs in Step 3.5."
        )

    # === USER-POLICY DISPATCH (see comment block at top of download_videos) ===
    # Branch A: subject contains a URL → MIXED Pixabay video + NanoBanana stills
    #           (interleaved P-N-P-N for real motion + on-prompt hero shots)
    # Branch B: no URL → Pixabay only (Pexels excluded — see policy comment)
    #
    # We detect URLs from `script.json#params.video_subject` (written by
    # save_script_data() before this function runs) since the LLM-derived
    # search_terms list usually strips the URL out.
    subject_for_url_check = _read_video_subject_from_script_json(task_id)
    haystack_for_url = (subject_for_url_check + " " + " ".join(search_terms)).lower()
    has_url = ("http://" in haystack_for_url) or ("https://" in haystack_for_url)

    from app.services import nanobanana as _nanobanana
    if has_url and _nanobanana.is_enabled():
        logger.info(
            "material: URL detected in topic; routing to MIXED Pixabay+NanoBanana "
            "(real-motion stock interleaved with on-prompt AI hero shots)."
        )
        mixed_paths = _mix_pixabay_and_nanobanana(
            task_id=task_id,
            search_terms=search_terms,
            audio_duration=audio_duration,
            max_clip_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        if mixed_paths:
            _write_asset_audit(task_id, {
                "visuals_mode": "auto",
                "auto_pexels_used": False,
                "mixed_clip_count": len(mixed_paths),
                "dispatch_reason": "url_detected_mixed",
                "model_asset": None,
                "product_assets": [],
            })
            return mixed_paths
        logger.warning("mixed Pixabay+NanoBanana returned 0 clips; falling through to Pixabay-only")

    valid_video_items = []
    valid_video_urls = []
    found_duration = 0.0

    # === USER POLICY: Pixabay only — see comment block at top ===
    # Pexels is excluded by user request (its relevance ranking returned
    # random clips for niche tech queries). To re-enable Pexels: replace
    # `search_videos_pixabay` below with `_search_stock_dual_source(...)`
    # OR with `search_videos_pexels` per term.
    for search_term in search_terms:
        video_items = search_videos_pixabay(
            search_term=search_term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        logger.info(f"found {len(video_items)} videos for '{search_term}' (pixabay-only)")
        for item in video_items:
            if item.url not in valid_video_urls:
                valid_video_items.append(item)
                valid_video_urls.append(item.url)
                found_duration += item.duration

    logger.info(
        f"found total videos: {len(valid_video_items)}, required duration: {audio_duration} seconds, found duration: {found_duration} seconds"
    )
    video_paths = []

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    if video_contact_mode.value == VideoConcatMode.random.value:
        random.shuffle(valid_video_items)

    total_duration = 0.0
    for item in valid_video_items:
        try:
            logger.info(f"downloading video: {item.url}")
            saved_video_path = save_video(
                video_url=item.url, save_dir=material_directory
            )
            if saved_video_path:
                logger.info(f"video saved: {saved_video_path}")
                video_paths.append(saved_video_path)
                seconds = min(max_clip_duration, item.duration)
                total_duration += seconds
                if total_duration > audio_duration:
                    logger.info(
                        f"total duration of downloaded videos: {total_duration} seconds, skip downloading more"
                    )
                    break
        except Exception as e:
            logger.error(f"failed to download video: {utils.to_json(item)} => {str(e)}")
    logger.success(f"downloaded {len(video_paths)} videos")

    # Spec 015 — supplement with AI-generated hero images for tech/AI topics
    # where stock video inventory is thin. Order: NanoBanana (best fit, cheap
    # at $0.04/img, can render the niche AI/CCTV imagery stock libraries lack)
    # → Shutterstock (skipped on free tier — license endpoint requires upgrade).
    # Both helpers gracefully no-op when their provider isn't configured.
    if total_duration < audio_duration:
        nb_paths = _supplement_with_nanobanana_images(
            task_id=task_id,
            search_terms=search_terms,
            duration_needed=audio_duration - total_duration,
            max_clip_duration=max_clip_duration,
        )
        video_paths.extend(nb_paths)
        # Re-tally before falling through to Shutterstock
        total_duration += len(nb_paths) * float(max_clip_duration)

    if total_duration < audio_duration:
        shutterstock_paths = _supplement_with_shutterstock_images(
            task_id=task_id,
            search_terms=search_terms,
            video_aspect=video_aspect,
            duration_needed=audio_duration - total_duration,
            max_clip_duration=max_clip_duration,
        )
        video_paths.extend(shutterstock_paths)

    # Spec 006 FR-021: every render writes an audit log regardless of mode.
    _write_asset_audit(task_id, {
        "visuals_mode": "auto",
        "auto_pexels_used": True,
        "pexels_clip_count": len(video_paths),
        "model_asset": None,
        "product_assets": [],
    })
    return video_paths


# ---------------------------------------------------------------------------
# Spec 006 — user-uploaded visuals branch
# ---------------------------------------------------------------------------


_KENBURNS_FPS = 30
_KENBURNS_MIN_DURATION = 2.0  # FR-014 / FR-016 floor


def _read_video_subject_from_script_json(task_id: str) -> str:
    """Read params.video_subject from the per-task script.json.

    Used by the URL-detection dispatch in download_videos. Returns "" on
    any failure (file missing, parse error, key missing) so the dispatch
    falls through to Branch B (Pixabay-only) gracefully.
    """
    script_json_path = path.join(utils.task_dir(task_id), "script.json")
    if not os.path.exists(script_json_path):
        return ""
    try:
        with open(script_json_path, encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("params", {}).get("video_subject") or "")
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        logger.warning(f"could not read video_subject from script.json: {exc}")
        return ""


def _mix_pixabay_and_nanobanana(
    *,
    task_id: str,
    search_terms: List[str],
    audio_duration: float,
    max_clip_duration: int,
    video_aspect: VideoAspect,
) -> List[str]:
    """Spec 015 — MIXED dispatch for URL-detected topics: combine real-motion
    Pixabay stock clips with on-prompt NanoBanana hero stills (Ken-Burns'd),
    interleaved as P-N-P-N-... so the playback alternates between real
    footage and AI-generated product-specific shots.

    Sizing:
      n_total = ceil(audio_duration / max_clip_duration), capped at 12
      target  = ~50% Pixabay + ~50% NanoBanana (rounded toward Pixabay
                because real-motion clips are higher value per slot)

    Cost: NanoBanana half × $0.04 ≈ $0.20-0.24 per video. Pixabay free.

    Falls back gracefully:
      - If Pixabay returns < target_pixabay clips, fill remaining slots
        with NanoBanana so n_total is still met.
      - If NanoBanana fails (FAL down etc), pad with extra Pixabay clips.
      - Returns whatever was successfully fetched/generated; never empty
        unless both providers fail.
    """
    from app.services import nanobanana

    clip_duration = float(max_clip_duration)
    n_total = max(4, int(round(audio_duration / clip_duration)))
    n_total = min(n_total, 12)
    target_pixabay = (n_total + 1) // 2  # ceil half — favour real motion
    target_nanobanana = n_total - target_pixabay
    logger.info(
        f"mix: targeting {n_total} clips ({target_pixabay} pixabay + "
        f"{target_nanobanana} nanobanana, ~${target_nanobanana * 0.04:.2f} AI cost)"
    )

    # --- Pixabay fetch (round-robin across terms, dedupe by URL) ---
    pixabay_items: list = []
    seen_urls: set = set()
    for term in search_terms:
        if len(pixabay_items) >= target_pixabay * 2:  # over-fetch for choice
            break
        items = search_videos_pixabay(
            search_term=term,
            minimum_duration=max_clip_duration,
            video_aspect=video_aspect,
        )
        for it in items:
            if it.url and it.url not in seen_urls:
                seen_urls.add(it.url)
                pixabay_items.append(it)
                if len(pixabay_items) >= target_pixabay * 2:
                    break
    logger.info(f"mix: pixabay over-fetched {len(pixabay_items)} (target {target_pixabay})")

    # Download top target_pixabay
    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    pixabay_paths: List[str] = []
    for it in pixabay_items:
        if len(pixabay_paths) >= target_pixabay:
            break
        try:
            saved = save_video(video_url=it.url, save_dir=material_directory)
            if saved:
                pixabay_paths.append(saved)
        except Exception as exc:
            logger.warning(f"pixabay download failed for {it.url[:60]}: {exc}")
    logger.info(f"mix: pixabay downloaded {len(pixabay_paths)}/{target_pixabay}")

    # If pixabay short, top up nanobanana target
    pixabay_short = target_pixabay - len(pixabay_paths)
    if pixabay_short > 0:
        target_nanobanana += pixabay_short
        target_nanobanana = min(target_nanobanana, 12)  # respect overall cost cap
        logger.info(f"mix: pixabay short by {pixabay_short}; bumping nanobanana to {target_nanobanana}")

    # --- NanoBanana generation (round-robin across terms) ---
    nb_dir = path.join(utils.task_dir(task_id), "nanobanana")
    os.makedirs(nb_dir, exist_ok=True)
    nb_paths: List[str] = []
    base_aesthetic = (
        "Photorealistic, professional product photography, vertical 9:16 "
        "composition, cinematic lighting, sharp focus, high detail. Subject: "
    )
    for i in range(target_nanobanana):
        term = search_terms[i % len(search_terms)] if search_terms else "modern technology"
        prompt = base_aesthetic + term
        logger.info(f"mix.nanobanana[{i + 1}/{target_nanobanana}]: {term!r}")
        url = nanobanana.generate_image(prompt)
        if not url:
            continue
        jpg_path = path.join(nb_dir, f"img-{i + 1}.jpg")
        if not nanobanana.download_image(url, jpg_path):
            continue
        clip_path = path.join(nb_dir, f"clip-{i + 1}.mp4")
        try:
            _make_kenburns_clip(jpg_path, clip_duration, clip_path, _compute_seed(jpg_path))
            nb_paths.append(clip_path)
        except Exception as exc:
            logger.warning(f"ken-burns failed for nanobanana mix image {i + 1}: {exc}")

    # --- Interleave P-N-P-N-... ---
    interleaved: List[str] = []
    p_iter = iter(pixabay_paths)
    n_iter = iter(nb_paths)
    p_done = n_done = False
    while not (p_done and n_done):
        try:
            interleaved.append(next(p_iter))
        except StopIteration:
            p_done = True
        try:
            interleaved.append(next(n_iter))
        except StopIteration:
            n_done = True

    logger.success(
        f"mix produced {len(interleaved)} clips: "
        f"{len(pixabay_paths)} pixabay + {len(nb_paths)} nanobanana "
        f"(${len(nb_paths) * 0.04:.2f} AI cost)"
    )
    return interleaved


def _generate_full_video_via_nanobanana(
    *,
    task_id: str,
    search_terms: List[str],
    audio_duration: float,
    max_clip_duration: int,
) -> List[str]:
    """Spec 015 — generate the ENTIRE Mode 5 video as Ken-Burns'd NanoBanana
    images. Used for tech/AI topics where stock-search relevance is broken.

    Cost: ceil(audio_duration / max_clip_duration) images × $0.04. A typical
    60s video at 5s/clip = 12 images = $0.48.

    Round-robins through the user's search_terms so each gets equal screen
    time. Falls back to whatever clips it could generate; the caller checks
    for an empty list and falls through to stock when generation fails.
    """
    from app.services import nanobanana

    clip_duration = float(max_clip_duration)
    n_needed = max(3, int(round(audio_duration / clip_duration)))
    n_needed = min(n_needed, 12)  # cap per-video spend at 12 imgs (~$0.48)

    out_dir = path.join(utils.task_dir(task_id), "nanobanana")
    os.makedirs(out_dir, exist_ok=True)
    out_paths: List[str] = []

    base_aesthetic = (
        "Photorealistic, professional product photography, vertical 9:16 "
        "composition, cinematic lighting, sharp focus, high detail. Subject: "
    )
    # Round-robin: cycle through search_terms so each gets equal coverage
    for i in range(n_needed):
        term = search_terms[i % len(search_terms)] if search_terms else "modern technology"
        prompt = base_aesthetic + term
        logger.info(f"nanobanana[{i + 1}/{n_needed}]: generating for {term!r}")
        url = nanobanana.generate_image(prompt)
        if not url:
            continue
        jpg_path = path.join(out_dir, f"img-{i + 1}.jpg")
        if not nanobanana.download_image(url, jpg_path):
            continue
        clip_path = path.join(out_dir, f"clip-{i + 1}.mp4")
        try:
            _make_kenburns_clip(jpg_path, clip_duration, clip_path, _compute_seed(jpg_path))
            out_paths.append(clip_path)
        except Exception as exc:
            logger.warning(f"ken-burns failed for nanobanana image {i + 1}: {exc}")

    logger.success(
        f"nanobanana primary: produced {len(out_paths)}/{n_needed} clips "
        f"(${len(out_paths) * 0.04:.2f} estimated cost)"
    )
    return out_paths


def _supplement_with_nanobanana_images(
    *,
    task_id: str,
    search_terms: List[str],
    duration_needed: float,
    max_clip_duration: int,
) -> List[str]:
    """Spec 015 — generate AI hero images via NanoBanana, Ken-Burns them.

    Triggers when:
    - NanoBanana is configured (FAL_KEY env var set)
    - Caller still needs more video duration
    - At least one search term contains a tech/AI keyword (avoids spending
      cents on generic topics that already get rich stock-video coverage)

    Cost: ~$0.04 per image. 5-8 images per video = $0.20-0.32. Generates
    the niche AI/CCTV/dashboard imagery stock libraries lack.

    Returns local paths of Ken Burns clips. Empty list on misconfig /
    non-tech topic / generation failures.
    """
    from app.services import nanobanana

    if not nanobanana.is_enabled():
        logger.info("nanobanana supplement skipped (FAL_KEY not configured)")
        return []

    haystack = " ".join(search_terms).lower()
    tech_keywords = (
        "ai", "artificial intelligence", "machine learning", "computer vision",
        "cctv", "surveillance", "security camera", "cybersecurity",
        "data center", "server", "control room", "dashboard", "tech",
        "warehouse", "factory", "industrial", "drone",
    )
    if not any(kw in haystack for kw in tech_keywords):
        logger.info("nanobanana supplement skipped (topic not tech/AI)")
        return []

    clip_duration = float(max_clip_duration)
    n_needed = max(1, int(round(duration_needed / clip_duration)))
    n_needed = min(n_needed, 8)  # cap per-video spend at 8 imgs (~$0.32)

    out_dir = path.join(utils.task_dir(task_id), "nanobanana")
    os.makedirs(out_dir, exist_ok=True)
    out_paths: List[str] = []

    # Build prompts: use each search term as the seed for a hero image.
    # The wrapper text gives NanoBanana the right tech-photography aesthetic.
    base_aesthetic = (
        "Photorealistic, professional product photography, vertical 9:16 "
        "composition, cinematic lighting, sharp focus, high detail. Subject: "
    )
    for i, term in enumerate(search_terms[:n_needed], start=1):
        prompt = base_aesthetic + term
        logger.info(f"nanobanana[{i}/{n_needed}]: generating for {term!r}")
        url = nanobanana.generate_image(prompt)
        if not url:
            continue
        jpg_path = path.join(out_dir, f"img-{i}.jpg")
        if not nanobanana.download_image(url, jpg_path):
            continue
        clip_path = path.join(out_dir, f"clip-{i}.mp4")
        try:
            _make_kenburns_clip(jpg_path, clip_duration, clip_path, _compute_seed(jpg_path))
            out_paths.append(clip_path)
        except Exception as exc:
            logger.warning(f"ken-burns failed for nanobanana image {i}: {exc}")

    logger.success(f"nanobanana supplement produced {len(out_paths)} ken-burns clips")
    return out_paths


def _supplement_with_shutterstock_images(
    *,
    task_id: str,
    search_terms: List[str],
    video_aspect: VideoAspect,
    duration_needed: float,
    max_clip_duration: int,
) -> List[str]:
    """Spec 015 — license Shutterstock images, Ken-Burns them into clips.

    Triggers only when:
    - Shutterstock is configured (SHUTTERSTOCK_CONSUMER_KEY etc set)
    - The caller still needs more video duration
    - At least one search term contains a tech/AI keyword (avoids spending
      the 500/mo quota on generic topics that already get rich video coverage)

    Returns local paths of generated Ken Burns clips. Empty list on
    misconfig / quota exhaustion / no matches.
    """
    from app.services import shutterstock

    if not shutterstock.is_enabled():
        logger.info("shutterstock supplement skipped (not configured)")
        return []

    # Domain gate — only burn quota for topics where Shutterstock has the
    # inventory advantage. Mirrors the keyword set in llm._DOMAIN_PROXIES.
    haystack = " ".join(search_terms).lower()
    tech_keywords = (
        "ai", "artificial intelligence", "machine learning", "computer vision",
        "cctv", "surveillance", "security camera", "cybersecurity",
        "data center", "server", "control room", "dashboard", "tech",
        "warehouse", "factory", "industrial", "drone",
    )
    if not any(kw in haystack for kw in tech_keywords):
        logger.info("shutterstock supplement skipped (topic not tech/AI)")
        return []

    clip_duration = float(max_clip_duration)
    n_needed = max(1, int(round(duration_needed / clip_duration)))
    # Cap at 8 to stay polite with the free 500/mo quota.
    n_needed = min(n_needed, 8)

    out_paths: List[str] = []
    out_dir = path.join(utils.task_dir(task_id), "shutterstock")
    os.makedirs(out_dir, exist_ok=True)

    # Round-robin through search terms — each term contributes one image
    # until we've gathered n_needed. Tighter coverage than draining one
    # term then moving on.
    images_per_term: dict[str, list] = {}
    for term in search_terms:
        if len(out_paths) >= n_needed:
            break
        hits = shutterstock.search_images(query=term, per_page=3, orientation="vertical")
        images_per_term[term] = list(hits)

    fetched_ids: set[str] = set()
    round_idx = 0
    while len(out_paths) < n_needed:
        progress_this_round = False
        for term, hits in images_per_term.items():
            if len(out_paths) >= n_needed:
                break
            if round_idx >= len(hits):
                continue
            img = hits[round_idx]
            if img.id in fetched_ids:
                continue
            fetched_ids.add(img.id)

            jpg_path = path.join(out_dir, f"img-{img.id}.jpg")
            if not shutterstock.license_and_download_image(img.id, jpg_path):
                continue
            clip_path = path.join(out_dir, f"clip-{len(out_paths) + 1}.mp4")
            try:
                _make_kenburns_clip(jpg_path, clip_duration, clip_path, _compute_seed(jpg_path))
                out_paths.append(clip_path)
                progress_this_round = True
            except Exception as exc:
                logger.warning(f"ken-burns failed for shutterstock image {img.id}: {exc}")
        round_idx += 1
        if not progress_this_round:
            # Either all terms exhausted their hits or all licenses failed
            break

    logger.success(
        f"shutterstock supplement produced {len(out_paths)} ken-burns clips "
        f"(needed {n_needed}, fetched {len(fetched_ids)} images)"
    )
    return out_paths


def _download_from_pre_signed_urls(task_id: str, urls: List[str]) -> List[str]:
    """Spec 015 (FR-022): fetch each pre-signed URL into the task's clips dir.

    Plain HTTP GET — Layer 3 does NOT verify the HMAC signature; that's
    Layer 2's responsibility at the ``/_signed/`` mount. 30s per-URL timeout,
    one retry on 5xx with 2s backoff.
    """
    out_dir = path.join(utils.task_dir(task_id), "clips")
    os.makedirs(out_dir, exist_ok=True)
    out_paths: List[str] = []
    for i, url in enumerate(urls, start=1):
        ext = ".mp4"
        if "." in url.rsplit("/", 1)[-1].split("?", 1)[0]:
            ext = "." + url.rsplit(".", 1)[-1].split("?", 1)[0]
        out_path = path.join(out_dir, f"clip-{i}{ext}")
        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                with requests.get(url, stream=True, timeout=30) as r:
                    if r.status_code >= 500 and attempt == 0:
                        import time as _t
                        _t.sleep(2)
                        continue
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                out_paths.append(out_path)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 — broad catch is intentional
                last_exc = exc
                if attempt == 0:
                    import time as _t
                    _t.sleep(2)
                    continue
        if last_exc is not None:
            logger.error(f"material.fetch_failed url={url!r}: {last_exc}")
            raise RuntimeError(f"material.fetch_failed: {url}") from last_exc
    logger.success(f"downloaded {len(out_paths)} clips from pre-signed URLs")
    _write_asset_audit(task_id, {
        "visuals_mode": "auto",
        "auto_pexels_used": False,
        "pre_signed_used": True,
        "pre_signed_clip_count": len(out_paths),
        "model_asset": None,
        "product_assets": [],
    })
    return out_paths


def _read_visuals_sidecar(task_id: str) -> Optional[dict]:
    """Return the parsed visuals.json sidecar for this task, or None."""
    sidecar_path = path.join(utils.task_dir(task_id), "visuals.json")
    if not os.path.exists(sidecar_path):
        return None
    try:
        with open(sidecar_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        logger.warning(f"failed to read visuals sidecar at {sidecar_path}: {exc}")
        return None


def _compute_seed(image_path: str) -> int:
    """Deterministic 32-bit seed derived from the image path.

    Same path → same Ken Burns parameters → reproducible renders. The audit
    log records the resolved path for each asset so this is stable across
    re-renders of the same task.
    """
    digest = hashlib.sha256(image_path.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16)


def _file_sha256(file_path: str) -> str:
    """Compute SHA-256 of a file's bytes; used for audit-log content_hash."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _make_kenburns_clip(image_path: str, duration: float, output_path: str,
                        seed: int) -> None:
    """Render a still → Ken Burns mp4 with aspect-aware fitting.

    Composition (Clarifications 2026-05-03 follow-up + Q2 enhancement):

    For SCREENSHOT-shaped sources (aspect > 1.4 — typical landscape UI/dashboard):
      Layer 0 (background): cover-fit + blurred + dimmed copy of the same image.
      Layer 1 (foreground): contain-fit copy showing the FULL image, no crop.
      → Preserves UI legibility; users can read every label/sidebar.

    For PHOTO-shaped sources (aspect ≤ 1.4 — portrait, square, mild landscape;
    typical for product photos, model headshots, lifestyle stills):
      Single layer: cover-fit with saliency-aware crop centered on the
      highest-detail region (subject, face, product). No blurred background —
      photos look better filling the frame than letterboxed.
      → Subject fills the frame at composition-correct framing.

    Ken Burns zoom + pan applied on top of the foreground layer in both cases,
    seeded for idempotent renders.
    """
    # Lazy MoviePy import.
    try:
        from moviepy import ImageClip, CompositeVideoClip
    except ImportError:
        from moviepy.editor import (
            ImageClip,
            CompositeVideoClip,
        )  # type: ignore[no-redef]

    # Pillow does the static image preparation (blurred bg + fitted fg) BEFORE
    # MoviePy sees them. ImageClip from numpy is more reliable than chaining
    # MoviePy resizers for the static layers.
    try:
        import numpy as np
        from PIL import Image, ImageFilter
    except ImportError as exc:  # pragma: no cover — both are hard deps
        raise RuntimeError(f"Pillow/numpy required for Ken Burns: {exc}") from exc

    rng = random.Random(seed)
    zoom_in = rng.choice([True, False])
    zoom_pct = rng.uniform(0.04, 0.08)
    pan_dx = rng.uniform(-0.03, 0.03)
    pan_dy = rng.uniform(-0.03, 0.03)

    target_w, target_h = 1080, 1920
    target_aspect = target_w / target_h  # 0.5625 (9:16)

    src = Image.open(image_path).convert("RGB")
    sw, sh = src.size
    src_aspect = sw / sh

    # Aspect-based fit-mode decision:
    #   landscape > 1.4 (i.e. wider than 7:5) → contain-fit-with-blurred-bg
    #     (preserves UI legibility on dashboard screenshots)
    #   ≤ 1.4 (portrait, square, mild landscape — typical photos) →
    #     cover-fit with saliency-aware crop (subject fills frame)
    is_screenshot_shape = src_aspect > 1.4

    if is_screenshot_shape:
        layers, layer_meta = _kb_layers_contain_with_blur(
            src, np, ImageFilter, Image, target_w, target_h,
        )
    else:
        layers, layer_meta = _kb_layers_cover_with_saliency(
            src, np, Image, target_w, target_h,
        )

    # Compose: foreground gets the Ken Burns motion; optional bg layer fills
    # the frame in screenshot mode. layer_meta tells us fg dimensions for
    # position computation.
    fg_w, fg_h = layer_meta["fg_size"]
    fg_arr = layers["fg"]
    bg_arr = layers.get("bg")  # may be None when no bg needed

    fg_clip = ImageClip(fg_arr)
    fg_clip = fg_clip.with_duration(duration) if hasattr(fg_clip, "with_duration") \
        else fg_clip.set_duration(duration)

    def zoom_factor(t: float) -> float:
        progress = t / duration if duration > 0 else 0
        if zoom_in:
            return 1.0 + zoom_pct * progress
        return (1.0 + zoom_pct) - zoom_pct * progress

    resized = getattr(fg_clip, "resized", None) or getattr(fg_clip, "resize")
    moving_fg = resized(zoom_factor)

    def fg_position(t: float):
        progress = t / duration if duration > 0 else 0
        dx = int(target_w * pan_dx * progress)
        dy = int(target_h * pan_dy * progress)
        if dx == 0 and dy == 0:
            return ("center", "center")
        cx = (target_w - fg_w) // 2 + dx
        cy = (target_h - fg_h) // 2 + dy
        return (cx, cy)

    set_pos_fg = getattr(moving_fg, "with_position", None) or getattr(moving_fg, "set_position")
    moving_fg = set_pos_fg(fg_position)

    layers_to_composite = []
    bg_clip = None
    if bg_arr is not None:
        bg_clip = ImageClip(bg_arr)
        bg_clip = bg_clip.with_duration(duration) if hasattr(bg_clip, "with_duration") \
            else bg_clip.set_duration(duration)
        set_pos_bg = getattr(bg_clip, "with_position", None) or getattr(bg_clip, "set_position")
        bg_clip = set_pos_bg((0, 0))
        layers_to_composite.append(bg_clip)
    layers_to_composite.append(moving_fg)

    composite = CompositeVideoClip(layers_to_composite, size=(target_w, target_h))
    composite = composite.with_duration(duration) if hasattr(composite, "with_duration") \
        else composite.set_duration(duration)

    composite.write_videofile(
        output_path,
        codec="libx264",
        fps=_KENBURNS_FPS,
        preset="medium",
        audio=False,
        logger=None,
    )
    try:
        composite.close()
        moving_fg.close()
        fg_clip.close()
        if bg_clip is not None:
            bg_clip.close()
    except Exception:
        pass


def _kb_layers_contain_with_blur(src, np, ImageFilter, Image, target_w, target_h):
    """Build {"fg", "bg"} layer arrays for a screenshot-shaped source.

    fg = full image scaled to fit inside target (preserves aspect, no crop).
    bg = same image cover-fit + Gaussian-blurred + dimmed.
    """
    sw, sh = src.size
    # Cover-fit blurred background
    cover_scale = max(target_w / sw, target_h / sh)
    cover_w = max(target_w, int(round(sw * cover_scale)))
    cover_h = max(target_h, int(round(sh * cover_scale)))
    bg = src.resize((cover_w, cover_h), Image.LANCZOS)
    bg_left = (cover_w - target_w) // 2
    bg_top = (cover_h - target_h) // 2
    bg = bg.crop((bg_left, bg_top, bg_left + target_w, bg_top + target_h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=24))
    bg_arr = np.array(bg).astype("int16")
    bg_arr = (bg_arr * 0.45).clip(0, 255).astype("uint8")

    # Contain-fit foreground
    contain_scale = min(target_w / sw, target_h / sh)
    fg_w = max(1, int(round(sw * contain_scale)))
    fg_h = max(1, int(round(sh * contain_scale)))
    fg = src.resize((fg_w, fg_h), Image.LANCZOS)
    fg_arr = np.array(fg)

    return {"fg": fg_arr, "bg": bg_arr}, {"fg_size": (fg_w, fg_h), "fit_mode": "contain_blur"}


def _kb_layers_cover_with_saliency(src, np, Image, target_w, target_h):
    """Build {"fg"} layer for a photo-shaped source: cover-fit at the
    saliency-detected focal region.

    Returns a single foreground layer that's exactly target_w × target_h
    (frame-filling). No background layer needed.
    """
    sw, sh = src.size

    # Cover-fit scale (so the shorter axis fully covers the target axis)
    cover_scale = max(target_w / sw, target_h / sh)
    cover_w = max(target_w, int(round(sw * cover_scale)))
    cover_h = max(target_h, int(round(sh * cover_scale)))
    cover = src.resize((cover_w, cover_h), Image.LANCZOS)

    # Saliency: where in the source image does the eye go?
    # Heuristic: find the region of highest edge-density in the original image,
    # then translate that to the cover-fit-resized coordinate space.
    sx_norm, sy_norm = _detect_saliency_center(src, np, Image)
    # Saliency center in cover-fit pixel space:
    cx = int(sx_norm * cover_w)
    cy = int(sy_norm * cover_h)

    # Crop a target_w × target_h box centered on (cx, cy), clamped to image bounds.
    half_w, half_h = target_w // 2, target_h // 2
    left = max(0, min(cover_w - target_w, cx - half_w))
    top = max(0, min(cover_h - target_h, cy - half_h))
    crop = cover.crop((left, top, left + target_w, top + target_h))

    fg_arr = np.array(crop)
    return {"fg": fg_arr}, {"fg_size": (target_w, target_h), "fit_mode": "cover_saliency"}


def _detect_saliency_center(src, np, Image):
    """Return (x_norm, y_norm) in [0, 1]^2 for the focal point of the image.

    NumPy + Pillow heuristic — no OpenCV dependency. The salient region is
    approximated by the 1/8-resolution gradient-magnitude tile with the
    highest energy, smoothed by a box-mean over a 3×3 neighborhood. Robust
    enough for product photos / portraits where the subject typically has
    high local contrast against a softer background.
    """
    # Downsample to a small grid for speed (saliency is a coarse signal).
    small = src.convert("L").resize((128, 128), Image.LANCZOS)
    arr = np.array(small).astype("float32")

    # Sobel-like gradient magnitude
    gx = np.zeros_like(arr)
    gy = np.zeros_like(arr)
    gx[:, 1:-1] = arr[:, 2:] - arr[:, :-2]
    gy[1:-1, :] = arr[2:, :] - arr[:-2, :]
    grad = np.sqrt(gx * gx + gy * gy)

    # Box-mean smoothing via summed-area-table-like trick (simple convolution
    # with a uniform kernel). 8×8 boxes give a 16×16 grid of regions.
    box = 8
    h, w = grad.shape
    nh, nw = h // box, w // box
    if nh == 0 or nw == 0:
        return 0.5, 0.5
    # Reshape into (nh, box, nw, box) and mean over the box dimensions
    reshaped = grad[: nh * box, : nw * box].reshape(nh, box, nw, box).mean(axis=(1, 3))

    # Argmax → highest-energy region's grid coordinates
    flat_idx = int(np.argmax(reshaped))
    iy, ix = flat_idx // nw, flat_idx % nw

    # Translate region center to normalized [0, 1] image coordinates
    x_norm = (ix + 0.5) / nw
    y_norm = (iy + 0.5) / nh
    return float(x_norm), float(y_norm)


def _build_clips_from_uploads(
    task_id: str,
    model_path: Optional[str],
    product_paths: List[str],
    audio_duration: float,
    video_aspect: VideoAspect,
) -> List[str]:
    """Convert uploaded stills → ordered Ken Burns mp4 clip paths.

    Order:
      [model_clip?, product_clip_1, ..., product_clip_N, model_clip?]
                  -- bookended ONLY when model_path is non-null --

    Each clip duration = max(2.0, audio_duration / n_clips). Per-clip
    duration is bound by FR-014 (≥ 2 s per image) and FR-016 (no flicker-
    fast cuts). When the floor (2 s × n_clips) exceeds audio_duration, the
    final video runs slightly longer than the voiceover — combine_videos
    handles trimming downstream.

    Side-effect: writes asset_audit to script.json for SC-001 verifiability.
    """
    if not product_paths:
        raise ValueError("no_product_assets")

    has_model = bool(model_path)
    n_clips = len(product_paths) + (2 if has_model else 0)
    per_clip_duration = max(_KENBURNS_MIN_DURATION, audio_duration / n_clips)

    task_dir = utils.task_dir(task_id, create=True) if "create" in \
        utils.task_dir.__code__.co_varnames else utils.task_dir(task_id)
    if not os.path.isdir(task_dir):
        os.makedirs(task_dir, exist_ok=True)

    clip_paths: List[str] = []
    audit_model: Optional[dict] = None
    audit_products: List[dict] = []

    # 1. Optional opening model clip.
    if has_model:
        model_clip = _render_one(
            task_id, task_dir, model_path, per_clip_duration, idx=0
        )
        clip_paths.append(model_clip)
        audit_model = _audit_entry(
            asset_path=model_path,
            kenburns_clip_path=model_clip,
            screen_time_seconds=per_clip_duration * 2,  # opening + closing
            placement="opening+closing",
        )

    # 2. Product clips in upload order.
    for idx, product_path in enumerate(product_paths, start=1):
        clip = _render_one(task_id, task_dir, product_path, per_clip_duration, idx=idx)
        clip_paths.append(clip)
        audit_products.append(_audit_entry(
            asset_path=product_path,
            kenburns_clip_path=clip,
            screen_time_seconds=per_clip_duration,
            placement=f"middle-{idx}",
        ))

    # 3. Optional closing model clip — reuses the same generated mp4.
    if has_model:
        clip_paths.append(clip_paths[0])

    _write_asset_audit(task_id, {
        "visuals_mode": "user_uploaded",
        "auto_pexels_used": False,
        "pexels_clip_count": 0,
        "model_asset": audit_model,
        "product_assets": audit_products,
    })

    logger.success(
        f"built {len(clip_paths)} Ken Burns clips for task {task_id} "
        f"(model={'yes' if has_model else 'no'}, products={len(product_paths)})"
    )
    return clip_paths


def _render_one(task_id: str, task_dir: str, image_path: str,
                duration: float, idx: int) -> str:
    """Render a single Ken Burns clip; return its absolute output path."""
    output_path = path.join(task_dir, f"uploaded-{idx}.mp4")
    seed = _compute_seed(image_path)
    _make_kenburns_clip(image_path, duration, output_path, seed)
    return output_path


def _audit_entry(asset_path: str, kenburns_clip_path: str,
                 screen_time_seconds: float, placement: str) -> dict:
    """Build one product/model audit entry from an asset path."""
    filename = os.path.basename(asset_path)
    # uuid is the part before the first dot (handles both `<uuid>.jpg` and
    # `<uuid>.cropped.jpg`).
    uid = filename.split(".")[0] if "." in filename else filename
    content_hash = _file_sha256(asset_path) if os.path.exists(asset_path) else ""
    return {
        "uuid": uid,
        "filename": filename,
        "content_hash": content_hash,
        "stored_path": asset_path,
        "cropped_path": asset_path,  # input IS the cropped derivative
        "kenburns_clip_path": kenburns_clip_path,
        "moderation_status": "passed_local_heuristic",
        "screen_time_seconds": screen_time_seconds,
        "placement": placement,
    }


def _write_asset_audit(task_id: str, audit: dict) -> None:
    """Atomically merge the asset_audit block into storage/tasks/<task>/script.json.

    Atomic update via tempfile + os.replace so a crash mid-write doesn't
    corrupt the file.
    """
    script_json_path = path.join(utils.task_dir(task_id), "script.json")
    if not os.path.exists(script_json_path):
        # Defensive: caller should always have written script.json first;
        # fall through silently rather than break a render that's almost done.
        logger.warning(f"script.json missing at {script_json_path}; "
                       f"skipping audit write")
        return
    try:
        with open(script_json_path, encoding="utf-8") as f:
            existing = json.load(f)
    except (OSError, ValueError) as exc:
        logger.error(f"failed to read script.json for audit merge: {exc}")
        return

    existing["asset_audit"] = audit
    serialized = json.dumps(existing, indent=2)
    target_dir = path.dirname(script_json_path)
    fd, tmp_path = tempfile.mkstemp(prefix="script.json.", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(tmp_path, script_json_path)
    except OSError as exc:
        logger.error(f"failed to atomically write audit log: {exc}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Spec 006 hybrid mode (Clarifications 2026-05-03)
# ---------------------------------------------------------------------------


def _search_stock_dual_source(
    query: str,
    video_aspect: VideoAspect,
    max_clip_duration: int,
):
    """Query Pixabay + Pexels in parallel; return deduped MaterialInfo list.

    **Pixabay first** — Pixabay's free-tier inventory is denser for business
    / industrial / professional B-roll than Pexels'. Pexels fills in gaps
    where Pixabay returns nothing for a given term. Dedupe by URL prevents
    the same clip from appearing twice when both providers host it.
    """
    seen_urls = set()
    results = []
    for search_fn in (search_videos_pixabay, search_videos_pexels):
        try:
            items = search_fn(
                search_term=query,
                minimum_duration=max_clip_duration,
                video_aspect=video_aspect,
            )
        except Exception as exc:
            logger.warning(f"{search_fn.__name__} raised for '{query}': {exc}")
            items = []
        for item in items or []:
            if item.url and item.url not in seen_urls:
                seen_urls.add(item.url)
                results.append(item)
    return results


def _fetch_stock_for_queries(
    task_id: str,
    queries: list,
    n_needed: int,
    video_aspect: VideoAspect,
    max_clip_duration: int,
):
    """Fetch up to n_needed stock clips with maximum scene diversity.

    Round-robin strategy:
      - Pre-fetch search results for ALL queries (one network call per query).
      - Pass 0: take 1st clip from each query in turn (so 5 queries → 5 different scenes).
      - Pass 1: if still short, take 2nd clip from each query.
      - Etc.

    This replaces the prior "fill until full from query 1" behavior that
    returned 5 clips of the same scene from the first query's results.

    Returns list of {"path", "provider", "query", "url"} dicts.
    """
    out: list = []
    seen_urls: set = set()

    material_directory = config.app.get("material_directory", "").strip()
    if material_directory == "task":
        material_directory = utils.task_dir(task_id)
    elif material_directory and not os.path.isdir(material_directory):
        material_directory = ""

    # Pre-fetch search results for each query (one round-trip per query).
    # Pixabay-first ordering inside _search_stock_dual_source means each
    # query's result list starts with Pixabay clips; if Pixabay returned
    # nothing for a query, Pexels fills that query's slot.
    query_results: dict[str, list] = {}
    for query in queries:
        try:
            query_results[query] = _search_stock_dual_source(
                query, video_aspect, max_clip_duration,
            )
        except Exception as exc:
            logger.warning(f"search failed for {query!r}: {exc}")
            query_results[query] = []

    # Round-robin pass through queries — pass 0 takes 1st clip per query,
    # pass 1 takes 2nd clip per query, etc.
    pass_num = 0
    while len(out) < n_needed:
        progressed_this_pass = False
        for query in queries:
            if len(out) >= n_needed:
                break
            items = query_results.get(query, [])
            if pass_num >= len(items):
                continue
            item = items[pass_num]
            if not getattr(item, "url", None) or item.url in seen_urls:
                continue
            try:
                saved = save_video(
                    video_url=item.url, save_dir=material_directory,
                )
                if saved:
                    seen_urls.add(item.url)
                    provider = getattr(item, "provider", "pexels") or "pexels"
                    out.append({
                        "path": saved,
                        "provider": provider,
                        "query": query,
                        "url": item.url,
                    })
                    progressed_this_pass = True
            except Exception as exc:
                logger.warning(f"failed to download stock for {query!r}: {exc}")
        if not progressed_this_pass:
            # No further clips available across any query — stop looping.
            break
        pass_num += 1
    return out


def _build_clips_hybrid(
    task_id: str,
    model_path,
    product_paths: list,
    audio_duration: float,
    video_aspect: VideoAspect,
    max_clip_duration: int,
    setting_tag: str,
    setting_queries: list,
):
    """Hybrid mode: interleave user uploads with Pexels + Pixabay setting footage.

    Pattern (FR-022): [stock_0, user_0, stock_1, user_1, ..., stock_closing]
      - user_0 is the model image when present, then product images in order
      - one stock clip between every pair of user clips, plus one closing stock
      - if no model: user_0 = product_paths[0]

    Three-tier retry (FR-024):
      1) Try the 5 specific setting queries.
      2) If insufficient, retry with the "general" tag's 5 queries.
      3) If still insufficient, fall back to all-user-images mode and write
         pexels_empty_fallback: true into the audit log.
    """
    if not product_paths:
        raise ValueError("no_product_assets")

    has_model = bool(model_path)
    user_clips_paths = ([model_path] if has_model else []) + list(product_paths)
    n_user_clips = len(user_clips_paths)
    n_stock_needed = n_user_clips + 1  # one between each pair + closing

    # Per-clip duration budget — keep stock + user equal length so the
    # alternation rhythm reads cleanly.
    n_total = n_user_clips + n_stock_needed
    per_clip_duration = max(_KENBURNS_MIN_DURATION, audio_duration / n_total)

    # Tier 1: specific setting queries
    queries = list(setting_queries) if setting_queries else []
    if not queries:
        # Defensive: if controller didn't write queries, use sensible defaults.
        from app.services.llm import _DEFAULT_SETTING_QUERIES
        queries = list(_DEFAULT_SETTING_QUERIES.get(setting_tag, _DEFAULT_SETTING_QUERIES["general"]))

    stock_fetched = _fetch_stock_for_queries(
        task_id, queries, n_stock_needed, video_aspect, max_clip_duration,
    )
    used_tier = 1
    fallback_used = False

    # Tier 2: retry with general queries if first tier came up short
    if len(stock_fetched) < n_stock_needed and setting_tag != "general":
        from app.services.llm import _DEFAULT_SETTING_QUERIES
        general_queries = list(_DEFAULT_SETTING_QUERIES["general"])
        more = _fetch_stock_for_queries(
            task_id,
            general_queries,
            n_stock_needed - len(stock_fetched),
            video_aspect,
            max_clip_duration,
        )
        stock_fetched.extend(more)
        used_tier = 2

    # Tier 3: fallback to user-only render
    if len(stock_fetched) < 1:
        logger.warning(
            f"hybrid mode: zero stock clips after tier {used_tier}; "
            f"falling back to user-only render"
        )
        result = _build_clips_from_uploads(
            task_id=task_id,
            model_path=model_path,
            product_paths=product_paths,
            audio_duration=audio_duration,
            video_aspect=video_aspect,
        )
        # Augment audit log with hybrid-fallback markers.
        _augment_audit_for_hybrid_fallback(
            task_id=task_id,
            setting_tag=setting_tag,
            setting_queries=queries,
        )
        return result

    # Render user clips via the existing Ken Burns helper.
    task_dir = (
        utils.task_dir(task_id, create=True)
        if "create" in utils.task_dir.__code__.co_varnames
        else utils.task_dir(task_id)
    )
    if not os.path.isdir(task_dir):
        os.makedirs(task_dir, exist_ok=True)

    # User clip rendering with idx 0..N (stable filenames).
    user_rendered = []
    for idx, p in enumerate(user_clips_paths):
        out_path = path.join(task_dir, f"uploaded-{idx}.mp4")
        seed = _compute_seed(p)
        _make_kenburns_clip(p, per_clip_duration, out_path, seed)
        user_rendered.append(out_path)

    # Build the interleave: alternate stock + user, with stock closing.
    interleaved = []
    audit_user_assets = []  # for product/model audit entries
    audit_stock_assets = []
    for i in range(n_user_clips):
        # stock at position 2*i
        if i < len(stock_fetched):
            stock_entry = stock_fetched[i]
            interleaved.append(stock_entry["path"])
            audit_stock_assets.append({
                "stored_path": stock_entry["path"],
                "provider": stock_entry["provider"],
                "query": stock_entry["query"],
                "source_url": stock_entry["url"],
                "screen_time_seconds": per_clip_duration,
                "placement": f"stock-{i}",
            })
        # user clip at position 2*i + 1
        interleaved.append(user_rendered[i])

    # Closing stock (last position)
    if n_user_clips < len(stock_fetched):
        closing = stock_fetched[n_user_clips]
        interleaved.append(closing["path"])
        audit_stock_assets.append({
            "stored_path": closing["path"],
            "provider": closing["provider"],
            "query": closing["query"],
            "source_url": closing["url"],
            "screen_time_seconds": per_clip_duration,
            "placement": "closing",
        })

    # Audit log entries for user assets
    audit_model = None
    if has_model:
        audit_model = _audit_entry(
            asset_path=model_path,
            kenburns_clip_path=user_rendered[0],
            screen_time_seconds=per_clip_duration,
            placement="hybrid-slot-2",  # FR-022: model goes in first user slot
        )
    audit_products = []
    product_offset = 1 if has_model else 0
    for idx, p in enumerate(product_paths):
        audit_products.append(_audit_entry(
            asset_path=p,
            kenburns_clip_path=user_rendered[product_offset + idx],
            screen_time_seconds=per_clip_duration,
            placement=f"hybrid-product-{idx + 1}",
        ))

    # Write the audit log per FR-025
    _write_asset_audit(task_id, {
        "visuals_mode": "hybrid",
        "auto_pexels_used": True,  # stock was used, even if mixed
        "pexels_clip_count": sum(1 for s in audit_stock_assets if s["provider"] == "pexels"),
        "pixabay_clip_count": sum(1 for s in audit_stock_assets if s["provider"] == "pixabay"),
        "setting_tag": setting_tag,
        "stock_queries": queries,
        "stock_assets": audit_stock_assets,
        "model_asset": audit_model,
        "product_assets": audit_products,
        "pexels_empty_fallback": False,
        "retry_tier_used": used_tier,
    })

    logger.success(
        f"hybrid render: {len(user_rendered)} user clips + "
        f"{len(audit_stock_assets)} stock clips "
        f"(setting={setting_tag}, tier={used_tier})"
    )
    return interleaved


def _augment_audit_for_hybrid_fallback(
    task_id: str,
    setting_tag: str,
    setting_queries: list,
) -> None:
    """When hybrid mode falls back to user-only, the user-only branch already
    wrote the base audit log. This adds the hybrid-specific markers so the
    audit invariant (`pexels_empty_fallback: true` is queryable) holds.
    """
    script_json_path = path.join(utils.task_dir(task_id), "script.json")
    if not os.path.exists(script_json_path):
        return
    try:
        with open(script_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    audit = data.get("asset_audit", {}) or {}
    audit["visuals_mode"] = "hybrid"
    audit["pexels_empty_fallback"] = True
    audit["setting_tag"] = setting_tag
    audit["stock_queries"] = list(setting_queries)
    audit["stock_assets"] = []
    audit["pixabay_clip_count"] = 0
    data["asset_audit"] = audit
    serialized = json.dumps(data, indent=2)
    target_dir = path.dirname(script_json_path)
    fd, tmp_path = tempfile.mkstemp(prefix="script.json.", suffix=".tmp", dir=target_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(serialized)
        os.replace(tmp_path, script_json_path)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    download_videos(
        "test123", ["Money Exchange Medium"], audio_duration=100, source="pixabay"
    )

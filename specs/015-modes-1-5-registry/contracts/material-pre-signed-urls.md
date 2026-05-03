# Contract: material.py Pre-signed URL Sidecar (Layer 3)

**Date**: 2026-05-03
**Owner**: Layer 3 (`MoneyPrinterTurbo` fork)
**Touches**: `app/services/material.py`, `app/services/task.py` (read path)
**Sidecar writer**: Layer 2 (`../visualai-orchestration/`) — separate contract referenced below

This contract specifies how `material.py`'s `download_videos` reads visual asset URLs from the per-task `visuals.json` sidecar Layer 2 writes pre-dispatch. It documents the Mode-2-Auto-path migration (debt #3 burndown) and the Mode-5 Pexels carve-out (constitution Principle IV exception).

---

## 1. Sidecar shape Layer 3 reads

**File**: `storage/tasks/<task_id>/visuals.json` (already populated by Layer 2 before Layer 3 starts the task).

**Schema**:

```json
{
  "tenant_id": "<string>",
  "user_id": "<string>",
  "mode": "short" | "faceless",
  "visuals_mode": "auto" | "user_uploaded" | "hybrid",
  "user_uploaded_paths": ["<local-path>", ...],
  "pre_signed_clip_urls": ["<https-url>", ...] | null
}
```

**Field semantics for Layer 3**:

| Field | Read by | Behaviour |
|---|---|---|
| `pre_signed_clip_urls` | `material.download_videos` | If non-null + non-empty, fetch each URL via `requests.get` with a 30-second per-URL timeout. Save to `storage/tasks/<task_id>/clips/clip-N.mp4` |
| `user_uploaded_paths` | `material.download_videos` | If `visuals_mode in ("user_uploaded", "hybrid")` and `pre_signed_clip_urls` is null/empty, copy from these paths into the task dir |
| `mode` | `material.download_videos` | Used for the Mode 5 fallback gate (see §3) |
| `visuals_mode` | `task.generate_terms` | Already used; no Step-3 change |
| `tenant_id`, `user_id` | observability | Logged via Loguru `bind()` for trace correlation |

---

## 2. The dispatch decision tree

```python
# app/services/material.py — pseudocode, not literal
def download_videos(task_id, params):
    sidecar = _read_sidecar(task_id)  # visuals.json
    mode = sidecar.get("mode") or params.mode
    pre_signed = sidecar.get("pre_signed_clip_urls")

    if pre_signed:
        # Mode 2 Auto path post-Step-3, Mode 2 Hybrid post-Step-3.5, ...
        return _download_from_pre_signed_urls(task_id, pre_signed)

    if mode == "faceless":
        # Mode 5 — constitution Principle IV permitted exception
        # Same code path as pre-Step-3 Mode 2 Auto: direct Pexels + Pixabay
        return _download_from_pexels_direct(task_id, params)

    if sidecar.get("visuals_mode") in ("user_uploaded", "hybrid"):
        return _copy_uploaded(task_id, sidecar["user_uploaded_paths"])

    # Should not reach: Layer 2 always populates one of the three sources for Mode 2
    raise RuntimeError(f"material.no_visuals_source: mode={mode}, sidecar={sidecar}")
```

---

## 3. Pre-signed URL fetcher

```python
def _download_from_pre_signed_urls(task_id: str, urls: list[str]) -> list[str]:
    """Fetch each URL into the task's clips dir. Preserves URL order.

    Per FR-022 + FR-023 of spec 015:
    - Plain HTTP GET — Layer 3 does NOT verify the HMAC signature (that's Layer 2's job).
    - 30s timeout per URL.
    - On 410/403/404 from any URL: log error, fail the task with material.fetch_failed.
    - On 5xx: retry once with 2s backoff, then fail.
    - Stream to disk (don't buffer in memory) — clips can be 50+ MB.
    """
    import requests
    out_dir = f"storage/tasks/{task_id}/clips"
    os.makedirs(out_dir, exist_ok=True)
    out_paths = []
    for i, url in enumerate(urls, start=1):
        out_path = os.path.join(out_dir, f"clip-{i}{_ext_from_url(url)}")
        for attempt in range(2):
            try:
                with requests.get(url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(out_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                out_paths.append(out_path)
                break
            except requests.exceptions.HTTPError as e:
                if e.response.status_code >= 500 and attempt == 0:
                    time.sleep(2); continue
                raise
            except requests.exceptions.Timeout:
                if attempt == 0:
                    time.sleep(2); continue
                raise
    return out_paths
```

---

## 4. Pexels + Pixabay direct (Mode 5 only — preserved)

The pre-Step-3 `_search_stock_dual_source` and `_fetch_stock_for_queries` functions stay in `material.py` unchanged. They're now called via the Mode 5 branch only:

```python
def _download_from_pexels_direct(task_id, params):
    # Pre-Step-3 logic, byte-for-byte
    queries = modes.pick("faceless").generate_terms(params, _read_script(task_id))
    return _fetch_stock_for_queries(queries, task_id, params)
```

This is the **constitution Principle IV permitted exception**: Mode 5's "faceless" content is exactly the use case the constitution carved out for direct stock-API access. Section IV reads: *"Mode 5 may call Pexels directly because faceless content has no per-tenant brand uniqueness; all other modes must accept assets via Layer 2."*

---

## 5. Error contract

| Error code | When | HTTP status from API | Task state |
|---|---|---|---|
| `material.no_visuals_source` | Sidecar has neither pre_signed_clip_urls nor user_uploaded_paths AND mode != faceless | 500 (internal) | `failed` |
| `material.fetch_failed` | Pre-signed URL returned 4xx (not 410/403 specifically) | n/a (logged) | `failed` |
| `material.url_expired` | Pre-signed URL returned 410 | n/a | `failed` (Layer 2 should refresh sidecar; Step 4 retry mechanism) |
| `material.url_forbidden` | Pre-signed URL returned 403 | n/a | `failed` |
| `material.fetch_timeout` | Per-URL timeout exceeded after retry | n/a | `failed` |
| `material.invalid_sidecar` | visuals.json missing or unparseable | 500 | `failed` |

---

## 6. Backwards compatibility

`download_videos` retains its existing public signature:

```python
def download_videos(
    task_id: str,
    params: VideoParams,
) -> list[str]:
    """Returns list of local video file paths to feed into video.combine_videos."""
```

No callers change. The internal dispatch tree is the only change. Existing Pexels-only paths (Mode 5, and pre-Step-3 Mode 2 Auto path that hasn't been migrated yet) keep working with **zero observable difference** to `task.py`.

---

## 7. Test contract

### 7.1 `test/services/test_material_pre_signed_urls.py`

Required cases:

| Test ID | Scenario | Expected |
|---|---|---|
| MAT-1 | Sidecar with `pre_signed_clip_urls=[u1, u2]` | Two HTTP GETs, two files in `clips/` |
| MAT-2 | Sidecar with `pre_signed_clip_urls=null` AND `mode="faceless"` | Pexels code path runs (mock `_fetch_stock_for_queries`) |
| MAT-3 | Sidecar with `pre_signed_clip_urls=null` AND `mode="short"` AND `visuals_mode="user_uploaded"` | Copies from `user_uploaded_paths` |
| MAT-4 | Sidecar with `pre_signed_clip_urls=null` AND `mode="short"` AND `visuals_mode="auto"` AND no upload paths | Raises `material.no_visuals_source` |
| MAT-5 | Pre-signed URL returns 410 | `material.url_expired`; task fails |
| MAT-6 | Pre-signed URL returns 5xx then 200 | Retries once successfully |
| MAT-7 | Pre-signed URL returns 5xx twice | `material.fetch_failed` |
| MAT-8 | Sidecar file missing | `material.invalid_sidecar` |
| MAT-9 | Sidecar JSON malformed | `material.invalid_sidecar` |
| MAT-10 | Order preservation: `[u1, u2, u3]` produces `clip-1`, `clip-2`, `clip-3` matching the URL order | True |

### 7.2 Existing tests stay green

`test_material.py` (pre-Step-3 Pexels-mocking tests for Mode 5 / faceless flow) MUST continue to pass with no changes — the Mode 5 dispatch branch is a literal re-call of the pre-Step-3 logic.

---

## 8. Observability

Every fetch logs with Loguru `bind()`:

```python
logger.bind(
    task_id=task_id,
    tenant_id=sidecar.get("tenant_id"),
    user_id=sidecar.get("user_id"),
    mode=mode,
    source="pre_signed" | "pexels_direct" | "user_uploaded",
    url_count=len(urls),
).info("material.download_videos.start")
```

Used by Step 4's per-tenant generation analytics. Step 3 just emits the structured log — no aggregation yet.

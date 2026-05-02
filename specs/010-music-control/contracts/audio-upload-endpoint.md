# Contract: Audio Upload Endpoint

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 2](../data-model.md)

This contract defines the HTTP shape of `POST /api/v1/uploads/audio` — the new endpoint that accepts a multipart audio upload, validates it, persists it, probes its duration, and returns a path string + duration the wizard places into `bgm_file` and shows to the creator.

The endpoint mirrors spec 009's `POST /api/v1/uploads/logo` structurally; this contract documents the audio-specific differences (MIME table, duration probe, slightly larger size cap, response field).

## Endpoint

```
POST /api/v1/uploads/audio
```

## Authentication

v1: none (Step 1 of the build plan is single-user, no auth, debt #2 in `STEP1_DEBT.md`). When debt #2 repays in Step 2, this endpoint inherits the JWT middleware applied to the video controllers, and uploads scope to `storage/uploads/<tenant_id>/<uuid>.<ext>` — same path-rewrite that spec 009's logo endpoint inherits.

## Request

| Aspect | Value |
|---|---|
| Content-Type | `multipart/form-data` |
| Field name | `file` |
| Allowed MIME types | `audio/mpeg`, `audio/wav`, `audio/x-wav`, `audio/ogg`, `audio/mp4` |
| Max body size | **10 MB** (FR-003) |

The frontend's proxy at `/api/upload-audio` re-multiparts the user's upload to this endpoint with the same `file` field name; no additional headers required.

## Success response

**Status**: 201 Created
**Body**:

```json
{
  "path": "storage/uploads/4f9c7e3a-2b1d-4a8f-9e0b-3c5d8e7f6a4b.mp3",
  "size_bytes": 4194304,
  "mime_type": "audio/mpeg",
  "duration_seconds": 138.42
}
```

| Field | Type | Notes |
|---|---|---|
| `path` | string | Filesystem-relative path the wizard places into `bgm_file`. Always begins with `storage/uploads/`. UUID4 filename + extension derived from MIME (NOT user filename). |
| `size_bytes` | integer | Stored file size in bytes. Useful for the wizard to display. |
| `mime_type` | string | Echoes the validated MIME type. |
| `duration_seconds` | float | Track duration in seconds, probed via ffprobe (with MoviePy `AudioFileClip` fallback). The wizard uses this to display the loop/truncate hint. Two-decimal precision is sufficient. |

## Error responses

All errors share the same body shape as spec 009's logo endpoint:

```json
{
  "detail": "<human-readable explanation>",
  "error_code": "<typed code>"
}
```

| HTTP | `error_code` | Trigger | Wizard UX |
|---|---|---|---|
| 400 | `unsupported_format` | MIME type not in allowed list | "Only MP3, WAV, OGG, or M4A supported." |
| 400 | `empty_upload` | No `file` field in body, or zero-byte file | "No file uploaded." |
| 413 | `file_too_large` | Body exceeds 10 MB | "Audio must be under 10 MB." |
| 415 | `invalid_audio` | ffprobe (and MoviePy fallback) can't determine duration → file not a valid audio container, despite valid MIME | "This file appears corrupt — please re-export and try again." |
| 500 | `storage_write_failed` | Disk full / IO error writing to `storage/uploads/` | "Couldn't save your track — please retry. If it persists, contact support." |
| 500 | `duration_probe_failed` | ffprobe binary missing AND MoviePy fallback also fails | "Server couldn't process audio metadata — please contact support." |

## Behavior contract

### Validation order

1. Parse multipart body (FastAPI built-in).
2. Reject empty bodies → 400 `empty_upload`.
3. Reject body size > 10 MB → 413 `file_too_large`. Use FastAPI's `Request.body()` size guard if possible to avoid reading the full body; otherwise reject after read.
4. Reject MIME not in allowed list → 400 `unsupported_format`.
5. Generate UUID4 + derive extension from MIME (see table below).
6. Write file to `storage/uploads/<uuid>.<ext>`. On IOError → 500 `storage_write_failed`.
7. **Probe duration**: invoke `ffprobe -v quiet -show_entries format=duration -of csv="p=0" <path>`. Parse stdout to float. If ffprobe missing or fails, fall back to `AudioFileClip(path).duration`. If both fail → delete the file and return 415 `invalid_audio`.
8. Return 201 with the path + size + mime + duration.

### Filename safety

Same rule as spec 009's logo endpoint: ignore the user-provided filename entirely. Generate a server-side UUID4 filename + extension derived ONLY from validated MIME:

| MIME | Saved extension |
|---|---|
| `audio/mpeg` | `.mp3` |
| `audio/wav`, `audio/x-wav` | `.wav` |
| `audio/ogg` | `.ogg` |
| `audio/mp4` | `.m4a` |

### Storage layout

| v1 (single-user) | v2 (tenant-scoped, after debt #2 repays) |
|---|---|
| `storage/uploads/<uuid>.<ext>` | `storage/uploads/<tenant_id>/<uuid>.<ext>` |

Shared with spec 009's logo endpoint. UUID4 + MIME-derived extension prevents any collision between audio and image uploads.

### Permission bits

Files saved with mode `0o644` (owner read+write, group + others read). Directories `0o755`. Matches MPT's existing `storage/tasks/` convention and spec 009's logo endpoint.

### Idempotency

Not idempotent — each call generates a new UUID4 and stores a new file. The wizard SHOULD only call it once per render; clients SHOULD NOT retry on 5xx without backoff.

### Cleanup policy (v1)

None. Files persist forever in `storage/uploads/` until the operator manually clears the directory. v2 may add a TTL sweeper job.

### Failure cleanup

If duration probe fails after the file has been persisted, the endpoint MUST delete the file before returning the 415 error. Don't leak orphan files for known-bad uploads.

## Examples

### Successful upload — curl

```sh
curl -X POST http://localhost:8090/api/v1/uploads/audio \
  -F "file=@./my-jingle.mp3"
```

→ Response:

```json
{
  "path": "storage/uploads/4f9c7e3a-2b1d-4a8f-9e0b-3c5d8e7f6a4b.mp3",
  "size_bytes": 4194304,
  "mime_type": "audio/mpeg",
  "duration_seconds": 138.42
}
```

### Failed upload — file too large

```sh
curl -X POST http://localhost:8090/api/v1/uploads/audio \
  -F "file=@./giant-album.wav"
```

→ Response (413):

```json
{
  "detail": "Audio must be under 10 MB.",
  "error_code": "file_too_large"
}
```

### Failed upload — corrupt audio

```sh
echo "not a real audio file" > broken.mp3
curl -X POST http://localhost:8090/api/v1/uploads/audio \
  -F "file=@./broken.mp3"
```

→ Response (415):

```json
{
  "detail": "This file appears corrupt — please re-export and try again.",
  "error_code": "invalid_audio"
}
```

(Server-side: the file was briefly written to `storage/uploads/`, then deleted when ffprobe rejected it.)

## Frontend proxy contract

The frontend route at `/api/upload-audio` (in `visualai-frontend/src/app/api/upload-audio/route.ts`) MUST:

1. Accept `multipart/form-data` from the browser with the same `file` field name.
2. Re-multipart the body to MPT's `/api/v1/uploads/audio` (URL from `process.env.NEXT_PUBLIC_LAYER3_URL`).
3. Forward the JSON response (or error) verbatim to the browser.
4. NOT log or persist the file contents on the Next.js server (no temp directories).

Mirrors spec 009's `/api/upload-logo` proxy exactly.

## Verification (drives task design)

| Test ID | Setup | Expected |
|---|---|---|
| AU-1 | Valid 1 s sine-wave WAV ≤ 10 MB | 201 with `path`, `duration_seconds ≈ 1.0` |
| AU-2 | Valid 1 s sine-wave MP3 (converted from WAV via ffmpeg in test fixture) | 201 with `.mp3` extension and `duration_seconds ≈ 1.0` |
| AU-3 | Valid OGG | 201 with `.ogg` extension |
| AU-4 | Valid M4A | 201 with `.m4a` extension |
| AU-5 | 12 MB body | 413 `file_too_large` |
| AU-6 | `.flac` upload (unsupported MIME) | 400 `unsupported_format` |
| AU-7 | Bytes claiming `audio/mpeg` MIME but actually plain text | 415 `invalid_audio`; file deleted from `storage/uploads/` after the failed probe |
| AU-8 | Filename `../../etc/passwd.mp3` | 201 with stored filename = UUID4.mp3 (path traversal NOT preserved) |

These eight tests are the contract surface for `/speckit-tasks` to schedule.

## Cross-spec coordination

- **Shared file**: `app/controllers/v1/uploads.py` — created by whichever feature ships first (spec 009 or this one). The MIME table, validation helper, and file-saving routine SHOULD be deduplicated between the audio and logo endpoints inside this file.
- **Shared validation helper** (suggested signature):
  ```python
  def _validate_upload(
      file: UploadFile,
      allowed_mimes: set[str],
      max_bytes: int,
  ) -> tuple[bytes, str, str]:
      """Returns (file_bytes, validated_mime, file_extension). Raises HTTPException on error."""
  ```
  Both `/api/v1/uploads/logo` and `/api/v1/uploads/audio` call this helper with their respective MIME tables and size caps. Keeps validation behavior in lock-step.

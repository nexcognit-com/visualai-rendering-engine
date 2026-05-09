# Contract: Selfie Upload MIME Handling

**Owner**: Layer 3 (`MoneyPrinterTurbo/app/controllers/v1/uploads.py:upload_selfie`)
**Caller**: Layer 2 (`visualai-orchestration/.../api/v1/avatars/upload`) which proxies multipart bodies from Layer 1 (`visualai-frontend` `/api/avatars/upload`).
**Spec links**: spec.md FR-008, FR-009, FR-010 · data-model.md §SpeakerReference (upload variant) · spec 018 (Mode 4 base contract).

## Endpoint

```
POST /api/v1/uploads/selfie
Content-Type: multipart/form-data; boundary=...
Authorization: Bearer <demo-bearer | tenant-jwt>

(form fields)
  file: <binary>      Required. The selfie video the creator captured/uploaded.
```

## Accepted MIME types

The validator MUST accept exactly these `Content-Type` values (after stripping parameters per the rule below):

| MIME (after strip) | Persisted extension | Persistence path |
|---|---|---|
| `video/mp4` | `.mp4` | move-in-place (no transcode) |
| `video/quicktime` | `.mov` | move-in-place (no transcode) |
| `video/webm` | `.webm` (input) → `.mp4` (output) | re-encode video to H.264 yuv420p, drop audio |
| `video/x-matroska` | `.mkv` (input) → `.mp4` (output) | re-encode video to H.264 yuv420p, drop audio |

## Parameter-stripping rule (FR-008)

The validator MUST treat `Content-Type` as a parameterised media type per RFC 7231 §3.1.1.1. The accept-list lookup key is computed as:

```
key = content_type.split(";", 1)[0].strip().lower()
```

So all of these MUST resolve to the same accept-list entry:

- `video/webm`
- `video/webm;codecs=vp8`
- `video/webm; codecs=vp9`
- `Video/WebM ; codecs="vp8,opus"`

## Re-encode rule (FR-009)

For inputs whose stripped MIME is `video/webm` or `video/x-matroska`, the persisted speaker reference MUST be produced by:

```
ffmpeg -loglevel error -y \
       -i <upload>      \
       -c:v libx264 -pix_fmt yuv420p -an \
       <out>.mp4
```

- Stream-copy (`-c copy`) is FORBIDDEN for these inputs (VP8/VP9 cannot live in MP4).
- The audio track MUST be dropped (`-an`).
- The output MUST have pixel format yuv420p for downstream MuseTalk compatibility.

For `video/mp4` and `video/quicktime`, the temp file is moved directly into place — no transcode.

## Success response

```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "ok": true,
  "slot_index": 1,
  "persisted_path": "<absolute path on L3>",
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "duration_seconds": 12.4,
  "face_detected": true
  // ... existing fields per spec 018 unchanged
}
```

## Error responses

### Unsupported MIME (FR-010)

```
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "detail": {
    "error_code": "format_unsupported",
    "message": "Unsupported MIME: <ORIGINAL Content-Type string>"
  }
}
```

**Critical**: the `message` field MUST include the **original** `Content-Type` string the client sent — not the parameter-stripped lookup key. This is so a creator whose browser sent something exotic (`video/x-flv;codecs=h263+`) sees exactly what they sent and can fix it on the client side.

### Body too large

Unchanged by this feature. Existing 413 path remains in place.

### Validation failures (face / duration / fps / resolution)

Unchanged by this feature. Existing 400 + typed `error_code` paths remain in place per spec 018.

## Test fixtures (informative)

The `test/controllers/test_image_upload.py` cases SHOULD include:

- `video/webm;codecs=vp8` → strips to `video/webm` → accepted
- `video/webm; codecs=vp9` (note the space) → strips to `video/webm` → accepted
- `video/webm;codecs=vp8,opus` → strips to `video/webm` → accepted
- `video/x-matroska;codecs=h264` → strips to `video/x-matroska` → accepted
- `image/png` → no strip needed → 400 with `Unsupported MIME: image/png`
- `video/x-flv;codecs=h263+` → strips to `video/x-flv` → 400 with full original string echoed
- A real WebM upload of a 6s VP8 selfie → persisted as MP4 with H.264 video, no audio track, ffprobe-confirmed
- A real MKV upload → same outcome

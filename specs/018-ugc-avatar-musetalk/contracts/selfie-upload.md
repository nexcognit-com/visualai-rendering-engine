# Contract — Selfie Upload Endpoint

**Surface**: L3 (rendering engine) at `POST /api/v1/uploads/selfie`. L2 proxies as `POST /api/v1/avatars/upload`. L1 wizard calls L2.

## Purpose

Persist a user's speaker-reference video to L3's filesystem under the hybrid last-3 retention model. Validate the upload (face detection, duration, format) before accepting. Return the resolved `path` + face-detection metadata so the wizard can show the chosen face crop and proceed to render.

## Request

### From L1 → L2 (auth via demo bearer)

```http
POST /api/v1/avatars/upload HTTP/1.1
Host: 127.0.0.1:8089
Authorization: Bearer demo-bearer-replace-in-production
Content-Type: multipart/form-data; boundary=----foo

------foo
Content-Disposition: form-data; name="file"; filename="selfie.mp4"
Content-Type: video/mp4

<binary mp4 bytes>
------foo--
```

### From L2 → L3 (forwarded as-is, plus tenant scoping)

```http
POST /api/v1/uploads/selfie HTTP/1.1
Host: 127.0.0.1:8090
Authorization: Bearer demo-bearer-replace-in-production
X-Tenant-Id: demo-tenant-001
X-User-Id: demo-user-001
Content-Type: multipart/form-data; ...
```

## Response — success

```json
{
  "uuid": "a3f9d6e2c1b8",
  "tenant_id": "demo-tenant-001",
  "user_id": "demo-user-001",
  "slot": 2,
  "path": "storage/uploads/demo-tenant-001/avatars/slot2/a3f9d6e2c1b8.mp4",
  "duration_seconds": 12.4,
  "width": 1080,
  "height": 1920,
  "face_count_detected": 1,
  "face_bbox": {
    "x": 384,
    "y": 512,
    "w": 312,
    "h": 416,
    "confidence": 0.94
  },
  "warnings": []
}
```

`warnings[]` is non-empty when the upload is accepted but flagged:

- `"multiple_faces_detected"` — `face_count_detected > 1`. Wizard should surface "we picked the largest centered face — re-upload if wrong" UX.
- `"face_partially_obscured"` — face detection confidence < 0.85. Lip-sync quality may degrade.
- `"low_frame_rate"` — < 30 fps but ≥ 24. Accepted but flagged.

## Response — error

```json
{
  "error_code": "no_face_detected",
  "message": "No face detected in the uploaded video. Please upload a clear selfie facing the camera.",
  "details": {"frames_scanned": 30, "max_confidence": 0.42}
}
```

### Error code matrix

| HTTP | error_code | Trigger |
|---|---|---|
| 400 | `no_face_detected` | Face detection scored < 0.7 across all sampled frames |
| 400 | `duration_out_of_range` | duration < 5.0s or > 60.0s |
| 400 | `format_unsupported` | MIME not in {mp4, mov, webm} |
| 400 | `frame_rate_too_low` | < 24 fps |
| 400 | `resolution_too_low` | shortest side < 480 px |
| 400 | `audio_only_upload` | container has no video stream |
| 401 | `unauthorized` | bearer or tenant header missing/invalid |
| 413 | `payload_too_large` | file size > 100 MB |
| 500 | `internal_validation_failed` | unexpected error during ffprobe / face-detect |

## Storage layout (L3 side, after success)

```text
storage/uploads/demo-tenant-001/avatars/slot2/
├── a3f9d6e2c1b8.mp4         # the upload, mp4-remuxed if originally mov/webm
└── a3f9d6e2c1b8.meta.json   # serialized response payload (data-model.md Entity 1 fields)
```

If a 4th upload arrives for the same tenant, the slot with the oldest `created_at` is evicted (file + .meta.json deleted) before the new one is written. Eviction is mtime-based, not slot-rotating.

## Side-effects

- File written to `storage/uploads/<tenant>/avatars/slot{N}/<uuid>.mp4`.
- Optional remux (if uploaded as `.mov` or `.webm`) to mp4 via FFmpeg with `-c copy` (no re-encode).
- Metadata sidecar `<uuid>.meta.json` written alongside.
- Eviction of oldest slot if 3 already occupied for this tenant.
- Loguru log line: `selfie_upload tenant=<tenant_id> user=<user_id> slot=<N> uuid=<uuid> duration=<s> faces=<count>`.

## Observability

Each upload increments tenant-scoped counters (when observability is wired in Step 4):
- `selfie_uploads_total{tenant, status="success|error"}`.
- `selfie_face_detect_latency_seconds` histogram.

For v1, plain loguru lines suffice.

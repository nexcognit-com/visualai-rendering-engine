# Contract: Logo Upload Endpoint

**Feature**: [spec.md](../spec.md) | **Plan**: [plan.md](../plan.md) | **Data Model**: [data-model.md §Entity 2](../data-model.md)

This contract defines the HTTP shape of the new `POST /api/v1/uploads/logo` endpoint that accepts a multipart logo upload, validates it, persists it, and returns a path string the wizard places into `Overlay.source_path`.

## Endpoint

```
POST /api/v1/uploads/logo
```

## Authentication

v1: none (Step 1 of the build plan is single-user, no auth, debt #2 in `STEP1_DEBT.md`). When debt #2 repays in Step 2, this endpoint inherits the JWT middleware applied to the video controllers, and uploads scope to `storage/uploads/<tenant_id>/<uuid>.<ext>`.

## Request

| Aspect | Value |
|---|---|
| Content-Type | `multipart/form-data` |
| Field name | `file` |
| Allowed MIME types | `image/png`, `image/jpeg`, `image/webp` |
| Max body size | 5 MB (FR-002) |

The frontend's proxy at `/api/upload-logo` re-multiparts the user's upload to this endpoint with the same `file` field name; no additional headers required.

## Success response

**Status**: 201 Created
**Body**:

```json
{
  "path": "storage/uploads/0e0a4f7a-2a1b-4d3c-9e9f-7c8d2a1b4d3c.png",
  "size_bytes": 184320,
  "mime_type": "image/png"
}
```

| Field | Type | Notes |
|---|---|---|
| `path` | string | Filesystem-relative path the wizard places into `Overlay.source_path`. Always begins with `storage/uploads/`. UUID4 filename + extension derived from MIME (NOT user filename). |
| `size_bytes` | integer | Stored file size in bytes. Useful for the wizard to display. |
| `mime_type` | string | Echoes the validated MIME type. |

## Error responses

All errors share the FastAPI default body shape:

```json
{
  "detail": "<human-readable explanation>",
  "error_code": "<typed code>"
}
```

| HTTP | `error_code` | Trigger | Wizard UX |
|---|---|---|---|
| 400 | `unsupported_format` | MIME type not in allowed list | "Only PNG, JPG, or WebP supported." |
| 400 | `empty_upload` | No `file` field in body, or zero-byte file | "No file uploaded." |
| 413 | `file_too_large` | Body exceeds 5 MB | "Logo must be under 5 MB." |
| 415 | `invalid_image` | Pillow can't open the file (corrupt image bytes despite valid MIME) | "This file appears corrupt — please re-export and try again." |
| 500 | `storage_write_failed` | Disk full / IO error writing to `storage/uploads/` | "Couldn't save your logo — please retry. If it persists, contact support." |

## Behavior contract

### Filename safety

The endpoint MUST NOT use the user-provided filename (which could contain path traversal sequences `../`, NUL bytes, or weird Unicode). It MUST generate a server-side UUID4 filename + extension derived ONLY from the validated MIME type:

| MIME | Saved extension |
|---|---|
| `image/png` | `.png` |
| `image/jpeg` | `.jpg` |
| `image/webp` | `.webp` |

### Storage layout

| v1 (single-user) | v2 (tenant-scoped, after debt #2 repays) |
|---|---|
| `storage/uploads/<uuid>.<ext>` | `storage/uploads/<tenant_id>/<uuid>.<ext>` |

The endpoint MUST create the directory if missing; MUST NOT fail if it already exists.

### Permission bits

Files saved with mode `0o644` (owner read+write, group + others read). Directories `0o755`. Matches MPT's existing `storage/tasks/` convention.

### Validation order

1. Parse multipart body (Fastify-style FastAPI built-in).
2. Reject empty bodies → 400 `empty_upload`.
3. Reject body size > 5 MB → 413 `file_too_large`. (Cap should be enforced at the FastAPI layer if possible to avoid reading the full body; otherwise reject after read.)
4. Reject MIME not in allowed list → 400 `unsupported_format`.
5. Open with Pillow to verify it's a valid image of the claimed type. Reject on `Pillow.UnidentifiedImageError` → 415 `invalid_image`.
6. Generate UUID4 + derive extension from MIME.
7. Write file. On IOError → 500 `storage_write_failed`.
8. Return 201 with the path string.

### Idempotency

The endpoint is NOT idempotent — each call generates a new UUID4 and stores a new file. The wizard SHOULD only call it once per overlay; clients SHOULD NOT retry on 5xx without backoff (each retry burns another UUID + disk slot).

### Cleanup policy (v1)

None. Files persist forever in `storage/uploads/` until the operator manually clears the directory. v2 may add a TTL sweeper job; not in v1 scope.

## Examples

### Successful upload — curl

```sh
curl -X POST http://localhost:8090/api/v1/uploads/logo \
  -F "file=@./mybrand.png"
```

→ Response:

```json
{
  "path": "storage/uploads/0e0a4f7a-2a1b-4d3c-9e9f-7c8d2a1b4d3c.png",
  "size_bytes": 184320,
  "mime_type": "image/png"
}
```

### Failed upload — file too large

```sh
curl -X POST http://localhost:8090/api/v1/uploads/logo \
  -F "file=@./giant-poster.tiff"
```

→ Response (413 if accepted-then-rejected, 415 if MIME caught first):

```json
{
  "detail": "Logo must be under 5 MB.",
  "error_code": "file_too_large"
}
```

### Failed upload — corrupt PNG

```sh
echo "not a real png" > broken.png
curl -X POST http://localhost:8090/api/v1/uploads/logo \
  -F "file=@./broken.png"
```

→ Response (415):

```json
{
  "detail": "This file appears corrupt — please re-export and try again.",
  "error_code": "invalid_image"
}
```

## Frontend proxy contract

The frontend route at `/api/upload-logo` (in `visualai-frontend/src/app/api/upload-logo/route.ts`) MUST:

1. Accept `multipart/form-data` from the browser with the same `file` field name.
2. Re-multipart the body to MPT's `/api/v1/uploads/logo` (URL from `process.env.NEXT_PUBLIC_LAYER3_URL`).
3. Forward the JSON response (or error) verbatim to the browser.
4. NOT log or persist the file contents on the Next.js server (no temp directories).

This keeps the bearer-secret-free contract intact and matches how `/api/generate` already proxies to MPT.

## Verification (drives task design)

Each row of the validation order table becomes an acceptance test:

| Test ID | Setup | Expected |
|---|---|---|
| UE-1 | Valid PNG ≤ 5 MB | 201 with `path` returned |
| UE-2 | Valid JPG ≤ 5 MB | 201 with `path` ending `.jpg` |
| UE-3 | Valid WebP ≤ 5 MB | 201 with `path` ending `.webp` |
| UE-4 | TIFF (unsupported MIME) | 400 `unsupported_format` |
| UE-5 | 6 MB PNG | 413 `file_too_large` |
| UE-6 | Empty file | 400 `empty_upload` |
| UE-7 | Bytes claiming `image/png` MIME but actually plain text | 415 `invalid_image` |
| UE-8 | Filename `../../etc/passwd.png` | 201 with stored filename = UUID4.png (NOT path-traversal preserved) |

These eight tests are the contract surface for `/speckit.tasks` to schedule.

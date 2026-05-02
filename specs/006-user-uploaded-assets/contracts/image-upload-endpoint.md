# Contract: `POST /api/v1/uploads/image`

**Feature**: 006-user-uploaded-assets
**Layer**: 3 (rendering engine)
**File**: `app/controllers/v1/uploads.py`

Adds a new image-upload route alongside spec 010's `POST /api/v1/uploads/audio` and spec 009's logo route. Mirrors the existing `_validate_upload` + UUID4 path discipline.

## Request

```http
POST /api/v1/uploads/image
Content-Type: multipart/form-data; boundary=----WebKit...
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | The image bytes. JPEG, PNG, or WebP only (FR-007). Max 10 MB (FR-008). |
| `role` | form text | yes | `"model"` or `"product"`. Used only for audit-log enrichment; does not change validation. |

## Response — 200 OK

```json
{
  "path": "storage/uploads/abc123-def456-789ghi.cropped.jpg",
  "original_path": "storage/uploads/abc123-def456-789ghi.jpg",
  "size_bytes": 2048576,
  "mime_type": "image/jpeg",
  "source_width_px": 4032,
  "source_height_px": 3024,
  "cropped_width_px": 1080,
  "cropped_height_px": 1920,
  "content_hash": "sha256:91d33c..."
}
```

`path` is the **cropped 9:16 derivative** — that's what the client persists in wizard state and includes in the eventual `POST /api/v1/videos` body as `uploaded_model_path` or an entry in `uploaded_product_paths`. `original_path` is included for forward compatibility (drag-to-reframe milestone, audit display).

## Errors

| HTTP | `error_code` | When |
|---|---|---|
| 400 | `empty_upload` | No file in form, or zero-byte file |
| 400 | `unsupported_role` | `role` field missing or not `"model"` / `"product"` |
| 400 | `unsupported_format` | MIME not in `image/jpeg`, `image/png`, `image/webp` |
| 413 | `file_too_large` | Body > 10 MB |
| 415 | `invalid_image` | Pillow fails to decode (corrupt/truncated/zip-bomb) |
| 415 | `degenerate_dimensions` | Width or height < 100 px, or width × height > 100 MP (post-decode bomb guard) |
| 422 | `low_resolution_warning` | Longest side < 720 px **but** request still succeeds — this is a soft-warning embedded in a 200 OK response with a `warning` field, not a 422. (FR-009 "MUST still be accepted.") *Documented here for client awareness; the actual response remains 200 with `"warning": "low_resolution"`.* |
| 500 | `storage_write_failed` | Filesystem write error |
| 500 | `crop_failed` | Pillow crop or re-encode raised; original is also discarded so no orphan |

## Response — 200 with soft warning

```json
{
  "path": "storage/uploads/abc.....cropped.jpg",
  "original_path": "storage/uploads/abc.....jpg",
  "size_bytes": 524288,
  "mime_type": "image/jpeg",
  "source_width_px": 600,
  "source_height_px": 400,
  "cropped_width_px": 600,
  "cropped_height_px": 1066,
  "content_hash": "sha256:...",
  "warning": "low_resolution"
}
```

When `warning == "low_resolution"`, the client SHOULD render an inline soft-warning toast ("This will look soft; prefer images ≥ 1080 px") but MUST allow the user to proceed (FR-009).

## Server-side processing pipeline

1. Read multipart body, validate role, validate MIME, validate size (`_validate_upload` reuse — extend the existing helper to accept `_IMAGE_MIMES` + 10 MB limit).
2. Generate UUID4. Compute target ext from MIME table.
3. Write original to `storage/uploads/<uuid>.<ext>`.
4. Open with Pillow, run `Image.open(...).verify()` then re-open for actual processing (Pillow's `verify()` invalidates the file handle).
5. Run `ImageOps.exif_transpose` to bake rotation into pixels.
6. Compute SHA-256 over the original bytes (audit hash).
7. Compute 9:16 center-crop bbox.
8. Write cropped derivative to `storage/uploads/<uuid>.cropped.jpg` (always JPEG, quality=88, sRGB, EXIF stripped).
9. Run local moderation heuristic (`MODERATION_REQUIRED=False` Step-1 default — heuristic logs but doesn't block).
10. Return JSON.

If any step 4–9 fails, delete the original (step 3) before returning the error so no orphans accumulate.

## Storage write discipline

- File is written via `with open(..., 'wb') as f: f.write(body)` then `os.chmod(path, 0o644)`.
- Directory `storage/uploads/` is created if missing via `utils.storage_dir("uploads", create=True)` (existing helper from spec 009/010).
- Server-generated UUID4 prevents path-traversal from user filenames; the user's `filename` is captured into the audit log only.

## Authentication

Step 1: none. The endpoint is open like the existing `/api/v1/videos` endpoint. **Continues debt #2** — when JWT middleware lands in Step 2, this endpoint gets the same middleware applied uniformly via the existing `app/router.py` registration; no per-route changes needed.

## Test coverage (planned)

- IU-1: happy path — JPEG 4032×3024, 2 MB, returns 200 with `cropped_width_px=1080, cropped_height_px=1920`.
- IU-2: PNG transparent → cropped JPEG with neutral fill (FR edge case).
- IU-3: 11 MB JPEG → 413 `file_too_large`.
- IU-4: `.tiff` MIME → 400 `unsupported_format`.
- IU-5: corrupt JPEG (truncated bytes) → 415 `invalid_image`, no orphan files.
- IU-6: 600×400 → 200 with `warning: "low_resolution"`.
- IU-7: 2×2 (degenerate) → 415 `degenerate_dimensions`.
- IU-8: zip-bomb (claims 50000×50000 in header) → 415 `degenerate_dimensions` (caught by 100 MP post-decode guard).
- IU-9: missing `role` form field → 400 `unsupported_role`.
- IU-10: SHA-256 hash matches `hashlib.sha256(file_bytes).hexdigest()` for a known fixture.

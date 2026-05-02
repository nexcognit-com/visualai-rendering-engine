# Quickstart: Music Track Control

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Audience**: developers verifying the feature; operators reproducing SC-001..SC-007 metrics.

---

## Part 1 — Verify zero regression for legacy callers (SC-007)

Run a baseline render through the **existing** non-VisualAI API path (or via the wizard with the Music panel never opened). The audio output MUST be byte-identical to today's pipeline.

```sh
# Direct API call mimicking a non-wizard caller — no bgm_* fields in body
curl -X POST http://localhost:8090/api/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "video_subject": "Diamond engagement ring",
    "video_script": "",
    "mode": "short",
    "video_aspect": "9:16",
    "video_count": 1
  }'
```

After the render completes, listen to the output. **Pass criterion (SC-007)**: the audio carries voiceover plus a randomly-selected bundled BGM at MPT's default 0.2 volume — exactly today's behavior. The existence of the new wizard surface MUST NOT change anything for this path.

---

## Part 2 — Verify wizard "None" mode (SC-002)

```sh
# Terminal 1 — MPT backend on :8090
cd MoneyPrinterTurbo && python main.py

# Terminal 2 — visualai-frontend on :3001 (or auto-rolled port)
cd visualai-frontend && pnpm dev
```

In your browser at `http://localhost:3001`:

1. Click "Short Marketing Video".
2. Fill the wizard subject + voice.
3. Open Step 3's new **Music** panel.
4. Pick **None**.
5. Submit. Wait for render.

**Pass criterion**: the rendered MP4's audio track is voiceover only — no music underneath. Confirmed by:

```sh
# Verify the output has no music in non-voice frequency bands
ffprobe -v quiet -show_entries stream=channels,sample_rate -of csv "<task>/final-1.mp4"
# Compare against a Part 1 baseline render: the "None" version's audio should have lower energy in 100–500 Hz range when voiceover is silent.
```

If you hear music underneath, the wizard didn't honor the "None" selection — file as a regression against FR-005's `bgm_type=""` path.

---

## Part 3 — Verify preset bundled track selection (SC-003)

In the wizard:

1. Step 3 → Music panel → Mode: **Preset**.
2. Pick a specific bundled track from the dropdown (e.g., `output005`).
3. Leave volume at default (20 %).
4. Submit.

**Pass criterion**: the rendered MP4 has THAT specific track audibly mixed under the voiceover. Verify by:

```sh
# Spot-check: extract a 5-second segment from the rendered video and the source track
ffmpeg -ss 10 -t 5 -i "<task>/final-1.mp4" -vn -acodec copy excerpt-rendered.aac
ffmpeg -ss 10 -t 5 -i resource/songs/output005.mp3 -vn -acodec copy excerpt-source.aac
# Listen — you should clearly recognize the source track in the rendered excerpt
```

---

## Part 4 — Verify custom upload (SC-004)

Upload a known MP3 (e.g., a public-domain piece).

```sh
# Pre-stage a test MP3 (or use one you already have)
ls /tmp/test-music.mp3 || curl -L -o /tmp/test-music.mp3 https://example.com/test.mp3
```

In the wizard:

1. Step 3 → Music panel → Mode: **Upload**.
2. Click "Choose audio file" → pick `/tmp/test-music.mp3`.
3. The wizard MUST display: filename, file size, duration in seconds (e.g., "138.4 s"). Hint text MUST indicate whether the track is shorter/longer than typical Mode 2 video duration.
4. Leave volume at default. Submit.

**Pass criteria**:

- Upload validates (no error inline).
- Render proceeds.
- The final MP4 audibly plays YOUR uploaded track underneath the voiceover.
- If your track is shorter than the rendered video, it loops (existing pipeline behavior).
- 3-second fade-out at the end (existing pipeline behavior).

---

## Part 5 — Verify volume control (SC-005)

Generate two renders with the same subject + same uploaded MP3 but different volumes:

| Render | Volume slider | Expected |
|---|---|---|
| A | 20 % (default) | Music subtle under voiceover |
| B | 60 % | Music noticeably louder relative to voice |

**Pass criterion**: when you listen to both back-to-back, render B's music is clearly louder than render A's. Voiceover stays intelligible in both. The 60 %-render MAY produce a "may overpower voice" warning in the wizard at submission time per FR-004 — wizard MUST NOT block submission, only warn.

For quantitative verification (optional):

```sh
# Loudness analysis on the BGM frequency band
ffmpeg -i render-A.mp4 -af "highpass=f=100,lowpass=f=500,loudnorm=print_format=json" -f null - 2>&1 | grep input_i
ffmpeg -i render-B.mp4 -af "highpass=f=100,lowpass=f=500,loudnorm=print_format=json" -f null - 2>&1 | grep input_i
# Render B's input_i (integrated loudness) should be ~5–8 LU higher than render A
```

---

## Part 6 — Verify error surfacing (FR-008, FR-011)

### 6a — Audio file too large

Try uploading a 12 MB MP3.

**Pass criterion**: the wizard rejects with HTTP 413 from the upload endpoint, surfaces "Audio must be under 10 MB" inline, and does NOT proceed to render. Confirms FR-011 + AU-5.

### 6b — Unsupported format

Try uploading a `.flac` or `.aiff` file.

**Pass criterion**: HTTP 400 `unsupported_format`, wizard shows "Only MP3, WAV, OGG, or M4A supported." Confirms AU-6.

### 6c — Corrupt audio file

```sh
echo "not a real audio" > /tmp/broken.mp3
```

Try uploading `/tmp/broken.mp3`.

**Pass criterion**: HTTP 415 `invalid_audio` after the server-side ffprobe rejects. The temp file is NOT left in `storage/uploads/` — verify by `ls storage/uploads/` after the failed upload; no orphan UUID4.mp3 entries from the failed attempt. Confirms AU-7.

---

## Part 7 — Run the smoke tests

```sh
cd MoneyPrinterTurbo
pytest test/controllers/test_uploads_audio.py -v
```

**Expected**: 8 passing tests (AU-1 through AU-8 of [contracts/audio-upload-endpoint.md](./contracts/audio-upload-endpoint.md)). Total wall clock < 30 seconds (synthetic audio fixtures generated on the fly via NumPy + ffmpeg).

If a test fails, the contract section it implements is violated — fix the offending code, not the test.

---

## Part 8 — Verify schema forward-compat (SC-006)

```sh
cd MoneyPrinterTurbo
python3 -c "
from app.models.schema import VideoParams
p = VideoParams(
    video_subject='test',
    bgm_type='file',
    bgm_file='brand-library/tenant_abc/music/intro_v3.mp3',  # future Brand Library path
    bgm_volume=0.4,
)
print('OK:', p.bgm_file, p.bgm_volume)
"
```

**Expected**: Pydantic validates cleanly; prints the future path string and the volume. Confirms FR-009: a future Brand Library path will pass through the v1 model without schema change.

---

## Part 9 — Verify the bundled-track enumeration endpoint

```sh
curl http://localhost:8090/api/v1/bgm/tracks | jq '.count, .tracks[0]'
```

**Expected**:

```json
29
{
  "name": "output000",
  "path": "resource/songs/output000.mp3",
  "duration_seconds": <a real float>
}
```

Confirms MC-8 of [contracts/music-config-contract.md](./contracts/music-config-contract.md).

---

## Operator runbook — adding a new bundled track in v1

When you want to add a new bundled BGM track:

1. Drop the `.mp3` (or `.wav`/`.ogg`/`.m4a`) file into `resource/songs/`.
2. The next call to `GET /api/v1/bgm/tracks` picks it up automatically (no server restart needed at v1; the endpoint reads the directory at request time).
3. The new track is immediately available in the wizard's Preset dropdown.

---

## Operator runbook — Brand Library music asset (v2 forward-compat)

When the Brand Library feature lands and a tenant has a saved music asset at `brand-library/<tenant>/music/<asset>.mp3`:

1. The wizard's music panel MAY (in v2) add a "Brand Library" mode alongside Preset / Upload / None.
2. The wizard sends `bgm_type="file"` + `bgm_file="brand-library/<tenant>/music/<asset>.mp3"`.
3. v1 would render with this path today IF the file exists on disk — but v1 doesn't ship the Brand Library writer, so paths under `brand-library/` resolve to nothing. v2 ships the writer; the wire shape is unchanged.

This keeps the migration zero-cost when Brand Library lands.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Upload returns 415 even on a valid MP3 | `ffprobe` not on PATH | Confirm `which ffprobe` returns a path; FFmpeg must be installed system-wide. The endpoint falls back to MoviePy if ffprobe is missing, but if MoviePy ALSO fails the upload returns 415. |
| Wizard's "duration" hint shows 0 | Endpoint returned `duration_seconds=0` due to ffprobe parse failure | Inspect the endpoint's response body in browser devtools; the bug is upstream of the wizard. |
| Volume slider has no audible effect | The wizard sent `bgm_volume=0.0` on every submit, OR didn't include `bgm_volume` in the body | Inspect the request body in devtools; `bgm_volume` MUST be present and non-zero when slider position > 0. |
| BGM track plays silently | Wizard sent `bgm_volume=0.0` (slider at 0) — equivalent to "None" mode but with bgm_file set | Move slider above 0 and re-submit. |
| Random preset picks the same track every time | Pipeline's random seed is deterministic in some MoviePy paths | Verify via the wizard that `bgm_type="random"` with no `bgm_file`; if same track keeps coming up across renders, file as upstream MPT issue. |
| `GET /api/v1/bgm/tracks` returns 0 tracks | `resource/songs/` is empty or missing | Verify directory exists with `.mp3` files; restore from git history if accidentally cleared. |
| Custom upload works but bundled-track preset doesn't | `bgm_file="resource/songs/output<NNN>.mp3"` is a relative path; the engine SHOULD resolve it | Confirm the wizard sends the path verbatim (devtools network tab); if MPT can't find the file, the path resolution rule may need updating. |

---

## Related contracts

- [contracts/audio-upload-endpoint.md](./contracts/audio-upload-endpoint.md) — `POST /api/v1/uploads/audio` HTTP shape
- [contracts/music-config-contract.md](./contracts/music-config-contract.md) — `bgm_type` / `bgm_file` / `bgm_volume` wire shape + `GET /api/v1/bgm/tracks`
- [Spec 009 — Brand Overlays](../009-brand-overlays/spec.md) — sibling spec; same upload pattern, different MIME table

#!/usr/bin/env bash
# Spec 018 — Mode 4 UGC Avatar Generator (MuseTalk lip-sync)
# Vendored clone + weights download for the lip-sync engine.
#
# Why a script (vs `pip install git+`)?
# MuseTalk's repo has no setup.py / pyproject.toml — it's a clone-and-use
# inference repo. Its requirements.txt also pins tensorflow==2.12.0 and
# numpy==1.23.5, which would crater the L3 venv if installed wholesale.
# This script:
#   1. clones the repo into vendor/musetalk/ at a pinned SHA,
#   2. downloads the model weights (~2 GB) into $MUSETALK_MODEL_DIR,
#   3. installs ONLY the lip-sync runtime deps the wrapper actually
#      needs (torch, diffusers, librosa, soundfile) — without dragging
#      in tensorflow which our existing edge-tts/faster-whisper stack
#      already provides via different paths.
#
# Run from the L3 repo root after creating + activating the .venv.
# On dev hosts without GPU/MPS, you can skip this script entirely and
# leave LIP_SYNC_ENGINE=mock (the wrapper bypasses MuseTalk).

set -euo pipefail

# Pinned SHA — bump deliberately, not via "latest". Verified 2026-05-06
# against TMElyralab/MuseTalk main.
MUSETALK_SHA="${MUSETALK_SHA:-0a89dec45a}"

# Repo root = parent dir of this script's parent.
SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
REPO_ROOT="$( cd -- "${SCRIPT_DIR}/.." &> /dev/null && pwd )"

VENDOR_DIR="${REPO_ROOT}/vendor/musetalk"
WEIGHTS_DIR="${MUSETALK_MODEL_DIR:-${HOME}/.cache/musetalk}"
VENV_PIP="${REPO_ROOT}/.venv/bin/pip3"

if [[ ! -x "${VENV_PIP}" ]]; then
  echo "ERROR: ${VENV_PIP} not found. Activate the L3 venv first." >&2
  exit 1
fi

echo "→ Cloning TMElyralab/MuseTalk @ ${MUSETALK_SHA} into ${VENDOR_DIR}"
mkdir -p "${REPO_ROOT}/vendor"
if [[ -d "${VENDOR_DIR}/.git" ]]; then
  echo "  (vendor exists; fetching pinned SHA)"
  git -C "${VENDOR_DIR}" fetch --depth 1 origin "${MUSETALK_SHA}"
  git -C "${VENDOR_DIR}" checkout "${MUSETALK_SHA}"
else
  git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git "${VENDOR_DIR}"
  git -C "${VENDOR_DIR}" fetch --depth 1 origin "${MUSETALK_SHA}"
  git -C "${VENDOR_DIR}" checkout "${MUSETALK_SHA}"
fi

echo "→ Installing lip-sync runtime deps into the L3 venv"
# Curated subset of MuseTalk's requirements.txt. We deliberately exclude
# tensorflow + tensorboard + opencv-python (replaced by opencv-python-headless
# in some envs; tensorflow conflicts with our edge-tts stack). MuseTalk's
# inference path doesn't actually need tensorflow at runtime — only its
# training/eval scripts do.
"${VENV_PIP}" install --quiet --upgrade \
  "torch>=2.1" \
  "torchaudio>=2.1" \
  "torchvision>=0.16" \
  "diffusers==0.30.2" \
  "accelerate==0.28.0" \
  "transformers==4.39.2" \
  "huggingface_hub==0.30.2" \
  "librosa==0.11.0" \
  "soundfile==0.12.1" \
  "einops"

echo "→ Downloading MuseTalk model weights into ${WEIGHTS_DIR} (~2 GB)"
mkdir -p "${WEIGHTS_DIR}"
# MuseTalk hosts weights on Hugging Face. Use huggingface-cli for resumable
# downloads + checksum verification.
"${VENV_PIP}" install --quiet "huggingface_hub[cli]"
"${REPO_ROOT}/.venv/bin/huggingface-cli" download TMElyralab/MuseTalk \
  --local-dir "${WEIGHTS_DIR}" \
  --local-dir-use-symlinks False \
  || {
    echo "WARN: huggingface-cli download failed. Falling back to manual" >&2
    echo "      instructions: visit https://huggingface.co/TMElyralab/MuseTalk" >&2
    echo "      and download weights into ${WEIGHTS_DIR}." >&2
  }

echo "→ Verifying installation"
"${REPO_ROOT}/.venv/bin/python" - <<'PY'
import sys, os
from pathlib import Path

vendor = Path(os.environ.get("REPO_ROOT", ".")) / "vendor" / "musetalk"
sys.path.insert(0, str(vendor))

try:
    import torch
    print(f"  torch {torch.__version__} backend={'cuda' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')}")
    import diffusers
    print(f"  diffusers {diffusers.__version__}")
    import librosa
    print(f"  librosa {librosa.__version__}")
    print("OK — runtime deps importable.")
except ImportError as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
PY

echo "✓ MuseTalk vendored at ${VENDOR_DIR}"
echo "✓ Weights at ${WEIGHTS_DIR}"
echo
echo "Next: set LIP_SYNC_ENGINE=musetalk in .env to flip the lip_sync.py wrapper from mock to real inference."

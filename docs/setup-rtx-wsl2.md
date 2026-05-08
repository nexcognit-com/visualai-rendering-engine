# RTX 4090 Mobile + WSL2 Ubuntu — VisualAI dev setup

End-to-end runbook for bringing up the three VisualAI repos on a Windows
11 + WSL2 Ubuntu host. Optimized for a single MSI laptop with an RTX 4090
Mobile that will become the primary runner for **Mode 4 (UGC Avatar with
real MuseTalk lip-sync)** and **Mode 3 (long-form 5–10 min videos)** —
neither of which run well on Apple Silicon.

> Read top-to-bottom. Every command is intended to be copy-pasted in
> order. Phases 1–2 happen in Windows; Phases 3–9 happen inside WSL2
> Ubuntu (Cursor's terminal panel after you "Connect to WSL").

---

## TL;DR for the impatient

```text
Windows:  Install Cursor, WSL2, Ubuntu, then Cursor's "WSL" extension.
          In Cursor → command palette → "WSL: Connect to WSL".

Ubuntu:   Install nvidia driver (verify with nvidia-smi), python3.11,
          node 20, pnpm, ffmpeg, imagemagick, gh CLI.

Ubuntu:   gh auth login. Clone the 3 repos to ~/dev/visualai/.

Ubuntu:   scp 3 .env files from your Mac (gitignored, can't be in git).

Ubuntu:   pip install -e . in L2 + L3 ; pnpm install in L1.

Ubuntu:   cd MoneyPrinterTurbo ; ./scripts/install_musetalk.sh.
          Flip LIP_SYNC_ENGINE=mock → musetalk in .env.

Ubuntu:   Start L3 + L2 + L1 in three terminals. Browser → :3000.

Verify:   Mode 4 produces MP4 with REAL lip-sync.
          Mode 3 long-form produces non-repeating B-roll.
```

---

## Phase 1 — Windows side: install Cursor, WSL2, Ubuntu, WSL extension

You install Cursor on **Windows**, not inside Ubuntu. Cursor's UI runs
on Windows; its terminals/files/extensions can target WSL2 via the
Microsoft "WSL" extension. This is the same model VS Code uses.

1. **Install Cursor for Windows** — download from https://cursor.com/.
2. **Enable WSL2 + install Ubuntu** (PowerShell as Administrator):

   ```powershell
   wsl --install -d Ubuntu
   wsl --set-default-version 2
   ```

   Reboot if prompted. Launch the freshly installed **Ubuntu** from the
   Start menu once to create your Linux user + password.

3. **Install NVIDIA driver for WSL2** on Windows (download from
   https://www.nvidia.com/Download/index.aspx — pick your RTX 4090
   Mobile). Reboot. The Windows-side driver is what exposes the GPU
   into WSL2; you do NOT install a Linux driver inside Ubuntu.

4. **Install the WSL extension in Cursor**:
   - Open Cursor on Windows.
   - Extensions panel (`Ctrl+Shift+X`) → search **"WSL"** → install
     the official Microsoft extension.
   - Command palette (`Ctrl+Shift+P`) → run **"WSL: Connect to WSL"**.
     Pick your Ubuntu distro. Cursor's title bar should now show
     `WSL: Ubuntu`. Every terminal you open from now on runs inside
     Ubuntu.

From this point forward, every command in this doc runs in Cursor's
terminal panel **after** the WSL connection is active.

---

## Phase 2 — Ubuntu pre-flight (verify GPU + install system deps)

```sh
# 1. Verify the Windows-side NVIDIA driver is exposed into WSL2.
nvidia-smi
# Expect: RTX 4090 Laptop GPU listed, driver 535+, CUDA 12.x. If this
# fails, fix the Windows driver before continuing — nothing else works
# without it.

# 2. CUDA toolkit (only if you need nvcc / build CUDA kernels;
#    PyTorch installs its own bundled CUDA libs, so this is OPTIONAL
#    for our use case, but harmless to install).
sudo apt update
sudo apt install -y nvidia-cuda-toolkit

# 3. Python 3.11 + venv + pip
sudo apt install -y python3.11 python3.11-venv python3-pip

# 4. Node 20 + pnpm (Layer 1 is Next.js 16 + React 19)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pnpm

# 5. System binaries the rendering engine needs
sudo apt install -y ffmpeg imagemagick git curl

# 6. GitHub CLI for auth + clone
sudo apt install -y gh
gh auth login        # follow the browser flow; pick HTTPS + git
```

---

## Phase 3 — Clone the three repos

```sh
mkdir -p ~/dev/visualai && cd ~/dev/visualai

# L3 — rendering engine (this repo, where the runbook lives)
git clone https://github.com/nexcognit-com/visualai-rendering-engine.git MoneyPrinterTurbo

# L2 — orchestration
git clone https://github.com/nexcognit-com/visualai-orchestration.git

# L1 — Next.js wizard
git clone https://github.com/nexcognit-com/visualai-frontend.git

# All three should be on the active dev branch:
for r in MoneyPrinterTurbo visualai-orchestration visualai-frontend; do
  git -C "$r" checkout 019-longform-10min-fix
  git -C "$r" pull --ff-only
done
```

Verify:

```sh
for r in MoneyPrinterTurbo visualai-orchestration visualai-frontend; do
  echo "--- $r ---"
  git -C "$r" log --oneline -1
done
# Expected HEAD commits (as of 2026-05-08):
#   MoneyPrinterTurbo:        c124ebb feat(longform): extend Mode 3 cap…
#   visualai-orchestration:   693ef52 fix(longform): reduce cross-segment clip repetition…
#   visualai-frontend:        43182ac feat(longform): wizard supports 8min + 10min targets…
```

---

## Phase 4 — Transfer the three `.env` files (out-of-band)

`.env` files are **gitignored** because they contain API keys. They
must be moved across machines manually. Pick ONE of the three options
below — never paste keys through chat / email / Slack.

### Option A (recommended) — `scp` over local Wi-Fi

From your Mac, with both machines on the same network:

```sh
# 1. Find the RTX laptop's WSL2 IP. Inside Ubuntu run:
#       ip addr show eth0 | grep 'inet '
#    (usually 172.x.x.x — that's the WSL2 internal IP, NOT what you
#    want from the Mac. Instead use the laptop's Windows-side LAN IP
#    from `ipconfig` in PowerShell, then enable Windows-→-WSL port
#    forwarding for SSH, OR install OpenSSH server inside Ubuntu and
#    forward port 22 from Windows.)
#
# 2. Easier: install OpenSSH server inside Ubuntu and use Windows port
#    forwarding once. Inside Ubuntu:
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
#
# 3. In Windows PowerShell as Admin (one-time port forward 22 → WSL):
#       netsh interface portproxy add v4tov4 listenport=22 listenaddress=0.0.0.0 \
#         connectport=22 connectaddress=$(wsl hostname -I).Trim()
#       New-NetFirewallRule -Name "WSL SSH" -DisplayName "WSL SSH" \
#         -Enabled True -Direction Inbound -Protocol TCP -LocalPort 22 \
#         -Action Allow

# 4. From the Mac (replace <user> + <rtx-ip>):
cd /Users/amraeid/Dropbox/Dev.lab/Cursor-Cluade/NexCognit-Content-generator/
scp MoneyPrinterTurbo/.env       <user>@<rtx-ip>:~/dev/visualai/MoneyPrinterTurbo/.env
scp visualai-orchestration/.env  <user>@<rtx-ip>:~/dev/visualai/visualai-orchestration/.env
scp visualai-frontend/.env.local <user>@<rtx-ip>:~/dev/visualai/visualai-frontend/.env.local
```

### Option B — encrypted USB stick

Copy the three files onto a USB drive on the Mac, plug it into the
laptop, drag them into the matching folders inside WSL via Windows
Explorer (`\\wsl$\Ubuntu\home\<user>\dev\visualai\…`).

### Option C — re-key from your password manager

Slowest but most auditable. Don't do this for the local-only signing
keys (`LAYER2_JWT_SIGNING_KEY`, `LAYER2_SIGNING_KEY`) — generate fresh
ones on the RTX since they only need to match within that machine.

### Required keys per file

For reference (so you know what you're moving). Values stay private.

**`MoneyPrinterTurbo/.env`** (L3):

```
LAYER3_ENV=local
LAYER3_REQUIRE_TENANT_CONTEXT=true
LAYER3_TRUST_LOCAL_UPSTREAM=true
LAYER2_JWT_SIGNING_KEY=…              # MUST match L2's value
SHUTTERSTOCK_CONSUMER_KEY=…           # optional, only if Mode 5 used
SHUTTERSTOCK_CONSUMER_SECRET=…        # optional
SHUTTERSTOCK_SUBSCRIPTION_ID=…        # optional
FAL_KEY=…                             # optional, for fal.ai paths
LIP_SYNC_ENGINE=mock                  # FLIP TO musetalk after Phase 7
```

**`visualai-orchestration/.env`** (L2):

```
LAYER2_ENV=local
LAYER2_PORT=8089
LAYER2_PUBLIC_BASE_URL=http://127.0.0.1:8089
LAYER1_ORIGIN=http://localhost:3000
LAYER3_BASE_URL=http://127.0.0.1:8090
LAYER2_DEMO_BEARER=demo-bearer-replace-in-production
LAYER2_DEMO_TENANT_ID=demo-tenant
LAYER2_DEMO_USER_ID=demo-user
LAYER2_JWT_SIGNING_KEY=…              # MUST match L3's value
LAYER2_SIGNING_KEY=…                  # pre-signed-URL HMAC; >= 48 hex chars
OPENAI_API_KEY=…
GOOGLE_API_KEY=…
PEXELS_API_KEY=…
PIXABAY_API_KEY=…
TWELVE_LABS_API_KEY=…
TWELVE_LABS_MODEL=Marengo-retrieval-2.7
VISUAL_RELEVANCE_THRESHOLD=0.30
VISUAL_RELEVANCE_MAX_FALLBACKS=1
LAYER25_IMAGE_PROVIDER=nanobanana
LAYER25_NANOBANANA_API_KEY=…
```

**`visualai-frontend/.env.local`** (L1):

```
NEXT_PUBLIC_LAYER2_URL=http://127.0.0.1:8089
NEXT_PUBLIC_LAYER2_DEMO_BEARER=demo-bearer-replace-in-production
NEXT_PUBLIC_LAYER3_VIDEO_BASE=http://127.0.0.1:8090
NEXCOGNIT_BASE_URL=https://middleware.nexcognit.com
NEXCOGNIT_APP_SLUG=visualai
NEXCOGNIT_AGENT_ID_MODE2=…            # only needed when credit-gating turns on
NEXCOGNIT_SERVICE_BEARER=…            # only needed when credit-gating turns on
```

---

## Phase 5 — Install Python + Node dependencies

```sh
# L3 — rendering engine
cd ~/dev/visualai/MoneyPrinterTurbo
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
deactivate

# L2 — orchestration
cd ~/dev/visualai/visualai-orchestration
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
deactivate

# L1 — Next.js wizard
cd ~/dev/visualai/visualai-frontend
pnpm install
```

Both Python repos use a `pyproject.toml` with hatchling — `pip install
-e .` is the right command for editable installs.

---

## Phase 6 — Install MuseTalk (the reason you're on the RTX)

This is the unlock. Apple Silicon can't run MuseTalk's diffusion stack
performantly. The RTX 4090 Mobile renders ~30s of lip-synced video in
~30–60s.

```sh
cd ~/dev/visualai/MoneyPrinterTurbo
source .venv/bin/activate
./scripts/install_musetalk.sh
```

What the installer does (so you know what to expect):

- Clones `TMElyralab/MuseTalk` at a pinned SHA into `vendor/musetalk/`.
- Installs the curated runtime deps (PyTorch with CUDA 12.x bundled,
  diffusers, transformers, librosa, …). PyTorch alone is ~2 GB.
- Downloads ~2 GB of model weights via `huggingface-cli` into
  `~/.cache/musetalk/`.
- Runs a verification step that prints something like:
  `torch 2.4.0 backend=cuda renderer=NVIDIA GeForce RTX 4090 Laptop GPU`.

If verification fails, **stop and read the error**. Common fixes:

- `nvidia-smi` works but PyTorch reports `backend=cpu` → reinstall
  `torch` with the CUDA-12 wheel index:
  `pip install --index-url https://download.pytorch.org/whl/cu124 torch`.
- `huggingface-cli: command not found` → `pip install huggingface_hub`.
- Disk full in `~/.cache/` → WSL2's default disk is small; resize via
  `wsl --shutdown` then expand the VHDX from Windows.

When verification passes, **flip the engine flag** in L3's `.env`:

```sh
sed -i 's/^LIP_SYNC_ENGINE=mock$/LIP_SYNC_ENGINE=musetalk/' .env
deactivate
```

---

## Phase 7 — Start the three services

Open three Cursor terminal panes (or use `tmux` inside one). All three
processes must stay running for the wizard to work end-to-end.

**Pane 1 — L3 (rendering engine, port 8090):**

```sh
cd ~/dev/visualai/MoneyPrinterTurbo
source .venv/bin/activate
python main.py
```

**Pane 2 — L2 (orchestration, port 8089):**

```sh
cd ~/dev/visualai/visualai-orchestration
source .venv/bin/activate
python main.py
```

**Pane 3 — L1 (Next.js wizard, port 3000 or 3001):**

```sh
cd ~/dev/visualai/visualai-frontend
pnpm dev
```

Verify all three are listening:

```sh
ss -tln | grep -E ':(8090|8089|3000|3001)\s'
# Expect 3-4 lines.
```

WSL2 forwards `localhost` to Windows automatically. From your Windows
browser, open **http://localhost:3000** (or 3001 if Next.js fell back).

---

## Phase 8 — Smoke matrix

Run BOTH tests below to confirm the migration is complete. Each
exercises a different pipeline.

### Test 1 — Mode 4 with real MuseTalk lip-sync (the unlock)

1. Browser → http://localhost:3000 → click **UGC Avatar Ad** card.
2. Step 1 (Selfie): record a 5–15s clip via webcam OR drag-drop a
   short selfie video.
3. Step 2 (Script): pick **Auto** + paste a brief like
   *"Caffeine-free organic energy drink for working parents"*.
4. Step 3 (Voice): pick **Ava (English Multilingual)**.
5. Step 4 (Generate). On the RTX, expect ~30–60s for a 30s output.

**Pass criteria**: the final 9:16 MP4 plays inline. The avatar's
**mouth visibly moves with the audio** — that's MuseTalk doing its
job. With the mock engine on the Mac, the mouth was static; on the
RTX it must lip-sync.

### Test 2 — Mode 3 long-form 5-min with the dedup-fix

1. Browser → http://localhost:3000 → click **Long-Form Video** card.
2. Source: **Topic**. Paste e.g.
   *"How a single coffee bean travels from a Colombian farm to your morning cup"*.
3. Duration: **5 min**. Voice: **Ava**. Music: pick any bundled BGM.
4. Generate. Expect ~30–40 min wall-clock.

**Pass criteria**:

- The L2 logs print `dedup_swaps>0` and `unavailable=` should NOT
  appear in any segment summary.
- Watch the final MP4: every B-roll clip should look visibly distinct
  from its neighbours. The pre-fix render had ~7 segments looping the
  same nature shot; post-fix should show ~24 unique clips for a 5-min
  video.

If both tests pass, the RTX is now your primary VisualAI runner. The
Mac becomes a secondary dev host (good for code edits + L1 wizard
work; bad for Mode 4 / heavy Mode 3).

---

## Phase 9 — Day-2 conventions

- **Pulling new commits**: `git -C <repo> pull --ff-only` in each of
  the three repos. The branches advance independently.
- **Updating Python deps**: re-run `pip install -e .` after pulling.
  pyproject.toml changes ship transitively.
- **Updating Node deps**: re-run `pnpm install` after pulling.
- **MuseTalk weight updates**: rare. If `install_musetalk.sh` bumps
  the pinned SHA, re-run it; it skips already-downloaded weights.
- **`.env` drift**: if a teammate adds new keys, you'll see them as
  `KeyError` on startup. Diff `.env.example` (committed) vs your
  `.env` (gitignored) to spot the missing keys, then transfer the
  values out-of-band.
- **GPU monitoring**: `nvidia-smi -l 2` in a spare pane shows VRAM +
  utilization while a render runs. Mode 4 typically uses 4–6 GB VRAM
  with MuseTalk + 1024×576 face crop.

---

## Out of scope for this doc

- Wiring NVENC into MoviePy for faster ffmpeg encoding (separate
  optimization, ~10–20% speedup).
- Production deployment to a cloud GPU host (RunPod / Lambda Labs).
- Auto-syncing storage between the Mac and the RTX. If you want render
  history portable, manually `rsync ~/dev/visualai/MoneyPrinterTurbo/storage/`
  between hosts; nothing in the codebase depends on it being shared.

---

## Recovery / common stumbles

| Symptom | Fix |
|---|---|
| `nvidia-smi: command not found` inside WSL2 | Install the **Windows-side** NVIDIA driver. Don't install nvidia driver in Ubuntu. |
| PyTorch reports `backend=cpu` despite `nvidia-smi` working | `pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision` inside the venv. |
| `gh auth login` fails to open browser | Use `gh auth login --web` and copy the URL into your Windows browser manually. |
| Cursor terminals open in Windows PowerShell, not Ubuntu | Command palette → "WSL: Connect to WSL" again; check the title bar shows `WSL: Ubuntu`. |
| `localhost:3000` from Windows browser hangs | WSL2 port forwarding sometimes lags after sleep; from Ubuntu run `pnpm dev` again, or `wsl --shutdown` from PowerShell + restart Ubuntu. |
| Mode 4 produces video but mouth doesn't move | `LIP_SYNC_ENGINE` is still `mock` in L3's `.env`. Flip to `musetalk` and restart L3. |
| Mode 3 long-form fails with `pre-signed URL expired` | L2's TTL is 4h; if your render legitimately takes longer (e.g. you sleep the laptop), bump `DEFAULT_TTL_SECONDS` in `visualai-orchestration/app/auth/pre_signer.py`. |
| `ffprobe: command not found` | `sudo apt install -y ffmpeg` (provides `ffprobe` too). |

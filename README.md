# AI Interview Assistant

Desktop app: Electron overlay + Python sidecar. Captures system loopback audio, transcribes interviewer speech, detects questions, and streams Claude answers into a capture-excluded overlay.

## Requirements

- Python 3.11+
- Node.js 20+
- Windows 10+ (primary). macOS needs a virtual loopback device such as BlackHole (not bundled).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
copy .env.example .env
cd electron
npm install
```

Put `ANTHROPIC_API_KEY` in `.env` for live answers. Optional: `DEEPGRAM_API_KEY` if you set STT engine to cloud. Never put keys in `config.json`.

## Run (unpacked)

From the repo root:

```powershell
cd electron
npm start
```

This starts Electron, spawns `backend/main.py` with `AIA_USER_DATA` set to Electron userData, and connects to `ws://127.0.0.1:8765`.

Backend only:

```powershell
.\.venv\Scripts\python.exe backend\main.py
```

## Audio

Windows: default speaker WASAPI loopback via `soundcard`. Play meeting audio through the system output, not a microphone.

macOS: install a virtual loopback device (BlackHole or similar) and select it in Settings. This app does not ship a macOS driver.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
cd electron
npm test
```

## Packaging

Whisper weights download on first listen (Hugging Face cache). Packaged builds do not bundle the model.

Sidecar (from repo root, after `pip install pyinstaller`):

```powershell
pyinstaller backend/packaging/aia-backend.spec
```

Output: `dist/aia-backend/` (`aia-backend.exe` on Windows).

Then from `electron/`:

```powershell
npx electron-builder --dir
```

Launch the unpacked app under `electron/dist`. Overlay and backend should start together.

Windows NSIS installer: `npx electron-builder --win nsis`. macOS DMG: build on macOS with `npx electron-builder --mac dmg` (unsigned is fine for MVP).

If PyInstaller is too heavy on this machine, keep using `npm start` with the venv Python sidecar. Packaged spawn looks for `resources/aia-backend/aia-backend.exe` (or `aia-backend` on macOS).

# Cardwright — Architecture

All source in `C:/Users/smyo9/upscaler`.

## Modules
- `main.py` — entrypoint (`from gui import App`).
- `version.py` — APP_NAME, APP_VERSION, GITHUB_REPO, DONATE_URL. **Single source of version.**
- `config.py` — paths (ROOT frozen-aware), MODELS, Auto mode, DPI (2976×4160 = 1200dpi), border/bleed/calibration/shadow constants, load_settings/save_settings (settings.json), ICON_FILE.
- `gui.py` — customtkinter. Classes: `App`, `QueueItem`, `ImportDialog`, `MPCDialog`, `ExportDialog`, `SetupDialog`. Gold/sand palette.
- `upscale.py` — pipeline: normalize → (trim MPC bleed) → Real-ESRGAN x4 → fit 2976×4160 → set 1200 DPI. No GPU: LANCZOS resize.
- `scryfall.py` — fetch by name/link/decklist/Gatherer/Archidekt; `resolve_decklist`, `fetch_archidekt`, `_fetch_gatherer`, `download_to_temp` (handles Drive, timeout 120).
- `mpcfill.py` — mpcfill.com API: `search`, `download`, `fetch_thumb`.
- `print_sheet.py` — `build_pdf` (3×3 / 4×2 layouts, quality, calibration, shadow, sharpen, bleed, duplex, split), `build_calibration`, `build_shadow_test`, `_deepen_black_border`.
- `bootstrap.py` — first-run download of engine + models; `probe_gpu` (Vulkan-only).
- `update.py` — auto-update from GitHub Releases; `_write_swap_script`.
- `installer.iss` — Inno Setup (per-user, no admin). Build with ISCC at `C:/Users/smyo9/AppData/Local/Programs/Inno Setup 6/ISCC.exe`.
- `icon.ico` — gold card+star (embedded).
- Engine/models are NOT in the repo (.gitignore); downloaded on first run.

## AI models (chosen by real comparison)
- Scans (pre 2023-06 LTR): AnimeVideo v3.
- Digital renders: UltraSharp.
- Realistic sets (msc/spm/mar Marvel): Real-ESRGAN x4+ (faces).
- Auto picks by released_at (date) or file size. UltraSharp/high-fidelity are CC-BY-NC (pulled from the Upscayl repo).

## Dependencies
customtkinter 6.0.0, pillow, requests, tkinterdnd2, reportlab, numpy, pyinstaller.
Note: Bash tool = Git Bash — `timeout` resolves to the Unix binary; use absolute paths.

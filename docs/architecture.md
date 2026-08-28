# Cardwright - Architecture

All source in `C:/Users/smyo9/upscaler`.

## Modules
- `main.py` - entrypoint (`from gui import App`).
- `version.py` - APP_NAME, APP_VERSION, GITHUB_REPO, DONATE_URL. **Single source of version.**
- `config.py` - paths (ROOT frozen-aware), MODELS, Auto mode, DPI (2976×4160 = 1200dpi), border/bleed/calibration/shadow constants, load_settings/save_settings (settings.json), ICON_FILE. **Also the only place platform differences are decided**: `IS_WINDOWS`, `NO_WINDOW_KWARGS` and the engine's filename. Everything else imports those rather than testing `sys.platform` again.
- `gui.py` - customtkinter. Classes: `App`, `QueueItem`, `ImportDialog`, `MPCDialog`, `ExportDialog`, `SetupDialog`. Gold/sand palette.
- `upscale.py` - pipeline: normalize → (trim MPC bleed) → Real-ESRGAN x4 → fit 2976×4160 → set 1200 DPI. No GPU: LANCZOS resize.
- `scryfall.py` - fetch by name/link/decklist/Gatherer/Archidekt; `resolve_decklist`, `fetch_archidekt`, `_fetch_gatherer`, `download_to_temp` (handles Drive, timeout 120).
- `mpcfill.py` - mpcfill.com API: `search`, `download`, `fetch_thumb`.
- `ygoprodeck.py` - Yu-Gi-Oh catalogue (db.ygoprodeck.com), same interface as `mpcfill.py` so `CardSearchDialog` can drive either.
- `print_sheet.py` - `build_pdf` (3×3 / 4×2 / 2×1 layouts, quality, calibration, shadow, sharpen, bleed, duplex, split), `build_calibration`, `build_shadow_test`, `_deepen_black_border`. `build_pdf` also writes PNG/JPEG: pass `image_format` and it draws through `_RasterCanvas` instead of reportlab's. That class is a stand-in for the handful of canvas calls `build_pdf` makes, implemented in Pillow, so there is **one** layout implementation rather than a second one to keep in step. Rasterising the finished PDF is not an option: the good rasteriser is PyMuPDF and it is AGPL.
- `bootstrap.py` - first-run download of engine + models; `probe_gpu`. Picks the platform's engine zip; on POSIX it re-applies the exec bit, which `write_bytes` drops.
- `update.py` - auto-update from GitHub Releases; `_write_swap_script`. Returns early off Windows: releases carry Windows assets only.
- `tests/` - `test_platform.py` covers every platform branch, asserting the **Windows** side as well as the POSIX one, from either OS. `.github/workflows/tests.yml` runs it on windows-latest and macos-latest. Run `python -m pytest tests/` before a release.
- `installer.iss` - Inno Setup (per-user, no admin). Build with ISCC at `C:/Users/smyo9/AppData/Local/Programs/Inno Setup 6/ISCC.exe`.
- `theme.py` - design tokens (colour ramp, spacing, radius, type). `gui.py` aliases its historical colour names onto these.
- `icon.ico` - gold card+star (embedded).
- Engine/models are NOT in the repo (.gitignore); downloaded on first run.

## AI models (chosen by real comparison)
- Scans (pre 2023-06 LTR): AnimeVideo v3.
- Digital renders: UltraSharp.
- Realistic sets (msc/spm/mar Marvel): Real-ESRGAN x4+ (faces).
- Auto picks by released_at (date) or file size. UltraSharp/high-fidelity are CC-BY-NC (pulled from the Upscayl repo).

## Dependencies
customtkinter 6.0.0, pillow, requests, tkinterdnd2, reportlab, numpy, pyinstaller.
`numpy` went undeclared in `requirements.txt` until v2.17.5 even though `gui.py` and `print_sheet.py` import it - a clean install from the README could not start the app. It is a floor (`>=1.26`), not a pin: numpy 2.4 needs Python 3.11+, and pinning would raise the project's minimum.
Note: Bash tool = Git Bash - `timeout` resolves to the Unix binary; use absolute paths.

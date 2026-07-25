# ProxyForge — Release Flow

Steps for each version:
1. Bump version in `version.py` + `installer.iss`.
2. Build: `python -m PyInstaller --noconfirm --onefile --windowed --name ProxyForge --icon "...icon.ico" --add-data "...icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 --workpath SCRATCH/build --distpath SCRATCH/dist --specpath SCRATCH main.py`
3. Copy exe to repo root; run `ISCC installer.iss`; delete old installer.
4. `git commit` + `git push`.
5. User creates the GitHub release (bare exe FIRST, then installer — the "_" in `ProxyForge_Setup` sorts after `.exe` so older clients pick the app exe).
6. Update `docs/changelog_ai.md`.

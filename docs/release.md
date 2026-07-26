# ProxyForge — Release Flow

Steps for each version:
1. Bump version in `version.py` + `installer.iss`.
2. Build: `python -m PyInstaller --noconfirm --onefile --windowed --name ProxyForge --icon "...icon.ico" --add-data "...icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 --workpath SCRATCH/build --distpath SCRATCH/dist --specpath SCRATCH main.py`
3. Copy exe to repo root; run `ISCC installer.iss`; delete old installer.
   - ISCC path: `C:/Users/smyo9/AppData/Local/Programs/Inno Setup 6/ISCC.exe`.
   - The exe must not be running (onefile = 2 processes); close ProxyForge first or the copy fails with "Device or resource busy".
4. `git commit` + `git push` (binaries are gitignored; this pushes code + docs).
5. Publish the GitHub release. **gh CLI is installed and authed as Boffo90**, so this can be done directly:
   `gh release create vX.Y.Z --repo Boffo90/proxyforge --title "..." --notes-file NOTES.md ProxyForge.exe installer/ProxyForge_Setup-X.Y.Z.exe`
   The "_" in `ProxyForge_Setup` sorts after `.exe` in the API listing, so the auto-update always picks the bare app exe. gh path: `C:/Program Files/GitHub CLI/gh.exe`. Publishing is user-authorized per release.
6. Update `docs/changelog_ai.md`.

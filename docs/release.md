# Cardwright - Release Flow

## When to release (set 2026-08-13)
**Batch by default.** Work lands on `main` and waits; several changes go out
together rather than one release per fix. On 2026-08-13 five versions shipped in
a day and at least one carried nothing a user needed that hour, which is noise
for anyone watching the repo and makes the auto-updater nag over nothing.

Two exceptions worth releasing on their own:
- **A regression that breaks something people are already hitting.** v2.17.8
  fixed a v2.17.7 feature that only worked if you were slow. Sitting on that
  would have left the previous release broken.
- **A fix for a report someone is waiting on**, where the point is to answer
  the person.

Everything else accumulates. Keep the changelog section for the pending version
up to date as work lands, so the release itself is only the build.

Steps for each version:
1. Bump version in `version.py` + `installer.iss`.
2. Build: `python -m PyInstaller --noconfirm --onefile --windowed --name Cardwright --icon "...icon.ico" --add-data "...icon.ico;." --collect-all customtkinter --collect-all tkinterdnd2 --workpath SCRATCH/build --distpath SCRATCH/dist --specpath SCRATCH main.py`
3. Copy exe to repo root; run `ISCC installer.iss`; delete old installer.
   - ISCC path: `C:/Users/smyo9/AppData/Local/Programs/Inno Setup 6/ISCC.exe`.
   - The exe must not be running (onefile = 2 processes); close Cardwright first or the copy fails with "Device or resource busy".
4. `git commit` + `git push` (binaries are gitignored; this pushes code + docs).
5. Publish the GitHub release. **gh CLI is installed and authed as Boffo90**, so this can be done directly:
   `gh release create vX.Y.Z --repo Boffo90/cardwright --title "..." --notes-file NOTES.md Cardwright.exe installer/Cardwright_Setup-X.Y.Z.exe`
   The "_" in `Cardwright_Setup` sorts after `.exe` in the API listing, so the auto-update always picks the bare app exe. gh path: `C:/Program Files/GitHub CLI/gh.exe`. Publishing is user-authorized per release.
6. Update `docs/changelog_ai.md`.
7. **Publish the SHA-256 of both assets** in the release notes. GitHub computes
   them, so there is nothing to hash by hand (and Defender may refuse to let you
   read the local copy anyway):

   ```
   gh api repos/Boffo90/cardwright/releases/tags/vX.Y.Z --jq '.assets[] | "\(.name)  \(.digest)"'
   ```

   This is the only way a stranger can confirm the file they downloaded is the
   file that was published, and it is what the README and the FAQ tell them to
   check.
8. **Report the new binary to Microsoft as a false positive**, at
   <https://www.microsoft.com/en-us/wdsi/filesubmission>, choosing "Software
   developer" and "Incorrectly detected as malware". Defender flags the app as
   `Trojan:Win32/Wacatac.C!ml`, an ML guess triggered by the PyInstaller
   single-file packaging, the runtime download of the AI engine, and the
   self-replacing updater.

   **This has to be redone every release**: the submission clears one file
   hash, and every build is a new hash. Until a code-signing certificate is in
   place there is no way around that. See `decisions.md` for why Azure Trusted
   Signing is not an option for this author.

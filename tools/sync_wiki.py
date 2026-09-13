"""
Push wiki/ to the GitHub wiki.

The guides live in wiki/ on main so they are versioned and reviewed like the
code. The wiki itself is a separate git repository, Boffo90/cardwright.wiki,
and this copies the pages across and pushes them. Anything edited directly on
the wiki is overwritten, which is what its footer tells readers.

    python tools/sync_wiki.py            # push
    python tools/sync_wiki.py --dry-run  # show what would change, push nothing

One thing it cannot do: create the wiki. GitHub does not make the wiki's git
repository until someone saves a first page through the website, and there is
no API for it. If this reports the repository is missing, open
https://github.com/Boffo90/cardwright/wiki, press "Create the first page",
save it with anything in it, and run this again. Home.md replaces that page.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/Boffo90/cardwright.wiki.git"
SRC = Path(__file__).resolve().parent.parent / "wiki"


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


def main():
    dry = "--dry-run" in sys.argv
    pages = sorted(SRC.glob("*.md"))
    if not pages:
        sys.exit(f"No pages in {SRC}")

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "wiki"
        got = git("clone", "--quiet", REPO, str(dest), check=False)
        if got.returncode != 0:
            sys.exit(
                "The wiki repository does not exist yet.\n\n"
                "GitHub only creates it once a first page has been saved on the "
                "website. Open https://github.com/Boffo90/cardwright/wiki, press "
                '"Create the first page", save it with anything, then run this '
                "again.\n\n" + got.stderr.strip())

        # Mirror, not merge: a page removed from wiki/ goes from the wiki too,
        # or the two drift apart and the footer's promise stops being true.
        for old in dest.glob("*.md"):
            old.unlink()
        for page in pages:
            shutil.copy2(page, dest / page.name)

        git("add", "-A", cwd=dest)
        diff = git("status", "--short", cwd=dest).stdout.strip()
        if not diff:
            print("Wiki already matches wiki/. Nothing to push.")
            return
        print(diff)
        if dry:
            print("\n--dry-run: nothing pushed.")
            return

        head = git("rev-parse", "--short", "HEAD",
                   cwd=SRC.parent, check=False).stdout.strip() or "?"
        git("commit", "--quiet", "-m",
            f"Sync from wiki/ at {head}", cwd=dest)
        git("push", "--quiet", "origin", "HEAD", cwd=dest)
        changed = len(diff.splitlines())
        print(f"\nPushed {changed} changed page(s) of {len(pages)}.")


if __name__ == "__main__":
    main()

"""
Push wiki/ to the GitHub wiki.

The guides live in wiki/ on main so they are versioned and reviewed like the
code. The wiki itself is a separate git repository, Boffo90/cardwright.wiki,
and this copies the pages across and pushes them. Anything edited directly on
the wiki is overwritten, which is what its footer tells readers.

    python tools/sync_wiki.py            # push
    python tools/sync_wiki.py --dry-run  # show what would change, push nothing
    python tools/sync_wiki.py --ahead    # push anyway, docs ahead of the release

Sync AFTER publishing a release, not before. The wiki describes the app people
can download, and main is usually ahead of that. Syncing from main first is how
the comparison feature came to be documented while every released build still
lacked it, which someone then filed as a bug: they were doing exactly what the
wiki said and nothing happened. The check in main() refuses that by default.

One thing it cannot do: create the wiki. GitHub does not make the wiki's git
repository until someone saves a first page through the website, and there is
no API for it. If this reports the repository is missing, open
https://github.com/Boffo90/cardwright/wiki, press "Create the first page",
save it with anything in it, and run this again. Home.md replaces that page.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "https://github.com/Boffo90/cardwright.wiki.git"
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "wiki"
GH = "C:/Program Files/GitHub CLI/gh.exe"


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


def _version(text):
    """(2, 17, 15) from a version string, so two of them can be compared."""
    return tuple(int(n) for n in re.findall(r"[0-9]+", text)[:3])


def released_vs_local():
    """(newest published tag, this tree's APP_VERSION), or (None, local).

    None when GitHub cannot be asked - no network, no gh, no releases yet - in
    which case the caller lets the sync through rather than blocking on a
    check it was unable to make.
    """
    found = re.search(r'APP_VERSION\s*=\s*"([^"]+)"',
                      (ROOT / "version.py").read_text(encoding="utf-8"))
    local = found.group(1) if found else "0"
    try:
        out = subprocess.run(
            [GH, "release", "view", "--repo", "Boffo90/cardwright",
             "--json", "tagName", "--jq", ".tagName"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None, local
    return (out.stdout.strip() or None), local


def main():
    dry = "--dry-run" in sys.argv
    pages = sorted(SRC.glob("*.md"))
    if not pages:
        sys.exit(f"No pages in {SRC}")

    tag, local = released_vs_local()
    if tag and _version(local) > _version(tag) and not (
            dry or "--ahead" in sys.argv):
        sys.exit(
            f"Refusing to sync: this tree is {local} and the newest published "
            f"release is {tag}.\n\n"
            f"The wiki describes the app people can download, so pushing now "
            f"would document features nobody has yet. Publish {local} first, "
            f"then run this again.\n\n"
            f"If the pages really are only about what {tag} already does, "
            f"pass --ahead.")

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

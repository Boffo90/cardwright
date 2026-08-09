"""
Yu-Gi-Oh! card lookup via the YGOPRODeck API.

Mirrors the shape of mpcfill.py (search -> pick a version -> download) so the
GUI can treat both the same way. A Yu-Gi-Oh card is 59x86 mm, so pick that
card size in Export; the upscale pipeline handles the rest.

YGOPRODeck's terms drive two things here:
  - "The rate limit is 20 requests per 1 second" -> requests are throttled.
  - "Do not continually hotlink images ... download and re-host the images
    yourself" -> full images are downloaded once to the user's output folder,
    and search thumbnails are cached on disk so a repeated search never
    re-fetches them.
"""

import time
from pathlib import Path

import requests

from config import TEMP_FOLDER
from version import APP_NAME, APP_VERSION

API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

_HEADERS = {"User-Agent": f"{APP_NAME}/{APP_VERSION} (personal proxy tool)"}

# thumbnails live here between sessions so we never re-hit their CDN
_THUMB_CACHE = TEMP_FOLDER / "ygo_thumbs"

_last_call = 0.0
_MIN_INTERVAL = 0.12          # well under their 20 req/s ceiling


class YGOError(Exception):
    pass


def _throttle():
    global _last_call
    dt = time.time() - _last_call
    if dt < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - dt)
    _last_call = time.time()


def search(query: str, limit: int = 60) -> list[dict]:
    """
    Cards whose name matches `query` (fuzzy). One entry per artwork, since a
    Yu-Gi-Oh card is often reprinted with different art.

    Each item: {name, source, dpi, size, thumb, download, ext, identifier}
    - the same keys the MPC search returns, so the GUI can share the dialog.
    """
    query = query.strip()
    if not query:
        return []

    _throttle()
    try:
        r = requests.get(API, params={"fname": query}, headers=_HEADERS,
                         timeout=30)
    except requests.RequestException as e:
        raise YGOError(str(e)) from e

    if r.status_code == 400:
        return []                       # their "no matches" response
    if r.status_code != 200:
        raise YGOError(f"YGOPRODeck search returned {r.status_code}")

    out = []
    for card in r.json().get("data", []):
        name = card.get("name", "?")
        sets = card.get("card_sets") or []
        set_name = sets[0].get("set_code", "") if sets else card.get("type", "")
        for art in card.get("card_images", []):
            out.append({
                "name": name,
                "source": set_name,
                "dpi": 0,               # unknown; the AI upscale handles it
                "size": 0,
                "thumb": art.get("image_url_small", ""),
                "download": art.get("image_url", ""),
                "ext": "jpg",
                "identifier": str(art.get("id", card.get("id", ""))),
            })
            if len(out) >= limit:
                return out
    return out


def download(card: dict, target) -> Path:
    """Download a chosen artwork at full size to `target`."""
    target = Path(target)
    url = card.get("download")
    if not url:
        raise YGOError(f"No image URL for '{card.get('name')}'")
    _throttle()
    try:
        r = requests.get(url, headers=_HEADERS, timeout=120,
                         allow_redirects=True)
    except requests.RequestException as e:
        raise YGOError(str(e)) from e
    if r.status_code != 200 or len(r.content) < 2000:
        raise YGOError(f"Could not download '{card.get('name')}'")
    target.write_bytes(r.content)
    return target


def fetch_thumb(url: str) -> bytes | None:
    """Search thumbnail, cached on disk - their terms ask us not to keep
    pulling the same images from their servers."""
    if not url:
        return None
    try:
        _THUMB_CACHE.mkdir(parents=True, exist_ok=True)
        cached = _THUMB_CACHE / (url.rsplit("/", 1)[-1] or "thumb.jpg")
        if cached.exists():
            return cached.read_bytes()
        _throttle()
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        cached.write_bytes(r.content)
        return r.content
    except (requests.RequestException, OSError):
        return None

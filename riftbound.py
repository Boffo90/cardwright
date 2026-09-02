"""
Riftbound (Riot's League of Legends TCG) card lookup via the Riftcodex API.

Mirrors the shape of mpcfill.py / ygoprodeck.py (search -> pick a version ->
download) so the GUI can treat all of them the same way.

Why this catalogue and not another:
  - **No API key.** That is the whole reason One Piece, Digimon and Dragon Ball
    are still blocked: apitcg.com demands a key on every call, and a binary
    handed to strangers cannot honour one. Riftcodex is open.
  - **Images are Riot's own**, served from the CDN behind the official card
    gallery at 744x1039 PNG - the same class as Scryfall's 745x1040, and far
    above the 600x825 ceiling every Pokemon catalogue has.

Riftcodex is an unofficial fan project, not affiliated with Riot. Images are
downloaded to the user's own folder rather than hotlinked, the same courtesy
the other sources get.
"""

import time
from pathlib import Path

import requests

from config import TEMP_FOLDER
from version import APP_NAME, APP_VERSION

API = "https://api.riftcodex.com"

_HEADERS = {"User-Agent": f"{APP_NAME}/{APP_VERSION} (personal proxy tool)"}

# thumbnails live here between sessions so a repeated search never re-fetches
_THUMB_CACHE = TEMP_FOLDER / "riftbound_thumbs"

_last_call = 0.0
_MIN_INTERVAL = 0.12

# The card image is ~1.4 MB, far too heavy for a gallery grid. The CDN is
# Sanity, which resizes on request, so a thumbnail is a query parameter.
#
# Downscaling only. Asking it to go UP is a trap worth naming: ?w=3000 answers
# 3000x4190 by upsampling the 744-wide original, and measured edge energy falls
# from 13.17 to 4.41 - it would hand the AI a blurred image dressed as detail.
# Take the native size for the real download and let our own pipeline upscale.
_THUMB_WIDTH = 240


class RiftboundError(Exception):
    pass


def _throttle():
    global _last_call
    dt = time.time() - _last_call
    if dt < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - dt)
    _last_call = time.time()


def _get(path: str, params: dict) -> dict:
    _throttle()
    try:
        r = requests.get(f"{API}{path}", params=params, headers=_HEADERS,
                         timeout=30)
    except requests.RequestException as e:
        raise RiftboundError(str(e)) from e
    if r.status_code == 404:
        return {}
    if r.status_code != 200:
        raise RiftboundError(f"Riftcodex returned {r.status_code}")
    try:
        return r.json()
    except ValueError as e:
        raise RiftboundError("Riftcodex sent a malformed reply") from e


def _thumb_url(image_url: str) -> str:
    if not image_url:
        return ""
    return f"{image_url.split('?')[0]}?w={_THUMB_WIDTH}"


def _entry(card: dict) -> dict | None:
    """One gallery tile, or None when the card has no usable image."""
    url = ((card.get("media") or {}).get("image_url") or "").split("?")[0]
    if not url:
        return None
    st = card.get("set") or {}
    cls = card.get("classification") or {}
    bits = [f"{(st.get('set_id') or '').upper()} #{card.get('collector_number', '?')}"]
    if cls.get("type"):
        bits.append(cls["type"])
    if cls.get("rarity"):
        bits.append(cls["rarity"])
    if card.get("orientation") == "landscape":
        # Said out loud because it changes what comes out of the printer: the
        # art is turned upright to fit a portrait slot, and the finished card
        # is one you hold sideways.
        bits.append("landscape")
    return {
        "name": card.get("name", "?"),
        "source": " · ".join(bits),
        "dpi": 0,
        "size": 0,
        "thumb": _thumb_url(url),
        "download": url,
        "ext": "png",
        "identifier": str(card.get("id") or card.get("riftbound_id") or ""),
    }


def search(query: str, limit: int = 60) -> list[dict]:
    """
    Cards matching `query`, best match first.

    Two calls, merged. `exact` returns EVERY printing of a name and is not
    capped, which is what a gallery wants once you know the card; `fuzzy` is
    capped at 10 by the server but catches partial typing and alternate arts.
    Exact first, so a known name lists its full print run before the
    neighbours - "Jinx - Rebel" has three printings and fuzzy alone shows them
    buried among Demolitionist and Loose Cannon.
    """
    query = query.strip()
    if not query:
        return []

    out, seen = [], set()
    for params in ({"exact": query}, {"fuzzy": query}):
        try:
            data = _get("/cards/name", {**params, "size": 60})
        except RiftboundError:
            if out:
                break          # the first call already gave us something
            raise
        for card in data.get("items") or []:
            entry = _entry(card)
            if entry is None or entry["identifier"] in seen:
                continue
            seen.add(entry["identifier"])
            out.append(entry)
            if len(out) >= limit:
                return out
    return out


def download(card: dict, target) -> Path:
    """Download a chosen card at full size to `target`."""
    target = Path(target)
    url = card.get("download")
    if not url:
        raise RiftboundError(f"No image URL for '{card.get('name')}'")
    _throttle()
    try:
        r = requests.get(url, headers=_HEADERS, timeout=120,
                         allow_redirects=True)
    except requests.RequestException as e:
        raise RiftboundError(str(e)) from e
    if r.status_code != 200 or len(r.content) < 2000:
        raise RiftboundError(f"Could not download '{card.get('name')}'")
    target.write_bytes(r.content)
    return target


def fetch_thumb(url: str) -> bytes | None:
    """Search thumbnail, cached on disk so a repeated search never re-hits
    the CDN."""
    if not url:
        return None
    try:
        _THUMB_CACHE.mkdir(parents=True, exist_ok=True)
        stem = url.split("?")[0].rsplit("/", 1)[-1] or "thumb.png"
        cached = _THUMB_CACHE / stem
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

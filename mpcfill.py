"""
MPC Autofill (mpcfill.com) integration.

Search the community card database and pull chosen versions. Images come
from contributors' Google Drives at print resolution (usually 1200 DPI)
and carry an MPC full-bleed edge, which the upscale pipeline trims.

Only the public read endpoints are used, one card at a time on the user's
own machine — the same requests the website makes.
"""

import time

import requests

API = "https://mpcfill.com"

_HEADERS = {
    "User-Agent": "Cardwright/2.8 (personal proxy tool)",
    "Content-Type": "application/json",
}

_sources_cache = None       # [[pk, True], ...]
_last_call = 0.0


class MPCError(Exception):
    pass


def _throttle():
    global _last_call
    dt = time.time() - _last_call
    if dt < 0.1:
        time.sleep(0.1 - dt)
    _last_call = time.time()


def _sources():
    global _sources_cache
    if _sources_cache is None:
        _throttle()
        r = requests.get(f"{API}/2/sources/", headers=_HEADERS, timeout=30)
        if r.status_code != 200:
            raise MPCError(f"MPC sources returned {r.status_code}")
        rows = r.json().get("results", [])
        _sources_cache = [
            [(s.get("pk") if isinstance(s, dict) else s), True] for s in rows]
    return _sources_cache


def search(query: str, limit: int = 60) -> list[dict]:
    """
    Return card versions matching `query`, best/most-preferred first. Each
    item: {name, source, dpi, size, thumb, download, ext, identifier}.
    """
    query = query.strip()
    if not query:
        return []

    payload = {
        "searchSettings": {
            "searchTypeSettings": {"fuzzySearch": False,
                                   "filterCardbacks": False},
            "sourceSettings": {"sources": _sources()},
            "filterSettings": {"minimumDPI": 0, "maximumDPI": 1500,
                               "maximumSize": 30, "includesTags": [],
                               "excludesTags": [], "languages": []},
        },
        "queries": [{"query": query, "cardType": "CARD"}],
    }
    _throttle()
    r = requests.post(f"{API}/2/editorSearch/", headers=_HEADERS,
                      json=payload, timeout=30)
    if r.status_code != 200:
        raise MPCError(f"MPC search returned {r.status_code}")
    results = r.json().get("results", {})
    if not results:
        return []
    ids = next(iter(results.values())).get("CARD", [])[:limit]
    if not ids:
        return []

    _throttle()
    r2 = requests.post(f"{API}/2/cards/", headers=_HEADERS,
                       json={"cardIdentifiers": ids}, timeout=30)
    if r2.status_code != 200:
        raise MPCError(f"MPC card lookup returned {r2.status_code}")
    cards = r2.json().get("results", {})

    out = []
    for cid in ids:                       # keep the search's ordering
        c = cards.get(cid)
        if not c:
            continue
        out.append({
            "name": c.get("name", "?"),
            "source": c.get("sourceName", ""),
            "dpi": c.get("dpi", 0),
            "size": c.get("size", 0),
            "thumb": c.get("smallThumbnailUrl", ""),
            "download": c.get("downloadLink", ""),
            "ext": (c.get("extension") or "png").lstrip("."),
            "identifier": c.get("identifier", cid),
        })
    return out


def download(card: dict, target) -> "Path":
    """Download a chosen card's full-resolution image to `target`."""
    from pathlib import Path
    target = Path(target)
    url = card.get("download") or \
        f"https://drive.google.com/uc?id={card['identifier']}&export=download"
    _throttle()
    r = requests.get(url, headers={"User-Agent": _HEADERS["User-Agent"]},
                     timeout=120, allow_redirects=True)
    if r.status_code != 200 or len(r.content) < 2000:
        raise MPCError(f"Could not download '{card.get('name')}' from MPC")
    target.write_bytes(r.content)
    return target


def fetch_thumb(url: str) -> bytes | None:
    try:
        _throttle()
        r = requests.get(url, headers={"User-Agent": _HEADERS["User-Agent"]},
                         timeout=20)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None

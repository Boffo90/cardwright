"""
Pokémon card lookup via the TCGdex API.

Mirrors the shape of mpcfill.py / ygoprodeck.py (search -> pick a version ->
download) so the gallery can treat it like any other catalogue. Pokémon cards
are 63x88 mm, the same as Magic, so no card-size switch is needed.

TCGdex was chosen over pokemontcg.io after measuring both:
  - identical image ceiling (600x825 "high"), so resolution did not decide it
  - no API key at all, where pokemontcg.io meters unauthenticated use and its
    terms allow one key per person — unworkable in a distributed desktop app
  - open source, and pokemontcg.io has been absorbed into a commercial product
  - 14 languages with real images, which the card-language picker can drive
  - low.webp thumbnails are ~16 KB against a 161 KB small PNG

600x825 is well under the 2976x4160 a 63x88 mm card needs at 1200 DPI, so the
upscale pipeline normalizes these before the AI pass rather than stretching
afterwards. See `upscale.upscale`.
"""

import time
from pathlib import Path

import requests

from config import TEMP_FOLDER
from version import APP_NAME, APP_VERSION

API = "https://api.tcgdex.net/v2"

_HEADERS = {"User-Agent": f"{APP_NAME}/{APP_VERSION} (personal proxy tool)"}

_THUMB_CACHE = TEMP_FOLDER / "pkmn_thumbs"

# TCGdex publishes no rate limit; throttle anyway rather than hammer a free
# open-source service.
_last_call = 0.0
_MIN_INTERVAL = 0.12

# our language codes -> TCGdex's. Anything else falls back to English: the
# card still arrives, just in English, which is how every other source here
# handles a language it cannot serve.
_LANGS = {"en", "fr", "de", "es", "it", "pt"}

_sets_cache: dict[str, dict[str, str]] = {}


class PokemonError(Exception):
    pass


def _throttle():
    global _last_call
    dt = time.time() - _last_call
    if dt < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - dt)
    _last_call = time.time()


def _lang(code: str | None) -> str:
    return code if code in _LANGS else "en"


def _get(path: str, **params):
    _throttle()
    try:
        r = requests.get(f"{API}/{path}", params=params or None,
                         headers=_HEADERS, timeout=30)
    except requests.RequestException as e:
        raise PokemonError(str(e)) from e
    if r.status_code != 200:
        raise PokemonError(f"TCGdex returned {r.status_code}")
    return r.json()


def _set_names(lang: str) -> dict[str, str]:
    """set id -> printable name. One request per language, then cached.

    A card's brief record carries no set, and fetching each card's full record
    would be one request per tile. The whole set list is 34 KB.
    """
    if lang not in _sets_cache:
        try:
            _sets_cache[lang] = {s["id"]: s.get("name", s["id"])
                                 for s in _get(f"{lang}/sets")}
        except PokemonError:
            _sets_cache[lang] = {}
    return _sets_cache[lang]


def search(query: str, limit: int = 60, lang: str | None = None) -> list[dict]:
    """
    Cards whose name matches `query`.

    Each item: {name, source, dpi, size, thumb, download, ext, identifier} —
    the keys the search gallery expects from every catalogue.
    """
    query = query.strip()
    if not query:
        return []

    code = _lang(lang)
    cards = _get(f"{code}/cards", name=f"like:{query}")
    if not cards and code != "en":
        code = "en"
        cards = _get("en/cards", name="like:" + query)

    names = _set_names(code)

    out = []
    for c in cards:
        image = c.get("image")
        if not image:
            # Plenty of records carry no artwork at all; they would be empty
            # tiles in the gallery.
            continue
        set_id = c["id"].rsplit("-", 1)[0]
        bits = [names.get(set_id, set_id)]
        if c.get("localId"):
            bits.append(f"#{c['localId']}")
        if code != "en":
            bits.append(code.upper())
        out.append({
            "name": c.get("name", "?"),
            "source": " · ".join(bits),
            "dpi": 0,
            "size": 0,
            # webp keeps a 60-tile gallery light; the pick gets the PNG
            "thumb": f"{image}/low.webp",
            "download": f"{image}/high.png",
            "ext": "png",
            "identifier": c["id"],
        })
        if len(out) >= limit:
            break
    return out


def download(card: dict, target) -> Path:
    """Download a chosen card at full size to `target`."""
    target = Path(target)
    url = card.get("download")
    if not url:
        raise PokemonError(f"No image URL for '{card.get('name')}'")
    _throttle()
    try:
        r = requests.get(url, headers=_HEADERS, timeout=120,
                         allow_redirects=True)
    except requests.RequestException as e:
        raise PokemonError(str(e)) from e
    if r.status_code != 200 or len(r.content) < 2000:
        raise PokemonError(f"Could not download '{card.get('name')}'")
    target.write_bytes(r.content)
    return target


def fetch_thumb(url: str) -> bytes | None:
    """Gallery thumbnail, cached on disk so a repeated search is free."""
    if not url:
        return None
    try:
        _THUMB_CACHE.mkdir(parents=True, exist_ok=True)
        # the url ends .../<set>/<number>/low.webp, so the last segment alone
        # would collide across cards
        parts = url.rstrip("/").split("/")
        cached = _THUMB_CACHE / ("-".join(parts[-4:]).replace(".", "_") + ".webp")
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

"""
Scryfall integration.

Turns a user-provided reference (a scryfall.com card link, an api URL, a
direct image URL, or just a card name) into one or more downloaded PNG
images ready to be upscaled.
"""

import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import (
    SCRYFALL_API,
    SCRYFALL_HEADERS,
    SCRYFALL_DELAY,
    TEMP_FOLDER,
)


class ScryfallError(Exception):
    pass


# Scryfall language codes (used to detect the /lang/ segment in card URLs)
SCRYFALL_LANGS = {
    "en", "es", "fr", "de", "it", "pt", "ja", "ko", "ru",
    "zhs", "zht", "he", "la", "grc", "ar", "sa", "ph", "qya",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _slug(text: str) -> str:
    """Filesystem-safe version of a card name (keeps spaces, drops junk)."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r'[<>:"/\\|?*]', "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _get(url: str, **kwargs) -> requests.Response:
    time.sleep(SCRYFALL_DELAY)
    r = requests.get(url, headers=SCRYFALL_HEADERS, timeout=30, **kwargs)
    return r


def looks_like_scryfall(text: str) -> bool:
    text = text.strip().lower()
    return (
        "scryfall.com" in text
        or "scryfall.io" in text
        or not _is_path(text)
    )


def _is_path(text: str) -> bool:
    try:
        return Path(text).exists()
    except OSError:
        return False


# --------------------------------------------------------------------------
# resolving a reference to a Scryfall card object
# --------------------------------------------------------------------------

def _card_from_reference(ref: str) -> dict:
    ref = ref.strip()

    # 1) A scryfall.com card page URL:
    #    English:  https://scryfall.com/card/<set>/<number>/<slug>
    #    Foreign:  https://scryfall.com/card/<set>/<number>/<lang>/<slug>
    m = re.search(
        r"scryfall\.com/card/([^/?#]+)/([^/?#]+)(?:/([^/?#]+))?", ref, re.I)
    if m:
        setcode, number, third = m.group(1), m.group(2), m.group(3)
        lang = third.lower() if third and third.lower() in SCRYFALL_LANGS else None

        url = f"{SCRYFALL_API}/cards/{setcode}/{number}"
        if lang and lang != "en":
            url += f"/{lang}"

        r = _get(url)
        if r.status_code != 200:
            where = f"{setcode}/{number}" + (f"/{lang}" if lang else "")
            raise ScryfallError(f"Card not found for {where}")
        return r.json()

    # 2) An api.scryfall.com/cards/... URL -> hit it directly
    if "api.scryfall.com/cards" in ref:
        r = _get(ref)
        if r.status_code != 200:
            raise ScryfallError(f"Scryfall API returned {r.status_code}")
        return r.json()

    # 3) A decklist-style line "Name (SET) number [tag]" -> EXACT printing.
    #    This is what identifies alternate arts / promos, so it must win over
    #    the fuzzy name search (which would return the default printing).
    entries, _ = parse_decklist(ref)
    if entries:
        e = entries[0]
        r = _get(f"{SCRYFALL_API}/cards/{e['set']}/{e['number']}")
        if r.status_code == 200:
            return r.json()
        # fall through to name search if that exact printing doesn't exist

    # 4) A plain card name -> fuzzy named search
    r = _get(f"{SCRYFALL_API}/cards/named", params={"fuzzy": ref})
    if r.status_code == 404:
        raise ScryfallError(f'No card matched "{ref}"')
    if r.status_code != 200:
        raise ScryfallError(f"Scryfall API returned {r.status_code}")
    return r.json()


def _png_urls(card: dict) -> list[tuple[str, str]]:
    """
    Returns a list of (image_url, suffix) for a card.
    Double-faced cards yield two entries (front / back).
    """
    results = []

    if "image_uris" in card and card["image_uris"].get("png"):
        results.append((card["image_uris"]["png"], ""))
    elif "card_faces" in card:
        faces = card["card_faces"]
        labels = ["-front", "-back"] if len(faces) == 2 else \
                 [f"-face{i+1}" for i in range(len(faces))]
        for face, label in zip(faces, labels):
            uris = face.get("image_uris") or {}
            if uris.get("png"):
                results.append((uris["png"], label))

    if not results:
        raise ScryfallError("No PNG image available for this card")

    return results


# --------------------------------------------------------------------------
# language
# --------------------------------------------------------------------------

def ref_names_a_printing(ref: str) -> bool:
    """
    True when the reference picks a specific printing — a URL, or a decklist
    line with a set and collector number. Those are deliberate choices and
    must never be second-guessed; only a bare card name is up for grabs.
    """
    if "scryfall.com" in ref.lower() or "scryfall.io" in ref.lower():
        return True
    if "gatherer.wizards.com" in ref.lower():
        return True
    entries, _ = parse_decklist(_extract_tags(ref)[0])
    return bool(entries)


def _ref_pins_language(ref: str) -> bool:
    """
    True when the reference itself names a language — a /ja/ Scryfall card
    URL, or a raw api.scryfall.com URL the caller built. An explicit link
    always beats the global preference: someone who pastes the Japanese
    printing wants the Japanese printing.
    """
    m = re.search(
        r"scryfall\.com/card/[^/?#]+/[^/?#]+/([^/?#]+)", ref, re.I)
    if m and m.group(1).lower() in SCRYFALL_LANGS:
        return True
    return "api.scryfall.com/cards" in ref


def _localize(card: dict, lang: str | None) -> tuple[dict, bool]:
    """
    Swap a resolved card for its printing in `lang`.

    Returns (card, fell_back). Scryfall has no bulk way to ask for a
    language — /cards/collection identifiers don't take one — so this is a
    per-card round trip on top of whatever resolved the card in the first
    place. At SCRYFALL_DELAY that is ~0.1 s per unique printing.

    A miss is normal, not an error: promos, Secret Lairs and older sets were
    frequently English-only. Callers report the fallbacks rather than failing.
    """
    if not lang or lang == "en" or card.get("lang") == lang:
        return card, False

    setcode = card.get("set")
    number = card.get("collector_number")
    if not setcode or not number:
        return card, True

    r = _get(f"{SCRYFALL_API}/cards/{setcode}/{number}/{lang}")
    if r.status_code == 200:
        localized = r.json()
        # Guard against a printing that exists but has no usable image in
        # that language — better the English art than no card at all.
        try:
            _png_urls(localized)
        except ScryfallError:
            return card, True
        return localized, False

    return card, True


# --------------------------------------------------------------------------
# best scan
# --------------------------------------------------------------------------
# Scryfall serves every PNG at the same 745x1040, so pixel dimensions say
# nothing about quality — what varies is how good the underlying scan is.
# Two signals, and both are needed:
#
#   image_status  drops the ones that aren't the card at all. A "placeholder"
#                 can easily outweigh a real scan (Silence: the m11
#                 placeholder is 810 KB, the real m14 scan 801 KB), so
#                 filtering by status has to happen BEFORE weighing bytes.
#   Content-Length  at identical dimensions and a lossless format, more bytes
#                 means more actual detail. A HEAD request gets it without
#                 transferring the image.

_IMAGE_STATUS_RANK = {"highres_scan": 0, "lowres": 1}

# Cards like basic lands have dozens of printings; ranking by metadata first
# and only weighing this many keeps a name lookup to a handful of HEADs.
_BEST_SCAN_CANDIDATES = 8


def _printings(name: str, lang: str | None) -> list[dict]:
    """Every printing of `name`, restricted to `lang` when one is given."""
    q = f'!"{name}"'
    if lang:
        q += f" lang:{lang}"
    r = _get(f"{SCRYFALL_API}/cards/search", params={
        "q": q, "unique": "prints", "include_multilingual": "true"})
    if r.status_code != 200:
        return []
    return r.json().get("data", [])


def _illustration(card: dict) -> str | None:
    """A card's illustration id (double-faced cards carry it per face)."""
    if card.get("illustration_id"):
        return card["illustration_id"]
    for face in card.get("card_faces") or []:
        if face.get("illustration_id"):
            return face["illustration_id"]
    return None


def _png_bytes(card: dict) -> int:
    """Size of a card's front PNG via HEAD, or 0 if it can't be measured."""
    try:
        url, _ = _png_urls(card)[0]
    except (ScryfallError, IndexError):
        return 0
    try:
        time.sleep(SCRYFALL_DELAY)
        r = requests.head(url, headers=SCRYFALL_HEADERS, timeout=15,
                          allow_redirects=True)
        return int(r.headers.get("Content-Length") or 0)
    except (requests.RequestException, ValueError):
        return 0


def best_printing(card: dict, lang: str | None,
                  status_callback=None) -> dict:
    """
    Swap a card for whichever of its printings has the best scan.

    Only ever called for a bare card name, where no particular printing was
    asked for. A decklist line or a link names an exact printing and is left
    alone — the user already chose.

    Falls back to `card` unchanged whenever the search turns up nothing
    usable, so this can never make a lookup fail.
    """
    name = card.get("name")
    if not name:
        return card

    candidates = _printings(name, lang)
    if not candidates and lang and lang != "en":
        candidates = _printings(name, "en")
    if not candidates:
        return card

    # Real scans only.
    usable = [c for c in candidates
              if c.get("image_status") in _IMAGE_STATUS_RANK
              and (c.get("image_uris") or c.get("card_faces"))]
    if not usable:
        return card

    # Same artwork only. This is a scan-quality upgrade, not an art swap —
    # "Silence" in English otherwise lands on a Secret Lair with completely
    # different art, which is not what someone typing a card name asked for.
    illus = _illustration(card)
    if illus:
        same_art = [c for c in usable if _illustration(c) == illus]
        if same_art:
            usable = same_art

    # Weigh bytes only WITHIN the best tier available. Across tiers it would
    # misjudge: a grainy low-res scan can out-weigh a clean high-res one,
    # since noise is exactly what PNG compresses worst.
    best_tier = min(_IMAGE_STATUS_RANK[c["image_status"]] for c in usable)
    usable = [c for c in usable
              if _IMAGE_STATUS_RANK[c["image_status"]] == best_tier]

    # Newest first, so the shortlist cut keeps the most recent printings.
    usable.sort(key=lambda c: c.get("released_at") or "", reverse=True)
    shortlist = usable[:_BEST_SCAN_CANDIDATES]

    if len(shortlist) == 1:
        return shortlist[0]

    if status_callback:
        status_callback(f"Comparing {len(shortlist)} printings...")

    best, best_size = card, -1
    for c in shortlist:
        size = _png_bytes(c)
        if size > best_size:
            best, best_size = c, size

    return best if best_size > 0 else shortlist[0]


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def fetch(ref: str, status_callback=None, lang: str | None = None,
          best_scan: bool = False) -> tuple[list[Path], dict]:
    """
    Resolve `ref` and download the full-resolution PNG(s) into TEMP_FOLDER.

    Returns (paths, meta):
      paths -> local files (one per card face)
      meta  -> {"released_at": "YYYY-MM-DD" | None, "set": code | None}
               (used by Auto mode to pick the model)
    """
    ref = ref.strip()

    # Direct image URL (cards.scryfall.io/...png) -> just download it
    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https") and parsed.path.lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp")
    ):
        if status_callback:
            status_callback("Downloading image...")
        name = Path(parsed.path).name
        return [_download(ref, TEMP_FOLDER / name)], {"released_at": None, "set": None}

    # Gatherer links resolve via multiverse id / set+number+lang, with the
    # Gatherer image itself as a last-resort fallback
    g = _gatherer_parse(ref)
    if g:
        return _fetch_gatherer(g, status_callback)

    if status_callback:
        status_callback("Looking up card...")

    card = _card_from_reference(ref)

    # A bare name doesn't choose a printing, so it can be upgraded to the one
    # with the best scan (which resolves the language at the same time).
    if best_scan and not ref_names_a_printing(ref):
        card = best_printing(card, lang, status_callback)

    # Otherwise a name or a plain decklist line resolves to the English
    # printing and the global preference goes on top. A link that already
    # names a language is left alone.
    elif lang and not _ref_pins_language(ref):
        if status_callback:
            status_callback(f"Looking for the {lang} printing...")
        card, _ = _localize(card, lang)

    # keep the finish marker (*E* / *F*) in the filename if one was given
    _, finish = _extract_tags(ref)

    return _download_card(card, status_callback, finish)


def _download_card(card: dict, status_callback=None, finish=None):
    """Download all faces of a resolved card object. Returns (paths, meta)."""
    base = f"{_slug(card['name'])}-{card.get('set','')}-{card.get('collector_number','')}"
    if card.get("lang") and card["lang"] != "en":
        base += f"-{card['lang']}"
    if finish:
        base += f"-{finish}"

    paths = []
    for url, label in _png_urls(card):
        target = TEMP_FOLDER / f"{base}{label}.png"
        if status_callback:
            status_callback(f"Downloading {card['name']}{label}...")
        paths.append(_download(url, target))

    return paths, {"released_at": card.get("released_at"), "set": card.get("set")}


def _download(url: str, target: Path) -> Path:
    r = _get(url)
    if r.status_code != 200:
        raise ScryfallError(f"Download failed ({r.status_code})")
    target.write_bytes(r.content)
    return target


# ==========================================================================
# GATHERER LINKS
# ==========================================================================
# Two URL styles:
#   classic: gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid=226399
#   new:     gatherer.wizards.com/M11/ja-jp/149/lightning-bolt
#
# Resolution: prefer Scryfall (its /cards/multiverse/{id} endpoint keeps the
# printed language, and its images are the best available). If Scryfall lacks
# the card or its image, fall back to Gatherer's own image handler, which
# serves 744px WEBP since the 2024+ redesign.

GATHERER_IMAGE = ("https://gatherer.wizards.com/Handlers/Image.ashx"
                  "?multiverseid={mid}&type=card")

# gatherer locale segment -> scryfall language code
_GATHERER_LOCALES = {
    "en-us": "en", "ja-jp": "ja", "ko-kr": "ko", "ru-ru": "ru",
    "zh-cn": "zhs", "zh-tw": "zht", "pt-br": "pt", "es-es": "es",
    "fr-fr": "fr", "de-de": "de", "it-it": "it",
}


def _gatherer_parse(ref: str):
    """Returns {'mid': int} or {'set','number','lang','name'} for Gatherer
    URLs. The trailing name slug is kept because it is the only part of a
    new-style link Scryfall is guaranteed to understand — see _fetch_gatherer."""
    if "gatherer.wizards.com" not in ref.lower():
        return None

    m = re.search(r"multiverseid=(\d+)", ref, re.I)
    if m:
        return {"mid": int(m.group(1))}

    m = re.search(
        r"gatherer\.wizards\.com/([^/?#]+)/([^/?#]+)/([^/?#]+)(?:/([^/?#]+))?",
        ref, re.I)
    if m and m.group(1).lower() not in ("pages", "handlers"):
        setcode, locale, number, slug = m.groups()
        lang = _GATHERER_LOCALES.get(locale.lower(), locale.lower()[:2])
        return {"set": setcode.lower(), "number": number, "lang": lang,
                "name": (slug or "").replace("-", " ").strip()}

    return None


def _printing_by_name(name: str, number=None, lang=None, status_callback=None):
    """Resolve a card by name, preferring the printing with `number`.

    Fuzzy, deliberately: the name comes out of a URL slug, so apostrophes and
    commas are already gone ("tyvars-stand" -> "Tyvar's Stand").
    """
    if status_callback:
        status_callback("Set code not on Scryfall — looking up by name...")
    r = _get(f"{SCRYFALL_API}/cards/named", params={"fuzzy": name})
    if r.status_code != 200:
        return None
    card = r.json()

    if number:
        prints = card.get("prints_search_uri")
        if prints:
            pr = _get(prints)
            if pr.status_code == 200:
                for c in pr.json().get("data", []):
                    if str(c.get("collector_number")) == str(number):
                        card = c
                        break

    if lang and lang != "en":
        card, _ = _localize(card, lang)
    return card


def _fetch_gatherer(g: dict, status_callback=None):
    """
    A Gatherer link yields the GATHERER image where one exists — that is the
    whole point of pasting one. Scryfall is consulted for the multiverse id
    (needed to fetch the image) and for naming / Auto-mode metadata.

    Where Gatherer has no image, Scryfall's is served instead rather than
    refusing the card: Gatherer never catalogued Secret Lairs, promos or foil
    printings, so a link to one has no multiverse id behind it. That is the
    same policy the decklist import already follows.
    """
    if status_callback:
        status_callback("Resolving Gatherer link...")

    card = None
    mid = g.get("mid")
    if mid is not None:
        r = _get(f"{SCRYFALL_API}/cards/multiverse/{mid}")
        if r.status_code == 200:
            card = r.json()
    else:
        # new-style link (set/lang/number): ask Scryfall for the printing so
        # we can read its multiverse id, then pull that image from Gatherer
        url = f"{SCRYFALL_API}/cards/{g['set']}/{g['number']}"
        if g["lang"] and g["lang"] != "en":
            url += f"/{g['lang']}"
        r = _get(url)
        if r.status_code == 200:
            card = r.json()
        elif g.get("name"):
            # Gatherer's set abbreviations are its own and do not always match
            # Scryfall's: Urza's Saga is UZ on Gatherer and usg on Scryfall, so
            # set+number never resolves. The card name is in the link too, and
            # it is the part both sites agree on.
            card = _printing_by_name(g["name"], g.get("number"), g.get("lang"),
                                     status_callback)
        if card:
            mids = card.get("multiverse_ids") or []
            mid = mids[0] if mids else None

    if mid is None:
        if card:
            if status_callback:
                status_callback("Not on Gatherer — using the Scryfall image...")
            return _download_card(card, status_callback)
        raise ScryfallError(
            "Could not find that card from the Gatherer link — neither "
            "Gatherer nor Scryfall recognises it.")

    if card:
        base = f"{_slug(card['name'])}-{card.get('set','')}-{card.get('collector_number','')}"
        if card.get("lang") and card["lang"] != "en":
            base += f"-{card['lang']}"
        meta = {"released_at": card.get("released_at"), "set": card.get("set")}
    else:
        base = f"gatherer-{mid}"
        meta = {"released_at": None, "set": None}

    try:
        return _gatherer_image(mid, base, status_callback), meta
    except ScryfallError:
        # the id resolved but the handler served no image; if Scryfall knows
        # the card, that beats handing back an error
        if card is None:
            raise
        if status_callback:
            status_callback("Gatherer has no image — using Scryfall's...")
        return _download_card(card, status_callback)


def _gatherer_image(mid: int, base: str, status_callback=None) -> list[Path]:
    """Download Gatherer's card image (webp) and convert it to PNG."""
    import io
    from PIL import Image

    if status_callback:
        status_callback("Downloading from Gatherer...")

    r = requests.get(
        GATHERER_IMAGE.format(mid=mid),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=30,
    )
    if r.status_code != 200 or r.content[:5].lower().startswith(b"<html"):
        raise ScryfallError(f"Gatherer image not available for id {mid}")

    target = TEMP_FOLDER / f"{base}.png"
    Image.open(io.BytesIO(r.content)).convert("RGBA").save(target, "PNG")
    return [target]


# ==========================================================================
# DECKLIST IMPORT
# ==========================================================================
# Parses lines exported by deckbuilders / proxy sites, e.g.:
#
#     1 Winota, Joiner of Forces (PRM) 80807 [matte]
#     3 Plains (MSC) 866 [matte]
#     1 Ajani, Nacatl Pariah // Ajani, Nacatl Avenger (MH3) 442 [matte]
#
# and resolves each to the EXACT printing on Scryfall via set + collector
# number (so promos / alternate arts come out right, not the default print).

# qty (optional) | name | (SET) | collector-number | [tag] (optional, ignored)
# Trailing markers we accept and ignore for lookup, in any order/quantity:
#   [matte] [foil] ...   -> print-finish notes from the proxy site
#   *E* *F* ...          -> deckbuilder markers (Etched / Foil)
# The collector number already identifies the exact printing (an etched card
# has its own number), so these only affect the label we show.
_TAGS_RE = re.compile(r"(?:\s+(?:\[[^\]]*\]|\*[^*]*\*))+\s*$")

_DECK_RE = re.compile(
    r"^\s*(?:(\d+)\s*[xX]?\s+)?(.+?)\s+\(([^)]+)\)\s+(\S+)\s*$"
)

_FINISH_LABELS = {"E": "etched", "F": "foil", "S": "surge foil"}


def _extract_tags(s: str):
    """Split trailing [..] / *..* markers off a line. Returns (line, finish)."""
    finish = None
    m = _TAGS_RE.search(s)
    if m:
        tags = m.group(0)
        s = s[: m.start()].strip()
        for code, label in _FINISH_LABELS.items():
            if f"*{code}*" in tags.upper():
                finish = label
                break
    return s, finish


def parse_decklist(text: str):
    """Return (entries, bad_lines). Entry: dict(qty, name, set, number, finish)."""
    entries, bad = [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s, finish = _extract_tags(s)
        m = _DECK_RE.match(s)
        if not m:
            bad.append(line.strip())
            continue
        qty = int(m.group(1)) if m.group(1) else 1
        entries.append({
            "qty": qty,
            "name": m.group(2).strip(),
            "set": m.group(3).strip().lower(),
            "number": m.group(4).strip(),
            "finish": finish,
        })
    return entries, bad


def _post_collection(identifiers: list[dict]) -> dict:
    time.sleep(SCRYFALL_DELAY)
    r = requests.post(
        f"{SCRYFALL_API}/cards/collection",
        headers={**SCRYFALL_HEADERS, "Content-Type": "application/json"},
        json={"identifiers": identifiers},
        timeout=30,
    )
    if r.status_code != 200:
        raise ScryfallError(f"Scryfall collection API returned {r.status_code}")
    return r.json()


def _related_tokens(card_objects, status_callback=None) -> list[dict]:
    """
    The tokens a set of cards makes, deduped, as resolved card objects.

    Scryfall hangs these off `all_parts`, so no guessing is involved — a card
    that makes no tokens simply has none. Fetched with one bulk /collection
    call rather than one request per token, since identifiers accept `id`.
    """
    ids, seen = [], set()
    for c in card_objects:
        for part in c.get("all_parts") or []:
            tid = part.get("id")
            if part.get("component") == "token" and tid and tid not in seen:
                seen.add(tid)
                ids.append({"id": tid})
    if not ids:
        return []

    if status_callback:
        status_callback(f"Fetching {len(ids)} token(s)…")

    fetched = []
    for i in range(0, len(ids), 75):
        try:
            data = _post_collection(ids[i:i + 75])
        except ScryfallError:
            break          # tokens are a bonus; never fail the import over them
        fetched.extend(data.get("data", []))

    # Three cards that each make a Goblin point at the Goblin printed in their
    # own set — three different ids, one actual token. Collapse those, keeping
    # the newest printing (the best scan, same reasoning as the Best scan
    # switch).
    #
    # NOT by name alone: "Elemental" has 94 printings but 26 genuinely
    # different tokens (3/1, 5/5, */*, 2/2 ...), and collapsing those would
    # hand the user the wrong one. The key is what actually distinguishes a
    # token on the table.
    best = {}
    for t in fetched:
        key = (t.get("name"), t.get("type_line"), t.get("power"),
               t.get("toughness"), t.get("oracle_text"))
        prev = best.get(key)
        if prev is None or (t.get("released_at") or "") > (prev.get("released_at") or ""):
            best[key] = t
    return list(best.values())


def resolve_decklist(text: str, status_callback=None, lang: str | None = None,
                     tokens: bool = False, source: str = "scryfall"):
    """
    Parse and resolve a decklist.

    Returns (cards, not_found, bad_lines, english_only, from_scryfall)
    where each card is:
        {
          "display":   "3x Plains"  (or just the name),
          "qty":       int,
          "downloads": [(basename, png_url), ...]   # 2 entries for DFCs
        }

    `english_only` lists the cards that had no printing in `lang` and came
    back in English instead — a normal outcome worth surfacing, since a deck
    that silently mixes languages looks like a bug to the user.
    """
    entries, bad = parse_decklist(text)

    # dedupe by (set, number), summing quantities, preserving order
    seen, order = {}, []
    for e in entries:
        key = (e["set"], e["number"])
        if key in seen:
            seen[key]["qty"] += e["qty"]
        else:
            seen[key] = dict(e)
            order.append(key)

    ids = [{"set": s, "collector_number": n} for (s, n) in order]

    resolved = {}
    not_found = []
    for i in range(0, len(ids), 75):
        chunk = ids[i:i + 75]
        if status_callback:
            status_callback(f"Resolving cards {i + len(chunk)}/{len(ids)}…")
        data = _post_collection(chunk)
        for c in data.get("data", []):
            resolved[(c["set"], c["collector_number"])] = c

    cards = []
    english_only = []
    from_scryfall = []
    for i, key in enumerate(order):
        e = seen[key]
        c = resolved.get(key)
        if not c:
            not_found.append(f'{e["name"]} ({e["set"].upper()}) {e["number"]}')
            continue

        if lang and lang != "en":
            if status_callback:
                status_callback(f"Localizing {i + 1}/{len(order)}…")
            c, fell_back = _localize(c, lang)
            if fell_back:
                english_only.append(
                    f'{c["name"]} ({c["set"].upper()}) {c["collector_number"]}')

        base = f"{_slug(c['name'])}-{c['set']}-{c['collector_number']}"
        if c.get("lang") and c["lang"] != "en":
            base += f"-{c['lang']}"
        if e.get("finish"):
            base += f"-{e['finish']}"

        try:
            downloads = [(f"{base}{label}", url) for url, label in _png_urls(c)]
        except ScryfallError:
            not_found.append(f'{c["name"]} ({c["set"].upper()}) {c["collector_number"]} — no image')
            continue

        display = f'{e["qty"]}x {c["name"]}' if e["qty"] > 1 else c["name"]
        if e.get("finish"):
            display += f' ({e["finish"]})'
        entry = {
            "display": display,
            "qty": e["qty"],
            "downloads": downloads,
            "released_at": c.get("released_at"),
            "set": c.get("set"),
        }
        if source == "gatherer":
            # Gatherer only knows cards with a multiverse id. Plenty do not:
            # every Secret Lair and promo, and — less obviously — every foil
            # printing, which Scryfall numbers with a star (198★) and gives no
            # multiverse id because Gatherer never catalogued foils separately.
            #
            # Dropping those left the user with an incomplete deck and a wall
            # of rejections. They fall back to the Scryfall image instead: the
            # right card, from the other source, reported rather than silent.
            mids = c.get("multiverse_ids") or []
            if mids:
                entry["ref"] = ("https://gatherer.wizards.com/Pages/Card/"
                                f"Details.aspx?multiverseid={mids[0]}")
            else:
                from_scryfall.append(
                    f'{c["name"]} ({c["set"].upper()}) {c["collector_number"]}')
        cards.append(entry)

    # Tokens last, so they land after the deck in the queue rather than
    # interleaved with it. Only the cards that actually resolved can make any.
    if tokens:
        for t in _related_tokens(
                [resolved[k] for k in order if k in resolved], status_callback):
            base = f"{_slug(t['name'])}-{t.get('set','')}-{t.get('collector_number','')}"
            try:
                downloads = [(f"{base}{label}", url)
                             for url, label in _png_urls(t)]
            except ScryfallError:
                continue
            cards.append({
                "display": f"{t['name']} (token)",
                "qty": 1,
                "downloads": downloads,
                "released_at": t.get("released_at"),
                "set": t.get("set"),
            })

    return cards, not_found, bad, english_only, from_scryfall


def download_to_temp(basename: str, url: str) -> Path:
    """Download a resolved image url into TEMP_FOLDER as <basename>.png.

    Handles Scryfall PNGs and Google Drive downloads (MPC images, ~12 MB),
    so it uses a generous timeout and follows redirects.
    """
    target = TEMP_FOLDER / f"{basename}.png"
    time.sleep(SCRYFALL_DELAY)
    r = requests.get(url, headers={"User-Agent": SCRYFALL_HEADERS["User-Agent"]},
                     timeout=120, allow_redirects=True)
    if r.status_code != 200 or len(r.content) < 2000:
        raise ScryfallError(f"Download failed ({r.status_code})")
    target.write_bytes(r.content)
    return target


# ==========================================================================
# DECK SITE URLS (Archidekt / Moxfield)
# ==========================================================================

def deck_url_kind(text: str):
    """'archidekt' | 'moxfield' | None for a pasted URL."""
    t = text.strip().lower()
    if "archidekt.com/decks/" in t:
        return "archidekt"
    if "moxfield.com/decks/" in t:
        return "moxfield"
    return None


# Moxfield deck import.
#
# HISTORY, so nobody re-litigates this from scratch: Moxfield's support was
# asked for API access and declined, citing WotC concerns, and this project
# recorded "do not scrape" as a result. That was revisited in July 2026 and
# the call was deliberately reversed by the author — see decisions.md. What
# follows uses the same unauthenticated endpoint their own web client calls.
#
# Because that access is theirs to withdraw, every failure path here has to
# land the user somewhere useful rather than just erroring: pasting an export
# has always worked and always will.
MOXFIELD_API = "https://api2.moxfield.com/v3/decks/all/{deck_id}"

_MOXFIELD_PASTE = ("In Moxfield use Export → copy the decklist text and "
                   "paste it here instead — that format is supported "
                   "directly.")

# Everything except the maybeboard, which is by definition cards the author
# has NOT put in the deck. Commanders and companions matter for Commander;
# the oddball boards cost nothing and someone printing an Attraction deck
# wants them.
MOXFIELD_BOARDS = (
    "commanders", "companions", "signatureSpells", "mainboard", "sideboard",
    "attractions", "stickers", "contraptions", "planes", "schemes",
)


def fetch_moxfield(url: str, status_callback=None) -> str:
    """
    Fetch a public Moxfield deck and return it as decklist text
    ("N Name (SET) number"), ready for resolve_decklist().
    """
    m = re.search(r"moxfield\.com/decks/([A-Za-z0-9_\-]+)", url, re.I)
    if not m:
        raise ScryfallError("Could not find a deck id in that Moxfield URL")

    if status_callback:
        status_callback("Fetching deck from Moxfield...")

    try:
        r = requests.get(MOXFIELD_API.format(deck_id=m.group(1)),
                         headers={"User-Agent": SCRYFALL_HEADERS["User-Agent"]},
                         timeout=30)
    except requests.RequestException as e:
        raise ScryfallError(
            f"Could not reach Moxfield ({e}). {_MOXFIELD_PASTE}") from e

    if r.status_code == 404:
        raise ScryfallError(
            "Moxfield returned 404 - check the link, and that the deck is "
            "public rather than private or unlisted.")
    if r.status_code in (401, 403, 429):
        # They are within their rights to close this off at any time.
        raise ScryfallError(
            f"Moxfield refused the request ({r.status_code}). "
            f"{_MOXFIELD_PASTE}")
    if r.status_code != 200:
        raise ScryfallError(
            f"Moxfield returned {r.status_code}. {_MOXFIELD_PASTE}")

    try:
        boards = r.json().get("boards") or {}
    except ValueError as e:
        raise ScryfallError(
            f"Moxfield sent something unreadable. {_MOXFIELD_PASTE}") from e

    lines = []
    for name in MOXFIELD_BOARDS:
        for entry in ((boards.get(name) or {}).get("cards") or {}).values():
            card = entry.get("card") or {}
            setcode, number = card.get("set"), card.get("cn")
            if not (card.get("name") and setcode and number):
                continue
            lines.append(f"{entry.get('quantity', 1)} {card['name']} "
                         f"({setcode.upper()}) {number}")

    if not lines:
        raise ScryfallError("No printable cards found in that deck")
    return chr(10).join(lines)


def fetch_archidekt(url: str, status_callback=None) -> str:
    """
    Fetch a public Archidekt deck and return it as decklist text
    ("N Name (SET) number"), ready for resolve_decklist().
    """
    m = re.search(r"archidekt\.com/decks/(\d+)", url, re.I)
    if not m:
        raise ScryfallError("Could not find a deck id in that Archidekt URL")

    if status_callback:
        status_callback("Fetching deck from Archidekt...")

    r = requests.get(f"https://archidekt.com/api/decks/{m.group(1)}/",
                     headers={"User-Agent": SCRYFALL_HEADERS["User-Agent"]},
                     timeout=30)
    if r.status_code != 200:
        raise ScryfallError(f"Archidekt returned {r.status_code} "
                            "(is the deck public?)")
    deck = r.json()

    lines = []
    for entry in deck.get("cards", []):
        qty = entry.get("quantity", 1)
        cats = entry.get("categories") or []
        if any(c.lower() in ("maybeboard", "sideboard considering") for c in cats):
            continue
        card = entry.get("card") or {}
        oracle = card.get("oracleCard") or {}
        name = oracle.get("name") or card.get("displayName") or ""
        setcode = (card.get("edition") or {}).get("editioncode") or ""
        number = card.get("collectorNumber") or ""
        if name and setcode and number:
            lines.append(f"{qty} {name} ({setcode.upper()}) {number}")

    if not lines:
        raise ScryfallError("No printable cards found in that deck")
    return "\n".join(lines)

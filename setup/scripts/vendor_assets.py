"""vendor_assets.py - loads the vendored, license-clean design assets for the
cockpit (`gamma_home.py` / `gamma_cockpit_ui.py`) at render time.

WHY THIS EXISTS: the cockpit page is a hard-constrained single self-contained
file (`gamma_cockpit_ui.py:6-9` - "one self-contained file. No CDN, no web
fonts, no external JS or CSS. Must work from a file:// URL with no network").
Every asset this module serves was downloaded ONCE and committed under
`setup/scripts/vendor/` (see `vendor/MANIFEST.md` for license/version/size/
source-URL/hash provenance per file) - nothing here is fetched at runtime.
This module never makes a network call; it only reads local files and
concatenates/transforms them into strings the page inliner drops into the
generated HTML.

Pure stdlib. No third-party dependency to build this module itself.

Public API:
    css(names=None)        -> str   concatenated Open Props / Radix Colors CSS
    js(names=None)          -> str   concatenated anime.js / CountUp / confetti JS
    icon(name, ...)         -> str   inline <svg> markup for one Lucide icon
    font_face_css()         -> str   @font-face rules, fonts base64-inlined
    manifest()              -> list[dict]  parsed rows of vendor/MANIFEST.md

CLI:
    python setup/scripts/vendor_assets.py --check
        Verifies every manifest row's file exists on disk with the recorded
        size (+/-5%), prints one line per asset, then totals (CSS+JS budget
        vs the 250,000-byte cap, icons, fonts). Non-zero exit on any failure.
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "vendor"
MANIFEST_PATH = VENDOR_DIR / "MANIFEST.md"

# ---------------------------------------------------------------------------
# CSS: Open Props (split token files) + Radix Colors (status/accent ramps)
# ---------------------------------------------------------------------------

_OPEN_PROPS_SLUGS = [
    "sizes", "shadows", "easings", "animations", "borders", "media", "zindex", "aspects",
]
_RADIX_COLORS = ["gray", "mauve", "indigo", "violet", "green", "red", "amber", "cyan"]
_RADIX_SUFFIXES = ["", "-dark", "-alpha", "-dark-alpha"]


def _all_css_filenames() -> list[str]:
    names = [f"openprops.{slug}.min.css" for slug in _OPEN_PROPS_SLUGS]
    for color in _RADIX_COLORS:
        for suffix in _RADIX_SUFFIXES:
            names.append(f"radix.{color}{suffix}.css")
    return names


def _resolve_css_filename(name: str) -> str:
    """Accepts either a short name ("sizes", "gray-dark") or a full vendored
    filename ("openprops.sizes.min.css", "radix.gray-dark.css")."""
    candidates = [name, f"{name}.css", f"openprops.{name}.min.css", f"radix.{name}.css"]
    for cand in candidates:
        if (VENDOR_DIR / cand).is_file():
            return cand
    available = ", ".join(sorted(set(_all_css_filenames())))
    raise KeyError(
        f"unknown css asset {name!r} - short names: "
        f"{', '.join(_OPEN_PROPS_SLUGS)}, {', '.join(_RADIX_COLORS)} "
        f"(+ '-dark'/'-alpha'/'-dark-alpha' suffixes); full filenames: {available}"
    )


def css(names: list[str] | None = None) -> str:
    """Concatenated CSS text for the requested Open Props / Radix Colors files.

    Defaults to every vendored CSS file, Open Props first then Radix, in a
    fixed deterministic order (so repeated renders are byte-identical).
    """
    filenames = _all_css_filenames() if names is None else [_resolve_css_filename(n) for n in names]
    return "\n".join((VENDOR_DIR / fname).read_text(encoding="utf-8") for fname in filenames)


# ---------------------------------------------------------------------------
# JS: anime.js (motion) + CountUp.js (number count-up) + canvas-confetti
# ---------------------------------------------------------------------------

_JS_FILES = {
    "anime": "anime.umd.min.js",       # global `anime`
    "countup": "countup.umd.js",       # global `countUp`
    "confetti": "confetti.browser.js",  # global `confetti`
}
_JS_ORDER = ["anime", "countup", "confetti"]


def js(names: list[str] | None = None) -> str:
    """Concatenated JS text for the requested libraries.

    Valid names: "anime", "countup", "confetti". Defaults to all three in a
    fixed order (anime.js first - callers rarely need one without the others).
    """
    keys = _JS_ORDER if names is None else names
    parts = []
    for key in keys:
        if key not in _JS_FILES:
            raise KeyError(f"unknown js asset {key!r} - available: {', '.join(_JS_ORDER)}")
        parts.append((VENDOR_DIR / _JS_FILES[key]).read_text(encoding="utf-8"))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Icons: hand-picked Lucide SVGs, inlined and re-attributed per call
# ---------------------------------------------------------------------------

_SVG_COMMENT_RE = re.compile(r"^\s*<!--.*?-->\s*", re.DOTALL)
_SVG_OPEN_TAG_RE = re.compile(r"<svg\b([^>]*)>", re.DOTALL)
_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
_ATTR_ORDER = [
    "class", "xmlns", "width", "height", "viewBox", "fill", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin",
    "role", "aria-label", "aria-hidden",
]


def _icon_names() -> list[str]:
    return sorted(p.stem for p in (VENDOR_DIR / "icons").glob("*.svg"))


def icon(name: str, cls: str = "ic", size: int = 16, label: str | None = None) -> str:
    """Inline <svg> markup for one vendored Lucide icon.

    Sets width/height to `size` and class to `cls`; leaves `stroke="currentColor"`
    untouched so CSS `color` drives icon tint. `aria-hidden="true"` unless
    `label` is given, in which case the icon gets `role="img"` + `aria-label`
    instead. Raises KeyError (listing every available name) for an unknown icon.
    """
    path = VENDOR_DIR / "icons" / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"unknown icon {name!r} - available: {', '.join(_icon_names())}")

    raw = _SVG_COMMENT_RE.sub("", path.read_text(encoding="utf-8"), count=1).strip()
    match = _SVG_OPEN_TAG_RE.search(raw)
    if not match:
        raise ValueError(f"icons/{name}.svg has no <svg> tag")

    attrs = dict(_ATTR_RE.findall(match.group(1)))
    attrs["class"] = cls
    attrs["width"] = str(size)
    attrs["height"] = str(size)
    attrs.pop("aria-hidden", None)
    attrs.pop("role", None)
    attrs.pop("aria-label", None)
    if label:
        attrs["role"] = "img"
        attrs["aria-label"] = label
    else:
        attrs["aria-hidden"] = "true"

    ordered_keys = [k for k in _ATTR_ORDER if k in attrs] + [k for k in attrs if k not in _ATTR_ORDER]
    new_open_tag = "<svg " + " ".join(f'{k}="{attrs[k]}"' for k in ordered_keys) + ">"
    return raw[: match.start()] + new_open_tag + raw[match.end():]


# ---------------------------------------------------------------------------
# Fonts: base64-inlined @font-face rules (never a network font request)
# ---------------------------------------------------------------------------

_FONT_FACES = [
    # (filename, family, weight)
    ("Inter-Regular.woff2", "Inter", 400),
    ("Inter-Medium.woff2", "Inter", 500),
    ("Inter-SemiBold.woff2", "Inter", 600),
    ("JetBrainsMono-Regular.woff2", "JetBrains Mono", 400),
]


def font_face_css() -> str:
    """@font-face rules with base64 data-URI sources for the vendored fonts.

    Returns "" if no font files are vendored - the page then falls back to
    its system font stack, which is a valid (not degraded) state.
    """
    rules = []
    for fname, family, weight in _FONT_FACES:
        path = VENDOR_DIR / fname
        if not path.is_file():
            continue
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{family}';font-style:normal;font-weight:{weight};"
            f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "\n".join(rules)


# ---------------------------------------------------------------------------
# Manifest: parsed from vendor/MANIFEST.md (never hand-maintained elsewhere)
# ---------------------------------------------------------------------------

_ROW_RE = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|"
    r"\s*([^|]+?)\s*\|\s*`([0-9a-f]+)`\s*\|\s*([^|]*?)\s*\|$"
)


def manifest() -> list[dict]:
    """Parse `vendor/MANIFEST.md`'s asset table.

    Each row: {file, version, license, bytes, source, sha256, note}.
    """
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    rows = []
    for line in text.splitlines():
        m = _ROW_RE.match(line.strip())
        if not m:
            continue
        fname, version, license_, size, url, sha, note = m.groups()
        rows.append({
            "file": fname,
            "version": version,
            "license": license_,
            "bytes": int(size),
            "source": url,
            "sha256": sha,
            "note": note,
        })
    return rows


# ---------------------------------------------------------------------------
# CLI: --check
# ---------------------------------------------------------------------------

_CSS_JS_BUDGET_BYTES = 250_000


def _check() -> int:
    rows = manifest()
    if not rows:
        print("FAIL: manifest() returned 0 rows - is vendor/MANIFEST.md missing or malformed?")
        return 1

    ok = fail = 0
    css_js_bytes = icon_bytes = font_bytes = 0
    for row in rows:
        path = VENDOR_DIR / row["file"]
        if not path.is_file():
            print(f"MISSING         {row['file']}")
            fail += 1
            continue
        actual = path.stat().st_size
        recorded = row["bytes"]
        tolerance = max(1, recorded * 0.05)
        if abs(actual - recorded) > tolerance:
            print(f"SIZE MISMATCH   {row['file']}  recorded={recorded} actual={actual}")
            fail += 1
            continue
        print(f"OK              {row['file']}  {actual}B  {row['license']}  v{row['version']}")
        ok += 1
        if row["file"].endswith(".woff2"):
            font_bytes += actual
        elif row["file"].startswith("icons/"):
            icon_bytes += actual
        else:
            css_js_bytes += actual

    print(f"--- {ok} ok, {fail} failed, {len(rows)} total ---")
    print(f"CSS+JS total: {css_js_bytes:,} B (budget {_CSS_JS_BUDGET_BYTES:,} B)")
    print(f"icons total:  {icon_bytes:,} B")
    print(f"fonts total:  {font_bytes:,} B (excluded from the CSS+JS budget)")

    if css_js_bytes >= _CSS_JS_BUDGET_BYTES:
        print(f"FAIL: CSS+JS budget exceeded ({css_js_bytes:,} >= {_CSS_JS_BUDGET_BYTES:,})")
        fail += 1

    return 1 if fail else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(_check())
    print(__doc__)

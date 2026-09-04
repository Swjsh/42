"""gamma_cockpit_vendor.py - wires setup/scripts/vendor/ into the cockpit page.

Bridges `vendor_assets.py` (generic loader) and `gamma_cockpit_ui.py` (the one
page that consumes it). Owns three things:

  ICONS          dict[name] -> inline <svg> markup, one entry per icon name
                 referenced anywhere in the cockpit (topbar chrome + tile
                 icons from COCKPIT-DESIGN-SPEC-2026-09-03.md section 5).
                 Built at import time; raises immediately if a name this
                 module lists is missing from vendor/MANIFEST.md, so a typo
                 in an icon name fails the test suite instead of shipping a
                 blank tile.
  vendor_head()  @font-face rules (base64 data: URIs) + the three Open Props
                 CSS files the token system depends on (sizes/easings/borders).
                 Radix Colors CSS is NOT inlined here -- only its hex values,
                 copied by hand into gamma_cockpit_ui.CSS -- the Radix files
                 stay on disk purely for provenance (spec section 6).
  vendor_scripts() CountUp + canvas-confetti, concatenated, with every
                 license-header URL elided so the self-contained-page rule
                 (no http(s):// reference anywhere in the shipped markup)
                 holds even inside vendored third-party comments. Also emits
                 `const ICONS={...};function ic(n){return ICONS[n]||''}` so
                 app JS can look an icon up by name without a second import.

Pure stdlib + vendor_assets. No network call; every byte returned here is
read from a file already committed under setup/scripts/vendor/.

CLI:
    python setup/scripts/gamma_cockpit_vendor.py --check
        Confirms every ICONS name round-trips (vendor_assets.icon() succeeds),
        vendor_head()/vendor_scripts() are non-empty and URL-free, then exits
        non-zero on any failure (mirrors vendor_assets.py --check).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vendor_assets  # noqa: E402

# Every icon name the cockpit references: chrome (topbar controls, keyboard
# hints render as text so "command"/"circle-help" are deliberately absent)
# plus the tile icon column from spec section 5. Kept as one flat list so a
# single load-time check catches a typo before it ships as an empty slot.
_ICON_NAMES = sorted(set([
    # chrome / controls
    "pause", "play", "refresh-cw", "sun", "moon", "chevron-down",
    "chevron-right", "x", "search",
    # tile icons (spec section 5's Icon column)
    "target", "gauge", "layers", "dollar-sign", "sunrise", "radio", "flame",
    "radar", "hourglass", "eye", "book-open", "layout-grid", "trending-up",
    "shield", "timer", "activity", "bot", "list-checks", "network", "wallet",
    "calendar",
    # rows added by the producers / answers modules (integration pass 2026-09-03)
    "heart-pulse", "check-circle-2",
]))

_URL_RE = re.compile(r"https?://\S+")


def _elide_urls(text: str) -> str:
    """Strip any http(s) URL (vendored license-header comments, mainly) so
    the page never carries a network reference, per the self-contained rule."""
    return _URL_RE.sub("(url elided)", text)


def _build_icons() -> dict[str, str]:
    manifest_files = {row["file"] for row in vendor_assets.manifest()}
    missing = [n for n in _ICON_NAMES if f"icons/{n}.svg" not in manifest_files]
    if missing:
        raise RuntimeError(
            "gamma_cockpit_vendor: icon(s) referenced but absent from "
            f"vendor/MANIFEST.md: {missing}"
        )
    return {name: vendor_assets.icon(name) for name in _ICON_NAMES}


ICONS: dict[str, str] = _build_icons()


def vendor_head() -> str:
    """@font-face (base64) + Open Props sizes/easings/borders, URL-elided.

    Radix Colors files are deliberately excluded -- their hex values are
    copied by hand into gamma_cockpit_ui.CSS's token block (spec section 6).
    """
    fonts = vendor_assets.font_face_css()
    props = vendor_assets.css(["sizes", "easings", "borders"])
    return _elide_urls(fonts + "\n" + props)


def vendor_scripts() -> str:
    """CountUp + confetti + the ICONS lookup table/helper, URL-elided as one
    pass over the whole concatenation -- icon markup carries a w3.org xmlns
    URL too, and the self-contained rule is "no http(s) reference anywhere",
    not "except inside an embedded SVG attribute"."""
    libs = vendor_assets.js(["countup", "confetti"])
    icons_js = "const ICONS=" + json.dumps(ICONS) + ";function ic(n){return ICONS[n]||''}"
    return _elide_urls(libs + "\n" + icons_js)


def _check() -> int:
    fail = 0
    for name in _ICON_NAMES:
        try:
            svg = vendor_assets.icon(name)
        except Exception as exc:  # noqa: BLE001
            print(f"MISSING icon   {name}  ({exc})")
            fail += 1
            continue
        if "<svg" not in svg:
            print(f"BAD SVG        {name}")
            fail += 1
    head = vendor_head()
    scripts = vendor_scripts()
    if len(head) < 1000:
        print(f"FAIL: vendor_head() suspiciously small ({len(head)} chars)")
        fail += 1
    if "countUp" not in scripts or "confetti" not in scripts:
        print("FAIL: vendor_scripts() missing an expected global")
        fail += 1
    if "://" in head or "://" in scripts:
        print("FAIL: a URL survived elision")
        fail += 1
    print(f"--- {len(_ICON_NAMES)} icons, head {len(head)}B, scripts {len(scripts)}B, "
          f"{fail} failed ---")
    return 1 if fail else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(_check())
    print(__doc__)

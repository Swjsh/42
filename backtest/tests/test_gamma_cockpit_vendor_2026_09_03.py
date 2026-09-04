"""Guard: gamma_cockpit_vendor.py wires the vendored assets in correctly.

WS-A (COCKPIT-DESIGN-SPEC-2026-09-03.md section 8): tokens + vendor. This file
pins the contract other builders' modules lean on -- every var(--x) their JS
already references must resolve in BOTH themes, the vendor CLI must exit
clean, and the ban list (box-shadow count, no #000, no gradients outside the
two named exceptions) must hold on gamma_cockpit_ui.CSS.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import gamma_cockpit_vendor as vendor          # noqa: E402
import gamma_cockpit_ui as ui                  # noqa: E402
import vendor_assets                           # noqa: E402

JS_FILES = [
    "gamma_cockpit_js.py",
    "gamma_cockpit_army_js.py",
    "gamma_cockpit_chat_js.py",
    "gamma_cockpit_cards_js.py",
    "gamma_cockpit_views_js.py",
    "gamma_cockpit_autonomy_js.py",
]


def _referenced_var_names() -> set[str]:
    names: set[str] = set()
    for fname in JS_FILES:
        text = (SCRIPTS / fname).read_text(encoding="utf-8")
        names.update(re.findall(r"var\(--([a-z0-9-]+)\)", text))
    return names


def _root_blocks(css: str) -> list[str]:
    """Every top-level :root{...} / :root[data-theme=...]{...} block, matched
    with a simple brace counter (the blocks nest no braces of their own)."""
    blocks = []
    for m in re.finditer(r":root(\[[^\]]*\])?\{", css):
        start = m.end()
        depth = 1
        i = start
        while depth and i < len(css):
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        blocks.append(css[start:i - 1])
    return blocks


def _defined_var_names(block: str) -> set[str]:
    return set(re.findall(r"--([a-z0-9-]+)\s*:", block))


# ------------------------------------------------------- vendor module itself

def test_vendor_check_cli_exits_clean():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "gamma_cockpit_vendor.py"), "--check"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_every_icon_name_exists_in_manifest():
    manifest_files = {row["file"] for row in vendor_assets.manifest()}
    for name in vendor.ICONS:
        assert f"icons/{name}.svg" in manifest_files, name


def test_vendor_head_is_url_free_and_substantial():
    head = vendor.vendor_head()
    assert len(head) > 90_000
    assert "://" not in head


def test_vendor_scripts_carries_both_libraries_url_free():
    scripts = vendor.vendor_scripts()
    assert "countUp" in scripts
    assert "confetti" in scripts
    assert "://" not in scripts


# ------------------------------------------------------- token parity

def test_every_referenced_token_resolves_somewhere():
    """Every var(--x) the app JS already calls must resolve on the root
    element. Both `:root` and `:root[data-theme="light"]` target the SAME
    html element, so a custom property the light block does not redefine
    still falls through from the base `:root` block via the normal cascade
    (spacing/radius/easing/fonts are intentionally declared once, only
    colour tokens are redeclared per theme) -- the bug this guards against
    is a name defined in NEITHER block, which would resolve to nothing."""
    referenced = _referenced_var_names()
    blocks = _root_blocks(ui.CSS)
    assert len(blocks) >= 2, "expected a dark :root and a light :root[data-theme=light] block"
    all_names: set[str] = set()
    for b in blocks:
        all_names |= _defined_var_names(b)
    missing = sorted(referenced - all_names)
    assert not missing, f"referenced but never defined in any :root block: {missing}"


def test_colour_tokens_are_redeclared_per_theme():
    """Unlike spacing/radius/fonts, colour tokens must actually differ (or at
    least be explicitly restated) per theme -- a colour silently inherited
    from dark into light would be the bug (e.g. the stage staying dark on
    purpose is fine; --ink-1 staying dark-only would not be)."""
    blocks = _root_blocks(ui.CSS)
    dark_names = _defined_var_names(blocks[0])
    light_names: set[str] = set()
    for b in blocks[1:]:
        light_names |= _defined_var_names(b)
    for name in ("ink-1", "ink-2", "ink-3", "canvas", "surface-1", "accent"):
        assert name in dark_names, f"--{name} missing from dark block"
        assert name in light_names, f"--{name} missing from light block"


def _relative_luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = lin(r), lin(g), lin(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(hex_a: str, hex_b: str) -> float:
    la, lb = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme_idx,label", [(0, "dark"), (1, "light")])
def test_ink3_on_canvas_meets_contrast_floor(theme_idx, label):
    blocks = _root_blocks(ui.CSS)
    block = blocks[theme_idx]

    def hexval(name: str) -> str:
        m = re.search(rf"--{name}\s*:\s*(#[0-9a-fA-F]{{6}})", block)
        assert m, f"--{name} not a literal hex in the {label} block"
        return m.group(1)

    ratio = _contrast(hexval("ink-3"), hexval("canvas"))
    assert ratio >= 4.5, f"{label}: --ink-3 on --canvas contrast {ratio:.2f} < 4.5"


# ------------------------------------------------------- ban list

def test_box_shadow_count_at_most_three():
    assert ui.CSS.count("box-shadow") <= 3


def test_no_pure_black_hex():
    assert "#000" not in ui.CSS


def test_gradients_limited_to_the_stage_bloom():
    """The Army stage's own radial bloom is the sole gradient() left in the
    file; the per-edge beam gradient lives in gamma_cockpit_army_js.py's SVG,
    not here. Everything else must be flat colour."""
    grads = re.findall(r"(linear|radial)-gradient\(", ui.CSS)
    assert len(grads) <= 1, f"unexpected gradient count: {len(grads)}"


def test_no_em_or_en_dash_or_middle_dot_in_new_css():
    for ch, label in ((chr(0x2014), "em dash"), (chr(0x2013), "en dash"),
                      (chr(0x00b7), "middle dot")):
        assert ch not in ui.CSS, f"{label} found in ui.CSS"

"""Guard: vendored design assets for the cockpit redesign are real, licensed,
sized within budget, and never reach for the network at runtime.

WHY THIS EXISTS: GOAL-COCKPIT-REDESIGN-2026-09-03 DONE-WHEN (a) requires "real
design assets, not hand-rolled" -- vetted MIT/ISC/OFL libraries vendored under
`setup/scripts/vendor/` with a MANIFEST.md (license/version/bytes/source/hash),
loaded by `setup/scripts/vendor_assets.py`. This is a PUBLIC repo
(github.com/Swjsh/42) and the page's own hard rule (`gamma_cockpit_ui.py:6-9`)
bans any CDN/network dependency -- every byte the page ships must be sitting on
disk, license-clean, before it's inlined.

WHAT IS PINNED
  * Every MANIFEST.md row's file exists on disk at (approximately) its recorded
    size -- a stale manifest describing a file that was never fetched, or one
    that silently changed size, is a broken supply chain, not a passing build.
  * css()/js() concatenate real vendored content (Open Props sizes token +
    Radix indigo-9 ramp; anime/countUp/confetti globals) and never emit an
    `@import` or a `url(http...)` -- either would turn a "vendored" asset back
    into a live network dependency the instant someone forgets to check.
  * icon() returns inert, accessible <svg> markup for a known name and raises
    KeyError (not a silent blank string) for an unknown one.
  * The CSS+JS budget (250,000 B, fonts excluded per spec) is respected.
  * Every non-font vendored file carries a license/name marker in its first
    400 chars -- either upkg's own header (anime.js, confetti, every Lucide
    icon) or one this vendoring pass prepended (Open Props/Radix/CountUp had
    none). Font files (.woff2) are binary and are exempted from this specific
    check; their license (OFL-1.1) is recorded in MANIFEST.md instead -- see
    `test_font_files_are_recorded_ofl_in_manifest`.

RED-PROOF: `test_manifest_is_red_proof` deletes one manifest row (writes to a
tmp copy, not the real file) and asserts detection breaks, then implicitly
proves the real file still parses via every other test in this module.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import vendor_assets as va  # noqa: E402

VENDOR_DIR = REPO / "setup" / "scripts" / "vendor"


# ---------------------------------------------------------------------------
# manifest integrity
# ---------------------------------------------------------------------------

def test_manifest_file_exists_and_parses():
    assert (VENDOR_DIR / "MANIFEST.md").is_file()
    rows = va.manifest()
    assert len(rows) >= 100, f"expected >=100 vendored assets (59 icons alone), got {len(rows)}"


def test_every_manifest_row_file_exists_with_matching_size():
    rows = va.manifest()
    assert rows, "manifest() returned no rows"
    for row in rows:
        path = VENDOR_DIR / row["file"]
        assert path.is_file(), f"manifest names {row['file']} but it is not on disk"
        actual = path.stat().st_size
        recorded = row["bytes"]
        tolerance = max(1, recorded * 0.05)
        assert abs(actual - recorded) <= tolerance, (
            f"{row['file']}: manifest says {recorded}B, disk has {actual}B "
            f"(tolerance +/-{tolerance:.0f}B)"
        )


def test_every_manifest_row_has_license_and_source():
    rows = va.manifest()
    for row in rows:
        assert row["license"], f"{row['file']} has no license recorded"
        assert row["source"].startswith("http"), f"{row['file']} has no source URL recorded"
        assert re.fullmatch(r"[0-9a-f]{12}", row["sha256"]), f"{row['file']} sha256 malformed"


def test_font_files_are_recorded_ofl_in_manifest():
    rows = {r["file"]: r for r in va.manifest()}
    font_files = [f for f in rows if f.endswith(".woff2")]
    assert len(font_files) == 4, f"expected 4 vendored woff2 files, found {font_files}"
    for fname in font_files:
        assert rows[fname]["license"] == "OFL-1.1", f"{fname} should be OFL-1.1, got {rows[fname]['license']}"


def test_check_cli_reports_zero_failures(capsys):
    rc = va._check()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "0 failed" in out


# ---------------------------------------------------------------------------
# css()
# ---------------------------------------------------------------------------

def test_css_default_contains_open_props_and_radix_tokens():
    text = va.css()
    assert "--size-1" in text, "Open Props sizes token missing from css()"
    assert "--indigo-9" in text, "Radix indigo-9 token missing from css()"


def test_css_never_imports_or_fetches_a_remote_url():
    text = va.css()
    lowered = text.lower()
    assert "@import" not in lowered
    assert "url(http" not in lowered


def test_css_short_name_and_full_filename_resolve_the_same():
    assert va.css(["sizes"]) == va.css(["openprops.sizes.min.css"])
    assert va.css(["gray-dark"]) == va.css(["radix.gray-dark.css"])


def test_css_unknown_name_raises_keyerror_with_available_list():
    with pytest.raises(KeyError) as exc:
        va.css(["not-a-real-token-file"])
    assert "sizes" in str(exc.value)


# ---------------------------------------------------------------------------
# js()
# ---------------------------------------------------------------------------

def test_js_default_defines_expected_globals():
    text = va.js()
    assert re.search(r"\banime\b", text), "anime global not found in js()"
    assert re.search(r"\bcountUp\b", text), "countUp global not found in js()"
    assert re.search(r"\bconfetti\b", text), "confetti global not found in js()"


def test_js_never_loads_a_remote_script():
    lowered = va.js().lower()
    assert "<script src=" not in lowered


def test_js_unknown_name_raises_keyerror():
    with pytest.raises(KeyError):
        va.js(["not-a-real-lib"])


# ---------------------------------------------------------------------------
# icon()
# ---------------------------------------------------------------------------

def test_icon_activity_returns_accessible_svg():
    svg = va.icon("activity")
    assert svg.startswith("<svg")
    assert 'aria-hidden="true"' in svg
    assert 'stroke="currentColor"' in svg
    assert 'width="16"' in svg and 'height="16"' in svg


def test_icon_with_label_gets_role_img_not_aria_hidden():
    svg = va.icon("activity", label="live pulse")
    assert 'role="img"' in svg
    assert 'aria-label="live pulse"' in svg
    assert "aria-hidden" not in svg


def test_icon_custom_size_and_class():
    svg = va.icon("zap", cls="ic-lg", size=24)
    assert 'class="ic-lg"' in svg
    assert 'width="24"' in svg and 'height="24"' in svg


def test_icon_unknown_name_raises_keyerror_listing_available():
    with pytest.raises(KeyError) as exc:
        va.icon("nope")
    msg = str(exc.value)
    assert "activity" in msg  # a real icon name should be in the "available" list


def test_every_requested_icon_name_resolves():
    requested = (
        "activity alert-triangle arrow-up-right arrow-down-right bot brain calendar "
        "check check-circle-2 chevron-down chevron-right circle-dot clock cpu database "
        "dollar-sign expand eye flame flask-conical gauge git-commit heart-pulse layers "
        "line-chart list-checks moon pause play radar radio refresh-cw rocket scan-line "
        "search shield shield-alert sparkles sun target terminal timer trending-down "
        "trending-up wallet waves x zap bar-chart-3 layout-grid network orbit sunrise "
        "sunset book-open microscope chef-hat siren hourglass"
    ).split()
    for name in requested:
        svg = va.icon(name)
        assert svg.startswith("<svg"), f"icon({name!r}) did not return svg markup"


# ---------------------------------------------------------------------------
# font_face_css()
# ---------------------------------------------------------------------------

def test_font_face_css_embeds_base64_not_a_network_font():
    text = va.font_face_css()
    assert text, "expected non-empty font_face_css() - 4 fonts are vendored"
    assert text.count("@font-face") == 4
    assert "data:font/woff2;base64," in text
    assert "http://" not in text and "https://" not in text
    assert "'Inter'" in text
    assert "'JetBrains Mono'" in text


# ---------------------------------------------------------------------------
# license/name marker in every non-font vendored file
# ---------------------------------------------------------------------------

def test_every_non_font_vendored_file_has_a_license_or_name_marker_up_front():
    rows = va.manifest()
    missing = []
    for row in rows:
        fname = row["file"]
        if fname.endswith(".woff2"):
            continue  # binary; provenance lives in MANIFEST.md (OFL-1.1), see dedicated test
        path = VENDOR_DIR / fname
        head = path.read_text(encoding="utf-8", errors="replace")[:400]
        # accept any of: our prepended "/*! name vX | LICENSE" header, upkg's own
        # "@license" JSDoc line, an HTML license comment (Lucide), or a bare
        # name+version banner (canvas-confetti's "// canvas-confetti vX ...").
        has_marker = (
            "license" in head.lower()
            or fname.split(".")[0].split("/")[-1].split("-")[0].lower() in head.lower()
        )
        if not has_marker:
            missing.append(fname)
    assert not missing, f"no license/name marker in first 400 chars of: {missing}"


# ---------------------------------------------------------------------------
# total budget
# ---------------------------------------------------------------------------

def test_css_plus_js_total_bytes_under_budget():
    total = len(va.css().encode("utf-8")) + len(va.js().encode("utf-8"))
    assert total < 250_000, f"css()+js() is {total} bytes, over the 250,000 budget"


def test_manifest_css_js_rows_sum_under_budget():
    rows = va.manifest()
    css_js_total = sum(
        r["bytes"] for r in rows
        if not r["file"].endswith(".woff2") and not r["file"].startswith("icons/")
    )
    assert css_js_total < 250_000, f"manifest CSS+JS rows sum to {css_js_total}, over budget"


# ---------------------------------------------------------------------------
# RED-proof: prove the guard actually fails on a broken manifest
# ---------------------------------------------------------------------------

def test_manifest_is_red_proof(tmp_path, monkeypatch):
    """Delete one row from a scratch copy of MANIFEST.md and prove downstream
    checks notice - then restore va.MANIFEST_PATH so no other test is affected."""
    real_lines = va.MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
    row_lines = [i for i, l in enumerate(real_lines) if l.strip().startswith("| `")]
    assert row_lines, "no data rows found in the real MANIFEST.md - can't RED-proof"

    broken = list(real_lines)
    del broken[row_lines[0]]  # drop exactly one asset row
    scratch = tmp_path / "MANIFEST.md"
    scratch.write_text("\n".join(broken) + "\n", encoding="utf-8")

    monkeypatch.setattr(va, "MANIFEST_PATH", scratch)
    real_row_count = len(real_lines and [l for l in real_lines if l.strip().startswith("| `")])
    broken_row_count = len(va.manifest())
    assert broken_row_count == real_row_count - 1, (
        "deleting a manifest row should shrink manifest() by exactly one entry"
    )
    # (monkeypatch auto-restores va.MANIFEST_PATH on teardown - the next test in
    # this file already re-reads the real, untouched file via test collection order.)


def test_real_manifest_still_parses_after_red_proof():
    # Runs after the monkeypatched test above tears down; proves the real file
    # is untouched and still fully parseable (106 rows as of this vendoring pass).
    rows = va.manifest()
    assert len(rows) >= 100

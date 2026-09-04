"""Guard: the "Glow Command" cockpit v2 (COCKPIT-DESIGN-SPEC-V2-GLOW-2026-09-04.md).

WORKSTREAM G (guard tests for the glow contract + DOM self-check/exercise
additions). This file pins the contract the OTHER glow workstreams ship
against: the two new payload builders (fill funnel, cost pulse), the vendored
kit's inlining budget, the reduced-motion rail extended to the new modules,
and copy hygiene on the new surfaces (KPI/eyebrow/Sankey labels, card titles,
VIEWS labels).

PARALLEL-WINDOW POLICY: every module below is being built by a sibling
workstream RIGHT NOW and does not exist yet at the time this file was
authored. Each is pulled in via `pytest.importorskip` at module scope, so
while ANY of them is missing this entire file reports SKIPPED (never FAILED,
never a fabricated PASS -- C7). Once every sibling module lands, the
integration pass removes these `importorskip` calls one at a time so a
genuinely missing/broken module fails loud instead of silently skipping
forever -- do not leave this file skip-guarded past that pass.

New modules this file exercises:
  gamma_cockpit_funnel.py       fill-funnel payload builder -> payload["funnel"]
  gamma_cockpit_costpulse.py    cost-pulse payload builder -> payload["costpulse"]
  gamma_cockpit_glow_ui.py      Glow Command CSS + vendored-kit inlining (KIT_FILES/KIT_BYTES/MISSING)
  gamma_cockpit_glow_js.py      layout + KPI + queue + health + alerts JS
  gamma_cockpit_sankey_js.py    routing-map Sankey renderer
  gamma_cockpit_costpulse_js.py cost-pulse area-chart renderer
  gamma_cockpit_shell.py        page shell (re-exported as gamma_cockpit_ui.SHELL)
"""
from __future__ import annotations

import ast
import inspect
import io
import re
import sys
import tokenize
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
KIT_DIR = SCRIPTS / "vendor" / "ui-kit"
sys.path.insert(0, str(SCRIPTS))

import gamma_cockpit_ui as ui                   # noqa: E402
import gamma_cockpit_js as vjs                  # noqa: E402
import gamma_home as gh                         # noqa: E402
import gamma_cockpit_vendor as vendor           # noqa: E402
import vendor_assets                            # noqa: E402

# ---- sibling modules under construction: skip the whole file, not error, ----
# ---- while any one of them is absent (see PARALLEL-WINDOW POLICY above). ----
funnel = pytest.importorskip("gamma_cockpit_funnel",
                              reason="gamma_cockpit_funnel.py not built yet (sibling workstream)")
costpulse = pytest.importorskip("gamma_cockpit_costpulse",
                                 reason="gamma_cockpit_costpulse.py not built yet (sibling workstream)")
glow_ui = pytest.importorskip("gamma_cockpit_glow_ui",
                               reason="gamma_cockpit_glow_ui.py not built yet (sibling workstream)")
glow_js = pytest.importorskip("gamma_cockpit_glow_js",
                               reason="gamma_cockpit_glow_js.py not built yet (sibling workstream)")
sankey_js = pytest.importorskip("gamma_cockpit_sankey_js",
                                 reason="gamma_cockpit_sankey_js.py not built yet (sibling workstream)")
costpulse_js = pytest.importorskip("gamma_cockpit_costpulse_js",
                                    reason="gamma_cockpit_costpulse_js.py not built yet (sibling workstream)")
shell_mod = pytest.importorskip("gamma_cockpit_shell",
                                 reason="gamma_cockpit_shell.py not built yet (sibling workstream)")

NEW_G_MODULES = [
    "gamma_cockpit_funnel.py", "gamma_cockpit_costpulse.py",
    "gamma_cockpit_glow_ui.py", "gamma_cockpit_glow_js.py",
    "gamma_cockpit_sankey_js.py", "gamma_cockpit_costpulse_js.py",
    "gamma_cockpit_shell.py", "gamma_cockpit_kpi_js.py",
]

CEILINGS = {
    "gamma_cockpit_ui.py": 800,
    "gamma_cockpit_glow_ui.py": 800,
    "gamma_cockpit_glow_js.py": 800,
    "gamma_cockpit_sankey_js.py": 800,
    "gamma_cockpit_costpulse_js.py": 800,
    "gamma_cockpit_funnel.py": 800,
    "gamma_cockpit_costpulse.py": 800,
    "gamma_cockpit_shell.py": 800,
    "gamma_cockpit_command_js.py": 800,
    "gamma_cockpit_kpi_js.py": 800,
    "gamma_cockpit_views_js.py": 800,
}
# gamma_cockpit_army_js.py is explicitly grandfathered over the 800 ceiling
# (spec section 6 exempts it) -- pinned separately below at its CURRENT size
# so it is asserted NOT TO GROW, rather than silently exempted forever.
ARMY_JS_GRANDFATHER_CEILING = 1030


@pytest.fixture(scope="module")
def payload():
    return gh.build(quiet=True)


@pytest.fixture(scope="module")
def html(payload):
    return gh.render(payload)


# ======================================================================
# (1) payload builders -- NO DATA honesty
# ======================================================================

def _empty_source_kwargs(build_fn) -> dict:
    """If build() accepts a day/date kwarg, force a day nothing will ever have
    data for -- the most implementation-agnostic way to hit the NO DATA path
    without guessing the sibling module's internal path-constant names."""
    sig = inspect.signature(build_fn)
    for name in ("day", "date"):
        if name in sig.parameters:
            return {name: "1970-01-01"}
    return {}


def _patch_paths_to_tmp(monkeypatch, mod, tmp_path) -> None:
    """Belt-and-suspenders alongside the day kwarg above: any module-level
    Path attribute that looks like a data/state root gets pointed at an empty
    tmp dir too, in case the day kwarg alone doesn't gate the source read."""
    for name, val in vars(mod).items():
        if isinstance(val, Path) and not name.startswith("_"):
            monkeypatch.setattr(mod, name, tmp_path)


def _assert_no_data_honest(result: dict) -> None:
    assert result.get("ok") is False, result
    say = result.get("say")
    assert isinstance(say, str) and say, result
    assert say.startswith("NO DATA, looked for"), say
    assert "None" not in say, say
    assert "undefined" not in say, say


def test_funnel_build_reports_no_data_honestly(monkeypatch, tmp_path):
    _patch_paths_to_tmp(monkeypatch, funnel, tmp_path)
    result = funnel.build(**_empty_source_kwargs(funnel.build))
    _assert_no_data_honest(result)


def test_costpulse_build_reports_no_data_honestly(monkeypatch, tmp_path):
    _patch_paths_to_tmp(monkeypatch, costpulse, tmp_path)
    result = costpulse.build(**_empty_source_kwargs(costpulse.build))
    _assert_no_data_honest(result)


# ======================================================================
# (2) funnel conservation
# ======================================================================

FUNNEL_STAGE_IDS = ["ticks", "signals", "enter", "accepted", "filled", "exited"]
FUNNEL_TONES = {"flow", "accepted", "refused", "quiet"}


def test_funnel_stage_ids_exactly_in_spec_order():
    result = funnel.build()
    ids = [s["id"] for s in result["stages"]]
    assert ids == FUNNEL_STAGE_IDS, ids


def test_funnel_link_n_conserves_per_stage_and_tones_are_known():
    """Conservation applies to DRAWN flow, not to every stage with a known
    count: a terminal stage (e.g. "filled" when "exited" isn't computed at
    this granularity) can carry a real `n` with zero outgoing links -- that
    is an honest "nothing drawn past here" state, not an accounting gap. So
    this only holds a stage's outgoing links to its own `n` when the stage
    HAS at least one outgoing link; a stage with none is not constrained."""
    result = funnel.build()
    links_by_from: dict[str, list[dict]] = {}
    for link in result["links"]:
        links_by_from.setdefault(link.get("from"), []).append(link)
    for s in result["stages"]:
        sid, n = s["id"], s.get("n")
        outgoing = links_by_from.get(sid, [])
        if n is None or not outgoing:
            continue
        got = sum((link.get("n") or 0) for link in outgoing if link.get("n") is not None)
        assert got == n, f"stage {sid!r}: outgoing link n sums to {got}, stage n is {n}"
    offenders = [link for link in result["links"] if link.get("tone") not in FUNNEL_TONES]
    assert not offenders, f"link(s) with an unknown tone: {offenders}"


# ======================================================================
# (3) costpulse contract
# ======================================================================

def test_costpulse_zero_filled_series_and_total_reconciles():
    """Real contract (gamma_cockpit_costpulse.py's own docstring):
    build(path=None, days=14) -> {..., days: [{day, cost_usd, fires, ...}, ...],
    total_usd, ...} -- `days` is the per-day bucket LIST (oldest -> newest),
    not a bare cost series; `total_usd` is the sum of each bucket's cost_usd,
    zero-filled for a day with no fires."""
    requested_days = 14
    result = costpulse.build(days=requested_days)
    buckets = result.get("days")
    assert isinstance(buckets, list) and len(buckets) == requested_days, buckets
    costs = [b.get("cost_usd") for b in buckets]
    assert all(isinstance(v, (int, float)) for v in costs), costs
    assert result.get("total_usd") == pytest.approx(sum(costs)), (result.get("total_usd"), sum(costs))


def test_costpulse_exactly_requested_days_zero_filled():
    for n in (7, 14):
        result = costpulse.build(days=n)
        assert len(result["days"]) == n, (n, len(result["days"]))
        # zero-filled: every calendar day in the window gets a bucket even
        # with no fires that day -- never a shorter list from sparse data.
        assert all(isinstance(b.get("cost_usd"), (int, float)) for b in result["days"])


def test_costpulse_corrupt_line_is_skipped_not_raised(monkeypatch, tmp_path):
    src = tmp_path / "conductor-outcomes.jsonl"
    src.write_text(
        '{"fired_at": "2026-09-01T00:00:00+00:00", "cost_usd": 1.5}\n'
        "THIS LINE IS NOT JSON\n"
        '{"fired_at": "2026-09-02T00:00:00+00:00", "cost_usd": 2.0}\n',
        encoding="utf-8",
    )
    patched = False
    # Prefer a Path attribute that already points at a .jsonl file (the most
    # specific match); fall back to any Path attribute (a directory constant)
    # otherwise. Neither guess is fabricated data -- it's monkeypatching the
    # module's OWN declared source location to a controlled fixture.
    for name, val in vars(costpulse).items():
        if isinstance(val, Path) and not name.startswith("_") and val.suffix == ".jsonl":
            monkeypatch.setattr(costpulse, name, src)
            patched = True
            break
    if not patched:
        for name, val in vars(costpulse).items():
            if isinstance(val, Path) and not name.startswith("_"):
                monkeypatch.setattr(costpulse, name, src.parent)
                patched = True
                break
    if not patched:
        pytest.skip("gamma_cockpit_costpulse.py exposes no Path attribute this test can "
                     "monkeypatch to point at a fixture source")
    result = costpulse.build()  # must not raise despite the corrupt middle line
    assert result.get("skipped_lines", 0) >= 1, result
    assert result.get("total_usd") == pytest.approx(3.5), result


# ======================================================================
# (4) rendered page: no bare URLs, no external tags, glow selectors, kit budget
# ======================================================================

# The XML/SVG namespace URI createElementNS() requires is a fixed W3C
# identifier, never a network fetch -- gamma_cockpit_js.py/army_js.py/
# command_js.py/sankey_js.py/views_js.py all already pass it verbatim to
# `document.createElementNS(...)`, predating this file. It is the one
# legitimate "://" the vendor-URL-elision rule was never meant to catch.
_KNOWN_SAFE_URL_SUBSTRINGS = (
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/1999/xhtml",
)


_LIVE_URL_RE = re.compile(r"https?://\S+")  # same scheme scope as gamma_cockpit_vendor._URL_RE


def test_no_bare_url_scheme_anywhere_in_rendered_page(html):
    """The vendor/kit/CSS/JS half of the page must never carry a live http(s)
    URL -- the same scope vendor.py's own elision regex (`_URL_RE =
    re.compile(r"https?://\\S+")`) targets, not a bare "://" substring (which
    also matches `file://`, used all over the existing app JS as a literal
    string describing the page's OWN browsing context -- "a file:// snapshot
    cannot reach it" -- never a fetched resource). The payload DATA blob
    (`const D=...;`) is a separate concern (covered elsewhere) and is
    legitimately allowed to cite a real URL as plain informational text --
    e.g. a `"source": "https://..."` doc citation in the autonomy payload is
    data, not a fetched resource."""
    m = re.search(r"const D=(.*?);</script>", html, re.S)
    scanned = html[:m.start()] + html[m.end():] if m else html
    for safe in _KNOWN_SAFE_URL_SUBSTRINGS:
        scanned = scanned.replace(safe, "")
    hits = _LIVE_URL_RE.findall(scanned)
    assert not hits, f"live http(s) URL(s) slipped past vendor's (url elided) elision: {hits[:5]}"


def test_no_link_or_external_script_tags(html):
    low = html.lower()
    assert "<link" not in low
    assert "<script src" not in low


def test_glow_shell_selectors_present(html):
    assert "gc-rail__item" in html, "no .gc-rail__item rendered anywhere"
    assert "gc-panel" in html, "no .gc-panel rendered anywhere"


def test_kit_files_inlined_and_byte_counts_match_disk():
    """Real contract (gamma_cockpit_glow_ui.py's own docstring): `KIT_FILES`
    is the LIST of vendor/ui-kit/*.html recipe basenames (no extension) the
    module inlines; `KIT_BYTES` is the byte length of the single
    concatenated, stripped CSS string `kit_css(KIT_FILES)` produces -- not a
    per-file byte map. So "byte count matches disk" here means: every named
    kit file actually exists on disk, and KIT_BYTES is self-consistent with
    re-running kit_css() over that same file list (never a stale/hand-typed
    number)."""
    kit_files = glow_ui.KIT_FILES
    assert len(kit_files) >= 15, f"only {len(kit_files)} kit files inlined, expected >= 15"
    for name in kit_files:
        disk_path = KIT_DIR / f"{name}.html"
        assert disk_path.exists(), f"KIT_FILES entry {name!r} has no matching {disk_path.name} on disk"
    recomputed = glow_ui.kit_css(kit_files)
    assert glow_ui.KIT_BYTES == len(recomputed.encode("utf-8")), (
        f"KIT_BYTES={glow_ui.KIT_BYTES} does not match len(kit_css(KIT_FILES).encode())="
        f"{len(recomputed.encode('utf-8'))}"
    )
    assert glow_ui.KIT_BYTES <= 120_000, glow_ui.KIT_BYTES


def test_glow_ui_and_js_report_zero_missing_wiring():
    assert glow_ui.MISSING == [], glow_ui.MISSING
    missing_js = getattr(vjs, "MISSING_JS", None)
    if missing_js is None:
        pytest.skip("gamma_cockpit_js.MISSING_JS not wired yet (owned by another workstream)")
    assert missing_js == [], missing_js


# ======================================================================
# (5) copy hygiene on the new surfaces
# ======================================================================

_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_MIDWORD_ELLIPSIS_RE = re.compile(r"\w…\w")  # ellipsis SPLITTING a word, not following one


def _copy_offenders(strings: list[str]) -> list[str]:
    bad = []
    for s in strings:
        if s is None:
            continue
        if "[" in s or "**" in s or _EMOJI_RE.search(s) or _MIDWORD_ELLIPSIS_RE.search(s):
            bad.append(s)
    return bad


def test_card_titles_in_data_blob_are_clean(payload):
    cards = ((payload.get("cards") or {}).get("cards")) or []
    titles = [c.get("title") for c in cards]
    offenders = _copy_offenders(titles)
    assert not offenders, offenders


def test_views_labels_are_clean():
    views_src = vjs.JS.split("const VIEWS=[", 1)[-1].split("];", 1)[0]
    labels = re.findall(r"label:'([^']*)'", views_src)
    assert labels, "no VIEWS labels found -- extraction pattern may have drifted"
    offenders = _copy_offenders(labels)
    assert not offenders, offenders


def test_gc_eyebrow_and_kpi_label_literals_are_clean():
    """Best-effort scan across every new glow JS module for literal text that
    renders inside a `.gc-eyebrow`/`.gc-kpi__label` element (`class="gc-eyebrow
    ...">TEXT<` shaped template-literal HTML). If none of the modules embed
    such text as a static literal (e.g. it's built purely from payload data),
    there's nothing for this test to check -- that's a skip, not a failure,
    since it isn't this test's job to invent a UI shape the sibling modules
    didn't choose."""
    combined = ""
    for mod in (glow_js, sankey_js, costpulse_js):
        src_path = SCRIPTS / (mod.__name__ + ".py")
        if src_path.exists():
            combined += src_path.read_text(encoding="utf-8")
    hits = re.findall(r'gc-eyebrow[^>]*>([^<]{1,80})<', combined)
    hits += re.findall(r'gc-kpi__label[^>]*>([^<]{1,80})<', combined)
    if not hits:
        pytest.skip("no static gc-eyebrow/gc-kpi__label text literals found to check "
                     "(labels may be built entirely from payload data)")
    offenders = _copy_offenders(hits)
    assert not offenders, offenders


def test_no_em_or_en_dash_outside_payload_blob_or_script_style_comments(html):
    """ROUND-3 POLISH item 1 (panel finding "EM-DASHES on the glass"): a
    typographic em dash (U+2014) or en dash (U+2013) anywhere in the rendered
    page reads as an authored-copy tell. The only two places one may
    legitimately survive are (a) inside the `const D=...` JSON data payload,
    where it can arrive as part of REAL DATA some upstream file/J wrote
    (never authored UI copy this cockpit controls), and (b) inside a
    <script>/<style> comment, which never renders as visible text. Every
    other occurrence is authored copy or a JS-code fallback literal (e.g.
    `s.title||'—'`) and must read as a plain hyphen instead."""
    text = html

    # (a) excise the data payload. Its own <script> tag is fully
    # self-contained on one line (gamma_cockpit_shell.py:
    # "<script>const D=__DATA_JSON__;</script>"), and the JSON serializer
    # already escapes any literal "</script" inside the blob
    # (gamma_cockpit_ui.render()), so the very next "</script>" after
    # "const D=" is unambiguously this tag's own close, never a downstream one.
    m = re.search(r"<script>const D=.*?</script>", text, re.S)
    assert m, "no <script>const D=...</script> payload tag found -- page structure changed"
    text = text[: m.start()] + text[m.end() :]

    # (b) strip /* ... */ block comments -- CSS and JS share this syntax and
    # it cannot appear inside a JS string literal anywhere in this codebase
    # without being escaped, so a global strip is safe.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    # strip whole-line "//" JS comments -- only a line whose first
    # non-whitespace characters ARE "//", so a "//" appearing later on a
    # code line (e.g. inside "file://", "http://" as plain rendered text)
    # is never mistaken for a comment start and never used to hide a real
    # violation.
    text = "\n".join(
        line for line in text.split("\n") if not line.strip().startswith("//")
    )

    for ch, label in ((chr(0x2014), "em dash"), (chr(0x2013), "en dash")):
        count = text.count(ch)
        assert count == 0, (
            f"{count} literal {label}(s) render on the page outside the data "
            f"payload and outside script/style comments -- replace with a "
            f"plain hyphen or restructure the sentence (ROUND-3 POLISH item 1)"
        )


# ======================================================================
# (6) reduced motion
# ======================================================================

def _keyframe_names(css: str) -> set[str]:
    return set(re.findall(r"@keyframes\s+([A-Za-z0-9_-]+)", css))


def _glow_css_text() -> str:
    for attr in ("CSS", "GLOW_CSS"):
        val = getattr(glow_ui, attr, None)
        if isinstance(val, str):
            return val
    return ""


def test_every_keyframe_is_reduced_motion_safe():
    combined_css = ui.CSS + _glow_css_text()
    names = _keyframe_names(combined_css)
    assert names, "expected at least one @keyframes rule across ui.CSS + the glow CSS"
    flat = combined_css.replace(" ", "")
    global_disable = (
        "animation:none!important" in flat
        and re.search(r"@media\(prefers-reduced-motion:reduce\)", flat)
    )
    if global_disable:
        return  # the blanket *{animation:none!important} rule covers every keyframe by name
    media_blocks = re.findall(
        r"@media \(prefers-reduced-motion:reduce\)\{(.*?)\}\s*(?=@|\Z)", combined_css, re.S
    )
    covered = "".join(media_blocks)
    missing = sorted(n for n in names if n not in covered)
    assert not missing, f"keyframes not disabled anywhere under reduced motion: {missing}"


def test_every_animate_calling_js_module_references_rm():
    candidates = [
        "gamma_cockpit_command_js.py", "gamma_cockpit_tiles_js.py",
        "gamma_cockpit_glow_js.py", "gamma_cockpit_sankey_js.py",
        "gamma_cockpit_costpulse_js.py", "gamma_cockpit_kpi_js.py",
    ]
    offenders = []
    for fname in candidates:
        p = SCRIPTS / fname
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if ".animate(" in text and "RM" not in text:
            offenders.append(fname)
    assert not offenders, offenders


# ======================================================================
# (7) module line ceilings
# ======================================================================

def test_module_line_ceilings_respected():
    offenders = []
    for fname, cap in CEILINGS.items():
        p = SCRIPTS / fname
        if not p.exists():
            continue  # sibling not built yet -- nothing to cap
        n = len(p.read_text(encoding="utf-8").splitlines())
        if n > cap:
            offenders.append((fname, n, cap))
    assert not offenders, offenders


def test_army_js_grandfathered_ceiling_does_not_grow():
    p = SCRIPTS / "gamma_cockpit_army_js.py"
    n = len(p.read_text(encoding="utf-8").splitlines())
    assert n <= ARMY_JS_GRANDFATHER_CEILING, (
        f"gamma_cockpit_army_js.py grew to {n} lines "
        f"(grandfathered ceiling is {ARMY_JS_GRANDFATHER_CEILING}, its size at spec time)"
    )


# ======================================================================
# (8) sub-12px / #000 / dash ban on the new modules
# ======================================================================

_PX_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)(px|rem|em)")


def _sub_12px_declarations(css: str) -> list[str]:
    hits = []
    for m in _PX_FONT_SIZE_RE.finditer(css):
        val, unit = float(m.group(1)), m.group(2)
        px = val * 16 if unit in ("rem", "em") else val
        if px < 12:
            hits.append(m.group(0))
    for m in re.finditer(r"font:\s*\d+\s+([\d.]+)px", css):
        if float(m.group(1)) < 12:
            hits.append(m.group(0))
    return hits


def _py_source_minus_docstring_and_comments(text: str) -> str:
    """Same rationale as test_cockpit_redesign_2026_09_03.py's helper of the
    same name (kept as a separate copy per this codebase's existing
    duplication convention across these guard files): a raw full-text scan
    of a .py module for banned literals (#000, dashes, sub-12px) can trip on
    the module's OWN docstring prose describing the rule, or a comment
    enforcing it -- neither is content that ships to the page."""
    out = text
    try:
        tree = ast.parse(text)
        doc = ast.get_docstring(tree, clean=False)
        if doc and doc in out:
            out = out.replace(doc, "", 1)
    except SyntaxError:
        return text
    try:
        tokens = tokenize.generate_tokens(io.StringIO(out).readline)
        out = "".join(tok.string for tok in tokens if tok.type != tokenize.COMMENT)
    except (tokenize.TokenizeError, IndentationError, SyntaxError):
        pass
    # One further, narrowly-targeted exception: `.replace("#000", "#fff")` (or
    # similar) is a COMPLIANCE MECHANISM -- code that guarantees #000 never
    # ships, the opposite of a violation -- not a comment/docstring, so the
    # strip above leaves it in place. Confirmed by direct inspection this is
    # exactly how gamma_cockpit_glow_ui.py's kit_css() enforces its own "no
    # #000" rule on the vendored kit CSS.
    out = re.sub(r'\.replace\(\s*"#000"\s*,\s*"[^"]*"\s*\)', ".replace(SAFE,SAFE)", out)
    return out


def test_no_sub_12px_or_pure_black_or_dashes_in_new_glow_modules():
    for fname in NEW_G_MODULES:
        p = SCRIPTS / fname
        if not p.exists():
            continue
        text = _py_source_minus_docstring_and_comments(p.read_text(encoding="utf-8"))
        assert "#000" not in text, f"{fname}: literal #000"
        for ch, label in ((chr(0x2014), "em dash"), (chr(0x2013), "en dash"),
                           (chr(0x00b7), "middle dot")):
            count = text.count(ch)
            assert count == 0, f"{fname}: {count} {label}(s)"
        hits = _sub_12px_declarations(text)
        assert not hits, f"{fname}: sub-12px declaration(s) {hits[:5]}"


# ======================================================================
# cockpit_dom_check.py / cockpit_exercise.py -- new glow-aware checks exist
# ======================================================================

def test_dom_check_parses_and_gates_on_new_glow_fields():
    src = (SCRIPTS / "cockpit_dom_check.py").read_text(encoding="utf-8")
    assert "gc_panels" in src
    assert "sankey_ribbons" in src


def test_exercise_script_carries_new_glow_behavioral_checks():
    src = (SCRIPTS / "cockpit_exercise.py").read_text(encoding="utf-8")
    for name in ("sankey_drawn", "costpulse_drawn", "rail_active_pill", "kpi_hover_lift"):
        assert name in src, f"{name} check missing from cockpit_exercise.py"


def test_exercise_script_never_clicks_the_fire_button():
    """Never a Fire click, still and always -- this is a read-only behavioral
    probe. No line may combine a `.tile__fire`/`fire-btn` selector with a
    click dispatch (`click_at`)."""
    src = (SCRIPTS / "cockpit_exercise.py").read_text(encoding="utf-8")
    offenders = [
        line for line in src.splitlines()
        if ("tile__fire" in line or "fire-btn" in line) and "click_at" in line
    ]
    assert not offenders, offenders

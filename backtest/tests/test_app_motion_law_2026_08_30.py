"""Static guards for the design laws the command-center build learned by measurement.

Both laws were found by RUNNING the page, not reading it, and both produce a surface that
looks correct in a foreground browser and lies everywhere else -- exactly what a static
test is for.

LAW 1 -- never animate a property whose from-state is invisible, and never let motion own
a value. During an animation's ACTIVE period the animated value applies regardless of
animation-fill-mode, and a SUSPENDED animation (hidden tab, headless capture, paused
compositor) never leaves that period, so `from{opacity:0}` pins the element at invisible
forever. Measured three times on the P&L sheet: element present, 195 cells rendered,
computed opacity 0. The JS half was worse -- an rAF number-roll left a STALE figure on a
trading cell when frames stopped.

LAW 2 -- green/red are reserved for money. A red FIGURE on this page must always mean
dollars lost.

Parsed from source rather than asserted in a browser, so they run offline in the normal
suite in under a second.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "gamma-companion" / "public" / "app"
CSS = APP / "css" / "app.css"


@pytest.fixture(scope="module")
def css() -> str:
    return CSS.read_text(encoding="utf-8", errors="replace")


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _keyframe_blocks(text: str):
    """Yield (name, body) for every @keyframes rule, brace-matched.

    A plain regex cannot do this -- keyframe bodies contain a nested {} per stop.
    """
    for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", text):
        name, i, depth = m.group(1), m.end(), 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        yield name, text[m.end():i - 1]


class TestNoInvisibleFromState:
    def test_no_keyframe_starts_at_opacity_zero(self, css):
        offenders = []
        for name, body in _keyframe_blocks(css):
            for stop in re.finditer(r"(?:^|\})\s*(from|0%)\s*\{([^}]*)\}", body):
                m = re.search(r"opacity\s*:\s*([\d.]+)", stop.group(2))
                if m and float(m.group(1)) <= 0.05:
                    offenders.append("{}({}: opacity {})".format(name, stop.group(1), m.group(1)))
        assert not offenders, (
            "these entrances vanish wherever animations do not advance: " + ", ".join(offenders))

    def test_the_law_is_written_where_it_would_be_broken(self, css):
        """A rule nobody can find next to the code is a rule that gets re-broken."""
        assert "FROM-STATE IS INVISIBLE" in css.upper()


class TestMotionNeverOwnsAValue:
    """The JS half of law 1: rAF is suspended in a hidden tab, so an interpolation
    that owns the displayed text leaves a STALE NUMBER on a trading surface."""

    def test_roll_writes_the_final_value_before_interpolating(self):
        src = (APP / "js" / "motion.js").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"function roll\([^)]*\)\s*\{(.*?)\n  \}", src, re.S)
        assert m, "roll() moved -- re-point this guard"
        body = m.group(1)
        write = body.find("node.textContent = fmt(to)")
        first_raf = body.find("requestAnimationFrame")
        assert write != -1, "roll() no longer writes the final value at all"
        assert write < first_raf, (
            "roll() starts animating before writing the truth -- with rAF suspended the "
            "cell keeps the OLD number, which is a stale figure on a trading surface")


class TestMoneyColoursAreReserved:
    # Deliberately EXCLUDES the BROKEN lane dot. That raised a real question when this
    # test first failed on it: may a broken research lane be red? Resolved yes, and the
    # law sharpened to what it actually protects. The risk is a red FIGURE that is not
    # money -- a reader seeing "-$459" and a red dot must never wonder which is which.
    # They live in different regions: money colours carry figures in the trading band; an
    # alarm dot in the rails sits beside the literal word BROKEN. What is forbidden is a
    # HEALTHY or NEUTRAL state wearing a money colour.
    # This test originally EXCLUDED the broken-lane dot, on the reasoning that a red dot
    # beside the literal word BROKEN could not be mistaken for a figure. An adversarial
    # review rejected that and was right: --neg was also doing duty for engine health,
    # memory pressure, the stop button and error rows, which made the stated guarantee
    # ("a red thing on this page always means money lost") literally false -- and worse,
    # a GREEN health chip could read as profit. State now has its own ramp: --live cyan
    # healthy, --warn amber degraded, --alarm broken (hue 45, sitting between the P&L
    # crimson at 25 and the amber at 80). The law is enforced with no exceptions.
    MONEY_SURFACES = ("panel__delta", "g-big", "garm__net", "garm__bar", "gcal__net",
                      "gcal__f", "g-spark", "flashUp", "flashDn", "--pos:", "--neg:")

    def test_money_colours_appear_only_on_money_surfaces(self, css):
        bad = []
        for line in css.splitlines():
            t = line.strip()
            if t.startswith(("*", "/*", "//")):
                continue
            if re.search(r"var\(--(pos|neg)\)", t) and \
               not any(k in t for k in self.MONEY_SURFACES):
                bad.append(t[:110])
        assert not bad, "a P&L colour escaped the money surfaces: " + " | ".join(bad)

    def test_state_has_its_own_ramp(self, css):
        assert "--alarm:" in css, "the state ramp lost its broken colour"
        assert "--live:" in css and "--warn:" in css

    def test_position_unknown_is_amber_not_red(self, css):
        m = re.search(r'\.g-state\[data-t="warn"\]\{([^}]*)\}', css)
        assert m, "the UNKNOWN position chip lost its rule"
        assert "--warn" in m.group(1)
        assert "--neg" not in m.group(1), (
            "UNKNOWN must not read as a loss -- nobody lost money, the file is stale")


class TestNoTextInsideScaledSvg:
    """This shipped twice as J's 'literally size two font'."""

    def test_no_svg_text_elements_in_app_js(self):
        # The first cut of this test failed on `<textarea` and on the two COMMENTS
        # describing the original bug. A test that cries wolf on its own documentation
        # gets deleted by the next person, so it runs on comment-stripped source and
        # anchors on a word boundary.
        offenders = []
        for js in sorted((APP / "js").glob("*.js")):
            src = _strip_comments(js.read_text(encoding="utf-8", errors="replace"))
            if re.search(r"""createElementNS\([^)]*['"]text['"]""", src) or \
               re.search(r"<text[\s>]", src):
                offenders.append(js.name)
        assert not offenders, (
            "text in a scaled viewBox cannot hold a font size: " + ", ".join(offenders))


class TestNoFabricatedFigures:
    """Every number is sourced or absent -- enforced at the render layer."""

    def test_money_refuses_a_missing_value(self):
        """money() is the single funnel every displayed figure passes through.

        The first cut of this guard flagged `Math.abs(r.net || 0) / peak`, which is
        BAR-WIDTH geometry: a null arm legitimately draws a zero-width bar while the
        figure beside it renders dash(). Coercing null to 0 is only a lie when the 0 is
        what the human READS -- so the check moved to the funnel.
        """
        src = (APP / "js" / "glass.js").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"function money\(v, opts\)\s*\{(.*?)\n  \}", src, re.S)
        assert m, "money() moved -- re-point this guard"
        body = m.group(1)
        assert "return null" in body, "money() must refuse a null, never coerce it"
        assert not re.search(r"v\s*(\|\||\?\?)\s*0", body), (
            "money() coerces a missing value to zero -- a fabricated figure on the glass")

    def test_every_strip_value_has_a_named_absence_branch(self):
        src = (APP / "js" / "glass.js").read_text(encoding="utf-8", errors="replace")
        for token in ("bookVal", "netVal", "todayVal", "tapeVal"):
            assert re.search(token + r"\s*=", src), "{} is gone from the strip".format(token)
        assert "function dash(" in src, "the named-absence helper is gone"
        assert src.count("dash(") >= 5, "a strip value lost its named-absence branch"


class TestReadabilityFloor:
    """J, three separate times, ending in 'literally size two font'."""

    def test_no_declared_font_size_below_12px(self, css):
        bad = []
        for m in re.finditer(r"font(?:-size)?\s*:\s*(?:\d+\s+)?(\d+(?:\.\d+)?)px", css):
            if float(m.group(1)) < 12:
                line = css[:m.start()].count("\n") + 1
                bad.append("line {}: {}px".format(line, m.group(1)))
        assert not bad, "sub-12px type on the glass: " + ", ".join(bad)


class TestNoMangledEscapes:
    """A whole class of SILENTLY DEAD regexes, found 2026-08-30.

    A `\b` written through a shell heredoc can arrive as a literal 0x08 BACKSPACE
    byte instead of the two characters backslash-b. The file still parses, the regex
    still compiles, and it matches nothing -- because it now requires a real backspace
    character in the input.

    It hid for a long time because every tool that displays it renders 0x08 as "\b":
    grep, JSON.stringify, and a terminal all showed exactly the source that was
    intended. It was only caught by dumping raw bytes after a regex that "obviously"
    matched refused to fire.

    Three real instances were live when this test was written: the activity wire's
    failure detector (so a Traceback read as "did some work"), the army view's git
    labeller, and a gamma_home output filter. All three were no-ops.
    """

    ROOTS = ("gamma-companion/public/app", "setup/scripts")

    def test_no_control_bytes_in_source(self):
        offenders = []
        for rel in self.ROOTS:
            base = ROOT / rel
            if not base.exists():
                continue
            for f in list(base.rglob("*.js")) + list(base.rglob("*.css")) + list(base.rglob("*.py")):
                if "node_modules" in str(f) or "__pycache__" in str(f):
                    continue
                try:
                    raw = f.read_bytes()
                except OSError:
                    continue
                # tab(9) newline(10) carriage-return(13) are legitimate; nothing else is
                stray = sorted({b for b in raw if b < 32 and b not in (9, 10, 13)})
                if stray:
                    offenders.append("{} {}".format(f.name, [hex(b) for b in stray]))
        assert not offenders, (
            "stray control bytes -- almost certainly a mangled regex escape: " +
            ", ".join(offenders))

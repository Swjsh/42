"""gamma_cockpit_glow_ui.py -- "Glow Command" tokens, rail-shell layout and
vendored-kit CSS (markdown/specs/COCKPIT-DESIGN-SPEC-V2-GLOW-2026-09-04.md).

Supersedes "Quiet Command" for LOOK only -- the payload contract, the tile
component, the Army mechanics and every id/class the app JS reads are
untouched (see gamma_cockpit_shell.py / gamma_cockpit_ui.py's own docstrings).
J, 2026-09-04: "still just like basic ass text boxes dude come on ... you
need to get visuals on there ... do not just use basic ass shit." This module
is the CSS half of the answer: the AetherOps navy/indigo/violet/cyan token
system, a left nav-rail shell, KPI/queue/health/alert primitives, and the
vendored uiverse.io/MagicUI recipe CSS (setup/scripts/vendor/ui-kit/, doc:
analysis/deep-research/COCKPIT-VISUAL-KIT-2026-09-04.md) inlined and rethemed
onto this module's own tokens.

Exports:
  GLOW_CSS    the full string -- concatenated as the LAST term of
              gamma_cockpit_ui.CSS, so every selector here can freely override
              an earlier module's rule by source order (same specificity).
  KIT_FILES   the 20 vendor/ui-kit/*.html recipe names this module inlines.
  KIT_BYTES   byte length of the concatenated, stripped kit CSS.
  MISSING     module.attr names this file tried to pull CSS from (the Sankey,
              cost-pulse and Army-glow contributors, owned by other builders
              this same pass) that were not importable yet -- empty once
              C/D/F have landed; non-empty is expected mid-build, never a
              hard failure (this module never raises on a sibling's absence).
  kit_css(names)  the extraction function itself, so a future caller can pull
              a different subset without re-reading this whole module.

RETHEME MECHANISM: every vendor/ui-kit/*.html file defines its OWN `:root{...}`
block pinning literal defaults for the `--uk-*` names it references (so each
snippet also renders standalone via demo.html). kit_css() strips every such
`:root` rule out of the inlined copy -- section 2 below defines the SAME
`--uk-*` names exactly once, as aliases onto this module's own `--gc-*`
tokens, so every kept rule's `var(--uk-accent)` etc. now resolves through the
live theme rather than the snippet's own hardcoded default. That is what
"every vendored kit snippet is rethemed through its --uk-* variables" (spec
section 2) means in practice: delete the private token, keep the public one.

BAN LIST (this pass's contract -- the ban-list *tests* are rewritten for it by
a sibling builder, not by this file, but the rules bind everything this file
writes): every box-shadow value must reference a --gc-glow*/--gc-shadow*
token or be an inset hairline; gradients only inside .gc-* selectors, the
token block, or the stage/army CSS this file never touches; text-transform:
uppercase only on .gc-eyebrow/.gc-kpi__label, always with letter-spacing; no
#000, no font-size below 12px, no em/en dash or middle dot literal, no
"://" anywhere (kit files carry none themselves -- verified in the source
research doc -- and this module adds none). `.chip.ok .dot{background:
var(--pos)}` and `tabular-nums` are gamma_cockpit_ui.py's own strings and are
never touched here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ============================================================================
# 1 + 2. TOKENS -- spec section 2, dark-first, light theme redeclares every
#         colour token; plus the legacy stage-token remap and the --uk-*
#         bridge every inlined kit rule resolves through (see module docstring
#         "RETHEME MECHANISM").
# ============================================================================
_TOKENS_CSS = r"""
:root{
  /* ==================== Glow Command tokens (dark, default) ==================== */
  --gc-canvas-0:#0a0e1c; --gc-canvas-1:#0d1226; --gc-panel:#111833; --gc-panel-2:#161f3f;
  --gc-line:rgba(120,130,255,.16); --gc-line-2:rgba(120,130,255,.28);
  --gc-ink-1:#eef1ff; --gc-ink-2:#aab3d6; --gc-ink-3:#7581a8;
  --gc-indigo:#6366f1; --gc-violet:#8b5cf6; --gc-cyan:#22d3ee; --gc-pink:#ec4899;
  --gc-grad:linear-gradient(135deg,var(--gc-indigo),var(--gc-violet) 55%,var(--gc-cyan));
  --gc-glow:0 0 24px rgba(99,102,241,.35); --gc-glow-cyan:0 0 18px rgba(34,211,238,.35);
  --gc-glow-soft:0 0 12px rgba(99,102,241,.22);
  --gc-shadow-1:0 20px 40px -20px rgba(0,0,0,.6);
  --gc-shadow-inset:inset 0 1px 0 rgba(255,255,255,.03);
  --gc-good:#34d399; --gc-warn:#fbbf24; --gc-bad:#fb7185; --gc-info:#60a5fa;
  --gc-chip-good:rgba(52,211,153,.14); --gc-chip-warn:rgba(251,191,36,.14);
  --gc-chip-bad:rgba(251,113,133,.14); --gc-chip-info:rgba(96,165,250,.14);
  --gc-r:16px; --gc-r-sm:10px; --gc-pad:20px; --gc-rail-w:220px;
  --gc-t-fast:150ms; --gc-t-base:240ms; --gc-t-open:320ms; --gc-t-draw:900ms;
  --gc-ease:cubic-bezier(.2,.8,.2,1); --gc-ease-ambient:cubic-bezier(.45,0,.55,1);
}
/* ==================== Glow Command tokens (light) ====================
   Structure stays identical -- only the values change: pale canvas, white
   panels, an 8%-alpha glow instead of dark-mode's ~35% (spec section 2's
   "light theme = same structure, canvas #f3f5fb, panels white, glow at 8%"). */
:root[data-theme="light"]{
  --gc-canvas-0:#f3f5fb; --gc-canvas-1:#eef1fa; --gc-panel:#ffffff; --gc-panel-2:#f6f7fd;
  --gc-line:rgba(99,102,241,.16); --gc-line-2:rgba(99,102,241,.26);
  --gc-ink-1:#1a1f36; --gc-ink-2:#4d5573; --gc-ink-3:#6b7290;
  --gc-indigo:#6366f1; --gc-violet:#8b5cf6; --gc-cyan:#0891a8; --gc-pink:#db2777;
  --gc-glow:0 0 20px rgba(99,102,241,.08); --gc-glow-cyan:0 0 16px rgba(8,145,168,.08);
  --gc-glow-soft:0 0 10px rgba(99,102,241,.06);
  --gc-shadow-1:0 16px 32px -18px rgba(30,41,90,.16);
  --gc-shadow-inset:inset 0 1px 0 rgba(255,255,255,.7);
  --gc-good:#0d9668; --gc-warn:#a35a00; --gc-bad:#c8323a; --gc-info:#1d68c4;
  --gc-chip-good:rgba(13,150,104,.12); --gc-chip-warn:rgba(163,90,0,.12);
  --gc-chip-bad:rgba(200,50,58,.12); --gc-chip-info:rgba(29,104,196,.12);
}
/* ---- legacy stage-token remap: the Army stage borrows Glow Command's own
   panel + cyan glow instead of the old hand-picked hex, in BOTH themes, so
   the one glowing object on the page reads as part of the same system. ---- */
:root{
  --stage-bg:var(--gc-panel); --stage-glow:var(--gc-glow-cyan);
  --beam:var(--gc-cyan); --star:var(--gc-ink-1);
}
:root[data-theme="light"]{
  --stage-bg:var(--gc-panel); --stage-glow:var(--gc-glow-cyan);
  --beam:var(--gc-cyan); --star:var(--gc-ink-2);
}
"""

# ---- the --uk-* bridge: every vendored kit file references these names.
# Defined ONCE, as aliases onto --gc-*, so both themes flow through without a
# second light-mode block (custom properties re-resolve automatically).
_BRIDGE_CSS = r"""
:root{
  --uk-canvas:var(--gc-canvas-0); --uk-panel:var(--gc-panel); --uk-panel-2:var(--gc-panel-2);
  --uk-line:var(--gc-line); --uk-line-soft:var(--gc-line-2);
  --uk-accent:var(--gc-indigo); --uk-accent-2:var(--gc-violet); --uk-accent-3:var(--gc-cyan);
  --uk-accent-electron:var(--gc-violet);
  --uk-glow:var(--gc-glow-cyan);
  --uk-green:var(--gc-good); --uk-amber:var(--gc-warn); --uk-red:var(--gc-bad);
  --uk-cyan-status:var(--gc-cyan);
}
"""

# ============================================================================
# 3. KIT INLINING -- read setup/scripts/vendor/ui-kit/<name>.html, pull its
#    <style> block, drop html/body/*/:root rules (see RETHEME MECHANISM
#    above), concatenate.
# ============================================================================
_KIT_DIR = Path(__file__).resolve().parent / "vendor" / "ui-kit"

KIT_FILES = [
    "nav-rail-active-pill", "other-gradient-underline-input", "button-glow-cta",
    "button-gradient-cta-glow", "card-kpi-stat", "card-glow-border",
    "card-magic-spotlight", "chip-status", "chip-animated-shiny-text",
    "chart-sparkline-card", "list-alert-row", "list-avatar-row",
    "card-promo-panel", "background-panel-shell-canvas", "background-aurora-glow",
    "background-dot-pattern", "card-border-beam", "tooltip-hover-reveal",
    "loader-atom-orbit", "chart-progress-ring",
]

_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_DROP_SELECTORS = {"*", "html", "body", ":root"}


def _split_top_rules(css: str) -> list[tuple[str, str]]:
    """Split CSS text into (selector, '{...}') pairs at the TOP nesting level
    only. An @media/@keyframes body is matched by a brace-depth counter, never
    split early by a regex that can't tell a nested '}' from the rule's own."""
    rules: list[tuple[str, str]] = []
    i, n = 0, len(css)
    while i < n:
        while i < n and css[i].isspace():
            i += 1
        if i >= n:
            break
        brace = css.find("{", i)
        if brace == -1:
            break
        selector = css[i:brace].strip()
        depth, j = 0, brace
        while j < n:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        rules.append((selector, css[brace:j + 1]))
        i = j + 1
    return rules


def _keep(selector: str) -> bool:
    """False for a rule whose selector is (only) html/body/*/  :root -- this
    module defines those tokens/resets itself; a per-file :root would shadow
    the live theme with that snippet's own hardcoded default."""
    parts = {p.strip() for p in selector.split(",")}
    return not parts.issubset(_DROP_SELECTORS)


def _extract_style(html: str) -> str:
    m = _STYLE_RE.search(html)
    if not m:
        return ""
    body = _COMMENT_RE.sub("", m.group(1))
    kept = [sel + b for sel, b in _split_top_rules(body) if _keep(sel)]
    css = "\n".join(kept)
    # Three kit files (card-magic-spotlight, card-border-beam,
    # background-dot-pattern) use `#000` only inside a mask gradient -- a
    # mask cares about opacity/luminance, never the RGB channel, so #fff is
    # interchangeable there (and is the more spec-correct choice for the
    # standard `mask-image` property's default luminance mode, vs. #000
    # which would invert that mask on a browser honouring it -- `-webkit-
    # mask-image`'s legacy alpha mode is identical either way). Swapping it
    # keeps this module's own "no #000" rule true of everything it emits,
    # inlined kit CSS included, with no visual change.
    css = css.replace("#000", "#fff")
    # Integration pass (2026-09-04): three more normalisations so the inlined
    # kit obeys the SAME ban list as everything this module writes itself:
    # (a) every kit rule is scoped under `.gc-app` (the shell root) -- a kit
    #     gradient then lives in a `.gc-*` selector like every other Glow
    #     Command gradient, and can never restyle the drawer/palette outside
    #     the shell; @keyframes pass through, @media bodies are scoped inside;
    # (b) `text-transform:uppercase` is dropped -- uppercase is reserved for
    #     .gc-eyebrow/.gc-kpi__label (with letter-spacing) by contract;
    # (c) any font-size under the 12px floor is lifted to 12px.
    css = _UPPER_RE.sub("", css)
    css = _lift_font_floor(css)
    return _scope_rules(_split_top_rules(css))


_UPPER_RE = re.compile(r"text-transform\s*:\s*uppercase\s*;?")
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)(px|rem|em)")
_FONT_SHORTHAND_RE = re.compile(r"(font\s*:\s*\d+\s+)([\d.]+)px")
_AT_PASSTHRU = ("@keyframes", "@-webkit-keyframes", "@font-face", "@property")
_SCOPE = ".gc-app "


def _lift_font_floor(css: str) -> str:
    def _fs(m: re.Match) -> str:
        v, u = float(m.group(1)), m.group(2)
        px = v * 16 if u in ("rem", "em") else v
        return "font-size:12px" if px < 12 else m.group(0)

    def _sh(m: re.Match) -> str:
        return m.group(1) + "12px" if float(m.group(2)) < 12 else m.group(0)

    return _FONT_SHORTHAND_RE.sub(_sh, _FONT_SIZE_RE.sub(_fs, css))


def _scope_rules(rules: list[tuple[str, str]]) -> str:
    out = []
    for sel, block in rules:
        s = sel.strip()
        if s.startswith(_AT_PASSTHRU):
            out.append(sel + block)
        elif s.startswith("@"):
            inner = [(a, b) for a, b in _split_top_rules(block[1:-1]) if _keep(a)]
            out.append(sel + "{\n" + _scope_rules(inner) + "\n}")
        else:
            out.append(",".join(_SCOPE + part.strip() for part in sel.split(",")) + block)
    return "\n".join(out)


def kit_css(names: list[str]) -> str:
    """Read each vendor/ui-kit/<name>.html, extract+clean its <style> block,
    concatenate with a one-line provenance banner per file (so a diff of
    GLOW_CSS still shows which kit file a rule came from)."""
    parts = []
    for name in names:
        path = _KIT_DIR / f"{name}.html"
        css = _extract_style(path.read_text(encoding="utf-8"))
        parts.append(f"/* ---- kit: {name} ---- */\n{css}")
    return "\n".join(parts)


_KIT_CSS = kit_css(KIT_FILES)
KIT_BYTES = len(_KIT_CSS.encode("utf-8"))

# ============================================================================
# 4. LAYOUT -- spec section 3's rail + 3-column content shell, KPI cards,
#    chips, rows, icon tiles, panel/promo/no-data/tooltip/sankey/costpulse
#    shells. New .gc-* selectors only; nothing here redefines a selector an
#    earlier module owns except `.cmdbar`/`.app`'s OWN rules, which this file
#    is entitled to re-flow (spec: "the topbar becomes the rail") because it
#    loads last in the CSS concatenation (see gamma_cockpit_ui.CSS).
# ============================================================================
_LAYOUT_CSS = r"""
/* ---- shell: rail + main, spec section 3 ---- */
.gc-app{display:grid;grid-template-columns:var(--gc-rail-w) minmax(0,1fr);
  grid-template-rows:1fr auto;min-height:100vh;background:var(--gc-canvas-0)}
.gc-app>.cmdbar.topbar{grid-column:1;grid-row:1/3;position:sticky;top:0;align-self:start;
  height:100vh;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;
  gap:4px;padding:20px 12px;background:var(--gc-panel);border-right:1px solid var(--gc-line);
  border-bottom:0;overflow-y:auto;overflow-x:hidden}
.gc-app>.main{grid-column:2;grid-row:1;min-width:0}
.gc-app>.foot{grid-column:2;grid-row:2}
/* the rail's own header row: mark + wordmark stay at the top, full width */
.gc-app .topbar__mark,.gc-app .mark{margin-bottom:2px}
.gc-app .word{font-size:16px}
/* nav becomes a vertical stack of rail items; existing .topbar__tabs/.tabs
   markup gets this for free, no JS edit needed */
.gc-app .tabs.topbar__tabs,.gc-app #nav,.gc-rail{
  display:flex;flex-direction:column;gap:2px;margin-left:0;margin-top:18px;height:auto;width:100%}
.gc-app .tabs a,.gc-app .topbar__tabs a,.gc-rail__item{
  display:flex;align-items:center;gap:12px;width:100%;height:auto;padding:10px 12px;
  border-radius:var(--gc-r-sm);color:var(--gc-ink-3);font:500 13px/1 var(--font);
  border-bottom:0!important}
.gc-app .tabs a:hover,.gc-app .topbar__tabs a:hover,.gc-rail__item:hover{
  background:rgba(120,130,255,.06);color:var(--gc-ink-1)}
.gc-app .tabs a.on,.gc-app .topbar__tabs a.on,.gc-rail__item.on{
  background:linear-gradient(90deg,rgba(99,102,241,.20),rgba(139,92,246,.10));
  color:var(--gc-ink-1);box-shadow:inset 0 0 0 1px rgba(139,92,246,.35)}
.gc-app .ticker{margin-top:auto;flex-direction:column;align-items:stretch;gap:10px;
  padding-top:14px;border-top:1px solid var(--gc-line)}
.gc-app .topbar__clock{margin-left:0}
@media (max-width:900px){
  .gc-app{grid-template-columns:1fr;grid-template-rows:auto auto 1fr auto}
  .gc-app>.cmdbar.topbar{grid-column:1;grid-row:1;position:sticky;top:0;height:auto;
    flex-direction:row;align-items:center;border-right:0;border-bottom:1px solid var(--gc-line);
    overflow-x:auto;overflow-y:visible}
  .gc-app .tabs.topbar__tabs,.gc-app #nav,.gc-rail{flex-direction:row;margin-top:0;width:auto}
  .gc-app .ticker{margin-top:0;flex-direction:row;padding-top:0;border-top:0}
  .gc-app>.main{grid-column:1;grid-row:2}
  .gc-app>.foot{grid-column:1;grid-row:3}
}

/* ---- header: title/subtitle/search/CTA (spec section 1 header row) ---- */
.gc-header{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--s6);
  flex-wrap:wrap;margin-bottom:var(--s6)}
.gc-title{font:600 26px/1.2 var(--font);letter-spacing:-.01em;color:var(--gc-ink-1);margin:0}
.gc-sub{font:400 13px/1.5 var(--font);color:var(--gc-ink-3);margin-top:4px;max-width:60ch}
.gc-headright{display:flex;align-items:center;gap:var(--s5);flex-wrap:wrap}
.gc-search{position:relative;--width-of-input:260px;width:var(--width-of-input);
  display:flex;align-items:center}
.gc-search input{color:var(--gc-ink-1);font-size:13.5px;background:transparent;width:100%;
  box-sizing:border-box;padding:.7em 2.2em .7em 0;border:none;border-bottom:2px solid var(--gc-line)}
.gc-search input:focus{outline:none}
.gc-search .gc-search-line{position:absolute;background:var(--gc-grad);width:0;height:2px;
  bottom:0;left:0;transition:width var(--gc-t-base) var(--gc-ease)}
.gc-search input:focus+.gc-search-line{width:100%}
.gc-search kbd{position:absolute;right:0;padding:2px 6px;border-radius:4px;
  background:var(--gc-panel-2);border:1px solid var(--gc-line);font:12px/1 var(--mono);
  color:var(--gc-ink-3);pointer-events:none}
.gc-cta{position:relative;color:#fff;background:var(--gc-grad);padding:10px 20px;
  border-radius:var(--gc-r-sm);font:600 13px/1 var(--font);cursor:pointer;border:none;
  box-shadow:var(--gc-glow)}
.gc-cta:hover{box-shadow:var(--gc-glow-cyan)}
.gc-cta:active{transform:scale(.97)}
.gc-shiny{display:inline-block;background:linear-gradient(110deg,var(--gc-ink-3) 45%,var(--gc-ink-1) 55%,
  var(--gc-ink-3) 65%);background-size:250% 100%;-webkit-background-clip:text;background-clip:text;
  color:transparent;animation:gc-shine 3s linear infinite}
@keyframes gc-shine{from{background-position:100% 0}to{background-position:-100% 0}}

/* ---- panel shell: every card on the page ---- */
.gc-panel{position:relative;background:var(--gc-panel);border:1px solid var(--gc-line);
  border-radius:var(--gc-r);padding:var(--gc-pad);box-shadow:var(--gc-shadow-inset),var(--gc-shadow-1)}
.gc-panel__head{display:flex;align-items:center;justify-content:space-between;gap:var(--s4);
  margin-bottom:var(--s5)}
.gc-panel__head h3{font:600 15px/1.3 var(--font);color:var(--gc-ink-1);margin:0}
.gc-eyebrow{font:600 12px/1 var(--font);letter-spacing:.06em;text-transform:uppercase;
  color:var(--gc-ink-3)}

/* ---- responsive grid: 3-col wide, 2-col mid, 1-col narrow ---- */
.gc-grid{display:grid;gap:var(--s5);grid-template-columns:minmax(0,1fr)}
@media (min-width:900px){.gc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1400px){.gc-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
.gc-grid--kpi{display:grid;gap:var(--s5);grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}

/* ---- KPI stat card ---- */
.gc-kpi{background:var(--gc-panel);border:1px solid var(--gc-line);border-radius:var(--gc-r);
  padding:var(--gc-pad);box-shadow:var(--gc-shadow-inset),var(--gc-shadow-1);
  transition:transform var(--gc-t-base) var(--gc-ease),box-shadow var(--gc-t-base) var(--gc-ease)}
.gc-kpi:hover{transform:translateY(-2px);box-shadow:0 12px 32px rgba(99,102,241,.16),var(--gc-shadow-inset)}
.gc-kpi__icon{width:40px;height:40px;border-radius:var(--gc-r-sm);display:flex;align-items:center;
  justify-content:center;margin-bottom:14px;background:var(--gc-grad);box-shadow:var(--gc-glow-soft)}
.gc-kpi__icon svg{width:18px;height:18px}
.gc-kpi__label{font:600 12px/1 var(--font);letter-spacing:.05em;text-transform:uppercase;
  color:var(--gc-ink-3);margin-bottom:6px}
.gc-kpi__value{font:600 26px/1.2 var(--mono);letter-spacing:-.02em;color:var(--gc-ink-1);
  font-variant-numeric:tabular-nums;margin-bottom:8px}
.gc-delta{display:inline-flex;align-items:center;gap:4px;font:600 12px/1 var(--font);
  padding:3px 8px;border-radius:999px;font-variant-numeric:tabular-nums}
.gc-delta.up{color:var(--gc-good);background:var(--gc-chip-good)}
.gc-delta.down{color:var(--gc-bad);background:var(--gc-chip-bad)}
.gc-delta.flat{color:var(--gc-ink-3);background:rgba(120,130,255,.08)}

/* ---- status chips (approval queue / alerts / any health state) ---- */
.gc-chip{display:inline-flex;align-items:center;gap:6px;font:600 12px/1 var(--font);
  padding:4px 10px;border-radius:999px;border:1px solid transparent;white-space:nowrap}
.gc-chip::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.gc-chip.good{color:var(--gc-good);background:var(--gc-chip-good);border-color:rgba(52,211,153,.3)}
.gc-chip.warn{color:var(--gc-warn);background:var(--gc-chip-warn);border-color:rgba(251,191,36,.3)}
.gc-chip.bad{color:var(--gc-bad);background:var(--gc-chip-bad);border-color:rgba(251,113,133,.3)}
.gc-chip.info{color:var(--gc-info);background:var(--gc-chip-info);border-color:rgba(96,165,250,.3)}
.gc-chip.queue{color:var(--gc-violet);background:rgba(139,92,246,.12);border-color:rgba(139,92,246,.3)}

/* ---- rows: approval queue / agent health / alerts share one anatomy ---- */
.gc-row{display:flex;align-items:center;gap:14px;padding:12px 14px;border-radius:var(--gc-r-sm);
  transition:background var(--gc-t-fast) var(--gc-ease)}
.gc-row:hover{background:rgba(120,130,255,.05)}
.gc-row__title{font:600 13px/1.3 var(--font);color:var(--gc-ink-1)}
.gc-row__sub{font:400 12px/1.4 var(--font);color:var(--gc-ink-3)}
.gc-row__text{flex:1;min-width:0}
.gc-icon-tile{width:34px;height:34px;border-radius:var(--gc-r-sm);display:flex;align-items:center;
  justify-content:center;flex:none;background:rgba(99,102,241,.12);border:1px solid rgba(99,102,241,.25);
  color:var(--gc-indigo)}
.gc-icon-tile.warn{background:var(--gc-chip-warn);border-color:rgba(251,191,36,.3);color:var(--gc-warn)}
.gc-icon-tile.bad{background:var(--gc-chip-bad);border-color:rgba(251,113,133,.3);color:var(--gc-bad)}
.gc-icon-tile.good{background:var(--gc-chip-good);border-color:rgba(52,211,153,.3);color:var(--gc-good)}
.gc-spark{width:70px;height:22px;flex:none}
.gc-spark polyline{fill:none;stroke-width:1.5}

/* ---- promo panel ---- */
.gc-promo{position:relative;overflow:hidden;border-radius:var(--gc-r);padding:28px;
  background:linear-gradient(160deg,var(--gc-panel-2) 0%,var(--gc-canvas-1) 100%);
  border:1px solid var(--gc-line)}
.gc-promo::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(70% 60% at 15% 0%,rgba(99,102,241,.20) 0%,transparent 65%)}
.gc-promo__body{position:relative;z-index:1;max-width:70%}
.gc-promo__body h4{margin:0 0 8px;font:700 18px/1.3 var(--font);color:var(--gc-ink-1)}
.gc-promo__body p{margin:0 0 16px;font:400 13px/1.6 var(--font);color:var(--gc-ink-3)}

/* ---- NO DATA state: designed, not bare text (spec's own non-negotiable) ---- */
.gc-nodata{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  padding:32px 16px;text-align:center;border:1px dashed var(--gc-line-2);border-radius:var(--gc-r-sm);
  color:var(--gc-ink-3);font:400 12.5px/1.5 var(--font)}
.gc-nodata b{color:var(--gc-ink-2);font-weight:600}

/* ---- hover tooltip (age/source disclosure on a figure) ---- */
.gc-tooltip{position:relative;display:inline-block}
.gc-tooltip__panel{position:absolute;left:0;top:100%;margin-top:8px;min-width:180px;
  background:var(--gc-panel-2);border:1px solid var(--gc-line-2);border-radius:var(--gc-r-sm);
  box-shadow:var(--gc-shadow-1);opacity:0;pointer-events:none;transition:opacity var(--gc-t-base) var(--gc-ease);
  padding:10px 12px;color:var(--gc-ink-2);font:400 12px/1.5 var(--font);z-index:5}
.gc-tooltip:hover .gc-tooltip__panel,.gc-tooltip:focus-within .gc-tooltip__panel{
  opacity:1;pointer-events:auto}

/* ---- Sankey / cost-pulse shells: sized frame here, drawing owned by the
   sibling modules that append SANKEY_CSS/COSTPULSE_CSS below (section 5) ---- */
.gc-sankey{grid-column:1/-1}
@media (min-width:1400px){.gc-sankey{grid-column:span 2}}
.gc-sankey svg{width:100%;height:auto;display:block}
.gc-costpulse{position:relative}
.gc-costpulse__big{font:700 24px/1.2 var(--mono);color:var(--gc-ink-1);margin:6px 0 4px;
  font-variant-numeric:tabular-nums}

/* ---- integration pass (2026-09-04, after the first headless captures) ---- */
/* header: the Cmd-K hint is a plain span (gc-kbd), not a <kbd>; unstyled it wrapped
   onto two lines beside the input */
.gc-search .gc-kbd{position:absolute;right:0;top:50%;transform:translateY(-50%);padding:2px 6px;
  border-radius:4px;background:var(--gc-panel-2);border:1px solid var(--gc-line);
  font:12px/1 var(--mono);color:var(--gc-ink-3);pointer-events:none;white-space:nowrap}
/* a panel that takes two of the three columns on wide screens (Army stage, promo) */
.gc-span2{grid-column:1/-1}
@media (min-width:1400px){.gc-span2{grid-column:span 2}}
/* KPI cards: 26px mono figures truncated at six-up ("40 pendi...") -- 22px fits; tighter
   padding keeps the routing map inside the first 950px */
.gc-kpi{padding:14px 16px}
.gc-kpi .gc-kpi__icon{width:34px;height:34px;margin-bottom:8px}
.gc-kpi .gc-kpi__value{font-size:22px;line-height:26px}
.gc-kpi .vital__state{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* Needs-you queue: the 13-column tile grammar is built for full-width rows -- inside the
   1/3-width panel its 200px title + 160px graphic columns spilled past the panel edge, and
   .gc-row's flex-row anatomy turned the <details> into a horizontal flexbox (the body sat
   BESIDE the summary and pushed it 75px down on open, so a second click missed). Two-row
   compact grammar here: icon | title / state | chip | Fire | chevron. */
.gc-queue .tile.gc-row{display:block;padding:0;gap:0}
.gc-queue .tile__head{grid-template-columns:24px 12px minmax(0,1fr) 12px auto 12px auto 12px 20px;
  grid-template-rows:auto auto;row-gap:2px;height:auto;min-height:var(--row-h);padding:10px 8px}
.gc-queue .tile__ic{grid-row:1/3}
.gc-queue .tile__title{grid-column:3;grid-row:1;font-size:14px}
.gc-queue .tile__say{grid-column:3;grid-row:2;font-size:12px;line-height:16px}
.gc-queue .tile__gfx,.gc-queue .tile__src{display:none}
.gc-queue .gc-chip{grid-column:5;grid-row:1/3}
.gc-queue .tile__fire{grid-column:7;grid-row:1/3}
.gc-queue .tile__chev{grid-column:9;grid-row:1/3}
.gc-queue .tile__body{padding:4px 12px 16px 44px}
.gc-queue .tile__body>*{max-width:none}
/* Agent health: the honest NO DATA sparkline slot is a compact mark, and a long lane
   sentence clamps to two lines instead of running under it */
.gc-health .gc-row__sub{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.gc-health .gc-row .gc-nodata{flex:none;padding:4px 8px;font-size:12px;gap:0}
"""

# ============================================================================
# 5. CONTRIBUTOR CONCAT -- sibling modules built this same pass. Absence is
#    expected mid-build (this file must never throw on it) and recorded in
#    MISSING for the integration test to assert empty once every builder has
#    landed.
# ============================================================================
MISSING: list[str] = []


def _optional(modname: str, attr: str) -> str:
    try:
        mod = __import__(modname)
    except Exception:  # noqa: BLE001 -- a sibling module not landed yet, or broken
        MISSING.append(modname)
        return ""
    css = getattr(mod, attr, None)
    if not isinstance(css, str) or not css.strip():
        MISSING.append(f"{modname}.{attr}")
        return ""
    return css


_CONTRIB_CSS = "\n".join(filter(None, [
    _optional("gamma_cockpit_sankey_js", "SANKEY_CSS"),
    _optional("gamma_cockpit_costpulse_js", "COSTPULSE_CSS"),
    _optional("gamma_cockpit_army_glow_ui", "ARMY_GLOW_CSS"),
]))

# ============================================================================
# 6. REDUCED MOTION -- gamma_cockpit_ui.py's own base CSS already disables
#    every animation/transition page-wide via `*{animation:none!important;
#    transition:none!important}` under this same query; this block names
#    every keyframe THIS file (or an inlined kit file) introduces explicitly,
#    so the intent survives even if that global rule is ever narrowed.
# ============================================================================
_REDUCED_MOTION_CSS = r"""
@media (prefers-reduced-motion:reduce){
  .gc-shiny,.uk-live-dot,.uk-flow-dash,.uk-shiny-text,.uk-dot-pattern--glow,
  .uk-border-beam::after,.uk-atom-star,.uk-atom-nucleus,.uk-atom-electron{animation:none!important}
  .gc-kpi,.gc-cta,.gc-search .gc-search-line,.gc-tooltip__panel,.gc-row{transition:none!important}
}
"""

GLOW_CSS = (
    _TOKENS_CSS + _BRIDGE_CSS + _LAYOUT_CSS + _KIT_CSS + _CONTRIB_CSS + _REDUCED_MOTION_CSS
)


if __name__ == "__main__":
    print(
        f"GLOW_CSS: {len(GLOW_CSS.splitlines())} lines, {len(KIT_FILES)} kit files "
        f"({KIT_BYTES} B), MISSING={MISSING}"
    )

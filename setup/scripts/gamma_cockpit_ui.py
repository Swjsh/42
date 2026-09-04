"""gamma_cockpit_ui.py - the COCKPIT's markup, styling and behaviour.

Split out of gamma_home.py so neither file passes the repo's 800-line ceiling.
This module owns PRESENTATION only: every number it renders arrives pre-computed
in the payload. It never reads a state file and never derives a metric.

HARD CONSTRAINT: one self-contained file. No CDN, no external JS or CSS, no
network font request. It must work from a file:// URL with no network, which
rules out every chart library - the sparklines, bars and the org graph are
hand-rolled SVG. Fonts and a handful of tiny CSS/JS libraries ARE inlined
(base64 data: URIs / vendored text via gamma_cockpit_vendor.py) - that is a
different thing from a network dependency, and the guard tests check for the
difference (every @font-face src: must be url(data:..., never a fetch).

DESIGN SYSTEM -- "Quiet Command" (markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md,
supersedes the 2026-08-30 spec for LOOK; that spec's plumbing choices survive only
where restated here). The load-bearing rules:
  * ONE glowing object. The Army stage is the only place light comes from; the
    rest of the page is a silent, near-black slate lit only by a luminance
    ladder (canvas -> surface-1 -> surface-2 -> surface-3) and 1px hairlines.
    No page-wide aurora, no ambient grain overlay.
  * A closed tone taxonomy: act | live | gain | loss | caution | nodata.
    Gain/loss (--pos/--neg) are reserved for a value whose SERIES IS P&L.
    System and agent health use traffic-light DOTS, never red/green fills -
    colour-collision between "is this healthy" and "did we make money" is a
    named dashboard anti-pattern and this file keeps them apart.
  * The accent is earned, not decorative: cyan, because that is the Army
    stage's own beam hue (--st-live) - the rest of the page borrows the one
    object's colour rather than introducing a second hue.
  * Elevation is LUMINANCE, not shadow. The CSS shadow property is banned
    except three named exceptions (the stage bloom, the Cmd-K palette, the
    chat dock's top edge) - a test greps the whole file for that property
    name and fails past 3 occurrences.
  * No gradients except the stage's own radial bloom and the per-edge beam
    gradient already living inside the Army SVG (owned by gamma_cockpit_army_js.py).
  * border-radius capped at 8px on every container; pills (999px) are for
    buttons/chips only.
  * No hover transforms anywhere - a row highlights by background only.
    Buttons get a single `:active{transform:scale(.97)}`, nothing on hover.
  * No entrance stagger on repeatedly-rendered rows/cards. The Army stage's
    own one-time load choreography (owned by army_js/command_js) is the sole
    exception, per spec section 4.1's "ambient motion budget = the Army stage
    only".
  * Tabular numerals everywhere a number can change.
  * Both a dark (default) and a light theme are first-class: every token
    used anywhere in the app JS is defined in BOTH `:root` and
    `:root[data-theme="light"]`, and --ink-3 on --canvas holds >=4.5:1
    contrast in both (test_gamma_cockpit_vendor_2026_09_03.py checks this).

HONESTY RULES BAKED INTO THE MARKUP
  * Every metric keeps its source path + age. Past the staleness window the
    badge goes amber. A cockpit that looks authoritative while showing stale
    data is worse than an ugly one.
  * Per-desk numbers are always shown; there is no aggregate-only view. An
    aggregate that hides a weak desk behind a strong one is the exact
    anti-pattern J has called out before.
  * The calendar colour ramp is CLAMPED so one blowout day cannot wash out the
    month, and the true min/max are annotated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamma_cockpit_vendor as vendor  # noqa: E402
import gamma_cockpit_ui_theme  # noqa: E402 -- new rules only; kept out of this file to hold its 800-line ceiling
import gamma_cockpit_ui_motion  # noqa: E402 -- spec section 10 CSS; same reason, new rules only
import gamma_cockpit_glow_ui  # noqa: E402 -- Glow Command tokens/shell/kit CSS (2026-09-04, WS-A)
import gamma_cockpit_shell  # noqa: E402 -- page-frame HTML, split out so this file holds 800 lines

_BASE_CSS = r"""
/* ============ DARK (default) -- Radix gray-dark / cyan-dark hex values,
   copied by hand so the page never depends on a --cyan-9-style name; the
   Radix CSS files stay on disk purely for provenance. ============ */
:root{
  --canvas:#111111;  --surface-1:#191919;  --surface-2:#222222;  --surface-3:#2a2a2a;
  --line:#313131;    --line-strong:#3a3a3a;
  /* --ink-3 measured (WCAG relative luminance): Radix gray-dark 10 #7b7b7b is
     4.46:1 on --canvas and 4.03:1 on --surface-2. #8a8a8a clears the 4.5:1
     floor on canvas (5.47), surface-1 (5.09) AND surface-2 (4.61), so meta
     text stays readable inside an expanded row, not just on the page ground. */
  --ink-1:#eeeeee;   --ink-2:#b4b4b4;  --ink-3:#8a8a8a;  --ink-4:#6e6e6e;
  /* THE accent: rhymes with the Army stage's own --st-live cyan. */
  --accent:#4ccce6;  --accent-fill:#00a2c7;  --accent-fill-hover:#23afd0;
  --accent-soft:#082c36;  --accent-line:#12677e;
  /* Closed tone taxonomy: act | live | gain | loss | caution | nodata.
     gain/loss are accepted ONLY by a spark/ring/figure whose series IS P&L. */
  --pos:#3dd68c;  --pos-fill:#30a46c;  --pos-soft:#132d21;
  --neg:#ff9592;  --neg-fill:#e5484d;  --neg-soft:#3b1219;
  --warn:#ffca16; --warn-fill:#ffc53d; --warn-soft:#302008;
  --dot-green:#30a46c; --dot-red:#e5484d; --dot-amber:#ffc53d; --dot-off:#484848;
  /* the ONE glowing object */
  --stage-bg:#0e1416; --stage-glow:rgba(0,162,199,.12); --beam:#4ccce6; --star:#eeeeee;
  --sp-1:var(--size-1);--sp-2:var(--size-2);--sp-3:.75rem;--sp-4:var(--size-3);--sp-6:var(--size-5);
  --sp-8:var(--size-7);--sp-12:var(--size-8);--sp-16:var(--size-9);
  --r-1:4px; --r-2:8px; --r-pill:999px;
  --ease-out:var(--ease-out-4); --ease-in:var(--ease-in-3); --ease-std:var(--ease-3);
  --t-fast:120ms; --t-base:200ms; --t-open:320ms; --t-wash:600ms;
  --content-max:1360px; --graphic-col:160px; --row-h:56px; --topbar-h:48px;
  --font:"Inter","Segoe UI Variable Text","Segoe UI",system-ui,sans-serif;
  --mono:"JetBrains Mono","Cascadia Mono",Consolas,ui-monospace,monospace;
  color-scheme:dark;
  /* ---- ALIASES: the names army_js/chat_js/cards_js/views_js/autonomy_js
     already reference. Values are the new system; the OLD names survive so
     that JS needs no edit this pass. ---- */
  --bg-canvas:var(--canvas); --bg-1:var(--surface-1); --bg-2:var(--surface-2); --bg-3:var(--surface-3);
  /* --bg-inset used to alias --stage-bg (always #0e1416, even in light theme)
     so every "recessed panel" on the page -- .bar tracks, the EKG .beat strip,
     the chat drawer's .chatbody -- inherited a background that could never
     flip with the theme toggle (round-1 review, critical: "light theme not
     wired through the page"). Round-2 review found the fix incomplete: the
     Army stage itself (hero card, session cards, everything painted inside
     `.stage`) was *deliberately* kept dark in light mode and that read as
     broken, not intentional (three independent critical findings, same
     screenshot). The stage now has its own light-theme surface (see the
     light :root block's --stage-bg) instead of a hardcoded dark lock, so
     --bg-inset can just be the plain theme-aware alias everywhere, stage
     included. */
  --bg-inset:var(--surface-3); --bd-subtle:var(--line); --bd:var(--line); --bd-strong:var(--line-strong);
  --tx-1:var(--ink-1); --tx-2:var(--ink-2); --tx-3:var(--ink-3); --tx-4:var(--ink-4);
  --acc:var(--accent); --acc-dim:var(--accent-line); --acc-deep:var(--accent-fill);
  --acc-deep-hi:var(--accent-fill-hover); --acc-soft:var(--accent-soft); --acc-line:var(--accent-line);
  --st-live:var(--accent-fill);
  --pos-dim:var(--pos-fill); --neg-dim:var(--neg-fill); --warn-dim:var(--warn-fill); --ring:var(--accent-line);
  --topline:none; --glow:var(--stage-glow); --glow-soft:transparent;
  --s1:2px;--s2:4px;--s3:8px;--s4:12px;--s5:16px;--s6:20px;--s7:24px;--s8:32px;--s9:40px;
  --r-sm:var(--r-1); --r-md:var(--r-2); --r-lg:var(--r-2); --r-xl:var(--r-2);
  --e-hover:var(--ease-std); --e-open:var(--ease-out); --e-close:var(--ease-in);
  --e-enter:var(--ease-out); --e-route:var(--ease-std);
  --sh-1:none;--sh-2:none;--sh-3:none;--sh-4:none;
  --side:240px;
}
/* ============ LIGHT ============ */
:root[data-theme="light"]{
  --canvas:#fcfcfc; --surface-1:#f9f9f9; --surface-2:#f0f0f0; --surface-3:#e8e8e8;
  --line:#e0e0e0; --line-strong:#d9d9d9;
  /* light --ink-3 #6a6a6a: 5.27 on canvas, 5.14 on surface-1, 4.75 on surface-2 */
  --ink-1:#202020; --ink-2:#646464; --ink-3:#6a6a6a; --ink-4:#8d8d8d;
  --accent:#107d98; --accent-fill:#00a2c7; --accent-fill-hover:#0797b9; --accent-soft:#def7f9; --accent-line:#7dcedc;
  --pos:#218358; --pos-fill:#30a46c; --pos-soft:#e6f6eb;
  --neg:#ce2c31; --neg-fill:#e5484d; --neg-soft:#feebec;
  --warn:#ab6400; --warn-fill:#ffc53d; --warn-soft:#fff7c2;
  --dot-green:#30a46c; --dot-red:#e5484d; --dot-amber:#ffc53d; --dot-off:#cecece;
  /* round-2 review (critical, 3x independently): forcing the stage to stay the
     dark-mode's exact #0e1416 in light theme rendered the hero + session cards
     as "two dark islands floating on a white page" -- a half-changed toggle,
     not a light theme. The stage keeps its own tinted, slightly-recessed
     surface (so it still reads as ONE distinct instrument on the page) but now
     genuinely belongs to the light palette: a pale cool-cyan surface instead
     of night-sky black, softer glow to match. Every rect/text inside the
     stage already paints via var(--bg-2)/var(--tx-1)/etc (gamma_cockpit_army_
     js.py), so removing the old `.stage`-scoped dark override (deleted below)
     is enough to make hero/session cards/text flip correctly -- no army_js
     edit needed. */
  --stage-bg:#eef6f8; --stage-glow:rgba(0,130,160,.10); --beam:#0f96b3; --star:#9aa5b1;
  color-scheme:light;
  --bg-canvas:var(--canvas); --bg-1:var(--surface-1); --bg-2:var(--surface-2); --bg-3:var(--surface-3);
  --bg-inset:var(--surface-3); --bd-subtle:var(--line); --bd:var(--line); --bd-strong:var(--line-strong);
  --tx-1:var(--ink-1); --tx-2:var(--ink-2); --tx-3:var(--ink-3); --tx-4:var(--ink-4);
  --acc:var(--accent); --acc-dim:var(--accent-line); --acc-deep:var(--accent-fill);
  --acc-deep-hi:var(--accent-fill-hover); --acc-soft:var(--accent-soft); --acc-line:var(--accent-line);
  --st-live:var(--accent-fill);
  --pos-dim:var(--pos-fill); --neg-dim:var(--neg-fill); --warn-dim:var(--warn-fill); --ring:var(--accent-line);
  --topline:none; --glow:var(--stage-glow); --glow-soft:transparent;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--canvas);color:var(--ink-1);font-family:var(--font);font-size:14px;
  line-height:1.5;-webkit-font-smoothing:antialiased;
  font-variant-numeric:lining-nums tabular-nums slashed-zero;
  font-feature-settings:"tnum" 1,"lnum" 1,"zero" 1;
  transition:background var(--t-base) var(--e-hover),color var(--t-base) var(--e-hover)}
.num,td.n,.big,.mid,.stat{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
.armywrap{position:relative}
.army-stars{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;opacity:.85}
/* the ONE glowing object: a bloom scoped to the stage only, never the page */
.armywrap::before{content:"";position:absolute;inset:-8px;pointer-events:none;
  background:radial-gradient(60% 55% at 50% 18%,var(--stage-glow),transparent 70%)}
/* THE ANSWER BAR -- one sentence at the F-pattern origin */
.ansbar{display:flex;align-items:center;gap:var(--s5);height:44px;flex:none;
  margin-bottom:var(--s4);padding:0 var(--s5);border-radius:var(--r-md);
  background:var(--bg-inset);border:1px solid var(--bd-subtle)}
.ansbar__say{font:500 14px/1 var(--font);color:var(--tx-3);letter-spacing:-.005em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ansbar__say b{color:var(--tx-1);font-weight:600;font-variant-numeric:tabular-nums}
.ansbar__say b.live{color:var(--st-live)}
.ansbar__say s{text-decoration:none;color:var(--tx-4)}
.ansbar__key{margin-left:auto;display:flex;gap:var(--s5);align-items:center;flex:none}
.ansbar__key .k{display:inline-flex;align-items:center;gap:6px;
  font:500 12px/1 var(--font);letter-spacing:.04em;color:var(--tx-4)}
.ansbar__key .k em{font-style:normal;letter-spacing:0}
.ag__dot{width:7px;height:7px;border-radius:50%;background:var(--tx-4);flex:none}
.ag__dot[data-s="live"]{background:var(--st-live)}
.armywrap svg{position:relative;z-index:1}
/* Beam comets: the Army stage's own ambient motion (spec 4.1's one exception
   to "ambient motion budget = the Army stage only"). Mechanics unchanged. */
.army-beam{stroke-dasharray:34 520;opacity:.55;
  animation:beamflow 5.5s linear infinite,beamin 1s var(--e-enter) backwards;
  transition:opacity .2s var(--e-hover)}
@keyframes beamin{from{opacity:.3}}
.army-beam.lit{opacity:1;stroke-width:2.2;filter:drop-shadow(0 0 5px var(--accent))}
.army-enter{animation:nodein .5s var(--e-enter)}
@keyframes nodein{from{transform:translateY(8px)}to{transform:none}}
.army-aura{transform-origin:center;transform-box:fill-box;animation:aurabreathe 4.6s ease-in-out infinite}
@keyframes aurabreathe{0%,100%{opacity:.55;transform:scale(.94)}50%{opacity:1;transform:scale(1.05)}}
.army-ping{transform-box:fill-box;transform-origin:center;animation:radarping 2.4s cubic-bezier(.22,.61,.36,1) infinite}
@keyframes radarping{0%{transform:scale(.55);opacity:.75}75%,100%{transform:scale(2.7);opacity:0}}
@keyframes beamflow{from{stroke-dashoffset:554}to{stroke-dashoffset:0}}
.army-trace{stroke-dasharray:70 930;animation:traceorbit 6s linear infinite;
  filter:drop-shadow(0 0 6px var(--accent))}
.army-trace2{stroke-dasharray:55 945;animation:traceorbit 9s linear infinite;opacity:.6;
  filter:drop-shadow(0 0 4px var(--accent))}
.army-spot{transition:opacity .4s var(--e-hover)}
@keyframes traceorbit{from{stroke-dashoffset:0}to{stroke-dashoffset:-1000}}
@media (prefers-reduced-motion:reduce){
  .army-enter,.army-aura,.army-ping,.army-beam,.army-trace,.army-trace2{animation:none}
  .army-beam{stroke-dashoffset:180}
  .army-stars{opacity:.4}
  .army-flick{display:none}
}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--bd-strong);border-radius:6px;border:3px solid var(--bg-canvas)}
::selection{background:var(--acc-dim)}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:var(--r-sm)}

/* ---------------- shell: topbar ---------------- */
.app{display:flex;flex-direction:column;min-height:100vh;position:relative;z-index:1}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.topbar,.cmdbar{height:var(--topbar-h);display:flex;align-items:center;gap:var(--s5);padding:0 var(--s6);
  background:var(--canvas);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:40}
.topbar__mark,.mark{width:26px;height:26px;border-radius:var(--r-sm);flex:none;position:relative;
  background:var(--accent-fill)}
.topbar__mark::after,.mark::after{content:"Γ";position:absolute;inset:0;display:grid;place-items:center;
  font:700 14px/1 var(--font);color:var(--canvas)}
.word{font:600 15px/1 var(--font);letter-spacing:-.005em;color:var(--tx-1)}
.topbar__tabs,.tabs{display:flex;align-items:center;gap:2px;margin-left:var(--s6);height:100%;position:relative}
.topbar__tabs a,.tabs a{display:flex;align-items:center;height:100%;padding:0 14px;position:relative;
  font:500 13px/1 var(--font);color:var(--tx-4);transition:color var(--t-fast) var(--e-hover)}
.topbar__tabs a:hover,.tabs a:hover{color:var(--tx-2);text-decoration:none}
.topbar__tabs a.on,.tabs a.on{color:var(--tx-1);border-bottom:2px solid var(--acc)}
.topbar__tabs a[data-alias],.tabs a[data-alias]{display:none}
.tabcursor{display:none}
/* a count, not a chip: plain mono text (spec 2.1 bans filled pills) */
.tabs a .badge{margin-left:6px;font:500 12px/1 var(--mono);color:var(--tx-3)}
.tabs a .badge.hot{color:var(--warn)}
.tabs .more{font:500 13px/1 var(--font);color:var(--tx-4);padding:6px 10px;cursor:pointer;
  border:0;background:none;border-radius:var(--r-sm)}
.tabs .more:hover{color:var(--tx-1);background:var(--bg-2)}
.topbar__clock,.ticker,.ticker>*{display:flex;align-items:center;gap:var(--s5)}
.topbar__clock{margin-left:auto;font:500 13px/1 var(--mono);color:var(--tx-2)}
.topbar__phase{font:500 13px/1 var(--font);color:var(--tx-2)}
/* the phase word replaces the old state chip (spec 3 nav); the chip stays in
   the markup for the boot writes/tests but is never painted */
#statechip{display:none}
.topbar__theme{width:28px;height:28px;border-radius:var(--r-sm);border:1px solid var(--bd);background:var(--bg-1);
  color:var(--tx-2);cursor:pointer;display:grid;place-items:center;transition:background var(--t-fast) var(--e-hover)}
.topbar__theme:hover{background:var(--bg-2)}
.kbd,.kbd-hint kbd{font:500 12px/1 var(--mono);color:var(--tx-4);border:1px solid var(--bd);
  border-radius:5px;padding:4px 6px;background:var(--bg-2)}
.main{flex:1;display:flex;flex-direction:column;min-height:0;padding:var(--s7) var(--s9) var(--s6)}
.app{padding-bottom:40px}  /* the chat dock handle is fixed 40px at the bottom */
@media (max-width:800px){.main{padding:var(--s5) var(--s5)}}

/* ---------------- page: sentence / dayline / stage / band ---------------- */
/* every view sits in the same centred column; .page is the same box for views that wrap themselves */
.view,.page{max-width:var(--content-max);width:100%;margin:0 auto}
.page{display:flex;flex-direction:column;gap:var(--s6)}
.sentence{font:600 20px/28px var(--font);letter-spacing:-.01em;color:var(--ink-1);max-width:78ch}
.sentence b{font-variant-numeric:tabular-nums}
/* THE SENTENCE, as discrete chips (round-1 review: a run-on prose sentence
   fails a 5-second read). Each .statusitem is a verdict dot + its own clause,
   divided by a hairline -- never a filled pill. Round-2 review (major, 2x):
   the dot alone read as equal-weight to routine status text; red/amber now
   also get the SAME soft-tint background an expanded tile's red/amber body
   uses (`--neg-soft`/`--warn-soft` below). Sizing is 20px/28px/600 to match
   `.sentence` -- see gamma_cockpit_ui_theme.py for the verdict-text-colour
   rules layered on top of this base. */
.statusrow{display:flex;flex-wrap:wrap;align-items:baseline;row-gap:var(--s3)}
.statusitem{display:inline-flex;align-items:baseline;gap:8px;padding:0 var(--s5);
  font:600 20px/28px var(--font);color:var(--ink-2);border-radius:var(--r-sm)}
.statusitem:first-child{padding-left:0}
.statusitem+.statusitem{border-left:1px solid var(--line)}
.statusitem[data-verdict="red"]{background:var(--neg-soft);padding:4px var(--s4);margin:-4px 0}
.statusitem[data-verdict="amber"]{background:var(--warn-soft);padding:4px var(--s4);margin:-4px 0}
.statusitem[data-verdict="red"]+.statusitem,.statusitem[data-verdict="amber"]+.statusitem,
.statusitem+.statusitem[data-verdict="red"],.statusitem+.statusitem[data-verdict="amber"]{border-left:0}
.statusitem .vd{position:relative;top:-1px}
.statusitem__t b{color:var(--ink-1);font-weight:700;font-variant-numeric:tabular-nums}
.dayline{height:56px;margin-top:var(--s2);display:flex;align-items:center;position:relative}
.dayline__track{position:relative;flex:1;height:1px;background:var(--line)}
.dayline__tick{position:absolute;top:-3px;width:6px;height:6px;border-radius:50%;transform:translateX(-50%);
  background:var(--ink-4)}
.dayline__tick[data-state="fired"]{background:var(--ink-2)}
.dayline__tick[data-state="upcoming"]{background:var(--ink-4)}
.dayline__tick[data-state="failed"]{background:var(--dot-red)}
.dayline__live{position:absolute;top:-1px;height:2px;background:var(--ink-2)}
.dayline__now{position:absolute;top:-4px;width:8px;height:8px;border-radius:50%;background:var(--accent-fill);
  transform:translateX(-50%)}
.dayline__now::after{content:"";position:absolute;left:3px;top:8px;width:1px;height:8px;background:var(--accent-fill)}
.dayline__lbl{position:absolute;top:10px;left:50%;transform:translateX(-50%);
  font:400 12px/16px var(--mono);color:var(--tx-3);white-space:nowrap}
.dayline__tick[data-state="upcoming"] .dayline__lbl{color:var(--tx-4)}
.dayline__tick[data-state="failed"] .dayline__lbl{color:var(--neg)}
/* ticks closer than a label width alternate above the track */
.dayline__tick[data-alt="1"] .dayline__lbl{top:auto;bottom:10px}
.dayline__cursorsvg{position:absolute;left:0;top:-1px;width:100%;height:2px;pointer-events:none;display:block}
.dayline__meta{position:absolute;right:0;top:-24px}
/* Capped + internally scrollable (round-1 review, critical: the Goal/Budget
   band and the spend figure -- "arguably the single most important
   glanceable metric" -- were pushed below the 1440x900 fold because the
   stage's SVG viewBox scales its RENDERED height to whatever width the
   centred column gives it, so a 2-3 session roster still rendered ~590px
   tall. Nothing about the Army graph is removed or resized internally
   (army_js keeps its own geometry untouched, per its delete-only module
   contract) -- the stage merely gets its own scroll pocket past a sane cap,
   so a short roster reads closer to its natural size and the KPI band below
   it stops depending on how many sessions happen to be running tonight. */
.stage{position:relative;border-radius:var(--r-2);background:var(--stage-bg);
  max-height:480px;overflow-y:auto;overscroll-behavior:contain;
  box-shadow:0 0 0 1px var(--accent-line),0 0 40px -12px var(--stage-glow)}
.stage__controls{position:absolute;top:var(--s4);right:var(--s4);display:flex;gap:6px;z-index:2}
.stage__controls button{width:28px;height:28px;border-radius:var(--r-sm);border:1px solid var(--accent-line);
  background:color-mix(in srgb,var(--canvas) 60%,transparent);color:var(--ink-2);cursor:pointer;display:grid;place-items:center}
.stage__pulse{padding:var(--s3) var(--s5);font:400 12px/1.4 var(--mono);color:var(--ink-3)}
/* round-2 review (major): hairline-above/below (spec sec 3 band 4, literal) read as
   "leftover status text floating on the page background", the one module that broke
   the "expandable tiles" pattern every row group above it uses. First attempt gave
   the whole 2-column grid ONE shared card -- caught rendering it: goal (closed, 56px)
   and budget (spend figure + spark + source, ~230px) sit in the same row, and a grid
   container's background fills to the TALLER column's height regardless of
   align-items, so the shorter column read as a slab of dead space inside its own
   box. Two independent cards -- each sized to ITS OWN content -- gives the row the
   same tile-like weight as its neighbours without that mismatch. */
.band{display:grid;grid-template-columns:2fr 1fr;gap:var(--s6);align-items:stretch}
.band__goal,.band__budget{display:flex;flex-direction:column;justify-content:center;min-width:0;
  background:var(--bg-1);border:1px solid var(--line);border-radius:var(--r-md);padding:0 var(--s6);
  min-height:64px}
.band__goal .tile__head{padding:0;grid-template-columns:24px 12px 200px 24px 48px 16px minmax(0,1fr) 16px auto 12px auto 12px 20px}
.band__goal .tile__src{max-width:150px}
.band__goal .tile__body{padding-left:0}
.band__goal .tile__body{padding-left:236px}
.ring-big{width:40px;height:40px}
/* .band__budget's own inline-row rules ("ONE 64-72px row") live in
   gamma_cockpit_ui_theme.THEME_CSS, appended to CSS below this module's
   own string -- new selectors only, so append order never matters. */

/* ---------------- tiles / rows / groups ---------------- */
:root{interpolate-size:allow-keywords}
.tgroup+.tgroup{margin-top:var(--s8)}
.tgroup__head{display:flex;align-items:baseline;gap:var(--s3);margin-bottom:var(--s3)}
.tgroup__head h2{font:600 15px/20px var(--font);letter-spacing:-.005em;color:var(--ink-1)}
.tgroup__count{font:500 13px/1 var(--mono);color:var(--tx-3)}
.tgroup__expand{margin-left:auto;font:500 12px/1 var(--font);color:var(--acc);cursor:pointer}
/* One anatomy for every producer, card and answer (spec 4). The <details> is a
   plain block; the <summary> carries the 13-column row grid:
   24 icon | 12 | 200 title | 24 | 160 graphic | 24 | 1fr sentence | 24 | auto source | 12 | auto fire | 12 | 20 chevron */
.tile{display:block;position:relative;min-width:0}
.tile+.tile{border-top:1px solid var(--line)}
.tile__head{display:grid;grid-template-columns:24px 12px 200px 24px var(--graphic-col) 24px minmax(0,1fr) 24px auto 12px auto 12px 20px;
  align-items:center;height:var(--row-h);padding:0 8px;cursor:pointer;list-style:none;
  transition:background var(--t-fast) var(--e-hover)}
.tile__head::-webkit-details-marker{display:none}
.tile__head::marker{content:""}
.tile__head:focus-visible{outline:2px solid var(--accent-line);outline-offset:-2px}
.tile__ic{grid-column:1;color:var(--tx-3);display:flex}
.tile__ic svg{width:16px;height:16px}
.tile__title{grid-column:3;font:500 15px/20px var(--font);color:var(--ink-1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile__gfx{grid-column:5;display:flex;align-items:center;min-height:24px}
.tile__gfx svg{display:block}
.tile__say{grid-column:7;font:400 13px/20px var(--font);color:var(--tx-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.tile__say .vd{margin-right:8px;position:relative;top:-1px}
.tile__say b{color:var(--ink-1);font-variant-numeric:tabular-nums;font-weight:500}
.tile__src{grid-column:9;font:400 12px/1 var(--mono);color:var(--tx-3);white-space:nowrap;max-width:260px;overflow:hidden;text-overflow:ellipsis}
.tile__fire{grid-column:11;justify-self:end;height:28px;padding:0 12px;border-radius:var(--r-pill);
  border:1px solid var(--accent-line);background:var(--accent-fill);color:var(--canvas);
  font:500 12px/1 var(--font);cursor:pointer}
.tile__fire:active{transform:scale(.97)}
.tile__fire:disabled{opacity:.5;cursor:default}
.tile__fire--done{border:0;background:none;color:var(--tx-3);font:400 12px/1 var(--mono);padding:0}
.tile__chev{grid-column:13;color:var(--tx-4);display:flex;transition:transform var(--t-fast) var(--e-hover)}
.tile__chev svg{width:16px;height:16px}
.tile[open] .tile__chev{transform:rotate(180deg)}
.tile__body{padding:8px 24px 24px 236px;font:400 13px/20px var(--font);color:var(--tx-2);overflow-x:auto}
.tile__body>*{max-width:72ch}
.tile__body .src{margin-top:0;padding-top:0;border-top:0;margin-bottom:var(--s3)}
.tile__body table{font-size:12px;font-family:var(--mono);max-width:none}
.tile__body .body{margin:2px 0}
.tile__body .meta{display:block;margin-bottom:var(--s2)}
.tgroup__body{border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.tgroup--collapsed .tgroup__body{display:none}
.tile--stale .tile__gfx{opacity:.6}
.tile--stale .tile__src{color:var(--warn)}
.vd{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--dot-off);flex:none}
[data-verdict="green"] .vd{background:var(--dot-green)}
[data-verdict="amber"] .vd{background:var(--dot-amber)}
[data-verdict="red"] .vd{background:var(--dot-red)}
[data-verdict="off"] .vd,[data-verdict="none"] .vd{background:var(--dot-off)}
[data-verdict="red"] .tile__body{background:var(--neg-soft)}
[data-verdict="amber"] .tile__body{background:var(--warn-soft)}
.wash{transition:background var(--t-wash) var(--e-hover)}
@media (hover:hover) and (pointer:fine){
  .tile__head:hover{background:var(--surface-1)}
}
details.tile::details-content{height:0;overflow:clip;
  transition:height var(--t-open) var(--ease-out),content-visibility var(--t-open) allow-discrete}
details.tile[open]::details-content{height:auto}
.figure{font:500 28px/32px var(--mono);color:var(--ink-1);font-variant-numeric:tabular-nums}
.figure-lg{font:500 40px/44px var(--mono);color:var(--ink-1);font-variant-numeric:tabular-nums}
/* round-2 review (major): spend over budget carried zero visual alarm -- "the one
   number most likely to matter to J at a glance carries zero visual alarm". This is
   a COST/budget series, not P&L (--pos/--neg stay reserved for real trading P&L per
   the tokens' own "gain/loss ONLY on a P&L series" rule) -- a budget overrun is the
   taxonomy's CAUTION case, same hue the app already uses for every other non-P&L
   severity (amber verdict dots, tile__body warn-soft), so --warn is the correct
   colour here, not --neg. */
.figure.over{color:var(--warn)}
.meta{font:400 12px/16px var(--mono);color:var(--tx-4)}
.meta.over{color:var(--warn);font-weight:600}

/* ---------------- chat dock ---------------- */
.chatdock{position:fixed;left:0;right:0;bottom:0;z-index:30;background:var(--surface-2);
  border-top:1px solid var(--line);height:40px;overflow:hidden;
  transition:height var(--t-open) var(--e-open)}
.chatdock--open{height:320px;box-shadow:0 -8px 24px rgba(0,0,0,.4)}
.chatdock__handle{height:40px;display:flex;align-items:center;padding:0 var(--s5);cursor:pointer;
  font:500 12px/1 var(--font);color:var(--tx-3)}
.foot{max-width:var(--content-max);width:100%;margin:0 auto;padding:var(--s3) var(--s9) var(--s5);
  font:400 12px/1 var(--mono);color:var(--tx-3)}

/* ---------------- primitives (kept classes, restyled to tokens) ---------------- */
.eyebrow{font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--tx-3)}
.big{font-size:40px;font-weight:500;letter-spacing:-.02em;line-height:1.1;font-family:var(--mono)}
.mid{font-size:24px;font-weight:500;letter-spacing:-.015em;line-height:1.25}
.stat{font-size:18px;font-weight:600;letter-spacing:-.01em}
.mut{color:var(--tx-2);font-size:14px}
.dim{color:var(--tx-3);font-size:12px}
.micro{color:var(--tx-3);font-size:12px;letter-spacing:.02em}
.pos{color:var(--pos)}.neg{color:var(--neg)}.warnc{color:var(--warn)}.acc{color:var(--acc)}
.mono{font-family:var(--mono)}
.grid{display:grid;gap:var(--s5)}
.g2{grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(215px,1fr))}
.stack{display:flex;flex-direction:column;gap:var(--s5)}
.row{display:flex;align-items:center;gap:var(--s4)}
.wrap{flex-wrap:wrap}
section+section{margin-top:var(--s8)}
.shead{display:flex;align-items:baseline;gap:var(--s4);margin-bottom:var(--s5)}
.shead h2{font-size:18px;font-weight:600;letter-spacing:-.01em}
h1,h2,h3{text-wrap:balance}

.card{background:var(--bg-1);border:1px solid var(--bd);border-radius:var(--r-lg);padding:var(--s6);
  position:relative}
.card h3{font-size:12px;font-weight:600;letter-spacing:.02em;color:var(--tx-3);margin-bottom:var(--s4)}
.card.click{cursor:pointer}
.card.click:hover{border-color:var(--bd-strong);background:var(--bg-2)}
.gborder{position:relative;border:1px solid var(--acc-line)}
.spot{position:relative}

.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:var(--r-pill);
  font-size:12px;font-weight:500;letter-spacing:.02em;border:1px solid var(--bd);background:var(--bg-2);
  color:var(--tx-2);white-space:nowrap}
.chip .dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
/* traffic-light DOTS for health. never red/green fills - that vocabulary is P&L's */
.chip.ok .dot{background:var(--pos)} .chip.warn .dot{background:var(--warn)} .chip.bad .dot{background:var(--neg)}
.chip.ok{color:var(--tx-1)} .chip.warn{color:var(--warn)} .chip.bad{color:var(--neg)}
.chip.live .dot{animation:pl 2.4s var(--e-hover) infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.4}}

.bar{height:6px;border-radius:var(--r-pill);background:var(--bg-inset);overflow:hidden;border:1px solid var(--bd-subtle)}
.bar>i{display:block;height:100%;background:var(--acc);transition:width .8s var(--e-open)}
.bar.done>i{background:var(--pos)}
.src{margin-top:var(--s5);padding-top:var(--s4);border-top:1px solid var(--bd-subtle);font-size:12px;
  font-family:var(--mono);color:var(--tx-3);display:flex;flex-wrap:wrap;gap:var(--s2) var(--s5)}
.src .stale{color:var(--warn)}
  .age{font-variant-numeric:tabular-nums}
  .age.stale{color:var(--warn)}
.stagger>*{opacity:1;transform:none}

/* ---------------- calendar ---------------- */
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.dow{font-size:12px;color:var(--tx-3);text-align:center;letter-spacing:.02em;font-weight:500;padding-bottom:var(--s2)}
.cell{min-height:70px;border:1px solid var(--bd-subtle);border-radius:var(--r-md);background:var(--bg-1);
  padding:6px 8px;display:flex;flex-direction:column;gap:2px;
  transition:border-color .14s var(--e-hover),background .14s var(--e-hover)}
.cell.empty{background:transparent;border-color:transparent}
.cell.has{cursor:pointer}
.cell.has:hover{border-color:var(--bd-strong);background:var(--bg-2)}
.cell .d{font-size:12px;color:var(--tx-3);font-weight:500;line-height:1;font-family:var(--mono)}
.cell .v{font-weight:500;font-family:var(--mono);font-size:clamp(12px,1.05vw,14px);line-height:1.15;margin-top:auto;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.cell .t{font-size:12px;color:var(--tx-3)}
.cell .arms{display:flex;gap:2px;margin-top:1px}
.cell .arms i{width:5px;height:5px;border-radius:1px;background:var(--tx-4);opacity:.7}
.legend{display:flex;align-items:center;gap:var(--s3);font-size:12px;color:var(--tx-3)}
.legend .ramp{width:110px;height:8px;border-radius:var(--r-pill);background:var(--bg-2);border:1px solid var(--bd-subtle)}

/* ---------------- heartbeat (EKG) ---------------- */
.beat{position:relative;display:flex;align-items:flex-end;gap:2px;height:44px;
  padding:0 2px;border-radius:var(--r-md);background:var(--bg-inset);
  border:1px solid var(--bd-subtle);overflow:hidden}
.beat i{flex:1 1 auto;min-width:2px;background:var(--tx-4);border-radius:1px;opacity:.55;
  transition:height .3s var(--e-open)}
.beat i.hold{background:var(--tx-3)}
.beat i.act{background:var(--acc);opacity:.95}
.beat i.exit{background:var(--warn);opacity:.9}
.beat i.stop{background:var(--neg);opacity:.9}
.beat i.now{animation:beatpulse 1.8s var(--e-hover) infinite}
@keyframes beatpulse{0%,100%{opacity:1;transform:scaleY(1)}50%{opacity:.45;transform:scaleY(.72)}}
/* the sweep gradient is retired: ambient motion budget is the Army stage
   only (spec 4.1) -- .beat.live's "alive" read now comes from .beat i.now's
   pulse alone, no page-wide gradient animation elsewhere. */
.beat.dead{filter:grayscale(1) brightness(.6)}
.beatlbl{display:flex;justify-content:space-between;font-size:12px;color:var(--tx-3);margin-top:var(--s2)}

/* ---------------- positions ---------------- */
.flatbig{font-size:34px;font-weight:500;letter-spacing:-.02em;color:var(--tx-2);font-family:var(--mono)}
.poswrap{display:flex;align-items:center;gap:var(--s7);flex-wrap:wrap}
.armpill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--r-pill);
  background:var(--bg-2);border:1px solid var(--bd);font-size:12px;color:var(--tx-2)}
.armpill b{color:var(--tx-1);font-variant-numeric:tabular-nums}

/* ---------------- army (orchestrator + sessions + workers + pulse) ---------------- */
.armywrap{overflow-x:auto}
.army-node{cursor:pointer}
.army-node rect{transition:stroke .18s var(--e-hover),filter .18s var(--e-hover)}
.army-node:hover rect{stroke:var(--acc-line);filter:drop-shadow(0 0 6px rgba(76,204,230,.45))}
.army-ring{animation:armyring 2.4s ease-in-out infinite;transform-origin:center}
@keyframes armyring{0%,100%{opacity:.30}50%{opacity:1}}
.army-glow{animation:armyglow .6s ease-out}
@keyframes armyglow{from{filter:drop-shadow(0 0 9px var(--acc))}to{filter:none}}
.army-pulse{filter:drop-shadow(0 0 6px var(--acc)) drop-shadow(0 0 14px var(--acc));
  animation:pulsebeat .9s ease-in-out infinite}
@keyframes pulsebeat{0%,100%{opacity:.85;r:5}50%{opacity:1;r:7}}

/* ---------------- action-card rail ---------------- */
.acard-item{transition:border-color .18s var(--e-hover),background .18s var(--e-hover)}
.acard-item:hover{border-color:var(--acc-line)!important;background:var(--bg-2)!important}
.acard-item:active{transform:scale(.99)}
.acard-item{position:relative;overflow:hidden}
.acard-item::before{content:"";position:absolute;left:0;top:0;bottom:0;width:1px;
  background:var(--acc);opacity:0;transition:opacity .18s var(--e-hover)}
.acard-item:hover::before{opacity:.9}
.acard-open{border:1px solid var(--acc-line);animation:acardin .2s var(--e-open)}
@keyframes acardin{from{opacity:0}to{opacity:1}}
.ctxbar{height:4px;border-radius:999px;background:var(--bg-2);overflow:hidden}
.ctxbar i{display:block;height:100%;border-radius:999px;background:var(--acc);
  transition:width .6s var(--e-hover)}
.ctxbar.hot i{background:var(--warn)}
.ctxbar.full i{background:var(--neg)}
@media (prefers-reduced-motion:reduce){
  .army-ring,.army-glow,.army-pulse,.acard-open{animation:none}
  .acard-item,.acard-item::before,.army-node rect,.ctxbar i{transition:none}
}
/* ---------------- cockpit chat ---------------- */
.chattabs{display:flex;gap:var(--s2);margin-top:var(--s5);border-bottom:1px solid var(--bd-subtle);
  padding-bottom:var(--s3)}
.chattab{font:600 12px/1 var(--font);padding:8px 14px;border-radius:var(--r-sm);cursor:pointer;
  border:1px solid transparent;background:transparent;color:var(--tx-3);transition:all .16s var(--e-hover)}
.chattab:hover{color:var(--tx-1);background:var(--bg-2)}
.chattab.on{color:var(--acc);border-color:var(--acc-line);background:var(--acc-soft)}
.chatpane{display:flex;flex-direction:column;gap:var(--s3);margin-top:var(--s4)}
.chathead{display:flex;align-items:center;gap:var(--s4);font-size:13px}
.chathead select{margin-left:auto;font:500 12px/1 var(--mono);padding:6px 10px;
  border-radius:var(--r-sm);border:1px solid var(--bd);background:var(--bg-2);color:var(--tx-2);cursor:pointer}
.chatbody{min-height:100px;max-height:16vh;overflow:auto;display:flex;flex-direction:column;
  gap:var(--s4);padding:var(--s5);border:1px solid var(--bd-subtle);border-radius:var(--r-md);
  background:var(--bg-inset)}
.chatturn{padding:10px 14px;border-radius:var(--r-md);border:1px solid transparent}
.chatturn-gamma{background:var(--bg-1);border-color:var(--bd-subtle)}
.chatturn-user{background:var(--acc-soft);border-color:var(--acc-line)}
.chatturn{display:flex;flex-direction:column;gap:var(--s2);animation:chatin .16s var(--e-open)}
@keyframes chatin{from{opacity:0}to{opacity:1}}
.chatwho{font:500 12px/1 var(--mono);letter-spacing:.02em;color:var(--tx-3)}
.chatturn-user .chatwho{color:var(--acc)}
.chattext{white-space:pre-wrap;word-break:break-word;font-size:13.5px;line-height:1.62;color:var(--tx-1)}
.chatturn-user .chattext{color:var(--tx-2)}
.chatsteps{display:flex;flex-direction:column;gap:2px;margin-top:var(--s2)}
.chatstep{font:400 12px/1.5 var(--mono);color:var(--tx-3)}
.chatstep.dim{color:var(--tx-4)}
.chatstep.ok{color:var(--pos)}
.chatstep.bad{color:var(--neg)}
.chatfoot{display:flex;gap:var(--s3);align-items:flex-end}
.chatfoot textarea{flex:1;resize:none;font:400 13.5px/1.55 var(--font);padding:11px 14px;
  border-radius:var(--r-md);border:1px solid var(--bd);background:var(--bg-1);color:var(--tx-1);
  outline:none;transition:border-color .16s var(--e-hover)}
.chatfoot textarea:focus{border-color:var(--acc-line)}
.chatfoot textarea:disabled{opacity:.55}
#chatsend{font:600 13px/1 var(--font);padding:12px 22px;border-radius:var(--r-sm);cursor:pointer;
  color:var(--canvas);border:1px solid var(--acc-line);background:var(--acc-deep);
  transition:background .16s var(--e-hover)}
#chatsend:hover:not(:disabled){background:var(--acc-deep-hi)}
#chatsend:active:not(:disabled){transform:scale(.97)}
#chatsend:disabled{opacity:.5;cursor:default}
.chatnote{color:var(--tx-4)}
.chatempty{margin:auto;text-align:center;padding:18px 0}
.chatempty-t{font:600 15px/1.3 var(--font);color:var(--tx-2);letter-spacing:-.01em}
.chatempty-s{font:400 12px/1.5 var(--font);color:var(--tx-4);margin-top:4px}
.chatempty-chips{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:14px}
.sugchip{font:500 12px/1 var(--font);padding:8px 14px;border-radius:999px;cursor:pointer;
  color:var(--tx-2);border:1px solid var(--bd);background:var(--bg-2);transition:all .16s var(--e-hover)}
.sugchip:hover{border-color:var(--acc-line);color:var(--tx-1);background:var(--acc-soft)}

/* ---------------- fire button: show what clicking does ---------------- */
.firewhat{font-size:12.5px;line-height:1.5;color:var(--tx-2);margin:0 0 10px}
.firewhat b{color:var(--acc);font-weight:600}
.firebtn{font:600 13px/1 var(--font);padding:12px 22px;border-radius:var(--r-sm);cursor:pointer;
  color:var(--canvas);border:1px solid var(--acc-line);background:var(--acc-deep);
  transition:background .16s var(--e-hover)}
.firebtn:hover:not(:disabled){background:var(--acc-deep-hi)}
.firebtn:active:not(:disabled){transform:scale(.97)}
.firebtn:disabled{opacity:.5;cursor:default;border-color:var(--bd);background:transparent;color:var(--tx-4)}
/* armed = second click will actually spend. It PULSES so it reads as hot, not idle. */
.firebtn.armed{background:var(--acc);color:var(--bg-canvas);border-color:var(--acc);
  animation:firearm 1s ease-in-out infinite}
@keyframes firearm{0%,100%{opacity:1}50%{opacity:.72}}
/* the comet: card -> graph, so cause and effect are one motion */
.firecomet{position:fixed;z-index:9999;width:14px;height:14px;border-radius:50%;
  background:var(--acc);pointer-events:none;
  transition:transform .85s cubic-bezier(.16,1,.3,1),opacity .85s ease-out}
.orc-spawn rect{animation:orcspawn 1.4s var(--e-hover)}
@keyframes orcspawn{0%{stroke:var(--acc);filter:drop-shadow(0 0 4px var(--acc))}
  30%{filter:drop-shadow(0 0 16px var(--acc))}100%{filter:none}}
.firetoast{position:fixed;left:50%;bottom:32px;transform:translateX(-50%) translateY(20px);
  z-index:10000;background:var(--acc);color:var(--bg-canvas);font:700 13px/1 var(--font);
  padding:12px 20px;border-radius:var(--r-md);border:1px solid var(--acc-line);opacity:0;pointer-events:none;
  transition:opacity .25s var(--e-hover),transform .25s var(--e-hover)}
.firetoast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@media (prefers-reduced-motion:reduce){
  .firebtn.armed,.orc-spawn rect{animation:none}
  .firecomet{display:none}
  .firetoast{transition:opacity .01s}
}
@media (prefers-reduced-motion:reduce){.chatturn{animation:none}}
.armyledger{max-height:240px;overflow:auto;margin-top:var(--s5);padding-top:var(--s4);
  border-top:1px solid var(--bd-subtle);font-size:12px;color:var(--tx-3)}
.armyledger div{display:flex;gap:var(--s3);padding:3px 0;white-space:nowrap;overflow:hidden}
.armyledger .t{color:var(--tx-4);font-family:var(--mono);flex:none}

/* ---------------- action cards ---------------- */
.actioncard .row .chip:first-child{font-variant-numeric:tabular-nums}
.fire-btn{transition:opacity .14s var(--e-hover),background .14s var(--e-hover)}
.fire-btn:disabled{opacity:.4;cursor:not-allowed;background:var(--bg-3)!important;
  border-color:var(--bd)!important;color:var(--tx-3)!important}
.fire-btn:not(:disabled):hover{background:var(--acc)!important;color:var(--canvas)!important}
.askstream{max-height:60vh;overflow:auto;font-family:var(--mono);font-size:12px;
  line-height:1.6;color:var(--tx-2);white-space:pre-wrap;word-break:break-word;
  background:var(--bg-inset);border:1px solid var(--bd-subtle);border-radius:var(--r-md);
  padding:var(--s4)}
.askstream div{padding:1px 0}

/* ---------------- table ---------------- */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:12px;font-weight:500;letter-spacing:.02em;color:var(--tx-3);
  padding:var(--s3) var(--s4);border-bottom:1px solid var(--bd);position:sticky;top:0;background:var(--bg-1);z-index:1}
td{padding:var(--s3) var(--s4);border-bottom:1px solid var(--bd-subtle);color:var(--tx-2)}
td.n{text-align:right;font-family:var(--mono);font-size:12px}
tbody tr{transition:background .12s var(--e-hover)}
tbody tr:hover{background:var(--bg-2)}
tr:last-child td{border-bottom:none}

/* ---------------- drawer ---------------- */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.5);opacity:0;
  pointer-events:none;transition:opacity .22s var(--e-open);z-index:40}
.scrim.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(720px,95vw);z-index:50;background:var(--bg-1);
  border-left:1px solid var(--bd);transform:translateX(101%);transition:transform .26s var(--e-open);
  display:flex;flex-direction:column}
.drawer.closing{transition-duration:.18s;transition-timing-function:var(--e-close)}
.drawer.on{transform:none}
.drawer header{padding:var(--s6) var(--s7);border-bottom:1px solid var(--bd-subtle);display:flex;
  align-items:center;gap:var(--s4)}
.drawer header h2{font-size:18px;font-weight:600;letter-spacing:-.01em}
.drawer .body{padding:var(--s6) var(--s7);overflow:auto;flex:1}
.x{margin-left:auto;background:var(--bg-2);border:1px solid var(--bd);color:var(--tx-2);width:30px;height:30px;
  border-radius:var(--r-md);cursor:pointer;font-size:16px;line-height:1;transition:background .14s var(--e-hover)}
.x:hover{background:var(--bg-3);color:var(--tx-1)}

/* ---------------- palette ---------------- */
.pal{position:fixed;inset:0;z-index:60;display:none;align-items:flex-start;justify-content:center;padding-top:13vh;
  background:rgba(0,0,0,.45)}
.pal.on{display:flex}
.pal .box{width:min(580px,92vw);background:var(--bg-2);border:1px solid var(--bd);border-radius:var(--r-lg);
  overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.4);animation:pop .16s var(--e-hover)}
@keyframes pop{from{opacity:0;transform:scale(.98)}to{opacity:1;transform:none}}
.pal input{width:100%;padding:16px 18px;background:transparent;border:none;outline:none;color:var(--tx-1);
  font-size:15px;font-family:var(--font);border-bottom:1px solid var(--bd-subtle)}
.pal .res{max-height:340px;overflow:auto;padding:var(--s2)}
.pal .res div{padding:10px 14px;cursor:pointer;display:flex;gap:11px;align-items:center;font-size:14px;
  border-radius:var(--r-md)}
.pal .res div.sel{background:var(--bg-3)}
.pal .res .k{margin-left:auto;color:var(--tx-3);font-size:12px;font-family:var(--mono)}

.brief{padding:var(--s7) var(--s8)}
.brieflines p{font-size:16px;line-height:1.65;color:var(--tx-1);margin-top:var(--s4);max-width:78ch}
.brieflines p:first-child{font-size:19px;letter-spacing:-.01em}
.flag{margin-top:var(--s5);padding:var(--s4) var(--s5);border-radius:var(--r-md);font-size:13.5px;
  border:1px solid var(--bd);background:var(--bg-2)}
.flag b{letter-spacing:.02em;font-size:12px;margin-right:var(--s3);color:var(--acc)}
.flag.bad{border-color:var(--warn-dim);background:var(--warn-soft)}
.flag.bad b{color:var(--warn)}
.note{padding:var(--s9);text-align:center;color:var(--tx-4);font-size:13px}
.kv{display:flex;justify-content:space-between;gap:var(--s5);padding:var(--s3) 0;
  border-bottom:1px solid var(--bd-subtle);font-size:13px}
.kv:last-child{border-bottom:none}
.kv .k{color:var(--tx-3);white-space:nowrap}
.kv .v{text-align:right;color:var(--tx-1)}

@container (max-width:250px){.card .spark{display:none}}
@media (max-width:1100px){
  :root{--graphic-col:120px}
  .tile__head{grid-template-columns:24px 12px minmax(0,1fr) 24px var(--graphic-col) 24px auto 12px auto 12px 20px}
  .tile__say{display:none}
  .tile__src{grid-column:7}.tile__fire{grid-column:9}.tile__chev{grid-column:11}
  .tile__body{padding-left:36px}
  .band{grid-template-columns:1fr}
}
@media (max-width:900px){
  .app{grid-template-columns:1fr}
  .view{padding:var(--s5)}
}
@media (prefers-reduced-motion:reduce){
  :root{--t-fast:0ms;--t-base:0ms;--t-open:0ms;--t-wash:0ms}
  *{animation:none!important;transition:none!important}
  ::view-transition-group(*),::view-transition-old(*),::view-transition-new(*){animation:none!important}
  details.tile::details-content{transition:none}
  .stagger>*{opacity:1;transform:none}
}
"""

CSS = (
    _BASE_CSS
    + gamma_cockpit_ui_theme.THEME_CSS
    + gamma_cockpit_ui_motion.MOTION_CSS
    + gamma_cockpit_glow_ui.GLOW_CSS
)

# Page-frame HTML lives in gamma_cockpit_shell.py (split out to hold this
# module's 800-line ceiling); re-exported under the same name so
# gamma_cockpit_ui.SHELL / gamma_cockpit_ui.render() are unchanged for every
# caller.
SHELL = gamma_cockpit_shell.SHELL


def render(payload: dict, js: str) -> str:
    """Assemble the page. The one sequence that could break out of a <script>
    block is neutralised; everything else is escaped by esc() at render time."""
    blob = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return (SHELL.replace("__VENDOR_HEAD__", vendor.vendor_head())
                 .replace("__CSS__", CSS)
                 .replace("__DATA_JSON__", blob)
                 .replace("__VENDOR_JS__", vendor.vendor_scripts())
                 .replace("__JS__", js))

"""gamma_cockpit_ui.py - the COCKPIT's markup, styling and behaviour.

Split out of gamma_home.py so neither file passes the repo's 800-line ceiling.
This module owns PRESENTATION only: every number it renders arrives pre-computed
in the payload. It never reads a state file and never derives a metric.

HARD CONSTRAINT: one self-contained file. No CDN, no web fonts, no external JS or
CSS. It must work from a file:// URL with no network, which rules out every chart
library - the sparklines, bars and the org graph are hand-rolled SVG.

DESIGN SYSTEM (from the 2026 design research, sources in the session report)
  * OKLCH neutrals on hue 265 at near-zero chroma. Perceptually even lightness
    steps, which a flat hex ladder does not give you - that evenness is what
    makes an elevation ramp read as a system instead of as noise.
  * Semantic colours pinned to L 68-72% so profit/loss/warning read as equally
    vivid against the canvas.
  * ONE MEANING PER COLOUR. Red/green are reserved for P&L only. System and agent
    health use traffic-light DOTS, never red/green fills - the UX research names
    colour-collision as a top dashboard anti-pattern.
  * Layered shadows (2-4 low-opacity stacks), not one hard shadow.
  * Motion: expo-out cubic-bezier(.16,1,.3,1) for hover; opens slower than
    closes; stagger capped at 8 items so long lists never feel slow. All of it
    off under prefers-reduced-motion.
  * Tabular numerals everywhere a number can change.

HONESTY RULES BAKED INTO THE MARKUP
  * Every metric keeps its source path + age. Past the staleness window the badge
    goes amber. A cockpit that looks authoritative while showing stale data is
    worse than an ugly one.
  * Per-desk numbers are always shown; there is no aggregate-only view. An
    aggregate that hides a weak desk behind a strong one is the exact anti-pattern
    J has called out before.
  * The calendar colour ramp is CLAMPED so one blowout day cannot wash out the
    month, and the true min/max are annotated.
"""
from __future__ import annotations

import json

CSS = r"""
:root{
  /* THEME: near-black greys, one space-purple accent (J, 2026-08-29).
     Grounds carry almost no chroma (.010-.018) so they read as black/grey rather than
     "purple UI"; the hue is still 300 so every neutral sits in the SAME family as the
     accent and the greys look chosen instead of inherited. The boldness is spent in one
     place -- --acc -- and nowhere else. */
  --bg-canvas:oklch(10% .012 300); --bg-1:oklch(14.5% .014 300); --bg-2:oklch(18% .016 300);
  --bg-3:oklch(23% .018 300); --bg-inset:oklch(8% .010 300);
  --bd-subtle:color-mix(in oklch, white 6%, transparent);
  --bd:color-mix(in oklch, white 11%, transparent);
  --bd-strong:color-mix(in oklch, white 19%, transparent);
  --tx-1:oklch(97% .006 300); --tx-2:oklch(79% .011 300);
  --tx-3:oklch(60% .013 300); --tx-4:oklch(44% .012 300);
  /* pos/neg stay where they are: red and green are RESERVED for P&L in this cockpit, so
     the accent must never be able to be mistaken for either. */
  --pos:oklch(72% .19 152); --pos-dim:color-mix(in oklch,var(--pos) 16%,transparent);
  --neg:oklch(68% .21 25);  --neg-dim:color-mix(in oklch,var(--neg) 16%,transparent);
  --warn:oklch(78% .17 80); --warn-dim:color-mix(in oklch,var(--warn) 16%,transparent);
  --acc:oklch(67% .21 300); --acc-dim:color-mix(in oklch,var(--acc) 16%,transparent);
  --acc-soft:color-mix(in oklch,var(--acc) 9%,transparent);
  --acc-line:color-mix(in oklch,var(--acc) 42%,transparent);
  /* Coloured elevation: a violet-tinted glow reads as light coming off the accent rather
     than a grey drop shadow bolted underneath it. */
  --glow:0 0 0 1px color-mix(in oklch,var(--acc) 30%,transparent),
         0 4px 24px -6px color-mix(in oklch,var(--acc) 34%,transparent);
  --glow-soft:0 0 18px -6px color-mix(in oklch,var(--acc) 45%,transparent);
  --sh-1:0 1px 2px oklch(0% 0 0/.24);
  --sh-2:0 1px 2px oklch(0% 0 0/.20),0 4px 10px oklch(0% 0 0/.24);
  --sh-3:0 2px 4px oklch(0% 0 0/.20),0 10px 24px oklch(0% 0 0/.32);
  --sh-4:0 4px 8px oklch(0% 0 0/.24),0 20px 48px oklch(0% 0 0/.40);
  --s1:2px;--s2:4px;--s3:8px;--s4:12px;--s5:16px;--s6:20px;--s7:24px;--s8:32px;--s9:40px;
  --r-sm:6px;--r-md:10px;--r-lg:14px;--r-xl:20px;--r-pill:999px;
  --e-hover:cubic-bezier(.16,1,.3,1); --e-open:cubic-bezier(.32,.72,0,1);
  --e-close:cubic-bezier(.4,0,1,1); --e-route:cubic-bezier(.65,0,.35,1);
  --font:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI Variable","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Menlo,Consolas,monospace;
  --side:240px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:var(--bg-canvas);color:var(--tx-1);font-family:var(--font);font-size:14px;
  line-height:1.5;-webkit-font-smoothing:antialiased}
.num,td.n,.big,.mid,.stat{font-variant-numeric:tabular-nums;font-feature-settings:"tnum" 1}
/* ambient wash + subliminal grain (kills gradient banding) */
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(900px 520px at 10% -10%,color-mix(in oklch,var(--acc) 12%,transparent),transparent 62%),
             radial-gradient(720px 440px at 94% 2%,color-mix(in oklch,var(--pos) 7%,transparent),transparent 64%)}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:999;opacity:.035;
  mix-blend-mode:overlay;background-image:url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/></filter><rect width="100%25" height="100%25" filter="url(%23n)"/></svg>')}
a{color:var(--acc);text-decoration:none}
a:hover{text-decoration:underline}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--bd-strong);border-radius:6px;border:3px solid var(--bg-canvas)}
::selection{background:var(--acc-dim)}
:focus-visible{outline:2px solid var(--acc);outline-offset:2px;border-radius:var(--r-sm)}

/* ---------------- shell ---------------- */
.app{display:grid;grid-template-columns:var(--side) 1fr;min-height:100vh;position:relative;z-index:1}
.side{border-right:1px solid var(--bd-subtle);background:var(--bg-inset);padding:var(--s6) var(--s4);
  position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:var(--s1)}
.brand{display:flex;align-items:center;gap:var(--s4);padding:var(--s1) var(--s3) var(--s6)}
.mark{width:32px;height:32px;border-radius:9px;flex:none;position:relative;
  background:linear-gradient(145deg,var(--acc),oklch(64% .19 300));
  box-shadow:inset 0 1px 0 color-mix(in oklch,white 22%,transparent),0 6px 18px -6px var(--acc)}
.mark::after{content:"Γ";position:absolute;inset:0;display:grid;place-items:center;font:700 17px/1 var(--font);color:#fff}
.brand b{font-size:15px;font-weight:600;letter-spacing:-.015em}
.brand small{display:block;color:var(--tx-3);font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-weight:600}
.nav{display:flex;flex-direction:column;gap:1px}
.nav a{display:flex;align-items:center;gap:11px;padding:9px 11px;border-radius:var(--r-md);color:var(--tx-2);
  font-size:14px;font-weight:500;position:relative;transition:background .14s var(--e-hover),color .14s var(--e-hover)}
.nav a:hover{background:var(--bg-1);color:var(--tx-1);text-decoration:none}
.nav a.on{background:var(--bg-2);color:var(--tx-1)}
.nav a.on::before{content:"";position:absolute;left:-12px;top:10px;bottom:10px;width:3px;border-radius:0 3px 3px 0;
  background:var(--acc);box-shadow:0 0 12px var(--acc)}
.nav .ic{width:17px;text-align:center;font-size:13px;opacity:.9}
.nav .badge{margin-left:auto;font-size:11px;font-weight:600;padding:1px 7px;border-radius:var(--r-pill);
  background:var(--bg-3);color:var(--tx-2);border:1px solid var(--bd)}
.nav .badge.hot{background:var(--warn-dim);color:var(--warn);border-color:color-mix(in oklch,var(--warn) 34%,transparent)}
.side .foot{margin-top:auto;font-size:11px;color:var(--tx-4);line-height:1.8;padding:var(--s4) var(--s3) 0;
  border-top:1px solid var(--bd-subtle)}
kbd{background:var(--bg-3);border:1px solid var(--bd);border-bottom-width:2px;border-radius:5px;padding:1px 5px;
  font:600 11px/1.4 var(--mono);color:var(--tx-2)}

.main{min-width:0;display:flex;flex-direction:column}
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:var(--s4);padding:var(--s5) var(--s7);
  border-bottom:1px solid var(--bd-subtle);
  background:color-mix(in oklch,var(--bg-canvas) 78%,transparent);
  backdrop-filter:blur(20px) saturate(160%);-webkit-backdrop-filter:blur(20px) saturate(160%)}
.top h1{font-size:24px;font-weight:600;letter-spacing:-.015em}
.sp{flex:1}
.clock{font:400 11px/1.4 var(--mono);color:var(--tx-3);letter-spacing:.02em;text-align:right}
.view{padding:var(--s7);max-width:1560px;width:100%}
.view.anim{animation:vin .3s var(--e-route)}
@keyframes vin{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* ---------------- primitives ---------------- */
.eyebrow{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--tx-3)}
.big{font-size:40px;font-weight:650;letter-spacing:-.02em;line-height:1.1}
.mid{font-size:24px;font-weight:600;letter-spacing:-.015em;line-height:1.25}
.stat{font-size:18px;font-weight:600;letter-spacing:-.01em}
.mut{color:var(--tx-2);font-size:14px}
.dim{color:var(--tx-3);font-size:12px}
.micro{color:var(--tx-4);font-size:11px;letter-spacing:.02em}
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

.card{background:var(--bg-1);border:1px solid var(--bd-subtle);border-radius:var(--r-lg);
  padding:var(--s6);box-shadow:var(--sh-2);position:relative;container-type:inline-size;
  transition:box-shadow .16s var(--e-hover),border-color .16s var(--e-hover),transform .16s var(--e-hover)}
.card h3{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--tx-3);
  margin-bottom:var(--s4)}
.card.click{cursor:pointer}
.card.click:hover{box-shadow:var(--sh-3);border-color:var(--bd);transform:translateY(-2px)}
/* mouse-following spotlight - the signature premium hover */
.spot::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;opacity:0;
  background:radial-gradient(340px circle at var(--mx,50%) var(--my,50%),var(--acc-dim),transparent 70%);
  transition:opacity .2s var(--e-hover)}
.spot:hover::before{opacity:1}
/* gradient hairline for the hero only - restraint is the point */
.gborder{position:relative}
.gborder::after{content:"";position:absolute;inset:0;border-radius:inherit;padding:1px;pointer-events:none;
  background:linear-gradient(135deg,var(--acc) 0%,transparent 55%);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;
  mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude;opacity:.7}

.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:var(--r-pill);
  font-size:11px;font-weight:600;letter-spacing:.03em;border:1px solid var(--bd);background:var(--bg-2);
  color:var(--tx-2);white-space:nowrap}
.chip .dot{width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
/* traffic-light DOTS for health. never red/green fills - that vocabulary is P&L's */
.chip.ok .dot{background:var(--pos)} .chip.warn .dot{background:var(--warn)} .chip.bad .dot{background:var(--neg)}
.chip.ok{color:var(--tx-1)} .chip.warn{color:var(--warn)} .chip.bad{color:var(--neg)}
.chip.live .dot{animation:pl 2.4s var(--e-hover) infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.4}}

.bar{height:6px;border-radius:var(--r-pill);background:var(--bg-inset);overflow:hidden;border:1px solid var(--bd-subtle)}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--acc),oklch(78% .14 250));
  transition:width .8s var(--e-open)}
.bar.done>i{background:linear-gradient(90deg,var(--pos),oklch(82% .15 152))}
.src{margin-top:var(--s5);padding-top:var(--s4);border-top:1px solid var(--bd-subtle);font-size:11px;
  color:var(--tx-4);display:flex;flex-wrap:wrap;gap:var(--s2) var(--s5)}
.src .stale{color:var(--warn)}
  .age{font-variant-numeric:tabular-nums}
  .age.stale{color:var(--warn)}
.stagger>*{opacity:0;transform:translateY(8px);animation:fu .4s var(--e-hover) forwards;
  animation-delay:calc(var(--i,0)*45ms)}
@keyframes fu{to{opacity:1;transform:none}}

/* ---------------- calendar ---------------- */
.cal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.dow{font-size:11px;color:var(--tx-4);text-align:center;letter-spacing:.06em;text-transform:uppercase;
  font-weight:600;padding-bottom:var(--s2)}
.cell{min-height:70px;border:1px solid var(--bd-subtle);border-radius:var(--r-md);background:var(--bg-1);
  padding:6px 8px;display:flex;flex-direction:column;gap:2px;
  transition:transform .14s var(--e-hover),border-color .14s var(--e-hover),box-shadow .14s var(--e-hover)}
.cell.empty{background:transparent;border-color:transparent}
.cell.has{cursor:pointer}
.cell.has:hover{transform:translateY(-2px);border-color:var(--bd-strong);box-shadow:var(--sh-2)}
.cell .d{font-size:11px;color:var(--tx-4);font-weight:600;line-height:1}
.cell .v{font-weight:650;font-size:clamp(11px,1.05vw,14px);line-height:1.15;margin-top:auto;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.cell .t{font-size:10px;color:var(--tx-4)}
.cell .arms{display:flex;gap:2px;margin-top:1px}
.cell .arms i{width:5px;height:5px;border-radius:1px;background:var(--tx-4);opacity:.7}
.legend{display:flex;align-items:center;gap:var(--s3);font-size:11px;color:var(--tx-4)}
.legend .ramp{width:110px;height:8px;border-radius:var(--r-pill);
  background:linear-gradient(90deg,var(--neg),var(--bg-2),var(--pos));border:1px solid var(--bd-subtle)}

/* ---------------- heartbeat (EKG) ---------------- */
/* One bar per recent tick, height/colour by verdict, newest pulsing. The sweep
   is a gradient that travels the strip so a LIVE engine reads as alive at a
   glance and a dead one is visibly frozen. All motion off under reduced-motion. */
.beat{position:relative;display:flex;align-items:flex-end;gap:2px;height:44px;
  padding:0 2px;border-radius:var(--r-md);background:var(--bg-inset);
  border:1px solid var(--bd-subtle);overflow:hidden}
.beat i{flex:1 1 auto;min-width:2px;background:var(--tx-4);border-radius:1px;opacity:.55;
  transition:height .3s var(--e-open)}
.beat i.hold{background:var(--tx-3)}
.beat i.act{background:var(--acc);opacity:.95;box-shadow:0 0 6px var(--acc)}
.beat i.exit{background:var(--warn);opacity:.9}
.beat i.stop{background:var(--neg);opacity:.9}
.beat i.now{animation:beatpulse 1.8s var(--e-hover) infinite}
@keyframes beatpulse{0%,100%{opacity:1;transform:scaleY(1)}50%{opacity:.45;transform:scaleY(.72)}}
.beat.live::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:linear-gradient(90deg,transparent 0%,color-mix(in oklch,var(--acc) 22%,transparent) 48%,transparent 62%);
  transform:translateX(-100%);animation:sweep 3.6s linear infinite}
@keyframes sweep{to{transform:translateX(100%)}}
.beat.dead{filter:grayscale(1) brightness(.6)}
.beatlbl{display:flex;justify-content:space-between;font-size:11px;color:var(--tx-4);margin-top:var(--s2)}

/* ---------------- positions ---------------- */
.flatbig{font-size:34px;font-weight:650;letter-spacing:-.02em;color:var(--tx-2)}
.poswrap{display:flex;align-items:center;gap:var(--s7);flex-wrap:wrap}
.armpill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--r-pill);
  background:var(--bg-2);border:1px solid var(--bd);font-size:12px;color:var(--tx-2)}
.armpill b{color:var(--tx-1);font-variant-numeric:tabular-nums}
/* ---------------- army (orchestrator + sessions + workers + pulse) ---------------- */
/* State dots reuse the health() ok/warn/bad -> pos/warn/neg vocabulary the engine-room
   and org graph already use for system health (see .chip.ok/.warn/.bad above) -- that
   is the resolved reading of "traffic-light, never a P&L fill": the dot is a small
   indicator, not a big number reporting money. */
.armywrap{overflow-x:auto}
.army-node{cursor:pointer}
/* Nodes lift toward the light on hover. transform+filter only, so it stays on the
   compositor and never reflows a 9-box grid mid-animation. */
.army-node rect{transition:stroke .18s var(--e-hover),filter .18s var(--e-hover)}
.army-node:hover rect{stroke:var(--acc-line);filter:drop-shadow(var(--glow-soft))}
.army-ring{animation:armyring 2.4s ease-in-out infinite;transform-origin:center}
@keyframes armyring{0%,100%{opacity:.30}50%{opacity:1}}
.army-glow{animation:armyglow .6s ease-out}
@keyframes armyglow{from{filter:drop-shadow(0 0 9px var(--acc))}to{filter:none}}
/* The travelling message dot gets a real corona -- J asked for "pulsing heartbeats for the
   messages going back and forth", and a flat 6px circle reads as a bullet, not a signal. */
.army-pulse{filter:drop-shadow(0 0 6px var(--acc)) drop-shadow(0 0 14px var(--acc));
  animation:pulsebeat .9s ease-in-out infinite}
@keyframes pulsebeat{0%,100%{opacity:.85;r:5}50%{opacity:1;r:7}}

/* ---------------- action-card rail ---------------- */
.acard-item{transition:transform .18s var(--e-hover),border-color .18s var(--e-hover),
  box-shadow .18s var(--e-hover),background .18s var(--e-hover)}
.acard-item:hover{transform:translateY(-2px);border-color:var(--acc-line)!important;
  box-shadow:var(--glow-soft);background:var(--bg-2)!important}
.acard-item:active{transform:translateY(0)}
/* A hairline of accent down the leading edge, revealed on hover -- cheaper than a border
   change and it reads as the card being "armed" rather than merely highlighted. */
.acard-item{position:relative;overflow:hidden}
.acard-item::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;
  background:var(--acc);opacity:0;transition:opacity .18s var(--e-hover)}
.acard-item:hover::before{opacity:.9}
.acard-open{box-shadow:var(--glow);animation:acardin .32s var(--e-open)}
@keyframes acardin{from{opacity:0;transform:translateY(-6px) scale(.985)}to{opacity:1;transform:none}}
/* Context bar under a session box: fill width is set inline from context_pct. */
.ctxbar{height:4px;border-radius:999px;background:color-mix(in oklch,white 8%,transparent);overflow:hidden}
.ctxbar i{display:block;height:100%;border-radius:999px;background:var(--acc);
  transition:width .6s var(--e-hover)}
.ctxbar.hot i{background:var(--warn)}
.ctxbar.full i{background:var(--neg)}
@media (prefers-reduced-motion:reduce){
  .army-ring,.army-glow,.army-pulse,.acard-open{animation:none}
  .acard-item,.acard-item::before,.army-node rect,.ctxbar i{transition:none}
  .acard-item:hover{transform:none}
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
.chathead select{margin-left:auto;font:600 11.5px/1 var(--mono);padding:6px 10px;
  border-radius:var(--r-sm);border:1px solid var(--bd);background:var(--bg-2);color:var(--tx-2);cursor:pointer}
.chatbody{min-height:120px;max-height:22vh;overflow:auto;display:flex;flex-direction:column;
  gap:var(--s5);padding:var(--s5);border:1px solid var(--bd-subtle);border-radius:var(--r-md);
  background:var(--bg-inset)}
.chatturn{display:flex;flex-direction:column;gap:var(--s2);animation:chatin .24s var(--e-open)}
@keyframes chatin{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.chatwho{font:600 10.5px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--tx-4)}
.chatturn-user .chatwho{color:var(--acc)}
.chattext{white-space:pre-wrap;word-break:break-word;font-size:13.5px;line-height:1.62;color:var(--tx-1)}
.chatturn-user .chattext{color:var(--tx-2)}
.chatsteps{display:flex;flex-direction:column;gap:2px;margin-top:var(--s2)}
.chatstep{font:500 11px/1.5 var(--mono);color:var(--tx-3)}
.chatstep.dim{color:var(--tx-4)}
.chatstep.ok{color:var(--pos)}
.chatstep.bad{color:var(--neg)}
.chatfoot{display:flex;gap:var(--s3);align-items:flex-end}
.chatfoot textarea{flex:1;resize:none;font:400 13.5px/1.55 var(--font);padding:11px 14px;
  border-radius:var(--r-md);border:1px solid var(--bd);background:var(--bg-1);color:var(--tx-1);
  outline:none;transition:border-color .16s var(--e-hover),box-shadow .16s var(--e-hover)}
.chatfoot textarea:focus{border-color:var(--acc-line);box-shadow:var(--glow-soft)}
.chatfoot textarea:disabled{opacity:.55}
#chatsend{font:700 13px/1 var(--font);padding:12px 20px;border-radius:var(--r-md);cursor:pointer;
  border:1px solid var(--acc);background:var(--acc-dim);color:var(--acc);
  transition:all .16s var(--e-hover)}
#chatsend:hover:not(:disabled){background:var(--acc);color:var(--bg-canvas)}
#chatsend:disabled{opacity:.5;cursor:default}
.chatnote{color:var(--tx-4)}
@media (prefers-reduced-motion:reduce){.chatturn{animation:none}}
.armyledger{max-height:240px;overflow:auto;margin-top:var(--s5);padding-top:var(--s4);
  border-top:1px solid var(--bd-subtle);font-size:11px;color:var(--tx-3)}
.armyledger div{display:flex;gap:var(--s3);padding:3px 0;white-space:nowrap;overflow:hidden}
.armyledger .t{color:var(--tx-4);font-family:var(--mono);flex:none}

/* ---------------- action cards ---------------- */
/* Deterministic, ranked, fire-or-read. The fire button is the ONE control on
   this whole page that can spawn a headless Claude session -- it gets its own
   disabled-state styling rather than reusing a generic button so a greyed-out
   RTH-blocked button reads unmistakably as "not now", not as broken chrome. */
.actioncard .row .chip:first-child{font-variant-numeric:tabular-nums}
.fire-btn{transition:opacity .14s var(--e-hover),background .14s var(--e-hover)}
.fire-btn:disabled{opacity:.4;cursor:not-allowed;background:var(--bg-3)!important;
  border-color:var(--bd)!important;color:var(--tx-3)!important}
.fire-btn:not(:disabled):hover{background:var(--acc)!important;color:#fff!important}
.askstream{max-height:60vh;overflow:auto;font-family:var(--mono);font-size:12px;
  line-height:1.6;color:var(--tx-2);white-space:pre-wrap;word-break:break-word;
  background:var(--bg-inset);border:1px solid var(--bd-subtle);border-radius:var(--r-md);
  padding:var(--s4)}
.askstream div{padding:1px 0}

/* ---------------- table ---------------- */
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--tx-4);
  padding:var(--s3) var(--s4);border-bottom:1px solid var(--bd);position:sticky;top:0;background:var(--bg-1);z-index:1}
td{padding:var(--s3) var(--s4);border-bottom:1px solid var(--bd-subtle);color:var(--tx-2)}
td.n{text-align:right;font-family:var(--mono);font-size:12px}
tbody tr{transition:background .12s var(--e-hover)}
tbody tr:hover{background:var(--bg-2)}
tr:last-child td{border-bottom:none}

/* ---------------- drawer ---------------- */
.scrim{position:fixed;inset:0;background:oklch(8% .01 265/.66);backdrop-filter:blur(3px);opacity:0;
  pointer-events:none;transition:opacity .22s var(--e-open);z-index:40}
.scrim.on{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(720px,95vw);z-index:50;background:var(--bg-1);
  border-left:1px solid var(--bd);transform:translateX(101%);transition:transform .26s var(--e-open);
  display:flex;flex-direction:column;box-shadow:var(--sh-4)}
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
  background:oklch(8% .01 265/.6);backdrop-filter:blur(4px)}
.pal.on{display:flex}
.pal .box{width:min(580px,92vw);background:var(--bg-2);border:1px solid var(--bd);border-radius:var(--r-lg);
  overflow:hidden;box-shadow:var(--sh-4);animation:pop .2s var(--e-hover)}
@keyframes pop{from{opacity:0;transform:translateY(-8px) scale(.98)}to{opacity:1;transform:none}}
.pal input{width:100%;padding:16px 18px;background:transparent;border:none;outline:none;color:var(--tx-1);
  font-size:15px;font-family:var(--font);border-bottom:1px solid var(--bd-subtle)}
.pal .res{max-height:340px;overflow:auto;padding:var(--s2)}
.pal .res div{padding:10px 14px;cursor:pointer;display:flex;gap:11px;align-items:center;font-size:14px;
  border-radius:var(--r-md)}
.pal .res div.sel{background:var(--bg-3)}
.pal .res .k{margin-left:auto;color:var(--tx-4);font-size:11px}

.brief{padding:var(--s7) var(--s8)}
.brieflines p{font-size:16px;line-height:1.65;color:var(--tx-1);margin-top:var(--s4);max-width:78ch}
.brieflines p:first-child{font-size:19px;letter-spacing:-.01em}
.flag{margin-top:var(--s5);padding:var(--s4) var(--s5);border-radius:var(--r-md);font-size:13.5px;
  border:1px solid var(--bd);background:var(--bg-2)}
.flag b{letter-spacing:.06em;font-size:11px;margin-right:var(--s3);color:var(--acc)}
.flag.bad{border-color:color-mix(in oklch,var(--warn) 34%,transparent);background:var(--warn-dim)}
.flag.bad b{color:var(--warn)}
.note{padding:var(--s9);text-align:center;color:var(--tx-4);font-size:13px}
.kv{display:flex;justify-content:space-between;gap:var(--s5);padding:var(--s3) 0;
  border-bottom:1px solid var(--bd-subtle);font-size:13px}
.kv:last-child{border-bottom:none}
.kv .k{color:var(--tx-3);white-space:nowrap}
.kv .v{text-align:right;color:var(--tx-1)}

@container (max-width:250px){.card .spark{display:none}}
@media (max-width:900px){
  .app{grid-template-columns:1fr}
  .side{position:static;height:auto;flex-direction:row;flex-wrap:wrap;align-items:center;gap:var(--s3)}
  .side .foot{display:none}.nav{flex-direction:row;flex-wrap:wrap}.nav a.on::before{display:none}
  .view{padding:var(--s5)}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  .stagger>*{opacity:1;transform:none}
}
"""

SHELL = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gamma — Cockpit</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>__CSS__</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <div class="brand"><div class="mark"></div><div><b>Gamma</b><small>Cockpit</small></div></div>
    <nav class="nav" id="nav"></nav>
    <div class="foot"><kbd>⌘</kbd><kbd>K</kbd> palette · <kbd>?</kbd> help<br><span id="footstamp"></span></div>
  </aside>
  <main class="main">
    <header class="top">
      <h1 id="vtitle">Overview</h1>
      <span class="chip live" id="statechip"><i class="dot"></i><span id="statetxt"></span></span>
      <div class="sp"></div>
      <div class="clock" id="clock"></div>
    </header>
    <div class="view anim" id="view"></div>
  </main>
</div>
<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <header><h2 id="dtitle"></h2><button class="x" id="dclose" aria-label="Close">×</button></header>
  <div class="body" id="dbody"></div>
</aside>
<div class="pal" id="pal">
  <div class="box"><input id="palin" placeholder="Jump to a view, desk, agent or day…" autocomplete="off">
  <div class="res" id="palres"></div></div>
</div>
<script>const D=__DATA_JSON__;</script>
<script>__JS__</script>
</body>
</html>
"""


def render(payload: dict, js: str) -> str:
    """Assemble the page. The one sequence that could break out of a <script>
    block is neutralised; everything else is escaped by esc() at render time."""
    blob = json.dumps(payload, default=str).replace("</script", "<\\/script")
    return (SHELL.replace("__CSS__", CSS)
                 .replace("__DATA_JSON__", blob)
                 .replace("__JS__", js))

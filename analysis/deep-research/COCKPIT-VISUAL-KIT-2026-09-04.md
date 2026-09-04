# Cockpit Visual Kit — vendored AetherOps recipe library (2026-09-04)

> Synthesis of two 2026-09-03 vendoring passes into ONE reference for whoever wires
> `gamma_cockpit_ui.py`. Nothing here is new research — every fact is quoted from
> files already on disk, re-verified this session (byte counts, file counts, license
> text all re-read fresh, not carried from memory). Full crawl narratives:
> [`2026-09-03-aetherops-ui-kit-port.md`](2026-09-03-aetherops-ui-kit-port.md) ·
> [`COCKPIT-REDESIGN-RESEARCH-2026-09-03.md`](COCKPIT-REDESIGN-RESEARCH-2026-09-03.md).

---

## 1. TL;DR

**Two separate vendored deliverables sit in `setup/scripts/vendor/ui-kit/` — pick ONE shape, don't ship both.**

| Deliverable | Shape | Files | Bytes | License mix |
|---|---|---|---|---|
| **Per-file pass** (primary — use this one) | 41 standalone `<kind>-slug>.html`, each self-contained (markup+CSS+optional JS) | 41 `.html` + `VENDOR-INDEX.md` + `REFERENCE-ONLY.md` + `demo.html` | 85,391 B (components) + 74,453 B (demo harness) + 21,136 B (docs) | 14 MIT-Uiverse, 16 MIT-MagicUI, 11 original/self-authored |
| **Bundle pass** (earlier, redundant subject matter) | 1 linked stylesheet + 1 script, `uk-*` classes | `aetherops-ui-kit.css` + `.js` + `MANIFEST.md` | 23,507 + 9,392 = 32,899 B | 16 MIT-MagicUI |

- **Component count (primary pass): 41**, verified via `ls setup/scripts/vendor/ui-kit/*.html | grep -v demo.html | wc -l` this session = `41`.
- **Total bytes, all vendor-kit files on disk** (both passes + docs, `du -sb`): **221,307 B**.
- **Licenses represented:** MIT (Uiverse.io, site-wide, stated on every crawled element's footer) · MIT (`magicuidesign/magicui`, confirmed verbatim via `gh api repos/magicuidesign/magicui/contents/LICENSE.md`, commit `2d671cc6c0e0`) · Original/self-authored (generic, uncopyrightable technique — no license needed) · N/A/recipe-only (monet.design DOM-extraction, text recorded in `REFERENCE-ONLY.md`, zero code copied).
- **Demo screenshot:** `C:\Users\jackw\Desktop\42\analysis\home\screens\ui-kit-demo.png` (360,404 B, confirmed on disk) — headless-Chrome capture of `demo.html` after 4 render bugs were root-caused and fixed (CORS fetch failure, a ripple positioning collision, an IntersectionObserver gate that never fired under `--virtual-time-budget`, and a meteor-angle sign flip that sent every meteor off-canvas — detail in source doc §"verify").
- **Byte-budget conflict, unresolved:** `../MANIFEST.md` (repo-wide vendor ledger) already tracks 207,429 B spent against a 250,000 B CSS+JS cap. Neither AetherOps pass fits the 42,571 B headroom alone (bundle pass alone is 32,899 B — fits with 9,672 B to spare; the per-file pass's 85,391 B of component HTML does not, though HTML snippets were arguably never meant to count against a CSS+JS-only cap — flag for the integrator, not resolved here). **Recommendation:** ship the per-file pass, inline only the `uk-*` snippets the built page actually uses (per-file shape makes this trivial), discard the bundle pass rather than carrying both.

---

## 2. The reference decoded — token block

J's reference ("AetherOps") is a **deep-navy canvas + indigo-tinted-hairline panel + indigo→violet→cyan gradient** system. Every recipe below reuses the SAME custom-property set (defined redundantly per-file since each `.html` is standalone; a real page build should hoist these once):

```css
:root{
  /* canvas + panel shell — self-authored, generalizing the monet.design
     "deep navy dashboard canvas" recipe (REFERENCE-ONLY.md #2) from its
     literal #0a0a0a/#111111/#2a2a2a greys into AetherOps' indigo-tinted navy */
  --uk-canvas:  #0a0e1c;                 /* root page background */
  --uk-panel:   #121933;                 /* card/panel fill */
  --uk-line:    rgba(99,102,241,.22);    /* 1px hairline border, indigo-tinted */
  --uk-line-soft: rgba(99,102,241,.18);  /* softer hairline variant (panel-shell) */

  /* accent gradient stops — lifted from the real MIT uiverse.io CTA
     (button-gradient-cta-glow.html, nima-mollazadeh/terrible-panda-97)
     and reused system-wide for gradient consistency */
  --uk-accent:   #6366f1;   /* indigo */
  --uk-accent-2: #8b5cf6;   /* violet */
  --uk-accent-3: #22d3ee;   /* cyan */
  --uk-glow:     rgba(139,92,246,.5);   /* violet glow, drop-shadow/filter use */

  /* semantic status — literal, NOT part of the brand retheme surface
     (VENDOR-INDEX.md: "status-semantic colors are left literal since
     they're meaning-coded, not part of the brand retheme surface") */
  --uk-green:  #34d399;   /* approved / healthy / positive delta */
  --uk-amber:  #fbbf24;   /* needs-review / degraded */
  --uk-red:    #f87171;   /* escalated / negative delta */
  --uk-cyan-status: #22d3ee;  /* resolved */
}
```

| Token family | Value(s) | Cited recipe |
|---|---|---|
| Canvas | `radial-gradient(1200px 600px at 20% -10%, #131a33 0%, #0a0e1c 55%, #0a0e1c 100%)` | `background-panel-shell-canvas.html` (self-authored, generalizes monet.design's flat `#0a0a0a` root per `REFERENCE-ONLY.md` #2) |
| Panel + hairline | `background:var(--uk-panel); border:1px solid var(--uk-line); border-radius:16-18px; box-shadow:inset 0 1px 0 rgba(255,255,255,.03), 0 20px 40px -20px rgba(0,0,0,.6)` | `background-panel-shell-canvas.html`, `flow-workflow-routing-map.html`, `chart-cost-pulse-area.html` (all three define the same shell) |
| Gradient (header CTA, node bars) | `linear-gradient(135deg, #6366f1, #8b5cf6)` | `button-gradient-cta-glow.html` (MIT, uiverse.io), reused in `card-kpi-stat.html`'s icon tile |
| Gradient (Sankey ribbons) | 3-stop `linear-gradient` indigo→violet→cyan, `userSpaceOnUse` across the full ribbon span | `flow-workflow-routing-map.html` (self-authored, §4 below) |
| Glow filter | `feGaussianBlur stdDeviation="6"` + `feMerge` (SVG), or `filter:blur(3-4px)` (CSS duplicate-path trick) | `flow-workflow-routing-map.html` SVG defs; `chart-cost-pulse-area.html`'s `.uk-area-line-glow` |
| Chip tone (12.5%-alpha background) | `background: rgba(<accent>, .125); border-color: rgba(<accent>, .3); color: <accent-full>` | `chip-status.html` (self-authored, generalizing monet.design's "chip color-at-12.5%-alpha token" per `REFERENCE-ONLY.md` #9, extended from 3 tones to 4) |
| Type | `'Inter', system-ui, sans-serif`; KPI big number `28px/600/-0.02em`; label `13px/#94a3b8`; delta chip `12px/600` | `card-kpi-stat.html` |

---

## 3. Component-by-component mapping

| Reference element (J's image) | Cockpit element | Real data source (Project Gamma) | Kit file(s) | Motion |
|---|---|---|---|---|
| Left nav rail, "Overview" active pill | Left nav rail | Static route list (Overview/Workflows/Agents — cockpit's own page sections) | `nav-rail-active-pill.html` | `background .2s, color .2s` hover; active = gradient pill, no animation |
| Header title + subtitle + ⌘K search | Header | Static copy + live search-if-wired | `other-gradient-underline-input.html` (MIT, uiverse.io/adamgiebl) + `chip-animated-shiny-text.html` (MIT, MagicUI `animated-shiny-text.tsx`) | Underline gradient sweep on focus; shiny-text sweeps subtitle |
| Gradient CTA ("New workflow") | Header primary CTA | n/a (UI action, no data) | `button-glow-cta.html` (MIT, uiverse.io/gharsh11032000) | Glow pulse on hover |
| 4 KPI stat cards ($48,320 / 98.6% / 94% / 18 + green delta) | KPI row | `automation/state/fleet/accounts.json` (equity), `analysis/go-live-gate.json` (gate %), `analysis/prod-shadow/summary.json` (net P&L), `automation/state/decisions.jsonl` (today's decision count) — all confirmed on disk this session | `card-kpi-stat.html` (MIT, uiverse.io/vk-uiux) + `card-bento-grid.html` (MIT, MagicUI `bento-grid.tsx`, grid layout) + `chart-number-ticker.html` (MIT, MagicUI `number-ticker.tsx`, count-up) | Icon-tile static gradient; number counts up into view; hover = translateY(-2px) lift |
| **Workflow routing map** (5-stage Sankey, Intake→Classify→Review→Fallback→Deliver) | **Workflow routing map (centerpiece)** | `automation/state/decisions.jsonl` / `automation/state/core-decisions.jsonl` (tick-by-tick engine decisions — the ONLY real source of stage-transition counts; ribbon %s must be computed from this, not hardcoded) | `flow-workflow-routing-map.html` (self-authored, §4 below) + `background-dot-pattern.html` (MIT, MagicUI `dot-pattern.tsx`, left decoration) + `loader-atom-orbit.html` (MIT, uiverse.io/OMPRABHU8125, "Live" chip spinner) | Dashed flow-line `stroke-dashoffset` animates `3.5s linear infinite`; "Live" dot pulses |
| Approval queue (3 rows: icon+title+subtitle+chip+avatar) | Approval queue | `analysis/recommendations-log.jsonl` (pending recommendation rows — real, on disk) | `card-magic-spotlight.html` (MIT, MagicUI `magic-card.tsx`, hover-glow) + `chip-status.html` (self-authored, 4 tones) + `list-avatar-row.html` (self-authored) | Mouse-follow spotlight glow on hover |
| Cost pulse ($48,320 + delta + area chart + tooltip) | Cost pulse panel | Anthropic API spend tracking (per CLAUDE.md §5 cost-discipline — no single file confirmed this session; flag for integrator to wire real spend, not the placeholder $48,320 in the recipe) | `chart-cost-pulse-area.html` (self-authored, §4 below) | Hover `pointermove` moves highlighted dot + tooltip; no idle animation |
| Agent health (name/version/%/Healthy chip/sparkline) | Agent health list | `automation/state/SCHEDULED-TASKS.md` (task registry, confirmed on disk) + `automation/state/kitchen-status.json` (confirmed on disk) | `chart-progress-ring.html` (MIT, MagicUI `animated-circular-progress-bar.tsx`) + `chart-sparkline-card.html` (self-authored) + `chip-status.html` | Ring sweeps 0→value on mount; sparkline static polyline |
| System alerts (warning/info + Review buttons) | System alerts | `automation/state/decisions.jsonl` filtered for rule-break / kill-switch events (no dedicated alerts file confirmed — integrator should point this at the actual guard-failure surface, not fabricate) | `list-alert-row.html` (self-authored) + `button-frosted-border-mask.html` (MIT, uiverse.io/TaniaDou, "Review" button) | Row hover-lift only |
| "Deploy smarter" promo panel | Promo panel | n/a (marketing/UI copy) | `card-promo-panel.html` (self-authored composite, embeds the MIT CTA below) + `button-gradient-cta-glow.html` (MIT, uiverse.io/nima-mollazadeh) | Radial highlight static; CTA glows on hover |
| Ambient premium-glow texture | Background decoration | n/a | `background-aurora-glow.html`, `background-animated-grid.html` (MIT, MagicUI), `background-meteors.html` (MIT, MagicUI, angle-bug fixed this session per source doc), `background-ripple.html` (MIT, MagicUI) | Grid drifts; meteors fall diagonally; ripple rings expand outward |
| "Live" status toggle | Any live/armed indicator | `automation/state/fleet/accounts.json` `live:` flag (confirmed field per CLAUDE.md Account context table) | `toggle-neon-power.html` (MIT, uiverse.io/vinodjangid07) | Track glows when on |

---

## 4. Verbatim recipes — the two centerpiece techniques

### 4a. Sankey routing-map (5-stage glowing ribbon)

**Math:** fixed 5 node x-positions `[90,290,490,690,890]` on a `960×380` viewBox. Each of 3 bands (Primary 68% / Secondary 22% / Fallback 10%) gets a **pixel height `= pct*2`**, stacked top-to-bottom with a 10px gap starting at `barTop=60`; node bars span the full stacked height. Each ribbon segment between adjacent nodes is a **closed cubic-Bezier band**: top edge curves from `(x1,top)` to `(x2,top)` via a flat-control-point S-curve at the midpoint `mx=(x1+x2)/2`, bottom edge mirrors it back — the same mirrored-S technique d3-sankey uses internally, hand-rolled here since the 5 stages are fixed (no dynamic layout solver needed). A second dashed path along each ribbon's vertical midpoint animates `stroke-dashoffset` for the "flow" effect.

**Full source** (`setup/scripts/vendor/ui-kit/flow-workflow-routing-map.html`, self-authored — no proprietary code copied, safe to use without attribution):

```html
<div class="uk-routing-panel">
  <div class="uk-routing-header">
    <h3>Workflow routing map</h3>
    <span class="uk-live-chip"><span class="uk-live-dot"></span>Live</span>
  </div>
  <svg viewBox="0 0 960 380" class="uk-routing-svg">
    <defs>
      <linearGradient id="uk-flow-grad" gradientUnits="userSpaceOnUse" x1="90" y1="0" x2="890" y2="0">
        <stop offset="0%" stop-color="#6366f1"/>
        <stop offset="50%" stop-color="#8b5cf6"/>
        <stop offset="100%" stop-color="#22d3ee"/>
      </linearGradient>
      <linearGradient id="uk-node-grad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#6366f1"/>
        <stop offset="100%" stop-color="#8b5cf6"/>
      </linearGradient>
      <pattern id="uk-dots" width="14" height="14" patternUnits="userSpaceOnUse">
        <circle cx="2" cy="2" r="1" fill="#334155"/>
      </pattern>
      <filter id="uk-glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="6" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <rect x="0" y="40" width="70" height="300" fill="url(#uk-dots)" opacity=".45"/>
    <g id="uk-ribbons" filter="url(#uk-glow)"></g>
    <g id="uk-flow-dashes"></g>
    <g id="uk-nodes"></g>
    <g id="uk-stage-labels" font-family="Inter,system-ui,sans-serif" font-size="12" fill="#94a3b8" text-anchor="middle"></g>
    <g id="uk-pct-labels" font-family="Inter,system-ui,sans-serif" font-size="11" fill="#e5e7eb" text-anchor="middle"></g>
  </svg>
  <div class="uk-legend">
    <span><i class="uk-swatch" style="background:linear-gradient(90deg,#6366f1,#8b5cf6)"></i>Primary path 68%</span>
    <span><i class="uk-swatch" style="background:linear-gradient(90deg,#8b5cf6,#a855f7)"></i>Secondary 22%</span>
    <span><i class="uk-swatch" style="background:linear-gradient(90deg,#475569,#64748b)"></i>Fallback 10%</span>
  </div>
</div>
<style>
:root{ --uk-canvas:#0a0e1c; --uk-panel:#121933; --uk-line:rgba(99,102,241,.22);
  --uk-accent:#6366f1; --uk-accent-2:#8b5cf6; --uk-accent-3:#22d3ee; --uk-glow:rgba(139,92,246,.5); }
.uk-routing-panel{background:var(--uk-panel);border:1px solid var(--uk-line);border-radius:18px;padding:20px;font-family:'Inter',system-ui,sans-serif;color:#e5e7eb}
.uk-routing-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.uk-routing-header h3{margin:0;font-size:1rem;font-weight:600}
.uk-live-chip{display:inline-flex;gap:6px;align-items:center;background:rgba(52,211,153,.12);color:#34d399;border:1px solid rgba(52,211,153,.3);border-radius:999px;padding:4px 10px;font-size:12px;font-weight:600}
.uk-live-dot{width:6px;height:6px;border-radius:50%;background:#34d399;animation:uk-pulse 1.6s ease-in-out infinite}
@keyframes uk-pulse{0%,100%{box-shadow:0 0 0 0 rgba(52,211,153,.6)}50%{box-shadow:0 0 0 6px rgba(52,211,153,0)}}
.uk-routing-svg{width:100%;height:auto;display:block}
.uk-flow-dash{stroke:#fff;stroke-opacity:.55;stroke-width:2;fill:none;stroke-dasharray:4 14;animation:uk-flow 3.5s linear infinite}
@keyframes uk-flow{to{stroke-dashoffset:-360}}
.uk-legend{display:flex;gap:20px;font-size:12px;color:#94a3b8;margin-top:6px;flex-wrap:wrap}
.uk-swatch{display:inline-block;width:14px;height:4px;border-radius:2px;margin-right:6px}
</style>
<script>
(function(){
  const stages=['Intake','Classify','Review','Fallback','Deliver'];
  const xs=[90,290,490,690,890];
  const bands=[
    {name:'Primary',pct:68,color1:'#6366f1',color2:'#8b5cf6'},
    {name:'Secondary',pct:22,color1:'#8b5cf6',color2:'#a855f7'},
    {name:'Fallback',pct:10,color1:'#475569',color2:'#64748b'}
  ];
  const barTop=60, gap=10;
  let y=barTop;
  const bandYs=bands.map(b=>{ const h=b.pct*2; const top=y, bot=y+h; y=bot+gap; return {top,bot,mid:(top+bot)/2,h}; });
  const barBottom=y-gap;
  const nodesG=document.getElementById('uk-nodes');
  const labelsG=document.getElementById('uk-stage-labels');
  const ribbonsG=document.getElementById('uk-ribbons');
  const dashesG=document.getElementById('uk-flow-dashes');
  const pctG=document.getElementById('uk-pct-labels');
  const svgNS='http://www.w3.org/2000/svg';
  xs.forEach((x,i)=>{
    const rect=document.createElementNS(svgNS,'rect');
    rect.setAttribute('x',x-7); rect.setAttribute('y',barTop);
    rect.setAttribute('width',14); rect.setAttribute('height',barBottom-barTop);
    rect.setAttribute('rx',7); rect.setAttribute('fill','url(#uk-node-grad)');
    nodesG.appendChild(rect);
    const label=document.createElementNS(svgNS,'text');
    label.setAttribute('x',x); label.setAttribute('y',barBottom+22);
    label.textContent=stages[i];
    labelsG.appendChild(label);
  });
  for(let i=0;i<xs.length-1;i++){
    const x1=xs[i]+7, x2=xs[i+1]-7, mx=(x1+x2)/2;
    bands.forEach((b,bi)=>{
      const {top,bot,mid}=bandYs[bi];
      const opacity = bi===2 ? 0.5 : 0.85;
      const d=`M ${x1},${top} C ${mx},${top} ${mx},${top} ${x2},${top} L ${x2},${bot} C ${mx},${bot} ${mx},${bot} ${x1},${bot} Z`;
      const path=document.createElementNS(svgNS,'path');
      path.setAttribute('d',d);
      path.setAttribute('fill', bi<2 ? 'url(#uk-flow-grad)' : '#475569');
      path.setAttribute('fill-opacity',opacity);
      ribbonsG.appendChild(path);
      const dash=document.createElementNS(svgNS,'path');
      dash.setAttribute('class','uk-flow-dash');
      dash.setAttribute('d',`M ${x1},${mid} C ${mx},${mid} ${mx},${mid} ${x2},${mid}`);
      dashesG.appendChild(dash);
      if(i===Math.floor((xs.length-2)/2)){
        const pct=document.createElementNS(svgNS,'text');
        pct.setAttribute('x',mx); pct.setAttribute('y',mid-8);
        pct.textContent=b.pct+'%';
        pctG.appendChild(pct);
      }
    });
  }
})();
</script>
```

### 4b. Glowing area chart with hover tooltip

**Math:** 12 data points normalized to a `640×220` viewBox, `y = 210 - ((v-min)/(max-min||1))*180`. Line path is a Catmull-Rom-style cubic-Bezier through consecutive points (control point = horizontal midpoint between each pair, at each point's own y — a cheap smooth-curve approximation, not a true spline). The **glow** is the standard "duplicate the path, blur it, put it underneath" trick: a 6px-wide, 35%-opacity, `filter:blur(4px)` copy of the line sits behind the crisp 2px line. The **fill** closes the same path down to `y=220` and back, painted with a top-to-bottom gradient fading `#8b5cf6` at 35% alpha to transparent. Hover: a `pointermove` listener on a transparent hit-rect finds the nearest data index by `round(relX / step)` and repositions a glow+core dot pair plus an absolutely-positioned tooltip div.

**Full source** (`setup/scripts/vendor/ui-kit/chart-cost-pulse-area.html`, self-authored — generalizes MDN's SVG-gradient tutorial + the generic blurred-duplicate-path glow idea; no proprietary values copied):

```html
<div class="uk-cost-panel">
  <p class="uk-cost-label">Cost pulse</p>
  <p class="uk-cost-big">$48,320 <span class="uk-cost-delta">&#8599; 8.2%</span></p>
  <div class="uk-chart-wrap">
    <svg viewBox="0 0 640 220" class="uk-area-chart" id="uk-area-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="uk-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path class="uk-area-fill" fill="url(#uk-area-grad)" stroke="none"/>
      <path class="uk-area-line-glow" fill="none" stroke="#a78bfa" stroke-width="6" stroke-linecap="round" opacity="0.35" style="filter:blur(4px)"/>
      <path class="uk-area-line" fill="none" stroke="#c4b5fd" stroke-width="2" stroke-linecap="round"/>
      <circle class="uk-hover-dot" r="9" fill="none" stroke="#a78bfa" stroke-opacity=".4" stroke-width="6" style="filter:blur(3px)"></circle>
      <circle class="uk-hover-dot-core" r="4" fill="#c4b5fd"></circle>
      <rect class="uk-hit-area" x="0" y="0" width="640" height="220" fill="transparent" style="pointer-events:all"></rect>
    </svg>
    <div class="uk-chart-tooltip"></div>
  </div>
</div>
<style>
.uk-cost-panel{background:#121933;border:1px solid rgba(99,102,241,.22);border-radius:16px;padding:20px;font-family:'Inter',system-ui,sans-serif;color:#e5e7eb;position:relative}
.uk-cost-label{font-size:.75rem;color:#94a3b8;margin:0 0 4px;text-transform:uppercase;letter-spacing:.05em}
.uk-cost-big{font-size:1.9rem;font-weight:700;margin:0 0 10px;color:#fff}
.uk-cost-delta{font-size:.8rem;font-weight:600;color:#34d399;background:rgba(52,211,153,.12);padding:2px 8px;border-radius:999px;vertical-align:middle}
.uk-chart-wrap{position:relative}
.uk-area-chart{width:100%;height:160px;display:block}
.uk-chart-tooltip{position:absolute;transform:translate(-50%,0);background:#1a2140;border:1px solid rgba(99,102,241,.35);color:#e5e7eb;font-size:12px;font-weight:600;padding:4px 8px;border-radius:6px;pointer-events:none;opacity:0;transition:opacity .15s;box-shadow:0 4px 14px rgba(0,0,0,.4)}
</style>
<script>
(function(){
  const points=[38000,40500,39200,43000,41800,45200,44100,47000,46200,48800,47600,48320].map((v,i,arr)=>{
    const min=Math.min(...arr), max=Math.max(...arr);
    const x=i/(arr.length-1)*640;
    const y=210-((v-min)/(max-min||1))*180;
    return {x,y,value:v};
  });
  let d=`M ${points[0].x},${points[0].y}`;
  for(let i=1;i<points.length;i++){
    const cpx=(points[i-1].x+points[i].x)/2;
    d+=` C ${cpx},${points[i-1].y} ${cpx},${points[i].y} ${points[i].x},${points[i].y}`;
  }
  const areaPath=d+` L ${points[points.length-1].x},220 L ${points[0].x},220 Z`;
  const svg=document.getElementById('uk-area-svg');
  svg.querySelector('.uk-area-fill').setAttribute('d',areaPath);
  svg.querySelector('.uk-area-line-glow').setAttribute('d',d);
  svg.querySelector('.uk-area-line').setAttribute('d',d);
  const dot=svg.querySelector('.uk-hover-dot'), core=svg.querySelector('.uk-hover-dot-core');
  const last=points[points.length-1];
  dot.setAttribute('cx',last.x); dot.setAttribute('cy',last.y);
  core.setAttribute('cx',last.x); core.setAttribute('cy',last.y);
  const tip=svg.closest('.uk-chart-wrap').querySelector('.uk-chart-tooltip');
  svg.querySelector('.uk-hit-area').addEventListener('pointermove', e => {
    const rect=svg.getBoundingClientRect();
    const relX=(e.clientX-rect.left)/rect.width*640;
    const step=640/(points.length-1);
    let i=Math.round(relX/step);
    i=Math.max(0,Math.min(points.length-1,i));
    const p=points[i];
    dot.setAttribute('cx',p.x); dot.setAttribute('cy',p.y);
    core.setAttribute('cx',p.x); core.setAttribute('cy',p.y);
    tip.style.left=(p.x/640*rect.width)+'px';
    tip.style.top=(p.y/220*rect.height-44)+'px';
    tip.textContent='$'+p.value.toLocaleString();
    tip.style.opacity=1;
  });
  svg.querySelector('.uk-hit-area').addEventListener('pointerleave', () => { tip.style.opacity=0; });
})();
</script>
```

---

## 5. REFERENCE-ONLY items (recipe text only, zero code copied — see `REFERENCE-ONLY.md` for full text)

| Item | Source | Why reference-only | What was vendored instead |
|---|---|---|---|
| Aurora glow panel (top radial bloom + gradient-border) | monet.design/c/stats-10 | Screenshot gallery, DOM-extracted, no stated license | `background-aurora-glow.html` (self-authored) |
| Deep-navy canvas + panel shell (hairline, inner glow) | monet.design/c/saaspo-feature-sections-devrev | Same | `background-panel-shell-canvas.html` (self-authored) |
| KPI stat tile (dot + metric + delta chip) | monet.design/c/saaspo-feature-sections-devrev | Same | `card-kpi-stat.html` (real MIT port, different source) |
| Node-and-line routing diagram (teal glow, dashed hub) | monet.design/c/conversion-integrations-section | Same | `flow-workflow-routing-map.html` (self-authored Sankey, different values) + `flow-animated-beam-ribbon.html` (real MIT MagicUI port) |
| Mini sparkline / progress bar colors | monet.design/c/saaspo-feature-sections-devrev | Same | `chart-sparkline-card.html` (self-authored) |
| Icon-tile + status-chip list row | monet.design/c/saaspo-feature-sections-devrev | Same | `list-avatar-row.html` + `list-alert-row.html` (self-authored) |
| Stats Bento / Skill Level Meters / Leaderboard Card / Area Chart / Grid Feature Cards / Bloom Field / Background snippets | 21st.dev (7 pages) | `Component.tsx` client-side-gated, never reached WebFetch; some state MIT on-page, code never extracted | Not ported; see MANIFEST.md's "Not ported" table |

---

## 6. What was skipped and why

| Skipped | Reason |
|---|---|
| 21st.dev-native components (7 pages above) | Real implementation loads client-side via JS the fetch tooling used couldn't execute; nothing copied, so nothing vendored. A JS-rendering fetch (browser pane) would be required to revisit. |
| Re-searching uiverse.io beyond the 14 crawled elements | The 41-file set already covers every visual role in J's reference image; no gap justified more crawling. |
| A literal live Sankey/multi-stage flow-ribbon component | None found on monet.design, uiverse.io, or 21st.dev matching J's 5-stage design exactly. `flow-workflow-routing-map.html` is therefore self-authored using the standard d3-sankey-style ribbon math (§4a) rather than ported — flagged, not hidden. |
| File literally named `INDEX.md` | Repo write-guard hard-blocks any file named `INDEX.md` anywhere (reserved for `obsidian_vault_sync.py`'s generated indexes). `VENDOR-INDEX.md` serves the same purpose. |
| Wiring these recipes into `gamma_cockpit_ui.py` | Out of this task's scope fence (writes restricted to `setup/scripts/vendor/ui-kit/` and `analysis/deep-research/`); this document is the recipe library, not the integration. |
| Resolving the CSS+JS byte-budget conflict (§1) | Same scope fence — flagged for the integration step, not resolved here. |
| Real cost-pulse data source | No single confirmed on-disk file for live Anthropic API spend was found this session (CLAUDE.md §5 states the discipline, not a data file); the recipe's `$48,320` figure is a placeholder from the source component, not real telemetry — integrator must wire real spend before shipping. |

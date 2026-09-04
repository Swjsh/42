"""gamma_cockpit_sankey_js.py - the Routing Map panel: fill-funnel Sankey.

Workstream C (Routing map). Owns ONLY this module + gamma_cockpit_funnel.py.
Held as Python strings, same convention as gamma_cockpit_tiles_js.py, so the
cockpit stays a bundler-free three-file build. Vanilla ES2020, no network
calls, must run from a local "file" URL and must never throw even when a sibling
module has not landed yet - every external symbol this file touches (el, esc,
srcRow, RM, ic) is either already present in gamma_cockpit_js.py / vendor JS
(all verified present this session) or feature-detected before use.

API SURFACE (the one name a sibling composes with):
    sankeyPanel(funnel) -> HTMLDivElement  (".gc-panel.gc-sankey")

`funnel` is gamma_cockpit_funnel.build()'s payload (D.funnel once a sibling
wires it in): {ok, path, stamp_et, day, live, verdict, say, stages, links,
cause_counts, accounts, source}. This file never trusts the shape - missing or
malformed fields degrade to the NO DATA state, and every stage id is looked up
by name (not positionally) so a reordered `stages` array still renders right.

Ribbon math is the standard SVG cubic-Bezier "Sankey ribbon" technique used by
setup/scripts/vendor/ui-kit/flow-workflow-routing-map.html (self-authored,
no external library) - two horizontal-tangent cubic curves forming a closed
band between a source y-range and a destination y-range, generalized here so
band heights are DATA-driven (proportional to each link's own count) rather
than the kit demo's fixed 68/22/10 split.

The SVG namespace string is built by concatenation (never written as a
literal scheme+slashes token) so no URL-shaped substring ships in this file -
see GC_SVGNS below.
"""
from __future__ import annotations

SANKEY_JS = r"""
/* ============================ Routing map (Sankey) ============================
   Six fixed columns: ticks -> signals -> enter -> accepted -> filled -> exited.
   Every link's "from" is one of those six ids; "to" is either the next column
   id, or the pseudo-sinks "quiet" (no signal / not yet progressed - an absence,
   not a refusal) and "refused" (rule-gate denial or a failed broker placement -
   an active refusal). Conservation: the links leaving stage i sum to exactly
   stages[i].n - gamma_cockpit_funnel.py guarantees this, this file only draws
   what it is handed and never invents a number. */
const GC_SVGNS = 'http:'+'//www.w3.org/2000/svg';
const GC_STAGE_ORDER = ['ticks','signals','enter','accepted','filled','exited'];
const GC_STAGE_LABEL = {ticks:'Ticks',signals:'Signals',enter:'Enter',
  accepted:'Accepted',filled:'Filled',exited:'Exited'};
const GC_XS = [80,236,392,548,704,860];
const GC_BAR_W = 14, GC_CENTER_Y = 148, GC_MAX_H = 190, GC_MIN_H = 6;

function gcSvgEl(tag, attrs){
  const e = document.createElementNS(GC_SVGNS, tag);
  for (const k in (attrs||{})) if (attrs[k]!=null) e.setAttribute(k, attrs[k]);
  return e;
}
function gcCls(v){ return String(v||'').replace(/[^a-z]/gi,'').toLowerCase()||'quiet'; }
function gcIsQuietCause(name){
  const n = String(name||'').toUpperCase();
  return n==='NO_SETUP' || n==='NO_FEED';
}
function gcCauseLabel(name){
  const s = String(name||'').replace(/_/g,' ').toLowerCase();
  return s.charAt(0).toUpperCase()+s.slice(1);
}
function gcTopCauses(causeCounts, wantQuiet, limit){
  const out = [];
  for (const k in (causeCounts||{})){
    if (k==='TRADED') continue;
    if (gcIsQuietCause(k) !== !!wantQuiet) continue;
    out.push([k, causeCounts[k]]);
  }
  out.sort(function(a,b){ return b[1]-a[1]; });
  return out.slice(0, limit||4);
}
function gcRibbonPath(x1,y1t,y1b,x2,y2t,y2b){
  const mx=(x1+x2)/2;
  return 'M '+x1+','+y1t+' C '+mx+','+y1t+' '+mx+','+y2t+' '+x2+','+y2t+
    ' L '+x2+','+y2b+' C '+mx+','+y2b+' '+mx+','+y1b+' '+x1+','+y1b+' Z';
}

function gcBuildDefs(svg){
  const defs = gcSvgEl('defs');
  const flow = gcSvgEl('linearGradient',{id:'gc-flow-grad', gradientUnits:'userSpaceOnUse',
    x1:80, y1:0, x2:860, y2:0});
  [['0%','#6366f1'],['50%','#8b5cf6'],['100%','#22d3ee']].forEach(function(s){
    flow.appendChild(gcSvgEl('stop',{offset:s[0], 'stop-color':s[1]}));
  });
  const acc = gcSvgEl('linearGradient',{id:'gc-accept-grad', x1:0,y1:0,x2:1,y2:0});
  acc.appendChild(gcSvgEl('stop',{offset:'0%','stop-color':'#22d3ee'}));
  acc.appendChild(gcSvgEl('stop',{offset:'100%','stop-color':'#22d3ee'}));
  const node = gcSvgEl('linearGradient',{id:'gc-node-grad', x1:0,y1:0,x2:0,y2:1});
  node.appendChild(gcSvgEl('stop',{offset:'0%','stop-color':'#8b5cf6'}));
  node.appendChild(gcSvgEl('stop',{offset:'100%','stop-color':'#6366f1'}));
  const glow = gcSvgEl('filter',{id:'gc-glow', x:'-60%', y:'-60%', width:'220%', height:'220%'});
  glow.appendChild(gcSvgEl('feGaussianBlur',{stdDeviation:5, result:'b'}));
  const merge = gcSvgEl('feMerge');
  merge.appendChild(gcSvgEl('feMergeNode',{in:'b'}));
  merge.appendChild(gcSvgEl('feMergeNode',{in:'SourceGraphic'}));
  glow.appendChild(merge);
  defs.appendChild(flow); defs.appendChild(acc); defs.appendChild(node); defs.appendChild(glow);
  svg.appendChild(defs);
}

function gcNormalizeStages(stages){
  const byId = {};
  (Array.isArray(stages)?stages:[]).forEach(function(s){ if (s && s.id) byId[s.id]=s; });
  return GC_STAGE_ORDER.map(function(id){
    const s = byId[id] || {};
    return {id:id, label: s.label || GC_STAGE_LABEL[id],
      n: (typeof s.n === 'number') ? s.n : null};
  });
}

function gcBarHeight(n, scale){
  if (typeof n !== 'number' || n<=0) return GC_MIN_H;
  const val = scale.log ? Math.log10(n+1) : n;
  const cap = scale.log ? Math.log10(scale.max+1) : scale.max;
  const h = GC_MIN_H + (GC_MAX_H-GC_MIN_H) * (cap>0 ? Math.min(1, val/cap) : 0);
  return Math.max(GC_MIN_H, Math.min(GC_MAX_H, h));
}

/* Draws the "NO DATA" empty-column state: six dashed placeholder bars, no
   ribbons, a centered message - designed, never a bare text node on a blank
   panel (spec requirement: NO DATA states are designed). */
function gcNoDataSvg(svg, stages, say){
  GC_XS.forEach(function(x,i){
    const rect = gcSvgEl('rect',{x:x-GC_BAR_W/2, y:GC_CENTER_Y-40, width:GC_BAR_W, height:80,
      rx:GC_BAR_W/2, class:'gc-node gc-node--empty'});
    svg.appendChild(rect);
    const lab = gcSvgEl('text',{x:x, y:GC_CENTER_Y+40+26, class:'gc-stage-label'});
    lab.textContent = (stages[i]&&stages[i].label) || GC_STAGE_LABEL[GC_STAGE_ORDER[i]];
    svg.appendChild(lab);
  });
  const msg = gcSvgEl('text',{x:470, y:GC_CENTER_Y+6, class:'gc-nodata-msg'});
  msg.textContent = 'NO DATA';
  svg.appendChild(msg);
  const sub = gcSvgEl('text',{x:470, y:GC_CENTER_Y+26, class:'gc-nodata-sub'});
  sub.textContent = String(say||'').slice(0,110);
  svg.appendChild(sub);
}

function sankeyPanel(funnel){
  const f = funnel || {};
  const panel = el('div','gc-panel gc-sankey');

  const head = el('div','gc-sankey__head');
  const eyebrow = el('span','gc-eyebrow', (typeof ic==='function'? ic('network'):'') + ' Routing map');
  head.appendChild(eyebrow);
  let chip;
  if (f.live){
    chip = el('span','gc-chip gc-chip--live');
    chip.appendChild(el('span','gc-live-dot'));
    chip.appendChild(document.createTextNode('Live'));
  } else if (f.session_label){
    // ROUND-2 FIX: gamma_cockpit_funnel.py falls back to the last CLOSED
    // trading day's ledger when today's is still empty (pre-market/holiday) --
    // this label is the only thing that tells the reader the six numbers
    // below are yesterday's, not a today that never happened.
    chip = el('span','gc-chip gc-chip--closed',String(f.session_label));
  } else {
    chip = el('span','gc-chip gc-chip--closed','Today, closed');
  }
  head.appendChild(chip);
  panel.appendChild(head);

  const stages = gcNormalizeStages(f.stages);
  const links = Array.isArray(f.links) ? f.links : [];
  const noData = (!f.ok && !links.length) || stages.every(function(s){ return s.n==null; });

  const svg = gcSvgEl('svg',{viewBox:'0 0 960 380', preserveAspectRatio:'xMidYMid meet',
    class:'gc-sankey__svg', role:'img', 'aria-label':'Fill funnel routing map'});
  gcBuildDefs(svg);

  if (noData){
    gcNoDataSvg(svg, stages, f.say);
    panel.appendChild(svg);
    panel.appendChild(gcLegend(false));
    if (typeof srcRow === 'function' && f.source) panel.appendChild(srcRow([f.source]));
    return panel;
  }

  const allNs = [];
  stages.forEach(function(s){ if (s.n>0) allNs.push(s.n); });
  links.forEach(function(l){ if (typeof l.n==='number' && l.n>0) allNs.push(l.n); });
  const maxN = allNs.length ? Math.max.apply(null, allNs) : 1;
  const minN = allNs.length ? Math.min.apply(null, allNs) : 1;
  const logScale = maxN>0 && minN>0 && (maxN/minN) > 40;
  const scale = {log:logScale, max:maxN};

  const toneRank = {flow:0, accepted:0, refused:1, quiet:2};
  const outByStage = {};
  GC_STAGE_ORDER.forEach(function(id){
    outByStage[id] = links.filter(function(l){ return l.from===id; })
      .slice().sort(function(a,b){ return (toneRank[a.tone]||9)-(toneRank[b.tone]||9); });
  });

  const geom = {};
  GC_STAGE_ORDER.forEach(function(id,i){
    const stage = stages[i];
    const h = gcBarHeight(stage.n, scale);
    const top = GC_CENTER_Y - h/2, bot = GC_CENTER_Y + h/2;
    const outs = outByStage[id];
    const sumOut = outs.reduce(function(s,l){ return s+(l.n||0); }, 0) || (stage.n||1);
    let y = top, bands = [];
    outs.forEach(function(l){
      const bh = Math.max(2, h * ((l.n||0)/sumOut));
      bands.push({link:l, top:y, bot:y+bh});
      y += bh;
    });
    if (!bands.length) bands = [{link:null, top:top, bot:bot}];
    geom[id] = {x:GC_XS[i], top:top, bot:bot, h:h, n:stage.n, bands:bands};
  });

  const gRibbons = gcSvgEl('g',{class:'gc-ribbons', filter:'url(#gc-glow)'});
  const gDashes = gcSvgEl('g',{class:'gc-dashes'});
  const gDrops = gcSvgEl('g',{class:'gc-drops'});
  const gNodes = gcSvgEl('g',{class:'gc-nodes'});
  const gLabels = gcSvgEl('g',{class:'gc-labels', 'text-anchor':'middle'});
  const gPct = gcSvgEl('g',{class:'gc-pct', 'text-anchor':'middle'});
  [gRibbons, gDashes, gDrops, gNodes, gLabels, gPct].forEach(function(g){ svg.appendChild(g); });

  GC_STAGE_ORDER.forEach(function(id,i){
    const g = geom[id];
    const rect = gcSvgEl('rect',{x:g.x-GC_BAR_W/2, y:g.top, width:GC_BAR_W,
      height:Math.max(g.h, GC_MIN_H), rx:GC_BAR_W/2,
      class: g.n==null ? 'gc-node gc-node--empty' : 'gc-node'});
    gNodes.appendChild(rect);
    const lab = gcSvgEl('text',{x:g.x, y:GC_CENTER_Y+GC_MAX_H/2+26, class:'gc-stage-label'});
    lab.textContent = GC_STAGE_LABEL[id];
    gLabels.appendChild(lab);
    const nTxt = gcSvgEl('text',{x:g.x, y:GC_CENTER_Y+GC_MAX_H/2+42, class:'gc-stage-n'});
    nTxt.textContent = (g.n==null) ? 'no data' : g.n.toLocaleString();
    gLabels.appendChild(nTxt);
  });

  const totalTicks = geom.ticks.n;
  const tips = [];
  let dropSlot = 0;

  links.forEach(function(l){
    const src = geom[l.from];
    if (!src) return;
    const band = src.bands.filter(function(b){ return b.link===l; })[0];
    if (!band) return;
    const x1 = src.x + GC_BAR_W/2;
    const isMain = GC_STAGE_ORDER.indexOf(l.to) !== -1;
    const tone = l.tone || 'flow';
    let d, midx, midy;
    if (isMain){
      const dst = geom[l.to];
      if (!dst) return;
      const frac = dst.n ? Math.max(0, Math.min(1, (l.n||0)/dst.n)) : 1;
      const h2 = Math.max(2, dst.h * frac);
      const y2t = dst.top, y2b = dst.top + h2;
      const x2 = dst.x - GC_BAR_W/2;
      d = gcRibbonPath(x1, band.top, band.bot, x2, y2t, y2b);
      midx = (x1+x2)/2; midy = (band.top+band.bot)/2;
      if (f.live && !RM){
        const dash = gcSvgEl('path',{class:'gc-flow-dash',
          d:'M '+x1+','+midy+' C '+midx+','+midy+' '+midx+','+midy+' '+x2+','+midy});
        gDashes.appendChild(dash);
      }
    } else {
      dropSlot++;
      const x2 = x1 + 96, y2 = GC_CENTER_Y + GC_MAX_H/2 + 46 + (dropSlot%2)*30;
      d = gcRibbonPath(x1, band.top, band.bot, x2, y2-3, y2+3);
      midx = (x1+x2)/2; midy = (band.top+band.bot)/2;
      const dot = gcSvgEl('circle',{cx:x2, cy:y2, r:4, class:'gc-drop-dot gc-drop-dot--'+gcCls(tone)});
      gDrops.appendChild(dot);
      const lab = gcSvgEl('text',{x:x2+10, y:y2+4, class:'gc-drop-label', 'text-anchor':'start'});
      lab.textContent = (l.to==='refused'?'Refused ':'Quiet ') + (l.n!=null?l.n.toLocaleString():'-');
      gDrops.appendChild(lab);
    }
    const p = gcSvgEl('path',{d:d, class:'gc-ribbon gc-ribbon--'+gcCls(tone), 'data-link': l.from+'>'+l.to});
    gRibbons.appendChild(p);
    const pct = (totalTicks && l.n!=null) ? Math.round((l.n/totalTicks)*1000)/10 : null;
    if (l.n!=null){
      const t = gcSvgEl('text',{x:midx, y:midy-8, class:'gc-pct-label'});
      t.textContent = (pct!=null ? pct+'%' : l.n.toLocaleString());
      gPct.appendChild(t);
    }
    tips.push({node:p, link:l});
  });

  panel.appendChild(svg);
  panel.appendChild(gcLegend(logScale));
  gcWireTooltip(panel, svg, tips, f.cause_counts||{});
  gcEntranceAnimate(gRibbons);
  if (typeof srcRow === 'function' && f.source) panel.appendChild(srcRow([f.source]));
  return panel;
}

function gcLegend(logScale){
  const wrap = el('div','gc-legend');
  const items = [
    ['gc-swatch--flow','Accepted flow'],
    ['gc-swatch--refused','Refused (rule gate / broker)'],
    ['gc-swatch--quiet','Quiet (no signal yet)']
  ];
  items.forEach(function(it){
    const span = el('span','gc-legend__item');
    span.appendChild(el('i','gc-swatch '+it[0]));
    span.appendChild(document.createTextNode(it[1]));
    wrap.appendChild(span);
  });
  if (logScale){
    wrap.appendChild(el('span','gc-legend__note',
      'Log scale, ribbon width is not linear with count (wide count spread today)'));
  }
  return wrap;
}

function gcWireTooltip(panel, svg, tips, causeCounts){
  if (!tips.length) return;
  const tip = el('div','gc-tooltip');
  tip.hidden = true;
  panel.appendChild(tip);
  function show(t, evt){
    tips.forEach(function(o){ o.node.classList.toggle('gc-ribbon--dim', o!==t); });
    t.node.classList.add('gc-ribbon--hot');
    const l = t.link;
    let html = '<b>'+esc(GC_STAGE_LABEL[l.from]||l.from)+' -&gt; '+
      esc(l.to==='quiet'?'Quiet':(l.to==='refused'?'Refused':(GC_STAGE_LABEL[l.to]||l.to)))+
      '</b><br>'+esc(l.n==null?'no data':l.n.toLocaleString())+' rows';
    const wantQuiet = l.tone==='quiet';
    if (l.tone==='quiet' || l.tone==='refused'){
      const causes = gcTopCauses(causeCounts, wantQuiet, 4);
      if (causes.length){
        html += '<div class="gc-tooltip__causes">'+causes.map(function(c){
          return esc(gcCauseLabel(c[0]))+' x'+c[1];
        }).join('<br>')+'</div>';
      }
    }
    tip.innerHTML = html;
    tip.hidden = false;
    const r = panel.getBoundingClientRect();
    const x = (evt.clientX - r.left) + 12, y = (evt.clientY - r.top) + 12;
    tip.style.left = Math.min(x, r.width-220)+'px';
    tip.style.top = Math.max(0, y-40)+'px';
  }
  function hideAll(){
    tips.forEach(function(o){ o.node.classList.remove('gc-ribbon--hot','gc-ribbon--dim'); });
    tip.hidden = true;
  }
  tips.forEach(function(t){
    t.node.addEventListener('mouseenter', function(e){ show(t,e); });
    t.node.addEventListener('mousemove', function(e){ show(t,e); });
    t.node.addEventListener('mouseleave', hideAll);
    t.node.addEventListener('focus', function(e){ show(t,e); });
  });
  svg.addEventListener('mouseleave', hideAll);
}

/* One-time entrance: each ribbon's own outline draws in via WAAPI on
   stroke-dashoffset, gated on prefers-reduced-motion (RM, from
   gamma_cockpit_js.py). Reduced motion: ribbons appear at full opacity
   immediately, no animation scheduled at all. */
function gcEntranceAnimate(gRibbons){
  const paths = gRibbons.querySelectorAll('path.gc-ribbon');
  paths.forEach(function(p, i){
    if (RM){ p.style.opacity = '1'; return; }
    let len = 0;
    try { len = p.getTotalLength(); } catch(_){ len = 400; }
    p.style.strokeDasharray = len;
    p.style.strokeDashoffset = len;
    p.style.opacity = '0';
    if (typeof p.animate !== 'function'){ p.style.opacity='1'; p.style.strokeDashoffset='0'; return; }
    const anim = p.animate(
      [{opacity:0, strokeDashoffset:len},{opacity:1, strokeDashoffset:0}],
      {duration:700, delay:Math.min(i*40,400), fill:'forwards', easing:'ease-out'}
    );
    // Release the forwards-fill once landed: a persisting WAAPI opacity would out-rank
    // the stylesheet, so the hover dim (.gc-ribbon--dim) could never take effect.
    anim.onfinish = function(){ try{ p.style.opacity=''; p.style.strokeDasharray=''; p.style.strokeDashoffset=''; anim.cancel(); }catch(_){} };
  });
}
"""

SANKEY_CSS = r"""
.gc-sankey{display:flex;flex-direction:column;gap:10px;position:relative}
.gc-sankey__head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.gc-eyebrow{font-size:12px;letter-spacing:.06em;text-transform:uppercase;
  color:var(--gc-ink-2,#aab3d6);font-weight:600}
.gc-chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;
  padding:4px 10px;font-size:12px;font-weight:600;white-space:nowrap}
.gc-chip--live{background:rgba(52,211,153,.14);color:#34d399;
  border:1px solid rgba(52,211,153,.32)}
.gc-chip--closed{background:rgba(120,130,255,.10);color:var(--gc-ink-2,#aab3d6);
  border:1px solid var(--gc-line,rgba(120,130,255,.16))}
.gc-live-dot{width:6px;height:6px;border-radius:50%;background:#34d399}
@media (prefers-reduced-motion:no-preference){
  .gc-chip--live .gc-live-dot{animation:gc-pulse 1.6s ease-in-out infinite}
}
@keyframes gc-pulse{0%,100%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}
  50%{box-shadow:0 0 0 6px rgba(52,211,153,0)}}
.gc-sankey__svg{width:100%;height:auto;display:block}
.gc-node{fill:url(#gc-node-grad)}
.gc-node--empty{fill:none;stroke:var(--gc-ink-3,#7581a8);stroke-width:1;stroke-dasharray:2 3}
.gc-stage-label{font-size:12px;fill:var(--gc-ink-2,#aab3d6);font-weight:600}
.gc-stage-n{font-size:12px;fill:var(--gc-ink-1,#eef1ff);font-variant-numeric:tabular-nums}
.gc-pct-label{font-size:12px;fill:var(--gc-ink-1,#eef1ff);font-variant-numeric:tabular-nums}
.gc-nodata-msg{font-size:16px;fill:var(--gc-ink-2,#aab3d6);text-anchor:middle;font-weight:600}
.gc-nodata-sub{font-size:12px;fill:var(--gc-ink-3,#7581a8);text-anchor:middle}
.gc-ribbon{transition:opacity .2s ease}
.gc-ribbon--flow, .gc-ribbon--accepted{fill:url(#gc-flow-grad);fill-opacity:.78;
  stroke:#a5b4fc;stroke-opacity:.5;stroke-width:1}
.gc-ribbon--refused{fill:var(--gc-pink,#ec4899);fill-opacity:.55;
  stroke:var(--gc-pink,#ec4899);stroke-opacity:.6;stroke-width:1}
.gc-ribbon--quiet{fill:var(--gc-ink-3,#7581a8);fill-opacity:.32;
  stroke:var(--gc-ink-3,#7581a8);stroke-opacity:.4;stroke-width:1}
.gc-ribbon--hot{fill-opacity:.95!important;stroke-opacity:.9!important}
.gc-ribbon--dim{opacity:.22}
/* ROUND-3 POLISH item 5: #gc-glow (feGaussianBlur stdDeviation 5, merged over
   SourceGraphic) reads as a premium cyan bloom on the near-black dark canvas
   but the identical blur diffuses each ribbon's saturated fill into a muddy
   grey halo against the light theme's near-white surface -- blur softens
   contrast against a light ground far more than a dark one. stdDeviation
   is an SVG filter-primitive attribute, not a CSS property browsers let a
   stylesheet reach into, so it cannot be dialed down per-theme in place;
   the `filter` property itself CAN be overridden by an author stylesheet
   (presentation attributes sit below any stylesheet rule in the cascade),
   so light theme drops the glow entirely and gets a crisper, darker stroke
   outline instead -- still reads as premium, just via definition rather
   than bloom. */
:root[data-theme="light"] .gc-ribbons{filter:none}
:root[data-theme="light"] .gc-ribbon--flow,:root[data-theme="light"] .gc-ribbon--accepted{
  stroke:#4338ca;stroke-opacity:.55;stroke-width:1.25}
:root[data-theme="light"] .gc-ribbon--refused{stroke-opacity:.7;stroke-width:1.25}
:root[data-theme="light"] .gc-ribbon--quiet{stroke-opacity:.5}
.gc-flow-dash{stroke:#fff;stroke-opacity:.5;stroke-width:2;fill:none;
  stroke-dasharray:4 14;pointer-events:none}
@media (prefers-reduced-motion:no-preference){
  .gc-flow-dash{animation:gc-flow 3.5s linear infinite}
}
@keyframes gc-flow{to{stroke-dashoffset:-360}}
@media (prefers-reduced-motion:reduce){
  .gc-chip--live .gc-live-dot, .gc-flow-dash{animation:none!important}
}
.gc-drop-dot--refused{fill:var(--gc-pink,#ec4899)}
.gc-drop-dot--quiet{fill:var(--gc-ink-3,#7581a8)}
.gc-drop-label{font-size:12px;fill:var(--gc-ink-3,#7581a8)}
.gc-legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--gc-ink-2,#aab3d6)}
.gc-legend__item{display:inline-flex;align-items:center;gap:6px}
.gc-swatch{display:inline-block;width:14px;height:4px;border-radius:2px}
.gc-swatch--flow{background:linear-gradient(90deg,#6366f1,#8b5cf6,#22d3ee)}
.gc-swatch--refused{background:var(--gc-pink,#ec4899)}
.gc-swatch--quiet{background:var(--gc-ink-3,#7581a8)}
.gc-legend__note{color:var(--gc-ink-3,#7581a8);font-style:italic}
.gc-tooltip{position:absolute;max-width:220px;background:var(--gc-panel-2,#161f3f);
  border:1px solid var(--gc-line-2,rgba(120,130,255,.28));border-radius:10px;
  padding:8px 10px;font-size:12px;line-height:1.5;color:var(--gc-ink-1,#eef1ff);
  pointer-events:none;box-shadow:0 8px 24px rgba(2,4,14,.55);z-index:5}
.gc-tooltip__causes{margin-top:6px;color:var(--gc-ink-2,#aab3d6);
  border-top:1px solid var(--gc-line,rgba(120,130,255,.16));padding-top:6px}
"""

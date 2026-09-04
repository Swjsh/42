"""gamma_cockpit_costpulse_js.py -- Cost pulse KPI panel client code (WS-D, 2026-09-04).

Exports COSTPULSE_JS (function costPulsePanel(cp, budget)) and COSTPULSE_CSS.
Renders off gamma_cockpit_costpulse.build() (`cp`) and `autonomy.budget` (`budget`)
-- never computes a number itself, only lays out numbers it was handed.

Chart recipe ported from vendor/ui-kit/chart-cost-pulse-area.html (gradient-fill
area + blurred-duplicate-path glow line + hover dot/tooltip), re-authored against
this cockpit's own CSS tokens (--bg-1/--tx-1/--bd/--pos/--neg/... from
gamma_cockpit_ui_theme.py) instead of the kit's own hardcoded demo palette, so the
panel stays theme-aware in both light and dark without depending on whichever
--uk-* vendor variables another workstream's module may or may not expose globally.

DEFENSIVE BY CONSTRUCTION (this ships in parallel with 9 other builders):
  * Only `el`/`esc`/`srcRow`/`RM`/`ic` are assumed to already exist as globals;
    every one is feature-detected with a local fallback so a load-order gap
    between sibling modules never throws (cp*-prefixed helpers below, kept
    distinct from every cmd*/tiles* helper already in the app).
  * A falsy `cp`, `cp.ok===false`, or an empty `cp.days` all render the SAME
    designed NO-DATA chart shell (axes drawn, no area, a message naming the
    file that was looked for) -- never a fabricated series.
  * `budget` missing or partial (no `spent_usd`) falls back to the 14-day
    total from `cp`, labelled "14d total" rather than silently mislabeling it
    as the daily budget spend.
"""
from __future__ import annotations

COSTPULSE_JS = r"""
/* ============================ Cost pulse panel (WS-D) ============================ */
function cpSafe(fn,fallback){ try{ return fn(); }catch(_){ return fallback; } }
function cpEl(t,c,h){
  if(typeof el==='function') return el(t,c,h);
  const e=document.createElement(t); if(c)e.className=c; if(h!==undefined)e.innerHTML=h; return e;
}
function cpEsc(s){
  if(typeof esc==='function') return esc(s);
  return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function cpUsd(v){
  if(v==null||isNaN(v))return'NO DATA';
  return'$'+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
function cpRM(){
  if(typeof RM!=='undefined')return RM;
  return cpSafe(()=>matchMedia('(prefers-reduced-motion:reduce)').matches,false);
}
function cpIc(name){
  return cpSafe(()=>(typeof ic==='function')?ic(name):'','');
}
function cpSrcRow(list){
  if(typeof srcRow==='function')return srcRow(list);
  const d=cpEl('div','src');
  (list||[]).forEach(s=>{ d.appendChild(cpEl('span',null,cpEsc((s&&s.path)||''))); });
  return d;
}

/* function costPulsePanel(cp, budget) -> HTMLElement
   cp     = gamma_cockpit_costpulse.build() payload (falsy/ok:false = no data)
   budget = autonomy.budget, may be undefined/partial */
function costPulsePanel(cp, budget){
  const panel=cpEl('div','gc-panel gc-costpulse');
  panel.appendChild(cpEl('p','gc-eyebrow',cpIc('activity')+' Cost pulse'));

  const bud=budget||{};
  const days=(cp&&Array.isArray(cp.days))?cp.days:[];
  const haveBudget=(bud.spent_usd!=null && !isNaN(bud.spent_usd));
  const totalUsd=(cp&&cp.total_usd!=null)?cp.total_usd:null;
  const bigVal=haveBudget?bud.spent_usd:totalUsd;
  const capVal=(haveBudget&&bud.cap_usd!=null)?bud.cap_usd:null;
  const over=(capVal!=null&&bigVal!=null&&!isNaN(bigVal)&&Number(bigVal)>Number(capVal));

  const bigRow=cpEl('p','gc-big num'+(over?' over':''),cpUsd(bigVal));
  if(capVal!=null) bigRow.appendChild(cpEl('span','gc-cap num',' / '+cpUsd(capVal)+' cap'));
  else if(!haveBudget) bigRow.appendChild(cpEl('span','gc-cap','14d total'));
  panel.appendChild(bigRow);

  if(capVal!=null && bigVal!=null && !isNaN(bigVal) && !isNaN(capVal) && Number(capVal)!==0){
    const diff=Number(bigVal)-Number(capVal);
    const pct=diff/Number(capVal)*100;
    const dir=Math.abs(pct)<1?'flat':(diff>0?'up':'down');
    const arrow=dir==='flat'?'~':(dir==='up'?'↑':'↓');
    panel.appendChild(cpEl('span','gc-delta '+dir,arrow+' '+Math.abs(pct).toFixed(1)+'% vs cap'));
  }

  const wrap=cpEl('div','gc-chart-wrap');
  const W=480,H=160,PAD=8;
  const ok=!!(cp&&cp.ok!==false&&days.length);

  if(!ok){
    wrap.innerHTML=
      '<svg class="gc-area-svg" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+
        '<line class="gc-baseline" x1="0" y1="'+(H-PAD)+'" x2="'+W+'" y2="'+(H-PAD)+'"></line>'+
        '<line class="gc-axis-y" x1="'+PAD+'" y1="0" x2="'+PAD+'" y2="'+(H-PAD)+'"></line>'+
      '</svg>';
    const say=(cp&&cp.say)?cp.say:'NO DATA, looked for automation/state/conductor-outcomes.jsonl';
    wrap.appendChild(cpEl('div','gc-nodata',cpEsc(say)));
    panel.appendChild(wrap);
    panel.appendChild(cpSrcRow([(cp&&cp.source)||{path:(cp&&cp.path)||'automation/state/conductor-outcomes.jsonl'}]));
    return panel;
  }

  const vals=days.map(d=>Number(d.cost_usd)||0);
  const maxV=Math.max.apply(null,vals.concat([1]));
  const n=days.length;
  const stepX=n>1?(W-2*PAD)/(n-1):0;
  const pts=days.map((d,i)=>({
    x:PAD+i*stepX,
    y:(H-PAD)-((Number(d.cost_usd)||0)/maxV)*(H-2*PAD),
    d:d,
  }));

  let line='M '+pts[0].x.toFixed(1)+','+pts[0].y.toFixed(1);
  for(let i=1;i<pts.length;i++){
    const cx=(pts[i-1].x+pts[i].x)/2;
    line+=' C '+cx.toFixed(1)+','+pts[i-1].y.toFixed(1)+' '+cx.toFixed(1)+','+pts[i].y.toFixed(1)+' '+pts[i].x.toFixed(1)+','+pts[i].y.toFixed(1);
  }
  const area=line+' L '+pts[n-1].x.toFixed(1)+','+(H-PAD)+' L '+pts[0].x.toFixed(1)+','+(H-PAD)+' Z';
  const last=pts[n-1];
  const gid='gc-area-grad';

  wrap.innerHTML=
    '<svg class="gc-area-svg" viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none">'+
      '<defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1">'+
        '<stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.38"></stop>'+
        '<stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"></stop>'+
      '</linearGradient></defs>'+
      '<line class="gc-baseline" x1="0" y1="'+(H-PAD)+'" x2="'+W+'" y2="'+(H-PAD)+'"></line>'+
      '<path class="gc-area-fill" fill="url(#'+gid+')" stroke="none" d="'+area+'"></path>'+
      '<path class="gc-area-line-glow" fill="none" d="'+line+'"></path>'+
      '<path class="gc-area-line" fill="none" d="'+line+'"></path>'+
      '<circle class="gc-hover-dot" r="8" cx="'+last.x.toFixed(1)+'" cy="'+last.y.toFixed(1)+'"></circle>'+
      '<circle class="gc-hover-core" r="3.5" cx="'+last.x.toFixed(1)+'" cy="'+last.y.toFixed(1)+'"></circle>'+
      '<rect class="gc-hit-area" x="0" y="0" width="'+W+'" height="'+H+'"></rect>'+
    '</svg>';
  panel.appendChild(wrap);

  const axis=cpEl('div','gc-x-axis');
  days.forEach((d,i)=>{
    if(i%2!==0 && i!==n-1) return;
    axis.appendChild(cpEl('span','gc-x-label num',cpEsc(String(d.day||'').slice(5))));
  });
  wrap.appendChild(axis);

  const tip=cpEl('div','gc-tooltip');
  wrap.appendChild(tip);

  const svg=wrap.querySelector('.gc-area-svg');
  const dot=svg.querySelector('.gc-hover-dot'), core=svg.querySelector('.gc-hover-core');
  const hit=svg.querySelector('.gc-hit-area');
  hit.addEventListener('pointermove', function(e){
    const rect=svg.getBoundingClientRect();
    const relX=(e.clientX-rect.left)/rect.width*W;
    let i=Math.round((relX-PAD)/(stepX||1));
    i=Math.max(0,Math.min(n-1,i));
    const p=pts[i];
    dot.setAttribute('cx',p.x); dot.setAttribute('cy',p.y);
    core.setAttribute('cx',p.x); core.setAttribute('cy',p.y);
    tip.style.left=(p.x/W*rect.width)+'px';
    tip.style.top=(p.y/H*rect.height-40)+'px';
    tip.textContent=(p.d.day||'')+', '+cpUsd(p.d.cost_usd)+', '+(p.d.fires||0)+' fires';
    tip.classList.add('show');
  });
  hit.addEventListener('pointerleave', function(){ tip.classList.remove('show'); });

  if(!cpRM()){
    const fillPath=svg.querySelector('.gc-area-fill');
    if(typeof fillPath.animate==='function')
      fillPath.animate([{opacity:0},{opacity:1}],{duration:700,easing:'ease-out',fill:'forwards'});
    const linePath=svg.querySelector('.gc-area-line');
    const len=cpSafe(()=>linePath.getTotalLength(),0);
    if(len && typeof linePath.animate==='function'){
      linePath.style.strokeDasharray=String(len);
      linePath.style.strokeDashoffset=String(len);
      linePath.animate([{strokeDashoffset:len},{strokeDashoffset:0}],{duration:900,easing:'ease-out',fill:'forwards'});
    }
  }

  panel.appendChild(cpSrcRow([(cp&&cp.source)||{path:(cp&&cp.path)||'automation/state/conductor-outcomes.jsonl'}]));
  return panel;
}
"""

COSTPULSE_CSS = r"""
.gc-panel.gc-costpulse{background:var(--bg-1);border:1px solid var(--bd);border-radius:var(--r-lg);
  padding:var(--sp-4);font-family:var(--font);color:var(--tx-1);position:relative;
  display:flex;flex-direction:column;gap:4px;animation:gcFadeUp .5s var(--e-open,ease-out) both}
.gc-eyebrow{margin:0;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--tx-3)}
.gc-big{margin:0;font-size:1.55rem;font-weight:700;color:var(--tx-1);line-height:1.15}
.gc-big.over{color:var(--neg)}
.gc-cap{font-size:.8rem;font-weight:500;color:var(--tx-3);margin-left:4px}
.gc-delta{display:inline-block;width:fit-content;font-size:12px;font-weight:600;
  padding:2px 8px;margin:2px 0 6px;border-radius:999px;background:var(--bg-2);color:var(--tx-2)}
.gc-chart-wrap{position:relative;margin-top:2px}
.gc-area-svg{width:100%;height:118px;display:block;overflow:visible}
.gc-baseline,.gc-axis-y{stroke:var(--bd);stroke-width:1}
.gc-area-line{stroke:#c4b5fd;stroke-width:2;stroke-linecap:round}
.gc-area-line-glow{stroke:#a78bfa;stroke-width:6;stroke-linecap:round;opacity:.35;filter:blur(4px)}
.gc-hover-dot{fill:none;stroke:#a78bfa;stroke-opacity:.4;stroke-width:6;filter:blur(3px)}
.gc-hover-core{fill:#c4b5fd}
.gc-hit-area{fill:transparent;pointer-events:all}
.gc-x-axis{display:flex;justify-content:space-between;margin-top:2px}
.gc-x-label{font-size:12px;color:var(--tx-3)}
.gc-tooltip{position:absolute;transform:translate(-50%,0);background:var(--bg-2);
  border:1px solid var(--bd);color:var(--tx-1);font-size:12px;font-weight:600;
  padding:4px 8px;border-radius:6px;pointer-events:none;opacity:0;transition:opacity .15s ease-std}
.gc-tooltip.show{opacity:1}
.gc-costpulse .gc-nodata{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  text-align:center;font-size:12px;color:var(--tx-3);padding:0 16px}
@keyframes gcFadeUp{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
@media (prefers-reduced-motion: reduce){
  .gc-costpulse{animation:none}
  .gc-costpulse *{animation:none!important;transition:none!important}
}
"""

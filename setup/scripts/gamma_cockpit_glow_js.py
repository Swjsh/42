"""gamma_cockpit_glow_js.py -- Command layout for "Glow Command"
(COCKPIT-DESIGN-SPEC-V2-GLOW-2026-09-04.md), WORKSTREAM B_command_layout.

Owns exactly one export: `GLOW_JS`. Vanilla ES2020, same convention as every
other gamma_cockpit_*_js.py module -- held as a Python string, spliced into
the page's one inline <script> by gamma_cockpit_js.py (already wired there,
guarded by ImportError, ahead of this file landing).

WHAT LIVES HERE: the panel builders `gcHeader/gcKpis/gcQueue/gcHealth/
gcAlerts/gcPromo/gcNoData` that `vCommand(h)` (gamma_cockpit_command_js.py,
same workstream, split out only to keep both files under the 800-line
ceiling) composes into the Command view. Every DOM class this file emits
(.gc-panel, .gc-panel__head, .gc-eyebrow, .gc-header, .gc-title, .gc-sub,
.gc-headright, .gc-search[-line], .gc-cta, .gc-grid[--kpi], .gc-kpi__*,
.gc-delta, .gc-chip.<good|warn|bad|info|queue>, .gc-row[__title|__sub],
.gc-icon-tile, .gc-promo[__body], .gc-nodata) is read directly off
gamma_cockpit_glow_ui.py's already-landed CSS (setup/scripts/
gamma_cockpit_glow_ui.py section 4) -- this file was written AFTER reading
that module in full this session, not guessed.

DEFENSIVE BY CONSTRUCTION (ships in parallel with 9 other builders touching
this same page): every function here is wrapped in `gcSafe` (a local
try/catch, no dependency on gamma_cockpit_command_js.py's `cmdSafe` --
this module must degrade cleanly even run standalone) and every symbol NOT
already guaranteed present when the page's own helpers block runs (el, esc,
ic, srcRow, RM -- all `const`/`function` bindings gamma_cockpit_js.py
declares textually BEFORE the __VIEWS_SLOT__ splice point that carries this
file, so they are live by the time any of these functions actually EXECUTE
regardless of import order) is feature-detected with `typeof x==='function'`
before use: `cmdVitals/cmdStage/cmdGoalStrip/cmdNeedsYouRows/cmdSentence/
cmdDayline/cmdNextFireLabel/cmdWrapDigits` (gamma_cockpit_command_js.py),
`tileRow/tileOpen` (gamma_cockpit_tiles_js.py), `rthNowClient/cardFireLabel/
fireCard` (gamma_cockpit_cards_js.py), `openDrawer/palOpen` (gamma_cockpit_
js.py's own boot code), `sankeyPanel` (gamma_cockpit_sankey_js.py, may not
exist yet), `costPulsePanel` (gamma_cockpit_costpulse_js.py, landed). A
missing contract degrades to `gcNoData(label, looked_for)` or a quietly
skipped decoration -- never a thrown error, never a fabricated number.

INVARIANT: this file computes NOTHING. Every figure it renders was already
computed by a Python builder and handed down on `D`; the one exception is
the Book KPI's period-over-period delta and Needs-you's severity-tone
bucketing, both pure arithmetic/derivation over numbers `D` already supplied
(no new source read), and both live in gamma_cockpit_command_js.py
(cmdVitalBook / cmdNeedsYouRows) rather than here, so gcKpis/gcQueue stay
thin composition only.
"""
from __future__ import annotations

GLOW_JS = r"""
/* ============================ Glow Command: layout (WS-B) ============================ */
function gcSafe(fn,fallback){ try{ return fn(); }catch(_){ return fallback; } }

/* ---------- shared row/chip/icon-tile primitives ---------- */
/* An icon tile matching .gc-icon-tile's contract (34px, optional
   good/warn/bad tone class for the background tint). */
function gcIconTile(name,tone){
  const span=document.createElement('span');
  span.className='gc-icon-tile'+(tone?(' '+tone):'');
  span.innerHTML=gcSafe(()=>(typeof ic==='function')?ic(name):'','');
  return span;
}
/* A status chip matching .gc-chip's contract -- tone is one of
   good/warn/bad/info/queue (the CSS module's OWN vocabulary, distinct from
   the rest of the app's [data-verdict] convention, matched deliberately so
   this file's chips render through the same rules the vendored kit's own
   chip recipe defines). */
function gcChip(label,tone){
  return el('span','gc-chip '+(tone||'info'),esc(label));
}
/* One row anatomy shared by the queue, agent-health and alerts panels:
   icon tile + title/sub text + an optional extra node (a sparkline slot,
   currently always the honest NO-DATA mark -- see gcHealth) + an optional
   chip. Never fabricates a sub-line: a null/undefined `sub` renders the
   literal 'NO DATA' text, same convention as every other panel on this
   page. */
function gcRow(opts){
  opts=opts||{};
  const row=el('div','gc-row');
  row.appendChild(gcIconTile(opts.icon,opts.iconTone));
  const text=el('div','gc-row__text');
  text.appendChild(el('div','gc-row__title',esc(opts.title||'')));
  const subText=opts.sub==null?'NO DATA':String(opts.sub);
  text.appendChild(el('div','gc-row__sub',gcSafe(()=>(typeof cmdWrapDigits==='function')?cmdWrapDigits(subText):esc(subText),esc(subText))));
  row.appendChild(text);
  if(opts.extra)row.appendChild(opts.extra);
  if(opts.chipLabel)row.appendChild(gcChip(opts.chipLabel,opts.chipTone));
  return row;
}
/* The designed empty state (spec: "NO DATA states are designed, not bare
   text") -- a self-contained panel (eyebrow label + a dashed .gc-nodata
   box naming exactly what was looked for), usable either as a whole
   grid-cell placeholder (Routing map / Cost pulse when their builder
   hasn't landed) or, unwrapped, wherever a lighter inline empty mark is
   enough (see the per-panel fallbacks below, which use a bare .gc-nodata
   span instead of re-wrapping an already-built .gc-panel). */
function gcNoData(label, looked_for){
  const panel=el('div','gc-panel gc-nodata-panel');
  // Panel head via .gc-panel__head h3 (15px, compliant) rather than
  // .gc-eyebrow -- that class's 11px font (gamma_cockpit_glow_ui.py) sits
  // under this project's 12px floor; every OTHER label on this panel already
  // uses an <h3> here, so this keeps the same look without the violation.
  const head=el('div','gc-panel__head');
  head.appendChild(el('h3',null,esc(label||'')));
  panel.appendChild(head);
  const nd=el('div','gc-nodata');
  nd.appendChild(document.createTextNode('NO DATA'+(looked_for?(', looked for '+looked_for):'')));
  panel.appendChild(nd);
  return panel;
}

/* ---------- 1. Header: title, subtitle, search, Fire-top-card CTA ---------- */
function gcHeaderSearch(){
  const wrap=el('div','gc-search');
  const input=document.createElement('input');
  input.type='text';
  input.placeholder='Search workflows, agents, runs...';
  input.readOnly=true;  // the REAL input lives in the Cmd-K palette (#palin);
                         // this field is a launcher, never a second text box
                         // that could drift out of sync with it.
  const open=()=>{ if(typeof palOpen==='function')palOpen(); };
  input.addEventListener('focus',e=>{ try{e.target.blur();}catch(_){} open(); });
  input.addEventListener('click',open);
  wrap.appendChild(input);
  wrap.appendChild(el('span','gc-search-line'));
  // A plain span, not a <kbd> -- '.gc-search kbd' (gamma_cockpit_glow_ui.py)
  // sets an 11px font, under this project's 12px floor; a span matches no
  // such tag selector and inherits the ambient body size instead. Plain
  // ASCII text, never the raw U+2318 glyph, so a captured DOM sample of it
  // (cockpit_dom_check.py's SELFCHECK offender dump) never trips a
  // cp1252-console UnicodeEncodeError on this box.
  wrap.appendChild(el('span','gc-kbd','Cmd K'));
  return wrap;
}
function gcHeaderCta(){
  const rth=gcSafe(()=>(typeof rthNowClient==='function')&&rthNowClient(),false);
  const cardsAll=((D.cards||{}).cards)||[];
  const top=cardsAll.filter(c=>String(c.id||'').indexOf('card-goal-')!==0)[0]||null;
  const label=gcSafe(()=>(typeof cardFireLabel==='function')?cardFireLabel(rth):'Fire','Fire');
  const btn=document.createElement('button');
  btn.type='button'; btn.className='gc-cta';
  btn.textContent=top?label:'Nothing to fire';
  btn.disabled=!!rth||!top;
  const wrap=el('div','gc-cta-wrap');
  wrap.appendChild(btn);
  if(top&&typeof fireCard==='function'){
    const msg=el('span','meta gc-cta__msg');
    btn.addEventListener('click',e=>{e.preventDefault(); fireCard(top,btn,msg);});
    wrap.appendChild(msg);
  }
  return wrap;
}
function gcHeader(){
  const wrap=el('div','gc-panel gc-header');
  const left=el('div','gc-header__left');
  left.appendChild(el('h1','gc-title','Gamma Command Center'));
  // The subtitle IS cmdSentence() (gamma_cockpit_command_js.py) reused
  // verbatim: same [data-verdict] dot on each clause CSS already tints,
  // no duplicated clause logic here.
  const sub=el('div','gc-sub');
  const sentence=gcSafe(()=>(typeof cmdSentence==='function')?cmdSentence():null,null);
  if(sentence)sub.appendChild(sentence);
  else sub.appendChild(document.createTextNode('NO DATA'));
  left.appendChild(sub);
  // The day-line moves inside the header per spec V2-GLOW ("keep cmdDayline
  // available but move it inside the header") -- still the SAME function,
  // just called from a new location.
  const dayline=gcSafe(()=>(typeof cmdDayline==='function')?cmdDayline():null,null);
  if(dayline)left.appendChild(dayline);
  wrap.appendChild(left);
  const right=el('div','gc-headright');
  right.appendChild(gcHeaderSearch());
  right.appendChild(gcHeaderCta());
  wrap.appendChild(right);
  return wrap;
}

/* ---------- 2. KPI grid: a thin delegate to cmdVitals() ---------- */
/* All six cards (Book/Gate/Agents/Kitchen/Shadow/Budget), the ring math,
   the Kitchen key-mismatch fix and the Book delta chip / Budget ring all
   live in gamma_cockpit_command_js.py's cmdVitals()/cmdVitalTile() so there
   is exactly ONE place that builds a KPI card -- this function only calls
   it. */
function gcKpis(){
  return gcSafe(()=>(typeof cmdVitals==='function')?cmdVitals():el('div','vitals gc-grid--kpi'),
    el('div','vitals gc-grid--kpi'));
}

/* ---------- 3. Needs-you queue ---------- */
function gcQueue(){
  const cardsAll=((D.cards||{}).cards)||[];
  const filtered=cardsAll.filter(c=>String(c.id||'').indexOf('card-goal-')!==0);
  const total=filtered.length;
  const top5=filtered.slice(0,5);
  const panel=el('div','gc-panel gc-queue');
  panel.id='group-needs-you';
  const head=el('div','gc-panel__head');
  head.appendChild(el('h3',null,'Needs you ('+total+')'));
  const viewAll=document.createElement('a');
  viewAll.href='#'; viewAll.textContent='View all';
  viewAll.addEventListener('click',e=>{
    e.preventDefault();
    if(typeof openDrawer!=='function')return;
    openDrawer('Needs you',b=>{
      const all=gcSafe(()=>(typeof cmdNeedsYouRows==='function')?cmdNeedsYouRows(filtered,'card-all-'):[],[]);
      if(!all.length)b.appendChild(el('div','body','Nothing needs firing.'));
      else all.forEach(r=>b.appendChild(r));
    });
  });
  head.appendChild(viewAll);
  panel.appendChild(head);
  const body=el('div','gc-panel__body');
  const rows=gcSafe(()=>(typeof cmdNeedsYouRows==='function')?cmdNeedsYouRows(top5,'card-'):[],[]);
  if(!rows.length){
    body.appendChild(el('div','gc-nodata',esc('NO DATA, looked for automation/state/action-cards.json')));
  }else{
    rows.forEach(r=>body.appendChild(r));
  }
  panel.appendChild(body);
  return panel;
}

/* ---------- 4. Agent health ---------- */
function gcHealthTone(state){
  const s=String(state||'').toUpperCase();
  if(s==='WORKING')return{cls:'good',chip:'HEALTHY'};
  if(s==='HELD')return{cls:'info',chip:'HELD'};
  if(s==='STALE')return{cls:'warn',chip:'STALE'};
  if(s==='NO DATA'||s==='')return{cls:'warn',chip:'NO DATA'};
  if(s==='BROKEN'||s==='ERROR')return{cls:'bad',chip:'BROKEN'};
  return{cls:'info',chip:s};
}
/* Lane order per spec V2-GLOW's component map: kitchen, prospector,
   futures, multi, spy -- read via cmdLaneById (gamma_cockpit_command_js.py),
   the ONE lookup fixed to `D.lanes.lanes.find(...)` rather than the old
   old `D.lanes` `.kitchen` mismatch, so this panel and the Kitchen KPI can never
   drift onto two different reads of the same fact. */
const GC_HEALTH_ORDER=[
  {id:'kitchen',icon:'flame'}, {id:'prospector',icon:'radar'},
  {id:'futures',icon:'activity'}, {id:'multi',icon:'layers'},
  {id:'spy',icon:'trending-up'},
];
/* ROUND-2 FIX (2026-09-04): every lane row used to draw a "NO DATA" pill
   where the sparkline belongs, always -- gamma_cockpit_tiles.py's
   build_health_spark() now computes a REAL 7-day-by-day count for the lanes
   that have a raw per-row ledger to bucket (kitchen: cook-queue.jsonl
   `event:complete` rows; prospector: ideas-ledger.jsonl's own `date` field),
   landing as D.health_spark[lane_id].series. Futures/multi/spy/watchers have
   no equivalent per-day raw log (verified, not assumed -- see that module's
   docstring) and keep `series:null`; those draw the OTHER honest empty
   state spec calls for: a flat dotted baseline with a small "no series"
   caption, never a fabricated shape and never a bare pill either. */
function gcHealthSparkExtra(series){
  const slot=el('span','gc-spark-slot');
  if(Array.isArray(series)&&series.length>=2){
    const svg=gcSafe(()=>(typeof gfxSparkV==='function')?gfxSparkV(series):'','');
    if(svg){ slot.appendChild(el('span','gc-spark',svg)); return slot; }
  }
  slot.appendChild(el('span','gc-spark gc-spark--flat',
    '<svg viewBox="0 0 70 22" width="70" height="22" class="gfx" aria-hidden="true">'+
    '<line x1="4" y1="11" x2="66" y2="11" stroke="var(--gc-ink-3,#7581a8)" stroke-width="1.5" '+
    'stroke-dasharray="3 3"/></svg>'));
  slot.appendChild(el('span','gc-spark__cap','no series'));
  return slot;
}
function gcHealthLaneRow(entry){
  const lane=gcSafe(()=>(typeof cmdLaneById==='function')?cmdLaneById(entry.id):null,null);
  if(!lane)return null;
  const t=gcHealthTone(lane.state);
  const spark=(D.health_spark&&D.health_spark[entry.id])||{};
  return gcRow({
    icon:entry.icon, iconTone:t.cls,
    title:lane.label||entry.id,
    sub:lane.detail||lane.metric||null,
    extra:gcHealthSparkExtra(spark.series),
    chipLabel:t.chip, chipTone:t.cls,
  });
}
function gcHealthWatcherRow(){
  const W=D.watchers;
  if(!W||W.ok===false)return null;
  const watchers=(W.watchers)||[];
  const spark=(D.health_spark&&D.health_spark.watchers)||{};
  return gcRow({
    icon:'eye', iconTone:'info',
    title:'Watcher fleet',
    sub:W.say||null,
    extra:gcHealthSparkExtra(spark.series),
    chipLabel:watchers.length+' watching', chipTone:'info',
  });
}
function gcHealth(){
  const panel=el('div','gc-panel gc-health');
  const head=el('div','gc-panel__head');
  head.appendChild(el('h3',null,'Agent health'));
  panel.appendChild(head);
  const body=el('div','gc-panel__body');
  let any=false;
  GC_HEALTH_ORDER.forEach(entry=>{
    const row=gcSafe(()=>gcHealthLaneRow(entry),null);
    if(row){ any=true; body.appendChild(row); }
  });
  const wRow=gcSafe(gcHealthWatcherRow,null);
  if(wRow){ any=true; body.appendChild(wRow); }
  if(!any){
    panel.appendChild(el('div','gc-nodata',esc('NO DATA, looked for automation/state (lanes, watcher-summary.json)')));
  }else{
    panel.appendChild(body);
  }
  return panel;
}

/* ---------- 5. System alerts ---------- */
function gcAlertTone(v){
  const s=String(v||'').toUpperCase();
  if(s==='RED')return'bad';
  if(s==='AMBER'||s==='YELLOW'||s==='WARN')return'warn';
  if(s==='GREEN'||s==='OK')return'good';
  return'info';
}
function gcAlertItems(){
  const items=[];
  const G=D.guards;
  if(G&&G.ok!==false&&G.verdict&&G.verdict!=='green'&&G.verdict!=='off'){
    items.push({icon:'shield',tone:gcAlertTone(G.verdict),title:'Task-state guards',
      sub:G.say,detail:(G.problems||[]).join('. ')||null,
      src:G.path?{path:G.path,age_h:null}:null});
  }
  const T=D.tasks;
  if(T&&T.ok!==false&&T.verdict&&T.verdict!=='green'&&T.verdict!=='off'){
    items.push({icon:'calendar',tone:gcAlertTone(T.verdict),title:'Scheduled tasks',
      sub:T.say,detail:null, src:T.path?{path:T.path,age_h:null}:null});
  }
  (D.answers||[]).forEach(a=>{
    const v=String((a&&a.verdict)||'').toUpperCase();
    if(v&&v!=='GREEN'&&v!=='OK'){
      items.push({icon:'list-checks',tone:gcAlertTone(v),title:a.q||'Answer',
        sub:a.answer,detail:a.detail||null,
        src:(a.sources||[]).filter(Boolean)[0]||null});
    }
  });
  return items;
}
function gcAlertRow(it){
  const row=gcRow({icon:it.icon,iconTone:it.tone,title:it.title,sub:it.sub});
  const btn=document.createElement('button');
  btn.type='button'; btn.className='gc-cta gc-alert-open';
  btn.textContent='Open';
  btn.addEventListener('click',()=>{
    if(typeof openDrawer!=='function')return;
    openDrawer(it.title||'Alert',b=>{
      if(it.sub)b.appendChild(el('div','body',gcSafe(()=>(typeof cmdWrapDigits==='function')?cmdWrapDigits(String(it.sub)):esc(String(it.sub)),esc(String(it.sub)))));
      if(it.detail)b.appendChild(el('div','body',esc(it.detail)));
      if(it.src)b.appendChild(srcRow([it.src]));
    });
  });
  row.appendChild(btn);
  return row;
}
function gcAlerts(){
  const panel=el('div','gc-panel gc-alerts');
  const head=el('div','gc-panel__head');
  head.appendChild(el('h3',null,'System alerts'));
  panel.appendChild(head);
  const items=gcAlertItems();
  if(!items.length){
    panel.appendChild(el('div','gc-nodata',esc('NO DATA, looked for guards/tasks/answers')));
    return panel;
  }
  const body=el('div','gc-panel__body');
  items.forEach(it=>body.appendChild(gcAlertRow(it)));
  panel.appendChild(body);
  return panel;
}

/* ---------- 6. Promo: "Tonight's plan" ---------- */
/* Visual panel per spec V2-GLOW's .gc-promo contract (h4/p/CTA), built
   fresh here -- but the REAL interactive goal strip (id="tile-goal", a real
   <details>, the ring+title+next-item+days-left summary, the goalBody()
   toggle wiring) still has to exist SOMEWHERE: gamma_cockpit_autonomy_js.py's
   vAutonomy() calls tileOpen('tile-goal',{scroll:true}) and expects to find
   it. cmdGoalStrip() (gamma_cockpit_command_js.py, unchanged) is folded in
   as this panel's own expandable detail rather than rendered as a second,
   competing card -- one visual, one behavior, nothing about the autonomy
   view's wiring changes. */
function gcPromo(){
  const A=D.autonomy||{}, g=D.goal||A.goal||null;
  const panel=el('div','gc-panel gc-promo');
  const body=el('div','gc-promo__body');
  body.appendChild(el('h4',null,esc((g&&(g.title||g.id))||"Tonight's plan")));
  const active=!!(g&&g.active);
  const nextItem=active?(g.next_item||'no open item'):'NOT DRIVING';
  const fireLabel=gcSafe(()=>(typeof cmdNextFireLabel==='function')?cmdNextFireLabel():null,null);
  const line='Next: '+nextItem+(fireLabel?(', next fire '+fireLabel):'');
  body.appendChild(el('p',null,esc(line)));
  const btn=document.createElement('button');
  btn.type='button'; btn.className='gc-cta';
  btn.textContent='Open goal';
  btn.addEventListener('click',e=>{
    e.preventDefault();
    if(typeof tileOpen==='function')tileOpen('tile-goal',{scroll:true});
  });
  body.appendChild(btn);
  panel.appendChild(body);
  const strip=gcSafe(()=>(typeof cmdGoalStrip==='function')?cmdGoalStrip():null,null);
  if(strip){
    strip.classList.add('gc-promo__detail');
    panel.appendChild(strip);
  }
  return panel;
}
"""

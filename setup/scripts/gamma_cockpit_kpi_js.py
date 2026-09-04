"""gamma_cockpit_kpi_js.py -- the six KPI vital cards of the Command view.

Split out of gamma_cockpit_command_js.py VERBATIM on the 2026-09-04 Glow
Command integration pass, purely to keep that module under the 800-line
ceiling (spec V2-GLOW section 6). Nothing here changed on the move: the
functions, their names, the classes they emit (`vital`/`vital__*` plus the
additive `gc-kpi`/`gc-kpi__icon`/`gc-kpi__value`) and the contracts they read
(`D.calendar`, `D.gate`, `D.army`, `D.lanes.lanes`, `D.shadow`, `D.autonomy.budget`,
`cmdGfx`/`cmdSafe`/`el`/`esc`/`ic` from the same concatenated script) are the
ones gamma_cockpit_command_js.py documents. Function declarations hoist across
the whole inline <script>, so `gcKpis()` (gamma_cockpit_glow_js.py) and
`vCommand()` call `cmdVitals()` regardless of textual order.

Export: KPI_JS -- concatenated by gamma_cockpit_js.py right before COMMAND_JS.
"""
from __future__ import annotations

KPI_JS = r"""
/* ---------- 4a. THE VITALS GRID (NEW, spec 10.1 band 3) ---------- */
/* 6 tiles, each a <details> whose expand affordance JUMPS to the matching
   producer row (tileOpen) rather than re-rendering that row's body a
   second time -- one body per fact, so the two can never drift apart. */
/* ROUND-2 REVIEW FIX (critical): a native <details> hides everything except
   its <summary> until opened -- gfx/figure/state used to live in a sibling
   .vital__body div, so every Vitals tile rendered at rest (the ONLY state a
   settled screenshot ever shows) as icon+label with NO ring/spark/figure at
   all. That is exactly spec 10.1's "collapsed = glance": the graphic, the
   big figure and the state line ARE the glance and must be visible with the
   tile closed. Fix: everything that must be visible at rest now lives
   inside <summary> (a flex column: icon+label row, then gfx, then figure,
   then state); ONLY the optional "Full detail below" jump link is the
   actual collapsible <details> content, since that's genuinely expand-only
   per spec ("Tiles are <details> too"). vitals_grid_min6_with_svg (which
   only checks svg PRESENCE in the DOM, not visibility) could not catch this
   -- see cmdVitalTile geometry note in cockpit_exercise.py if adding a
   visibility-checking guard later. */
function cmdVitalTile(spec){
  const d=document.createElement('details');
  // 'gc-kpi' (spec V2-GLOW section 4): the KPI stat-card look. Added
  // ALONGSIDE 'vital', never in place of it -- cockpit_exercise.py's
  // check_spend_figure/check_vitals_grid still address '.vitals .vital' and
  // '#vital-budget .vital__figure' verbatim.
  d.className='vital gc-kpi'+(spec.stale?' vital--stale':''); if(spec.id)d.id=spec.id;
  d.dataset.verdict=spec.verdict||'none';
  const s=document.createElement('summary'); s.className='vital__head';
  const top=el('div','vital__top');
  top.appendChild(el('span','vital__ic gc-kpi__icon',tilesSafeIcOrEmpty(spec.icon)));
  // 'gc-kpi__label' deliberately NOT added here: gamma_cockpit_glow_ui.py's
  // rule for that class sets an 11px font, and (equal specificity, later in
  // the CSS concatenation) would override 'vital__label's compliant 12px --
  // this project's own "no text < 12 px" floor wins over the visual match.
  top.appendChild(el('span','vital__label',esc(spec.label||'')));
  s.appendChild(top);
  const gfx=el('div','vital__gfx'); if(spec.gfx)gfx.innerHTML=spec.gfx; s.appendChild(gfx);
  s.appendChild(el('div','vital__figure gc-kpi__value',esc(spec.figure==null?'NO DATA':String(spec.figure))));
  // ROUND-2 FIX (2026-09-04): spec wants "a delta chip on every card" -- a
  // card whose caller could not compute one used to render NOTHING (an
  // empty slot the reviewer read as a missing feature, not a considered
  // absence). Every tile now gets a chip: a real one when the caller
  // computed spec.delta, else an explicit 'NO DATA' chip (flat tone) --
  // never a fabricated comparison, never a blank slot either.
  const deltaSpec=spec.delta&&spec.delta.text?spec.delta:{text:'NO DATA',dir:'flat'};
  s.appendChild(el('span','gc-delta '+(deltaSpec.dir||'flat'),esc(deltaSpec.text)));
  // ROUND-2 FIX (2026-09-04): every KPI card's state line is MUTED METADATA
  // ("7 trading days, 7d", "2 idle", "Fires 0/8, cap $30.00") -- the card's
  // own verdict is already carried by data-verdict (tile background/border
  // tint) and, for Gate, the big figure text itself. A leading .vd dot here
  // just read as a stray bullet in front of a non-verdict sentence (spec:
  // "use the tone dot only on verdict words").
  const state=el('div','vital__state');
  state.appendChild(el('span',null,spec.state||'NO DATA'));
  s.appendChild(state);
  d.appendChild(s);
  if(spec.jumpTo){
    const body=document.createElement('div'); body.className='vital__body';
    const more=el('div','vital__more');
    const a=document.createElement('a'); a.href='#'+spec.jumpTo; a.textContent='Full detail below';
    a.addEventListener('click',e=>{e.preventDefault();if(typeof tileOpen==='function')tileOpen(spec.jumpTo,{scroll:true});});
    more.appendChild(a);
    body.appendChild(more);
    d.appendChild(body);
  }
  return d;
}
function tilesSafeIcOrEmpty(name){ return cmdSafe(()=>(typeof ic==='function')?ic(name):'',''); }

function cmdSignedUsd(v){
  if(v==null||isNaN(v))return'NO DATA';
  return(v>=0?'+':'-')+cmdUsd(v);
}
function cmdVitalBook(){
  const views=(D.calendar&&D.calendar.views)||{}, book=views.BOOK||{days:{}};
  const allDates=Object.keys(book.days||{}).sort();
  const last7=allDates.slice(-7), prev7=allDates.slice(-14,-7);
  const sumOf=ds=>{
    const vs=ds.map(k=>book.days[k].n).filter(v=>v!=null);
    return vs.length?vs.reduce((a,b)=>a+b,0):null;
  };
  const vals=last7.map(k=>book.days[k].n).filter(v=>v!=null);
  const net=sumOf(last7);
  const prevNet=sumOf(prev7);
  // Delta chip: real-derived only -- both windows must have at least one
  // scored day, or no chip renders at all (never a comparison against a
  // fabricated zero baseline).
  let delta=null;
  if(net!=null&&prevNet!=null){
    const diff=net-prevNet;
    delta={text:cmdSignedUsd(diff)+' vs prior 7d', dir:diff>0?'up':(diff<0?'down':'flat')};
  }
  return cmdVitalTile({
    id:'vital-book', icon:'dollar-sign', label:'Book',
    verdict:vals.length?(net>=0?'green':'red'):'off',
    gfx:vals.length>=2?cmdGfx('gfxSparkV',vals,{pnl:true}):'',
    figure:vals.length?cmdUsd(net):'NO DATA',
    delta:delta,
    state:vals.length?(last7.length+' trading days, 7d'):'NO DATA',
    jumpTo:'tile-money',
  });
}
function cmdVitalGate(){
  const gt=D.gate;
  if(!gt||gt.ok===false)return cmdVitalTile({id:'vital-gate',icon:'gauge',label:'Gate',verdict:'off',state:'NO DATA, looked for go-live-gate.json',jumpTo:'tile-gate'});
  const at=(gt.ci&&gt.ci.as_traded)||{};
  const cl=at.ci_lower;
  const v=cmdGateVerdict(gt);
  // Delta chip (spec: "CI-lower delta vs last Friday reading if available
  // in analysis/go-live-gate.json history else 'vs 1.0 bar' chip"). That
  // file is a single point-in-time snapshot with no history array today
  // (verified, not assumed), so this is always the distance from the go-
  // live bar itself -- still a real, non-fabricated number, just not a
  // week-over-week one.
  const delta=(cl!=null)?
    {text:(cl>=1.0?'+':'')+(cl-1.0).toFixed(2)+' vs 1.0 bar', dir:cl>=1.0?'up':'down'}:null;
  return cmdVitalTile({
    id:'vital-gate', icon:'gauge', label:'Gate',
    verdict:v,
    gfx:cl!=null?cmdGfx('gfxRingV',Math.max(0,cl),1):'',
    figure:v==='green'?'LIVE':(v==='none'?'NO DATA':'NOT LIVE'),
    delta:delta,
    state:cmdWrapDigits(gt.say||'NO DATA'),
    jumpTo:'tile-gate',
  });
}
function cmdVitalAgents(){
  const a=D.army;
  if(!a)return cmdVitalTile({id:'vital-agents',icon:'bot',label:'Agents',verdict:'off',state:'NO DATA',jumpTo:'tile-agents'});
  const c=cmdArmyCounts(a);
  const total=((a.sessions)||[]).length;
  // Delta chip (spec: "running vs 24h peak from army") -- peak_24h_sessions
  // is gamma_cockpit_army.py's own disclosed proxy (distinct session_ids
  // per busiest trailing-24h hour bucket in pulse.jsonl -- see its
  // docstring for what it is and isn't a measurement of), not a
  // fabricated number; null when the ledger can't answer it.
  const peak=a.peak_24h_sessions;
  const delta=(peak!=null)?
    {text:c.running+' vs 24h peak '+peak, dir:c.running>=peak?'up':'flat'}:null;
  return cmdVitalTile({
    id:'vital-agents', icon:'bot', label:'Agents',
    verdict:c.running>0?'green':'off',
    gfx:total?cmdGfx('gfxRingV',c.running,total):'',
    figure:total?(c.running+'/'+total):'0',
    delta:delta,
    state:c.waiting+' idle',
    jumpTo:'tile-agents',
  });
}
/* D.lanes is `{lanes:[...]}` -- one row per research lane, each carrying its
   own `id` (gamma_lanes.py's lane_kitchen/lane_futures/lane_multi/
   lane_prospector/lane_spy). The Kitchen KPI used to read a `.kitchen`
   property directly off `D.lanes`, one that never existed on that shape
   (spec V2-GLOW section 6's
   named fix) -- every reader of a lane by id goes through this one lookup
   now, gcHealth() in gamma_cockpit_glow_js.py included. */
function cmdLaneById(id){
  return cmdSafe(()=>{
    const arr=(D.lanes&&D.lanes.lanes)||[];
    for(let i=0;i<arr.length;i++){ if(arr[i]&&arr[i].id===id)return arr[i]; }
    return null;
  },null);
}
function cmdVitalKitchen(){
  const lane=cmdLaneById('kitchen');
  if(!lane)return cmdVitalTile({id:'vital-kitchen',icon:'flame',label:'Kitchen',verdict:'off',state:'NO DATA',jumpTo:'tile-kitchen'});
  const dm=/(\d+)\s*pending/.exec(String(lane.detail||''));
  const mm=/\$([\d.]+)\s*\/\s*\$([\d.]+)/.exec(String(lane.metric||''));
  const spend=mm?parseFloat(mm[1]):null, cap=mm?parseFloat(mm[2]):null;
  const verdict=lane.state==='WORKING'?'green':lane.state==='HELD'?'none':
    (lane.state==='STALE'||lane.state==='NO DATA')?'amber':(lane.state==='BROKEN'||lane.state==='ERROR')?'red':'none';
  // Delta chip (spec: "done today vs 7d avg from learning-ledger.json").
  // D.learning.windows carries real today/7d aggregate task counts (see
  // learning_ledger.py); avg7 = that 7d total / 7, so this is a real pace
  // comparison, not a fabricated one. null (-> NO DATA chip) when the
  // ledger has neither window.
  const lw=(D.learning&&D.learning.windows)||{};
  const kToday=lw.today&&lw.today.kitchen_tasks_completed;
  const k7d=lw['7d']&&lw['7d'].kitchen_tasks_completed;
  let delta=null;
  if(kToday!=null&&k7d!=null){
    const avg7=k7d/7;
    const diff=kToday-avg7;
    delta={text:(diff>=0?'+':'')+diff.toFixed(1)+' vs 7d avg '+avg7.toFixed(1),
      dir:diff>0?'up':(diff<0?'down':'flat')};
  }
  return cmdVitalTile({
    id:'vital-kitchen', icon:'flame', label:'Kitchen',
    verdict:verdict,
    gfx:(spend!=null&&cap!=null)?cmdGfx('gfxPulseV',spend,cap):'',
    figure:dm?(dm[1]+' pending'):(lane.state||'NO DATA'),
    delta:delta,
    state:cmdWrapDigits(lane.detail||lane.state||'NO DATA'),
    jumpTo:'tile-kitchen',
  });
}
function cmdVitalShadow(){
  const sh=D.shadow;
  if(!sh||sh.ok===false)return cmdVitalTile({id:'vital-shadow',icon:'hourglass',label:'Shadow',verdict:'off',state:'NO DATA, looked for SHADOW.md',jumpTo:'tile-shadow'});
  const heat=sh.heat||[];
  const nowN=(sh.live||[]).length;
  // Delta chip (spec: "clocks vs last week") -- live_count_7d_ago is a real
  // re-parse of SHADOW.md as git had it ~7 days ago (build_shadow(), same
  // module), not a live/fabricated comparison. null (-> NO DATA chip) when
  // git can't find a commit that far back yet (a young repo window).
  const prevN=sh.live_count_7d_ago;
  const delta=(prevN!=null)?
    {text:(nowN-prevN>=0?'+':'')+(nowN-prevN)+' vs last week ('+prevN+')',
      dir:nowN>prevN?'up':(nowN<prevN?'down':'flat')}:null;
  return cmdVitalTile({
    id:'vital-shadow', icon:'hourglass', label:'Shadow',
    verdict:'none',
    gfx:heat.length?cmdGfx('gfxHeatV',heat):'',
    figure:nowN+' clocks',
    delta:delta,
    state:cmdWrapDigits(sh.say||'NO DATA'),
    jumpTo:'tile-shadow',
  });
}
function cmdVitalBudget(){
  const A=D.autonomy||{}, bud=A.budget||{};
  const CM=D.cost_meter||{};
  const vals=cmdCostSeries(CM);
  const haveRing=(bud.spent_usd!=null&&bud.cap_usd!=null&&!isNaN(bud.spent_usd)&&!isNaN(bud.cap_usd)&&Number(bud.cap_usd)>0);
  const over=(haveRing&&Number(bud.spent_usd)>Number(bud.cap_usd));
  // Delta chip (spec: "spent vs cap %") -- pure arithmetic over bud's own
  // two numbers, same haveRing guard the ring graphic already uses (never a
  // percentage against a zero/missing cap).
  const pct=haveRing?(Number(bud.spent_usd)/Number(bud.cap_usd)*100):null;
  const delta=(pct!=null)?
    {text:pct.toFixed(0)+'% of cap', dir:pct>=100?'down':(pct>=75?'flat':'up')}:null;
  // spec V2-GLOW component map: "Budget (ring spent/cap)" -- a ring reads the
  // spend-vs-cap fraction at a glance the way Gate/Agents already do; falls
  // back to the 14d spend spark when spent/cap aren't both present (never a
  // ring drawn against a fabricated denominator).
  return cmdVitalTile({
    id:'vital-budget', icon:'target', label:'Budget',
    verdict:over?'amber':'none',
    stale:!!CM.as_of_et_date,
    gfx:haveRing?cmdGfx('gfxRingV',bud.spent_usd,bud.cap_usd):(vals.length>=2?cmdGfx('gfxSparkV',vals):''),
    figure:(bud.spent_usd!=null)?cmdUsd(bud.spent_usd):'NO DATA',
    delta:delta,
    state:(bud.fires_used!=null&&bud.fires_cap!=null)?('Fires '+bud.fires_used+'/'+bud.fires_cap+', cap '+cmdUsd(bud.cap_usd)):'NO DATA',
    jumpTo:null,
  });
}
function cmdVitals(){
  // 'gc-grid--kpi' (spec V2-GLOW section 4) is purely an additional CSS hook
  // for the responsive card grid; 'vitals' stays first and unchanged --
  // cockpit_exercise.py's check_vitals_grid selects '.vitals .vital'.
  const grid=el('div','vitals gc-grid--kpi');
  [cmdVitalBook,cmdVitalGate,cmdVitalAgents,cmdVitalKitchen,cmdVitalShadow,cmdVitalBudget]
    .forEach(fn=>grid.appendChild(cmdSafe(fn,el('div','vital'))));
  return grid;
}
function cmdCostDays(CM){
  const raw=CM&&CM.days;
  if(!raw)return[];
  if(Array.isArray(raw))return raw.slice();
  return Object.keys(raw).sort().map(k=>Object.assign({date_et:k},raw[k]));
}
function cmdCostSeries(CM){
  return cmdCostDays(CM).map(d=>(d.total_usd&&d.total_usd.usd!=null)?d.total_usd.usd:null).filter(v=>v!=null);
}
function cmdUsd(v){
  if(v==null||isNaN(v))return'NO DATA';
  return'$'+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
}
/* cmdBudgetPane/cmdBand (the old 2-column Goal/Budget band) are retired by
   spec 10.1 -- budget now renders as one of the 6 Vitals tiles (cmdVitalBudget
   above) and the goal as the one-line cmdGoalStrip above. cmdCostDays/
   cmdCostSeries/cmdUsd stay: cmdVitalBudget still calls them verbatim. */
"""

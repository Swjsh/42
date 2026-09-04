"""gamma_cockpit_command_js.py - the Command view (Quiet Command rebuild, 2026-09-03).

WORKSTREAM F_command_view. Owns exactly one export: `COMMAND_JS`, defining
`vCommand(h)` -- the sentence, the day-line, the Army stage frame, the Goal/
Budget band, and the four row groups ("Needs you" / Trading / Research / Rig).
Held as a Python string, same convention as every other gamma_cockpit_*_js.py
module, so the whole cockpit stays a bundler-free file:// build.

THIS FILE IS WRITTEN AGAINST CONTRACTS BUILT BY PARALLEL SESSIONS THIS SAME
EVENING -- verified present on disk before writing a line here:
  - `tileRow(spec)` / `groupRows({id,title,rows})` / `tileOpen(id,{scroll})` /
    `gfxGauge/gfxMeter/gfxSpark/gfxHeat/gfxRings/gfxFunnel/gfxDots/gfxBars/
    gfxRingBig` / `tilesInit()` -- gamma_cockpit_tiles_js.py (WS-C), read in
    full this session.
  - `producerRows(group)` for group in 'trading'|'research'|'rig' -- already
    complete in gamma_cockpit_producers_js.py, read in full this session. This
    file therefore CALLS producerRows() rather than redefining it (redefining
    it here would sit textually AFTER producers_js in the concatenated script
    -- TILES_JS + VIEWS_JS + PRODUCERS_JS + COMMAND_JS, gamma_cockpit_js.py's
    JS assembly -- and would silently clobber the real implementation with a
    worse one; never do that to another builder's finished work).
  - `armyMount(host)` -- gamma_cockpit_army_js.py (WS-G), mounts the whole
    Army stage (SVG, stars, legend, controls, poll) into any host element.
  - `D.gate` / `D.tasks.dayline` / the other 7 new payload keys --
    gamma_cockpit_tiles.py (WS-B), read in full this session (`build_tasks()`
    returns exactly `[{label,time_et,name,fired_today,failed_today}]`, `say`
    fields are pre-composed sentences with real numbers, never fabricated
    here).
  - `fireCard(card,btn,msg)` / `cardFireLabel(rth)` / `rthNowClient()` --
    gamma_cockpit_cards_js.py, UNCHANGED. "Needs you" rows call fireCard
    directly rather than through tileRow's own `act`/`tilesFire` path, because
    tilesFire assumes a synchronous or Promise-returning onclick and would
    swap the button for a "Fired HH:MM" span before fireCard's own async
    fetch/.then chain gets to manage the button's state -- so this file
    inserts its own button at the same visual slot tileRow uses for `act`
    instead of passing `act` through tilesFire.

Every one of those symbols is still feature-detected (`typeof x==='function'`)
before use. Nothing here computes a metric or fabricates a number; every
number is read from `D`, which Python built. A missing contract degrades to
an honest "NO DATA" node, never a thrown error and never a guessed graphic.
"""
from __future__ import annotations

COMMAND_JS = r"""
/* ============================ COMMAND: the one screen ============================ */
/* spec: markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md section 3 */

/* ---------- small helpers this file owns ---------- */
function cmdGfx(name,...args){
  try{
    const f=(typeof window!=='undefined')?window[name]:null;
    return (typeof f==='function')?f(...args):'';
  }catch(_){ return ''; }
}
function cmdWrapDigits(s){
  const t=esc(s);
  try{ if(typeof _wrapDigits==='function')return _wrapDigits(t); }catch(_){}
  return t;
}
function cmdSafe(fn,fallback){ try{ return fn(); }catch(_){ return fallback; } }

/* ---------- 1. THE SENTENCE ---------- */
/* Round-1 review (critical/major): the four clauses used to ship as one
   run-on prose sentence ("Market closed. 4 agents running... Gate RED...")
   with zero visual separation and the word "RED" in plain ink -- a 5-second
   skim had to parse the whole clause before finding the one that mattered.
   Each clause now degrades independently to "<thing> NO DATA" exactly as
   before (never a guessed word), but ALSO carries a `verdict` so it renders
   as its own discrete chip: a `.vd` dot (the SAME dot vocabulary every tile
   already uses, `[data-verdict=...] .vd`, spec 4's "Sentence" row) followed
   by its text, separated from its neighbours by a hairline divider rather
   than a run of words. This stays inside the ban list -- no colour on the
   text itself, no filled pill background -- the dot alone carries severity,
   so "RED" reads as red without a single new banned pattern. */
function cmdMarketClause(){
  const pw=cmdSafe(()=>(typeof phaseWord==='function')?phaseWord():null,null);
  if(pw==='Live')return{verdict:'green',text:'Market open'};
  if(pw==='Premarket')return{verdict:'amber',text:'Market opens soon'};
  if(pw==='Weekend')return{verdict:'off',text:'Market closed, weekend'};
  if(pw==='After hours')return{verdict:'off',text:'Market closed'};
  const w=(D.hq&&D.hq.state_word)||'';
  if(w==='TRADING')return{verdict:'green',text:'Market open'};
  if(w==='RESEARCHING')return{verdict:'off',text:'Market closed'};
  if(w==='STANDING BY')return{verdict:'off',text:'Market closed, weekend'};
  return{verdict:'none',text:'market NO DATA'};
}
function cmdArmyCounts(a){
  const S=(a&&a.sessions)||[];
  const running=S.reduce((n,s)=>n+(s.worker_active||0),0);
  const waiting=S.filter(s=>s.activity==='idle').length;
  return{running,waiting};
}
function cmdArmyClause(){
  /* spec 10.1: the sentence's agents clause is JUST "N agents running" --
     idle-session "waiting" no longer rides along here (it was a different
     signal from "needs you" anyway); see cmdNeedsYouClause below for the
     count that actually maps to the "Needs you" group. */
  const a=D.army; if(!a)return{verdict:'none',text:'agents NO DATA'};
  const c=cmdArmyCounts(a);
  return{
    verdict:c.running>0?'green':'off',
    text:'<b>'+c.running+'</b> agent'+(c.running===1?'':'s')+' running',
  };
}
function cmdNeedsYouClause(){
  const cards=((D.cards||{}).cards)||[];
  const n=cards.filter(c=>!String(c.id||'').startsWith('card-goal-')).length;
  return{verdict:n>0?'amber':'off',text:'<b>'+n+'</b> need'+(n===1?'s':'')+' you'};
}
function cmdBookClause(){
  const p=D.positions; if(!p)return{verdict:'none',text:'book NO DATA'};
  if(p.flat)return{verdict:'off',text:'Book flat'};
  const o=(p.open||[])[0];
  if(o)return{verdict:'amber',text:'Book '+esc(o.arm)+' '+esc(o.side)+' '+esc(o.symbol)};
  return{verdict:'amber',text:'Book open'};
}
function cmdGateVerdict(gt){
  const v=String((gt&&(gt.overall_verdict||gt.verdict))||'').toUpperCase();
  if(v==='GREEN')return'green';
  if(v==='RED')return'red';
  if(v==='AMBER'||v==='YELLOW')return'amber';
  return'none';
}
/* spec 10.1: the sentence's own gate clause is a PLAIN WORD -- "NOT LIVE"
   (red WORD, never a red bar) or "LIVE" -- the CI-lower metric this used to
   carry inline ("Gate RED. PF CI-lower 0.42 vs 1.0, 42 days") moves to the
   Gate Vitals tile instead (cmdVitalGate below), which still reads
   D.gate.say verbatim so the real number is never re-derived, just moved. */
function cmdGateWordClause(){
  const gt=D.gate; if(!gt||gt.ok===false)return{verdict:'none',text:'gate NO DATA'};
  const v=cmdGateVerdict(gt);
  if(v==='green')return{verdict:'green',text:'LIVE'};
  if(v==='red'||v==='amber')return{verdict:v,text:'NOT LIVE'};
  return{verdict:'none',text:'gate NO DATA'};
}
function cmdStatusItem(clause){
  const item=el('span','statusitem'); item.dataset.verdict=clause.verdict||'none';
  item.appendChild(el('i','vd'));
  const t=el('span','statusitem__t'); t.innerHTML=clause.text; item.appendChild(t);
  return item;
}
function cmdSentence(){
  const wrap=el('div','statusrow sentence');
  // order per spec 10.1: gate word, market, agents, needs-you, book
  [cmdGateWordClause(),cmdMarketClause(),cmdArmyClause(),cmdNeedsYouClause(),cmdBookClause()]
    .forEach(c=>wrap.appendChild(cmdStatusItem(c)));
  return wrap;
}

/* ---------- 2. THE DAY-LINE ---------- */
/* Domain: 08:00 (start of the trading-critical schedule) .. 00:10 next day
   (Conductor). Times before 08:00 are treated as belonging to "tomorrow"
   for placement only -- ordering, never a fabricated value. */
const CMD_DL_START=480, CMD_DL_END_MIN=1450;
let CMD_DL_END=CMD_DL_END_MIN;
function cmdDlMinutesAbs(hhmm){
  let m=cmdMinutesET(hhmm);
  if(m==null)return null;
  if(m<CMD_DL_START)m+=1440;
  return m;
}
function cmdDlDomain(ticks){
  /* the axis ends at the latest scheduled tick (or now), never before 00:10 */
  let end=CMD_DL_END_MIN;
  ticks.forEach(t=>{const m=cmdDlMinutesAbs(t.time_et); if(m!=null&&m>end)end=m;});
  const now=cmdDlMinutesAbs(cmdISOToHHMM(D.built_at_et));
  if(now!=null&&now>end)end=now;
  CMD_DL_END=end+20;  /* breathing room so the last label does not sit on the edge */
}
const DAYLINE_DEFAULT=[
  {label:'LaunchTV',time_et:'08:00',name:'Gamma_LaunchTV',fired_today:null,failed_today:null},
  {label:'Premarket',time_et:'08:30',name:'Gamma_Premarket',fired_today:null,failed_today:null},
  {label:'HeartbeatCore',time_et:'09:30',name:'Gamma_HeartbeatCore',fired_today:null,failed_today:null},
  {label:'EodFlatten',time_et:'15:55',name:'Gamma_EodFlatten',fired_today:null,failed_today:null},
  {label:'EOD',time_et:'16:45',name:'Gamma_AnalystEodReview',fired_today:null,failed_today:null},
  {label:'GymSession',time_et:'17:00',name:'Gamma_GymSession',fired_today:null,failed_today:null},
  {label:'Conductor',time_et:'00:10',name:'Gamma_Conductor',fired_today:null,failed_today:null},
];
function cmdISOToHHMM(iso){
  if(!iso)return null;
  const m=/T(\d{2}):(\d{2})/.exec(String(iso));
  return m?(m[1]+':'+m[2]):null;
}
function cmdMinutesET(hhmm){
  const m=/^(\d{1,2}):(\d{2})$/.exec(String(hhmm||''));
  return m?(parseInt(m[1],10)*60+parseInt(m[2],10)):null;
}
function dlPos(hhmm){
  const m=cmdDlMinutesAbs(hhmm);
  if(m==null)return null;
  return Math.max(0,Math.min(100,(m-CMD_DL_START)/(CMD_DL_END-CMD_DL_START)*100));
}
let CMD_CHOREO_DONE=false;
/* The day-line cursor: an SVG line from 00:00 to "now", stroke-drawn in via
   stroke-dashoffset on the FIRST render this page load only (motion table
   4.1), gated by RM. Every later render (route back to Command) paints the
   resting position instantly -- no repeat show. */
function cmdDaylineCursor(pct){
  const ns='http://www.w3.org/2000/svg', W=1000;
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('class','dayline__cursorsvg');
  svg.setAttribute('viewBox','0 0 '+W+' 2'); svg.setAttribute('preserveAspectRatio','none');
  svg.setAttribute('width','100%'); svg.setAttribute('height','2');
  const line=document.createElementNS(ns,'line');
  line.setAttribute('x1','0'); line.setAttribute('y1','1'); line.setAttribute('x2',String(W)); line.setAttribute('y2','1');
  line.setAttribute('stroke','var(--accent-fill,var(--acc))'); line.setAttribute('stroke-width','2');
  line.setAttribute('stroke-dasharray',String(W));
  const offset=W*(1-pct/100);
  if(!RM&&!CMD_CHOREO_DONE){
    CMD_CHOREO_DONE=true;
    line.style.strokeDashoffset=String(W);
    requestAnimationFrame(()=>{
      line.style.transition='stroke-dashoffset 600ms ease-out';
      requestAnimationFrame(()=>{line.style.strokeDashoffset=String(offset);});
    });
  }else{
    line.style.strokeDashoffset=String(offset);
  }
  svg.appendChild(line);
  return svg;
}
function cmdDayline(){
  const wrap=el('div','dayline');
  const T=D.tasks;
  const ok=!!(T&&T.ok!==false&&Array.isArray(T.dayline)&&T.dayline.length);
  const ticks=ok?T.dayline:DAYLINE_DEFAULT;
  cmdDlDomain(ticks);
  const track=el('div','dayline__track');
  const liveStart=dlPos('09:30'), liveEnd=dlPos('15:55');
  if(liveStart!=null&&liveEnd!=null){
    const live=el('div','dayline__live');
    live.style.left=liveStart+'%'; live.style.width=Math.max(0,liveEnd-liveStart)+'%';
    track.appendChild(live);
  }
  const nowHHMM=cmdISOToHHMM(D.built_at_et);
  const nowPct=nowHHMM!=null?dlPos(nowHHMM):null;
  if(nowPct!=null)track.appendChild(cmdDaylineCursor(nowPct));
  /* spec 10.1: "ALL labels below the track, min 56px apart (drop the
     collision pair 08:30/09:30 -> show 09:30 only; 16:45/17:00 -> 17:00
     only)" -- ticks are sorted ascending, so a collision drops the PREVIOUS
     tick's label (never alternates it to a second row -- that read as two
     competing label lanes, not one clean line). */
  let prevPos=null, prevTick=null;
  const LBL_PCT=4.2;  /* a 5-char mono label plus a gap, as a share of the track */
  ticks.slice().sort((a,b)=>(cmdDlMinutesAbs(a.time_et)||0)-(cmdDlMinutesAbs(b.time_et)||0)).forEach(t=>{
    let pos=dlPos(t.time_et);
    if(pos==null){
      const dflt=DAYLINE_DEFAULT.find(d=>d.name===t.name);
      pos=dflt?dlPos(dflt.time_et):null;
    }
    if(pos==null)return;  // never place a tick at a fabricated time
    const state=t.failed_today?'failed':(t.fired_today?'fired':'upcoming');
    const tk=el('div','dayline__tick'); tk.dataset.state=state;
    tk.style.left=pos+'%';
    if(prevPos!=null&&prevTick&&(pos-prevPos)<LBL_PCT)prevTick.dataset.hideLabel='1';
    prevPos=pos; prevTick=tk;
    tk.title=(t.name||t.label||'')+(t.time_et?' '+t.time_et:' time NO DATA');
    tk.appendChild(el('span','dayline__lbl mono',esc(t.time_et||'?')));
    track.appendChild(tk);
  });
  if(nowPct!=null){
    const now=el('div','dayline__now'); now.style.left=nowPct+'%';
    track.appendChild(now);
  }
  wrap.appendChild(track);
  if(!ok)wrap.appendChild(el('div','dayline__meta mut','NO DATA'));
  return wrap;
}

/* ---------- 3. THE ARMY STAGE ---------- */
function cmdStagePulseLine(){
  const pulses=(D.army&&D.army.pulses)||[];
  const last=pulses.length?pulses[pulses.length-1]:null;
  const line=el('div','stage__pulse mono');
  if(!last){ line.textContent='NO DATA'; return line; }
  /* textContent, so no esc(): escaping here double-encoded quotes as &#39; on screen */
  line.textContent=String(last.ts||'').slice(11,19)+' '+String(last.event||'')+
    (last.detail?' '+String(last.detail).slice(0,160):'');
  return line;
}
function cmdNextFireLabel(){
  /* spec 10.1's zero-session stage text: "Next fire HH:MM ET" -- reuses the
     SAME dayline tick source cmdDayline() already reads (never a second,
     divergent schedule), picking the first tick strictly after "now" that
     is not already fired_today. Falls back to a plain word, never a
     fabricated time, when nothing qualifies. */
  const T=D.tasks;
  const ok=!!(T&&T.ok!==false&&Array.isArray(T.dayline)&&T.dayline.length);
  const ticks=ok?T.dayline:DAYLINE_DEFAULT;
  const nowM=cmdDlMinutesAbs(cmdISOToHHMM(D.built_at_et));
  if(nowM==null)return null;
  const upcoming=ticks
    .map(t=>({t,m:cmdDlMinutesAbs(t.time_et)}))
    .filter(x=>x.m!=null&&!x.t.fired_today&&x.m>nowM)
    .sort((a,b)=>a.m-b.m);
  return upcoming.length?(upcoming[0].t.time_et+' ET'):null;
}
function cmdStage(){
  const wrap=el('div','stage');
  const host=el('div'); host.id='stagehost';
  wrap.appendChild(host);
  if(typeof armyMount==='function'){
    try{armyMount(host);}
    catch(e){host.appendChild(el('div','mut','NO DATA, the Army stage failed to mount'));}
  }else{
    host.appendChild(el('div','mut','NO DATA, armyMount is not wired yet'));
  }
  // spec 10.1 band 4: "When zero sessions are live the stage still earns
  // its space: the star-field + a slow radial sweep (ambient) + the
  // sentence 'Nothing running. Next fire 00:10 ET' centred". armyMount()
  // above already drew the star-field (it draws it unconditionally); this
  // only ADDS the sweep + sentence on top when there is truly nothing to
  // show, so the delete-only army_js module needs no edit for this.
  const nSessions=cmdSafe(()=>((D.army&&D.army.sessions)||[]).length,0);
  if(nSessions===0){
    const sweep=el('div','stage__sweep'); sweep.append(el('i'),el('i'),el('i'));
    wrap.appendChild(sweep);
    const next=cmdNextFireLabel();
    const empty=el('div','stage__empty');
    empty.appendChild(el('span',null,'Nothing running. '+(next?('Next fire '+esc(next)):'No upcoming fire on today\'s schedule')));
    wrap.appendChild(empty);
  }
  wrap.appendChild(cmdStagePulseLine());
  return wrap;
}

/* ---------- 4. GOAL STRIP + VITALS GRID ---------- */
/* spec 10.1: "Goal + Budget band collapses INTO the Vitals grid (Budget
   tile) and a one-line goal strip directly above 'Needs you'." The strip
   keeps id="tile-goal" (the 'autonomy' alias's tileOpen target,
   gamma_cockpit_autonomy_js.py:vAutonomy) and stays a real <details> so a
   click still expands the untouched goalBody() content -- only the
   COLLAPSED anatomy changes, from a 56px tile row to a 40px single line. */
function cmdGoalStrip(){
  const A=D.autonomy||{}, g=D.goal||A.goal||null;
  const q=(g&&g.queue)||[];
  const done=q.filter(x=>x.state==='done').length, total=q.length;
  const active=!!(g&&g.active);
  const d=document.createElement('details');
  d.className='tile'; d.id='tile-goal'; d.dataset.verdict=active?'none':'off';
  const s=document.createElement('summary'); s.className='goalstrip';
  const ring=el('span','goalstrip__ring'); if(total)ring.innerHTML=cmdGfx('gfxRingBig',done,total);
  s.appendChild(ring);
  s.appendChild(el('span','goalstrip__t',esc((g&&(g.title||g.id))||'No active goal')));
  s.appendChild(el('span','goalstrip__next',active?esc(g.next_item||'no open item'):'NOT DRIVING'));
  if(active&&g.days_left!=null)s.appendChild(el('span','goalstrip__days','<b>'+g.days_left+'</b> days left'));
  d.appendChild(s);
  const body=document.createElement('div'); body.className='tile__body';
  d.appendChild(body);
  let built=false;
  d.addEventListener('toggle',()=>{
    if(!d.open||built)return; built=true;
    if(typeof goalBody==='function')goalBody(body);
    else body.appendChild(el('div','mut','NO DATA, goalBody is not wired yet'));
  });
  return d;
}

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
  d.className='vital'+(spec.stale?' vital--stale':''); if(spec.id)d.id=spec.id;
  d.dataset.verdict=spec.verdict||'none';
  const s=document.createElement('summary'); s.className='vital__head';
  const top=el('div','vital__top');
  top.appendChild(el('span','vital__ic',tilesSafeIcOrEmpty(spec.icon)));
  top.appendChild(el('span','vital__label',esc(spec.label||'')));
  s.appendChild(top);
  const gfx=el('div','vital__gfx'); if(spec.gfx)gfx.innerHTML=spec.gfx; s.appendChild(gfx);
  s.appendChild(el('div','vital__figure',esc(spec.figure==null?'NO DATA':String(spec.figure))));
  const state=el('div','vital__state');
  state.appendChild(el('i','vd'));
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

function cmdVitalBook(){
  const views=(D.calendar&&D.calendar.views)||{}, book=views.BOOK||{days:{}};
  const dates=Object.keys(book.days||{}).sort().slice(-7);
  const vals=dates.map(k=>book.days[k].n).filter(v=>v!=null);
  const net=vals.reduce((a,b)=>a+b,0);
  return cmdVitalTile({
    id:'vital-book', icon:'dollar-sign', label:'Book',
    verdict:vals.length?(net>=0?'green':'red'):'off',
    gfx:vals.length>=2?cmdGfx('gfxSparkV',vals,{pnl:true}):'',
    figure:vals.length?cmdUsd(net):'NO DATA',
    state:vals.length?(dates.length+' trading days, 7d'):'NO DATA',
    jumpTo:'tile-money',
  });
}
function cmdVitalGate(){
  const gt=D.gate;
  if(!gt||gt.ok===false)return cmdVitalTile({id:'vital-gate',icon:'gauge',label:'Gate',verdict:'off',state:'NO DATA, looked for go-live-gate.json',jumpTo:'tile-gate'});
  const at=(gt.ci&&gt.ci.as_traded)||{};
  const cl=at.ci_lower;
  const v=cmdGateVerdict(gt);
  return cmdVitalTile({
    id:'vital-gate', icon:'gauge', label:'Gate',
    verdict:v,
    gfx:cl!=null?cmdGfx('gfxRingV',Math.max(0,cl),1):'',
    figure:v==='green'?'LIVE':(v==='none'?'NO DATA':'NOT LIVE'),
    state:cmdWrapDigits(gt.say||'NO DATA'),
    jumpTo:'tile-gate',
  });
}
function cmdVitalAgents(){
  const a=D.army;
  if(!a)return cmdVitalTile({id:'vital-agents',icon:'bot',label:'Agents',verdict:'off',state:'NO DATA',jumpTo:'tile-agents'});
  const c=cmdArmyCounts(a);
  const total=((a.sessions)||[]).length;
  return cmdVitalTile({
    id:'vital-agents', icon:'bot', label:'Agents',
    verdict:c.running>0?'green':'off',
    gfx:total?cmdGfx('gfxRingV',c.running,total):'',
    figure:total?(c.running+'/'+total):'0',
    state:c.waiting+' idle',
    jumpTo:'tile-agents',
  });
}
function cmdVitalKitchen(){
  const lane=((D.lanes)||{}).kitchen;
  if(!lane)return cmdVitalTile({id:'vital-kitchen',icon:'flame',label:'Kitchen',verdict:'off',state:'NO DATA',jumpTo:'tile-kitchen'});
  const dm=/(\d+)\s*pending/.exec(String(lane.detail||''));
  const mm=/\$([\d.]+)\s*\/\s*\$([\d.]+)/.exec(String(lane.metric||''));
  const spend=mm?parseFloat(mm[1]):null, cap=mm?parseFloat(mm[2]):null;
  const verdict=lane.state==='WORKING'?'green':lane.state==='HELD'?'none':
    (lane.state==='STALE'||lane.state==='NO DATA')?'amber':(lane.state==='BROKEN'||lane.state==='ERROR')?'red':'none';
  return cmdVitalTile({
    id:'vital-kitchen', icon:'flame', label:'Kitchen',
    verdict:verdict,
    gfx:(spend!=null&&cap!=null)?cmdGfx('gfxPulseV',spend,cap):'',
    figure:dm?(dm[1]+' pending'):(lane.state||'NO DATA'),
    state:cmdWrapDigits(lane.detail||lane.state||'NO DATA'),
    jumpTo:'tile-kitchen',
  });
}
function cmdVitalShadow(){
  const sh=D.shadow;
  if(!sh||sh.ok===false)return cmdVitalTile({id:'vital-shadow',icon:'hourglass',label:'Shadow board',verdict:'off',state:'NO DATA, looked for SHADOW.md',jumpTo:'tile-shadow'});
  const heat=sh.heat||[];
  return cmdVitalTile({
    id:'vital-shadow', icon:'hourglass', label:'Shadow board',
    verdict:'none',
    gfx:heat.length?cmdGfx('gfxHeatV',heat):'',
    figure:(sh.live||[]).length+' clocks',
    state:cmdWrapDigits(sh.say||'NO DATA'),
    jumpTo:'tile-shadow',
  });
}
function cmdVitalBudget(){
  const A=D.autonomy||{}, bud=A.budget||{};
  const CM=D.cost_meter||{};
  const vals=cmdCostSeries(CM);
  const over=(bud.spent_usd!=null&&bud.cap_usd!=null&&Number(bud.spent_usd)>Number(bud.cap_usd));
  return cmdVitalTile({
    id:'vital-budget', icon:'target', label:'Budget',
    verdict:over?'amber':'none',
    stale:!!CM.as_of_et_date,
    gfx:vals.length>=2?cmdGfx('gfxSparkV',vals):'',
    figure:(bud.spent_usd!=null)?cmdUsd(bud.spent_usd):'NO DATA',
    state:(bud.fires_used!=null&&bud.fires_cap!=null)?('Fires '+bud.fires_used+'/'+bud.fires_cap+', cap '+cmdUsd(bud.cap_usd)):'NO DATA',
    jumpTo:null,
  });
}
function cmdVitals(){
  const grid=el('div','vitals');
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

/* ---------- 5. ROW GROUPS ---------- */
function cmdRowFallback(spec){
  const d=document.createElement('details');
  d.className='row'; if(spec.id)d.id=spec.id; d.dataset.verdict=spec.verdict||'none';
  const s=document.createElement('summary'); s.className='row__head';
  s.appendChild(el('span','row__title',esc(spec.title||'')));
  s.appendChild(el('span','row__say',spec.say||''));
  const src=el('span','row__src');
  if(spec.src&&spec.src.path)src.appendChild(document.createTextNode(esc(spec.src.path)));
  s.appendChild(src);
  d.appendChild(s);
  const body=el('div','row__body'); d.appendChild(body);
  let built=false;
  d.addEventListener('toggle',()=>{ if(d.open&&!built){built=true; if(typeof spec.body==='function')spec.body(body);} });
  return d;
}
function cmdGroupFallback(id,title,rows){
  const g=el('div','tgroup'); g.id=id;
  g.appendChild(el('div','tgroup__head',esc(title)+' <span class="tgroup__count">'+rows.length+'</span>'));
  const body=el('div','tgroup__body'); rows.forEach(r=>body.appendChild(r));
  g.appendChild(body);
  return g;
}
function cmdGroup(id,title,rows){
  return(typeof groupRows==='function')?groupRows({id,title,rows}):cmdGroupFallback(id,title,rows);
}

/* "Needs you" = action cards, one tileRow per card, Fire wired straight to the
   existing fireCard() (unchanged) rather than through tileRow's own `act`,
   see the module docstring for why. The card sharing the goal band's next
   item (card-goal-*, cards.py) is filtered out so the same item never shows
   twice (test_cards_active_goal_picks_first_open_item). */
function cmdNeedsYouRows(){
  const cards=((D.cards||{}).cards)||[];
  const rth=cmdSafe(()=>(typeof rthNowClient==='function')&&rthNowClient(),false);
  const filtered=cards.filter(c=>!String(c.id||'').startsWith('card-goal-'));
  const n=filtered.length;
  return filtered.map((c,i)=>{
    // spec 10.2: every "Needs you" row gets a severity-bar graphic, never a
    // text-only row. Rank weight = the row's own worst-first position
    // (already how build_cards() orders `cards`); tone buckets that same
    // position into thirds -- the row's REAL `gated` flag still drives the
    // verdict dot/tint independently, this is only the bar's colour.
    const tone=n<=1?'red':(i<n/3?'red':(i<2*n/3?'amber':'none'));
    const spec={
      id:'card-'+String(c.id||c.rank||'').replace(/[^A-Za-z0-9_-]/g,'')||('card-'+(c.rank||0)),
      icon:'target',
      title:c.title||'',
      verdict:c.gated?'amber':'none',
      gfx:cmdGfx('gfxSeverity',i,n,tone),
      say:cmdWrapDigits([c.kind||'',(c.why&&c.why[0])||''].filter(Boolean).join('. ')),
      src:{path:c.source_path||'', stamp:null, age_h:c.source_age_h},
      fresh_h:c.source_age_h,
      body:(host)=>{
        (c.why||[]).forEach(w=>host.appendChild(el('div','body','- '+esc(w))));
        if(c.objective)host.appendChild(el('div','body',esc(c.objective)));
        host.appendChild(srcRow([{path:c.source_path,age_h:c.source_age_h}]));
      },
    };
    const tile=(typeof tileRow==='function')?tileRow(spec):cmdRowFallback(spec);
    if(typeof fireCard==='function'){
      const btn=document.createElement('button');
      btn.type='button'; btn.className='tile__fire';
      const label=cmdSafe(()=>(typeof cardFireLabel==='function')?cardFireLabel(rth):'Fire','Fire');
      btn.textContent=label; btn.disabled=!!rth;
      const msg=el('div','meta tile__firemsg');
      const bodyHost=tile.querySelector('.tile__body')||tile.querySelector('.row__body');
      if(bodyHost)bodyHost.insertBefore(msg,bodyHost.firstChild);
      btn.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();try{tile.open=true;}catch(_){}fireCard(c,btn,msg);});
      const chev=tile.querySelector('.tile__chev');
      if(chev&&chev.parentNode)chev.parentNode.insertBefore(btn,chev);
      else{const summary=tile.querySelector('summary'); if(summary)summary.appendChild(btn);}
    }
    return tile;
  });
}
function cmdProducerRows(group){
  return cmdSafe(()=>(typeof producerRows==='function')?producerRows(group):[],[]);
}

/* ---------- 6. confetti ---------- */
/* Only two triggers, both compared against a value stored earlier THIS
   session (sessionStorage) so a cold load never celebrates, and each is
   deduped for the day in localStorage['gamma-celebrated'] so a page that
   re-renders Command a dozen times a minute does not replay it a dozen
   times. */
function cmdConfetti(){
  if(RM)return;
  try{
    const prevGate=sessionStorage.getItem('gamma-cmd-prev-gate');
    const curGate=(D.gate&&D.gate.overall_verdict)||(D.gate&&D.gate.verdict)||null;
    if(curGate)sessionStorage.setItem('gamma-cmd-prev-gate',curGate);
    const gateFlip=!!(prevGate&&String(prevGate).toUpperCase()!=='GREEN'&&String(curGate).toUpperCase()==='GREEN');
    const views=(D.calendar&&D.calendar.views)||{};
    const today=D.today;
    let crossedArm=null;
    Object.keys(views).forEach(arm=>{
      if(arm==='BOOK')return;
      const day=((views[arm]||{}).days||{})[today];
      const n=day&&day.n;
      const key='gamma-cmd-prevpnl-'+arm;
      const prevN=sessionStorage.getItem(key);
      if(n!=null)sessionStorage.setItem(key,String(n));
      if(n!=null&&n>=100&&(prevN==null||Number(prevN)<100))crossedArm=arm;
    });
    if(!(gateFlip||crossedArm))return;
    let celeb={};
    try{celeb=JSON.parse(localStorage.getItem('gamma-celebrated')||'{}');}catch(_){celeb={};}
    const dedKey=(gateFlip?'gate:':'pnl:'+crossedArm+':')+today;
    if(celeb[dedKey])return;
    celeb[dedKey]=true;
    try{localStorage.setItem('gamma-celebrated',JSON.stringify(celeb));}catch(_){}
    if(typeof confetti==='function'){
      confetti({particleCount:80,colors:['#00a2c7','#30a46c','#eeeeee']});
    }
  }catch(_){}
}

/* ---------- 7. LOAD CHOREOGRAPHY (spec 10.5) ---------- */
/* ONE WAAPI timeline, run once per page load (never on a re-render or a
   route back to Command -- CMD_LOAD_CHOREO_DONE below), entirely skipped
   under reduced motion (the elements' resting CSS state is already fully
   visible either way -- WAAPI releases control back to that state when an
   animation finishes without `fill:'forwards'`, so skipping never leaves
   anything stuck invisible). The Army stage's own entrance (stars/
   orchestrator/beams) is army_js's existing mechanism, untouched here. */
let CMD_LOAD_CHOREO_DONE=false;
function cmdAnimate(el,keyframes,opts){
  try{ if(el&&typeof el.animate==='function')el.animate(keyframes,opts); }catch(_){}
}
function cmdChoreograph(host){
  if(RM||CMD_LOAD_CHOREO_DONE)return;
  CMD_LOAD_CHOREO_DONE=true;
  try{
    // sentence: words fade/rise, 0-200ms, staggered
    Array.prototype.slice.call(host.querySelectorAll('.statusitem')).forEach((n,i)=>{
      cmdAnimate(n,[{opacity:0,transform:'translateY(4px)'},{opacity:1,transform:'none'}],
        {duration:200,delay:i*30,easing:'ease-out'});
    });
    // vitals: tiles settle in 60ms steps, 200-800ms (spec 4.1's mission-
    // control-style "bento cells settle in 60ms steps" graft, applied here)
    const vitals=Array.prototype.slice.call(host.querySelectorAll('.vitals .vital'));
    vitals.forEach((n,i)=>{
      cmdAnimate(n,[{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'none'}],
        {duration:240,delay:200+i*60,easing:'cubic-bezier(0,0,.2,1)'});
    });
    // ring graphics: stroke-dashoffset draws in from empty to its real value
    Array.prototype.slice.call(host.querySelectorAll('.gfx-ringv,.gfx-ringbig')).forEach((svg,i)=>{
      const circ=svg.querySelector('circle[stroke-dasharray]');
      if(!circ)return;
      const dash=circ.getAttribute('stroke-dasharray')||'';
      const total=(parseFloat(dash.split(' ')[1])||parseFloat(dash.split(' ')[0])||0);
      if(!total)return;
      cmdAnimate(circ,[{strokeDashoffset:total},{strokeDashoffset:0}],
        {duration:500,delay:220+i*40,easing:'cubic-bezier(0,0,.2,1)'});
    });
    // sparkline: the line path draws in via its own true length
    Array.prototype.slice.call(host.querySelectorAll('.gfx-sparkv path[stroke]:not([stroke="none"])')).forEach((p,i)=>{
      let len=0; try{len=p.getTotalLength();}catch(_){}
      if(!len)return;
      cmdAnimate(p,[{strokeDasharray:len+'px',strokeDashoffset:len+'px'},
                    {strokeDasharray:len+'px',strokeDashoffset:0}],
        {duration:520,delay:240+i*40,easing:'cubic-bezier(0,0,.2,1)'});
    });
    // heatmap: cells stagger 12ms each (spec 10.5's literal figure)
    Array.prototype.slice.call(host.querySelectorAll('.gfx-heatv rect')).forEach((r,i)=>{
      cmdAnimate(r,[{opacity:0,transform:'scale(.5)'},{opacity:1,transform:'none'}],
        {duration:180,delay:260+i*12,easing:'ease-out'});
    });
    // day-line ticks fade in alongside the cursor's own stroke-draw (100-400ms)
    Array.prototype.slice.call(host.querySelectorAll('.dayline__tick')).forEach((n,i)=>{
      cmdAnimate(n,[{opacity:0},{opacity:1}],{duration:200,delay:100+i*20,easing:'ease-out'});
    });
  }catch(_){}
}

/* ---------- vCommand ---------- */
function vCommand(h){
  h.appendChild(cmdSentence());
  h.appendChild(cmdDayline());
  h.appendChild(cmdVitals());
  h.appendChild(cmdStage());
  h.appendChild(cmdGoalStrip());
  h.appendChild(cmdGroup('group-needs-you','Needs you',cmdNeedsYouRows()));
  h.appendChild(cmdGroup('group-trading','Trading',cmdProducerRows('trading')));
  h.appendChild(cmdGroup('group-research','Research',cmdProducerRows('research')));
  h.appendChild(cmdGroup('group-rig','Rig',cmdProducerRows('rig')));
  if(typeof tilesInit==='function'){try{tilesInit();}catch(_){}}
  cmdConfetti();
  cmdChoreograph(h);
}
"""

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
  const a=D.army; if(!a)return{verdict:'none',text:'agents NO DATA'};
  const c=cmdArmyCounts(a);
  return{
    verdict:c.running>0?'green':'off',
    text:'<b>'+c.running+'</b> agent'+(c.running===1?'':'s')+' running, <b>'+c.waiting+'</b> waiting for you',
  };
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
function cmdGateClause(){
  const gt=D.gate; if(!gt||gt.ok===false)return{verdict:'none',text:'gate NO DATA'};
  const s=gt.say||gt.overall_verdict||gt.verdict||null;
  if(!s)return{verdict:'none',text:'gate NO DATA'};
  return{verdict:cmdGateVerdict(gt),text:'Gate '+cmdWrapDigits(s)};
}
function cmdStatusItem(clause){
  const item=el('span','statusitem'); item.dataset.verdict=clause.verdict||'none';
  item.appendChild(el('i','vd'));
  const t=el('span','statusitem__t'); t.innerHTML=clause.text; item.appendChild(t);
  return item;
}
function cmdSentence(){
  const wrap=el('div','statusrow sentence');
  [cmdMarketClause(),cmdArmyClause(),cmdBookClause(),cmdGateClause()]
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
  let prevPos=null, prevAlt=false;
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
    const alt=(prevPos!=null&&!prevAlt&&(pos-prevPos)<LBL_PCT);
    if(alt)tk.dataset.alt='1';
    prevPos=pos; prevAlt=alt;
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
  wrap.appendChild(cmdStagePulseLine());
  return wrap;
}

/* ---------- 4. GOAL + BUDGET BAND ---------- */
function cmdGoalTile(){
  const A=D.autonomy||{}, g=D.goal||A.goal||null;
  const q=(g&&g.queue)||[];
  const done=q.filter(x=>x.state==='done').length, total=q.length;
  const gfx=total?cmdGfx('gfxRingBig',done,total):'';
  const active=!!(g&&g.active);
  let say;
  if(!active){
    say='NOT DRIVING. no active goal';
  }else{
    const bits=[esc(g.next_item||'no open item')];
    if(g.days_left!=null)bits.push('<b>'+g.days_left+'</b> days left');
    say=bits.join('. ');
  }
  const spec={
    id:'tile-goal', icon:'target',
    title:(g&&(g.title||g.id))||'No active goal',
    verdict:active?'none':'off',
    gfx:gfx||'',
    say:say,
    src:{path:(g&&g.source)||'goal file', stamp:(g&&g.opened_at_et)||null},
    fresh_h:24*7,
    body:(host)=>{
      if(typeof goalBody==='function')goalBody(host);
      else host.appendChild(el('div','mut','NO DATA, goalBody is not wired yet'));
    },
  };
  return(typeof tileRow==='function')?tileRow(spec):cmdRowFallback(spec);
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
function cmdBudgetPane(){
  /* ONE 64-72px row (Fable review, 2026-09-03, item 1): fires meter, spend
     figure, an inline sparkline, source+age -- all in one flex row beside the
     goal row, not stacked into their own ~240px column. See module docstring
     for the contract this reuses (cmdGfx/cmdUsd/cmdCostSeries unchanged). */
  const A=D.autonomy||{}, bud=A.budget||{};
  const pane=el('div','band__budget');
  const row=el('div','band__budget-row');

  const firesWrap=el('div','band__budget-fires');
  const firesTxt=(bud.fires_used!=null&&bud.fires_cap!=null)?('Fires <b>'+bud.fires_used+'</b>/<b>'+bud.fires_cap+'</b>'):'Fires NO DATA';
  firesWrap.appendChild(el('span','meta',firesTxt));
  const meterS=cmdGfx('gfxMeter',bud.fires_used,bud.fires_cap);
  if(meterS){const g=el('span','band__budget-meter');g.innerHTML=meterS;firesWrap.appendChild(g);}
  row.appendChild(firesWrap);

  /* round-2 review (major): "$34.56 / $30.00" is 115% of budget but rendered in the
     same neutral ink as every on-budget figure -- the one number most likely to
     matter to J at a glance carried zero visual alarm. Over cap now gets the figure's
     own `.over` class (--warn, the CAUTION hue -- a budget overrun is not P&L, so
     --neg stays off-limits here) plus an explicit "+$X over" delta so it reads as a
     problem in the first second, not the tenth. */
  const over=(bud.spent_usd!=null&&bud.cap_usd!=null&&Number(bud.spent_usd)>Number(bud.cap_usd))
    ?Number(bud.spent_usd)-Number(bud.cap_usd):0;
  const CM=D.cost_meter||{};
  const figure=el('span','figure mono band__budget-figure'+(over>0?' over':''),cmdUsd(bud.spent_usd)+' / '+cmdUsd(bud.cap_usd));
  if(CM.as_of_et_date)figure.title='cost-meter '+CM.as_of_et_date;
  row.appendChild(figure);
  if(over>0)row.appendChild(el('span','meta over','+'+cmdUsd(over)));

  const vals=cmdCostSeries(CM);
  const sparkS=vals.length>=2?cmdGfx('gfxSpark',vals):'';
  if(sparkS){const sw=el('span','band__budget-spark');sw.innerHTML=sparkS;row.appendChild(sw);}

  /* basename, not srcRow()'s usual full path -- "automation/state/cost-meter.json"
     alone is wider than the fires block and the figure combined, which is what
     kept forcing a 3rd wrapped line here even after the rest of the row was
     already compact. srcRow's own last_write/age_h fallback stays intact by
     routing through it with a shortened path, rather than re-deriving the
     age here. */
  const srcWrap=el('div','band__budget-src');
  const src=D.cost_meter_source;
  if(src&&src.path){
    const base=_fnOf('tilesBaseName');
    srcWrap.appendChild(srcRow([Object.assign({},src,{path:base?base(src.path):src.path})]));
  }
  row.appendChild(srcWrap);

  pane.appendChild(row);
  return pane;
}
function cmdBand(){
  const band=el('div','band');
  const left=el('div','band__goal'); left.appendChild(cmdGoalTile());
  band.append(left,cmdBudgetPane());
  return band;
}

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
  return cards.filter(c=>!String(c.id||'').startsWith('card-goal-')).map(c=>{
    const spec={
      id:'card-'+String(c.id||c.rank||'').replace(/[^A-Za-z0-9_-]/g,'')||('card-'+(c.rank||0)),
      icon:'target',
      title:c.title||'',
      verdict:c.gated?'amber':'none',
      gfx:'',
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

/* ---------- vCommand ---------- */
function vCommand(h){
  h.appendChild(cmdSentence());
  h.appendChild(cmdDayline());
  h.appendChild(cmdStage());
  h.appendChild(cmdBand());
  h.appendChild(cmdGroup('group-needs-you','Needs you',cmdNeedsYouRows()));
  h.appendChild(cmdGroup('group-trading','Trading',cmdProducerRows('trading')));
  h.appendChild(cmdGroup('group-research','Research',cmdProducerRows('research')));
  h.appendChild(cmdGroup('group-rig','Rig',cmdProducerRows('rig')));
  if(typeof tilesInit==='function'){try{tilesInit();}catch(_){}}
  cmdConfetti();
}
"""

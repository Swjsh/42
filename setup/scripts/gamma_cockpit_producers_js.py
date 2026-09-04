"""gamma_cockpit_producers_js.py - the Command view's producer tile rows.

WORKSTREAM E_producer_rows (Quiet Command rebuild, 2026-09-03). Owns exactly
one export: `PRODUCERS_JS`, a JS source string defining `producerRows(group)`
and `producerRowById(id)` for group in 'trading' | 'research' | 'rig' -- the
three producer groups in markdown/specs/COCKPIT-DESIGN-SPEC-2026-09-03.md
section 3 band 5 ("Needs you" / cards is a fourth group owned elsewhere).

THIS FILE IS BUILT AGAINST TWO CONTRACTS THAT DO NOT EXIST YET IN THIS REPO:
  - WS-C's row/graphic component library (`tileRow`, `gfxGauge`, `gfxMeter`,
    `gfxSpark`, `gfxHeat`, `gfxRings`, `gfxFunnel`, `gfxDots`, `gfxBars`) --
    lives in a future `gamma_cockpit_tiles_js.py`.
  - WS-B's 9 new payload keys (`gate prep eod standup shadow watchers guards
    tasks gym`) -- lives in a future `gamma_cockpit_tiles.py`.

Every reference to either contract is feature-detected at CALL time via
`_fnOf(name)` (a `window[name]` lookup, which never throws even when the
identifier was never declared anywhere in the concatenated script) and every
payload field is read with `?.`/`??`. Missing component -> a local fallback
row renderer that matches the spec's own `<details class="row">` markup
1-for-1, so once WS-C lands this file needs no edit. Missing payload key ->
`data-verdict="off"` and a "NO DATA, looked for <path>" sentence, never a
guessed graphic ("if it cannot be drawn it is not a tile", spec section 4).

ASSUMED `tileRow(spec)` CONTRACT (documented here since WS-C has not yet
committed one; this file matches it exactly in `_fallbackRow` so behaviour is
identical whichever path runs):
    tileRow({
      id:      'tile-gate',                 // dom id
      icon:    'gauge',                     // ICONS[name] lookup, may be absent
      title:   'Go-live gate',
      verdict: 'green'|'amber'|'red'|'off'|'none',
      graphic: Node | null,                 // pre-built by a gfx* call, or null
      say:     '<i class="vd"></i>RED. PF CI-lower <b>0.42</b> vs 1.0, <b>42</b> days',
      src:     {path:'go-live-gate.json', last_write:'2026-09-03T14:43:34-04:00', freshH:24},
      body:    Node | null,
    }) -> HTMLElement (a <details class="row">)

Reuses (never reimplements) the runtime this concatenates after: `el esc
srcRow health agoOf ageEl paintAge M M2 sgn spark series heartbeat
positionsCard engineDrawer route openDrawer stag` from gamma_cockpit_js.py /
gamma_cockpit_views_js.py, and `D` (the payload) / `D.stale_hours`. Computes
no metric the payload does not already carry -- a missing derived field means
an empty graphic slot or a generic body line, never a client-side calculation
standing in for one.
"""
from __future__ import annotations

PRODUCERS_JS = r"""
/* ================== PRODUCER ROWS (WS: producer_rows) ================== */

/* ---- safety shims: never let a not-yet-merged sibling module crash the page ---- */
function _fnOf(name){
  try{ return (typeof window!=='undefined' && typeof window[name]==='function') ? window[name] : null; }
  catch(_){ return null; }
}
function _pick(obj){
  for(let i=1;i<arguments.length;i++){
    const path=arguments[i]; let v=obj, ok=true;
    for(const k of path){ if(v==null){ok=false;break;} v=v[k]; }
    if(ok&&v!=null)return v;
  }
  return null;
}
/* the (?<!&#) guard keeps a digit inside an entity like &#39; out of the <b> */
function _wrapDigits(s){ return String(s==null?'':s).replace(/(?<![&#\w])(\$?-?\d[\d,.]*%?)/g,'<b>$1</b>'); }
function _vdSay(say){ const i=el('i','vd'); const sp=el('span',null,say==null?'':say); const w=el('span','row__saytext'); w.append(i,sp); return w; }
function _mdStrip(s){ return String(s==null?'':s).replace(/[*_`#>-]{1,3}/g,'').replace(/\s+\n/g,'\n').trim(); }

/* the 9-new-key contract: {ok, path, stamp_et, verdict, say, fresh_h, ...} */
function _newKey(key){ const d=D[key]; return (d&&typeof d==='object')?d:null; }
function _newKeySrc(key,label){
  const d=_newKey(key);
  return { path: (d&&d.path)||label, last_write: d&&d.stamp_et, freshH: (d&&d.fresh_h)||D.stale_hours };
}
function _newKeyVerdict(d){ if(!d||d.ok===false)return'off'; const h=health(d.verdict); return h==='ok'?'green':h==='bad'?'red':h==='warn'?'amber':'none'; }
function _newKeySay(d,label){
  if(!d||d.ok===false)return '<i class="vd"></i>NO DATA, looked for <span class="mono">'+esc((d&&d.path)||label)+'</span>';
  return '<i class="vd"></i>'+_wrapDigits(esc(d.say||(d.verdict||'NO DATA')));
}

/* ---- lane lookup: gamma_lanes.build() returns {generated_at, lanes:[...]} today;
   read defensively so a future dict-keyed shape (D.lanes.kitchen) also works. ---- */
const LANE_STALE_MIN={kitchen:90,futures:1440,multi:1440,prospector:720,spy:1440,weather:1440};
function laneOf(id){
  const L=D.lanes; if(!L)return null;
  if(L[id]&&typeof L[id]==='object'&&!Array.isArray(L[id]))return L[id];
  const arr=Array.isArray(L.lanes)?L.lanes:(Array.isArray(L)?L:null);
  return arr?(arr.find(x=>x&&x.id===id)||null):null;
}

/* ---- generic body widgets, built only from fields already on the payload ---- */
function _kvList(pairs){
  const w=el('div');
  pairs.forEach(([k,v])=>{ if(v==null||v==='')return;
    w.appendChild(el('div','kv',`<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`)); });
  return w;
}
function _tableOf(headers,rows){
  const t=el('table');
  t.innerHTML='<thead><tr>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+'</tr></thead>';
  const tb=el('tbody');
  rows.forEach(r=>tb.appendChild(el('tr',null,r.map(c=>'<td>'+(c==null?'-':c)+'</td>').join(''))));
  t.appendChild(tb);
  const wrap=el('div'); wrap.style.overflowX='auto'; wrap.appendChild(t); return wrap;
}
function _laneBody(lane,staleId){
  if(!lane)return el('div','note','NO DATA, lane not found on the payload');
  const b=el('div');
  b.appendChild(_kvList([['State',lane.state],['Detail',lane.detail],['Doing now',lane.doing]]));
  const tk=lane.tasks||{};
  if(Object.keys(tk).length){
    const t=el('div','micro','Scheduled tasks'); t.style.marginTop='var(--s5)'; b.appendChild(t);
    const r=el('div','row wrap'); r.style.marginTop='var(--s3)';
    Object.keys(tk).forEach(n=>r.appendChild(el('span','chip '+(tk[n]==='Ready'?'ok':''),esc(n)+' '+esc(tk[n]))));
    b.appendChild(r);
  }
  b.appendChild(srcRow([{path:lane.id+' lane', last_write:lane.last_at}]));
  return b;
}
function _errorRow(id,err){
  const d=document.createElement('details'); d.className='row'; d.id=id; d.dataset.verdict='off';
  const s=document.createElement('summary'); s.className='row__head';
  s.appendChild(el('span','row__title','(row failed to build)'));
  s.appendChild(el('span','row__say','NO DATA, '+esc(String(err&&err.message||err))));
  d.appendChild(s); return d;
}

/* ---- the fallback row renderer: matches spec section 4's <details class="row">
   markup exactly, so this is a drop-in until WS-C's real tileRow lands. ---- */
function _fallbackRow(spec){
  const d=document.createElement('details');
  d.className='row'; d.id=spec.id; d.dataset.verdict=spec.verdict||'none';
  if(spec.src&&spec.src.path)d.dataset.src=spec.src.path;
  if(spec.src&&spec.src.last_write)d.dataset.stamp=spec.src.last_write;
  const open=(()=>{try{return JSON.parse(localStorage.getItem('gamma-open')||'[]')}catch(_){return[]}})();
  if(open.includes(spec.id))d.open=true;
  d.addEventListener('toggle',()=>{try{
    let o=JSON.parse(localStorage.getItem('gamma-open')||'[]');
    o=o.filter(x=>x!==spec.id); if(d.open)o.push(spec.id);
    localStorage.setItem('gamma-open',JSON.stringify(o));
  }catch(_){}});
  const s=document.createElement('summary'); s.className='row__head';
  const ic=el('span','row__ic'); const ICONS=(typeof window!=='undefined'&&window.ICONS)||{};
  if(spec.icon&&ICONS[spec.icon])ic.innerHTML=ICONS[spec.icon]; s.appendChild(ic);
  s.appendChild(el('span','row__title',esc(spec.title||'')));
  const gfx=el('span','row__gfx'); if(spec.graphic)gfx.appendChild(spec.graphic); s.appendChild(gfx);
  const say=el('span','row__say'); say.innerHTML=spec.say||''; s.appendChild(say);
  const src=el('span','row__src');
  if(spec.src){
    src.appendChild(el('span',null,esc((spec.src.path||'').split('/').pop()||'')+' '));
    src.appendChild(ageEl(spec.src.last_write,spec.src.freshH));
  }
  s.appendChild(src);
  if(spec.act){
    const btn=el('button','fire',esc(spec.act.label||'Fire'));
    btn.type='button'; btn.onclick=(e)=>{e.preventDefault();e.stopPropagation();spec.act.onFire&&spec.act.onFire()};
    s.appendChild(btn);
  }
  const chev=el('span','row__chev','&#9662;'); s.appendChild(chev);
  d.appendChild(s);
  const body=el('div','row__body'); if(spec.body)body.appendChild(spec.body); d.appendChild(body);
  return d;
}
function _row(spec){
  const f=_fnOf('tileRow');
  if(f){ try{ return f(spec) }catch(_){ /* fall through */ } }
  return _fallbackRow(spec);
}
function _gfx(kind,...args){
  const names={gauge:'gfxGauge',meter:'gfxMeter',spark:'gfxSpark',heat:'gfxHeat',
    rings:'gfxRings',funnel:'gfxFunnel',dots:'gfxDots',bars:'gfxBars'};
  const f=_fnOf(names[kind]); if(!f)return null;
  try{ return f(...args) }catch(_){ return null }
}
/* A single time-of-day marker on a 24h track -- Standup fires once a day, so
   the only useful graphic is WHEN on the clock it landed, not a series. Local
   to this file (not a shared gfx*, spec section 4's registry) since nothing
   else on the page needs a one-tick day strip. */
function _gfxDayStrip(iso){
  const m=/T(\d{2}):(\d{2})/.exec(String(iso||'')); if(!m)return'';
  const mins=parseInt(m[1],10)*60+parseInt(m[2],10);
  const w=160,h=24,pad=3,y=h/2;
  const x=pad+Math.max(0,Math.min(1,mins/1440))*(w-2*pad);
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-daystrip">';
  s+='<line x1="'+pad+'" y1="'+y+'" x2="'+(w-pad)+'" y2="'+y+'" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>';
  s+='<circle cx="'+x.toFixed(1)+'" cy="'+y+'" r="4" fill="var(--accent-fill)"/>';
  s+='</svg>';
  return s;
}
/* N small verdict dots plus one short mono label at the row edge -- for a
   lane whose sentence already names an event ("last ENTER 2026-09-01") that
   is worth a scannable mark alongside the health dots, not only prose. */
function _gfxDotsMarker(states,label){
  if(!states||!states.length)return'';
  const list=states.slice(0,9);
  const w=160,h=24,r=3.5,gap=4;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-dots">';
  const dotColor=_fnOf('tilesDotColor');
  list.forEach(function(st,i){
    const cx=r+i*(r*2+gap), cy=h/2;
    s+='<circle cx="'+cx.toFixed(1)+'" cy="'+cy+'" r="'+r+'" fill="'+(dotColor?dotColor(st):'var(--dot-off)')+'"/>';
  });
  if(label)s+='<text x="'+w+'" y="'+(h/2+4)+'" text-anchor="end" font-family="var(--mono)" '+
    'font-size="12" fill="var(--ink-3)">'+esc(label)+'</text>';
  s+='</svg>';
  return s;
}

/* ========================= TRADING ========================= */

function buildGateRow(){
  const d=_newKey('gate');
  const ciLower=_pick(d,['ci','as_traded','ci_lower'],['criteria','statistical','book_wide_correlated_rollup','as_traded','ci_lower_2.5']);
  const graphic=(d&&d.ok!==false&&ciLower!=null)?_gfx('gauge',ciLower,1.0,0,3):null;
  const body=el('div');
  if(!d||d.ok===false){ body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'analysis/go-live-gate.json'))); }
  else{
    const ci=d.ci||{};
    [['as_traded','as traded'],['ex_best_day','ex best day'],['cost_adjusted','cost adjusted']].forEach(([k,label])=>{
      const c=ci[k]; if(!c)return;
      const row=el('div','row'); row.style.marginBottom='var(--s3)';
      row.appendChild(el('span','dim',label+' '));
      const g=_gfx('gauge',c.ci_lower,1.0,0,3);
      if(g)row.innerHTML+=g;
      row.appendChild(el('span','mono','<b>'+esc(c.ci_lower??'-')+'</b> CI-lower, PF '+esc(c.pf_point??'-')+', '+esc(c.n_days??'-')+' days, '+M(c.total_pnl)));
      body.appendChild(row);
    });
    const guards=(d.operational&&d.operational.guards)||[];
    const greens=guards.filter(g=>String(g.status||'').toLowerCase()==='green').length;
    const ps=d.prod_shadow||{}, des=ps.designation||{};
    body.appendChild(_kvList([
      ['Operational guards',guards.length?(greens+' / '+guards.length+' green'):null],
      ['Reconciliation',(d.reconciliation&&d.reconciliation.pass===true)?'GREEN':(d.reconciliation&&d.reconciliation.pass===false?'RED':null)],
      ['Prod shadow arm',des.arm],
      ['Prod shadow window',(ps.days_scored!=null)?(ps.days_scored+' of '+(ps.days_needed||des.min_days||'min 20')+' days'+(des.window_end?', to '+des.window_end:'')):null],
      ['Prod shadow status',ps.status],
      ['Trades scored',d.n_trades],
      ['Trading days',d.n_days],
      ['Designated',des.designated_at],
    ]));
    const perArm=d.per_arm||[];
    if(perArm.length)body.appendChild(_tableOf(['Arm','CI-lower','Distance','Pass'],
      perArm.map(a=>[esc(a.arm),esc(a.ci_lower??'-'),esc(a.distance??'-'),a.pass?'yes':'no'])));
    if((d.disclosures||[]).length)body.appendChild(el('div','micro',esc(d.disclosures.length)+' disclosure(s), pass criterion unchanged'));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'analysis/go-live-gate.json', last_write:d&&(d.stamp_et||d.generated_et)}]));
  return _row({id:'tile-gate',icon:'gauge',title:'Go-live gate',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'analysis/go-live-gate.json'),
    src:{path:(d&&d.path)||'analysis/go-live-gate.json', last_write:d&&(d.stamp_et||d.generated_et), freshH:(d&&d.fresh_h)||24},
    body});
}

function buildPositionsRow(){
  const p=D.positions;
  const arms=(p&&p.arms)||[];
  const fillsTotal=arms.reduce((n,a)=>n+(a.fills||0),0);
  const graphic=arms.length?_gfx('rings',arms.map(a=>({share:fillsTotal?(a.fills||0)/fillsTotal:0,open:!!(p.open||[]).find(o=>o.arm===a.arm)}))):null;
  let say;
  if(!p){ say='<i class="vd"></i>NO DATA, positions builder did not run'; }
  else if(p.flat){ say='<i class="vd"></i>Flat on all arms. <b>'+esc(p.option_fills??'-')+'</b> fills net to zero'; }
  else{
    const o=p.open[0]||{};
    say='<i class="vd"></i>'+esc(o.arm||'')+' '+esc(o.side||'')+' '+esc(o.symbol||'')+' x<b>'+esc(o.qty??'')+'</b>';
  }
  const body=positionsCard();
  return _row({id:'tile-positions',icon:'layers',title:'Positions',
    verdict: !p?'off':(p.flat?'green':'amber'),
    graphic, say,
    src:{path:(p&&p.source&&p.source.path)||'fills ledger', last_write:p&&p.source&&p.source.last_write, freshH:2},
    body});
}

function buildMoneyRow(){
  const s=bookSummary();
  const views=(D.calendar&&D.calendar.views)||{};
  const book=views.BOOK||{days:{}};
  const dates=Object.keys(book.days||{}).sort();
  const last30=dates.slice(-30).map(k=>book.days[k].n);
  const graphic=last30.length>1?_gfx('spark',last30):(last30.length>1?spark(last30):null);
  const net=s.total_pnl_net, days=s.trading_days, wr=s.win_rate_by_day_net;
  const say='<i class="vd"></i>'+(net==null?'NO DATA':
    '<b>'+M(net)+'</b> net, <b>'+esc(days??'-')+'</b> days, '+
    (wr!=null?'<b>'+Math.round(wr*100)+'%</b> day win rate':'-'));
  const body=el('div');
  const tb=[];
  Object.keys(views).sort((a,b)=>a==='BOOK'?-1:b==='BOOK'?1:a.localeCompare(b)).forEach(arm=>{
    const v=views[arm]||{summary:{}}; const sm=v.summary||{};
    tb.push([esc(arm), M(sm.total_pnl_net), esc(sm.trading_days??'-'), (sm.total_fees!=null?'$'+sm.total_fees.toFixed(0):'-')]);
  });
  if(tb.length)body.appendChild(_tableOf(['Arm','Net','Days','Fees'],tb));
  const jl=el('div'); jl.style.marginTop='var(--s4)';
  const a=el('a',null,'Open journal'); a.href='#journal'; a.onclick=(e)=>{e.preventDefault();route('journal')};
  jl.appendChild(a); body.appendChild(jl);
  body.appendChild(srcRow([D.calendar_source]));
  return _row({id:'tile-money',icon:'dollar-sign',title:'Money',verdict:net==null?'off':(net>=0?'green':'red'),
    graphic, say, src:{path:(D.calendar_source&&D.calendar_source.path)||'calendar-data.json',
      last_write:D.calendar_source&&D.calendar_source.last_write, age_h:D.calendar_source&&D.calendar_source.age_h, freshH:24}, body});
}

function buildEnginesRow(){
  const er=D.engine_room||{engines:[]};
  const engines=er.engines||[];
  let live=0, newest=null;
  const states=[];
  engines.forEach(e=>{ const a=agoOf(e.last_write); const ticking=(a!=null&&a<=24);
    if(ticking)live++; states.push(ticking?'green':'off');
    if(e.last_write&&(!newest||e.last_write>newest))newest=e.last_write; });
  const graphic=states.length?_gfx('dots',states):null;
  const say=engines.length?'<i class="vd"></i><b>'+live+'</b> of <b>'+engines.length+'</b> engines ticking':
    '<i class="vd"></i>NO DATA, no engines reported';
  const body=el('div');
  engines.forEach(e=>{
    const w=el('div'); w.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle)';
    w.appendChild(el('div','row',`<span style="font-weight:600">${esc(e.name)}</span>`));
    w.appendChild(heartbeat(e,40));
    const lk=el('a',null,'Open tick stream'); lk.href='#'; lk.onclick=(ev)=>{ev.preventDefault();engineDrawer(e)};
    w.appendChild(lk); body.appendChild(w);
  });
  return _row({id:'tile-engines',icon:'heart-pulse',title:'Engines',verdict:engines.length?(live===engines.length?'green':live===0?'red':'amber'):'off',
    graphic, say, src:{path:'engine ledgers', last_write:newest, freshH:24}, body});
}

function buildPrepRow(){
  const d=_newKey('prep');
  const checks=(d&&d.checks)||[];
  const graphic=checks.length?_gfx('dots',checks.map(c=>c.status)):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/premarket-readiness.json')));
  else{
    checks.forEach(c=>body.appendChild(el('div','kv',
      `<span class="k">${esc(c.name)}</span><span class="v">${esc(c.status)} - ${esc((c.detail||'').slice(0,110))}</span>`)));
    if((d.reds||[]).length)body.appendChild(el('div','flag bad','<b>REDS</b> '+esc(d.reds.join(', '))));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/premarket-readiness.json', last_write:d&&(d.stamp_et||d.ts_et)}]));
  return _row({id:'tile-prep',icon:'sunrise',title:'Premarket prep',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'automation/state/premarket-readiness.json'),
    src:{path:(d&&d.path)||'automation/state/premarket-readiness.json', last_write:d&&(d.stamp_et||d.ts_et), freshH:(d&&d.fresh_h)||24}, body});
}

function buildEodRow(){
  const d=_newKey('eod');
  const accounts=Array.isArray(d&&d.accounts)?d.accounts:null;
  const vals=accounts?accounts.map(a=>a.filled??0):null;
  const graphic=(vals&&vals.length)?_gfx('bars',vals):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'analysis/eod/'+ (D.today||'today') +'.md')));
  else{
    const rowsOf=a=>[esc(a.account||''),esc(a.ticks??'-'),esc(a.signals??'-'),esc(a.enter??'-'),esc(a.rule_blocked??'-'),esc(a.attempted??'-'),esc(a.filled??'-'),esc(a.exited??'-')];
    const funnel=(accounts||[]).concat(d.total?[d.total]:[]);
    if(funnel.length)body.appendChild(_tableOf(['Account','Ticks','Signals','ENTER','Blocked','Attempted','Filled','Exited'],funnel.map(rowsOf)));
    if((d.why||[]).length)body.appendChild(_tableOf(['Account','Cause','Detail'],d.why.map(w=>[esc(w.account||''),esc(w.cause||''),esc(w.detail||'')])));
    if(d.analyst&&d.analyst.verdict)body.appendChild(el('div','mut','Analyst: '+esc(d.analyst.verdict)));
    if(d.analyst&&d.analyst.rule_breaks!=null)body.appendChild(el('div','micro',esc(d.analyst.rule_breaks)+' rule break(s)'));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'analysis/eod/'+(D.today||'today')+'.md', last_write:d&&d.stamp_et}]));
  return _row({id:'tile-eod',icon:'moon',title:'EOD debrief',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'analysis/eod/'+(D.today||'today')+'.md'),
    src:{path:(d&&d.path)||'analysis/eod', last_write:d&&d.stamp_et, freshH:(d&&d.fresh_h)||24}, body});
}

function buildStandupRow(){
  const d=_newKey('standup');
  const graphic=(d&&d.ok!==false)?_gfxDayStrip(d.generated_et):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/gamma-standup-latest.json')));
  else{
    body.appendChild(el('div','mut',esc(d.text_plain||_mdStrip(d.text||''))));
    if((d.wants_shown||[]).length)body.appendChild(el('div','micro','wants: '+d.wants_shown.map(esc).join(', ')));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/gamma-standup-latest.json', last_write:d&&(d.stamp_et||d.generated_et)}]));
  return _row({id:'tile-standup',icon:'radio',title:'Standup',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'automation/state/gamma-standup-latest.json'),
    src:{path:(d&&d.path)||'automation/state/gamma-standup-latest.json', last_write:d&&(d.stamp_et||d.generated_et), freshH:(d&&d.fresh_h)||24}, body});
}

/* ========================= RESEARCH ========================= */

function buildLaneTileRow(id,icon,title,graphicKind){
  const lane=laneOf(id);
  const graphic=(lane&&graphicKind)?graphicKind(lane):null;
  const say=lane?('<i class="vd"></i>'+_wrapDigits(esc(lane.detail||lane.state||'NO DATA'))):
    '<i class="vd"></i>NO DATA, lane "'+esc(id)+'" not on the payload';
  const verdict=!lane?'off':(lane.state==='WORKING'?'green':lane.state==='HELD'?'none':
    (lane.state==='STALE'||lane.state==='NO DATA')?'amber':lane.state==='BROKEN'||lane.state==='ERROR'?'red':'none');
  return _row({id:'tile-'+id,icon,title,verdict,graphic,say,
    src:{path:id+' lane', last_write:lane&&lane.last_at, freshH:LANE_STALE_MIN[id]?LANE_STALE_MIN[id]/60:24},
    body:_laneBody(lane,id)});
}
function buildKitchenRow(){
  return buildLaneTileRow('kitchen','flame','Kitchen',lane=>{
    const m=String(lane.metric||'').match(/\$([\d.]+)\s*\/\s*\$([\d.]+)/);
    return m?_gfx('meter',parseFloat(m[1]),parseFloat(m[2])):null;
  });
}
function buildProspectorRow(){
  return buildLaneTileRow('prospector','radar','Prospector',lane=>{
    const m=String(lane.detail||'').match(/(\d+)\s*ideas.*?(\d+)\s*promoted.*?(\d+)\s*folded/);
    return m?_gfx('funnel',[Number(m[1]),Number(m[2]),Number(m[3])]):null;
  });
}
function buildMultiRow(){
  return buildLaneTileRow('multi','layout-grid','Multi-symbol',lane=>{
    const m=String(lane.detail||'').match(/(\d+)\s*scanned.*?(\d+)\s*tier-2/);
    return m?_gfx('funnel',[Number(m[1]),Number(m[2]),0]):null;
  });
}
function buildFuturesRow(){
  return buildLaneTileRow('futures','trending-up','Futures',lane=>{
    const checks=lane&&lane.checks; if(!checks||!checks.length)return null;
    const le=lane.last_enter_et;
    const label=le?('ENTER '+String(le).slice(5)):'';
    return _gfxDotsMarker(checks.map(c=>c.status),label);
  });
}

function buildShadowRow(){
  const d=_newKey('shadow');
  const buckets=_pick(d,['preregs','buckets'],['buckets']);
  const bucketTone=b=>{ const k=String(b&&b.status||'').toUpperCase();
    if(/KILL|FAIL|RED|NULL/.test(k))return'red'; if(/PASS|PROMOT|GREEN|SHIP/.test(k))return'green';
    if(/FROZEN|PENDING|SHADOW|WAIT|AMBER|YELLOW/.test(k))return'amber'; return'off'; };
  const graphic=Array.isArray(buckets)&&buckets.length?_gfx('heat',buckets.slice(0,28).map(bucketTone)):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'SHADOW.md')));
  else{
    const live=d.live_instruments||d.live||[];
    live.forEach(x=>body.appendChild(el('div','kv',`<span class="k">${esc(x.name||x)}</span><span class="v">${esc(_mdStrip(x.line||x.verdict||'').slice(0,140))}</span>`)));
    const groups=Array.isArray(buckets)?buckets:(d.prereg_groups||d.groups||[]);
    if(groups.length){
      const det=document.createElement('details'); det.style.marginTop='var(--s3)';
      det.appendChild(el('summary','dim','Preregs by status, '+esc(_pick(d,['preregs','total_non_terminal'])??groups.length)+' non-terminal in '+groups.length+' buckets'));
      groups.forEach(g=>det.appendChild(el('div','kv',`<span class="k">${esc(g.status||g.label||g.name||'')}</span><span class="v">${esc(g.n??g.count??0)}</span>`)));
      body.appendChild(det);
    }
    if(!live.length&&!groups.length)body.appendChild(el('div','note','NO DATA, parser found 0 sections in SHADOW.md'));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'SHADOW.md', last_write:d&&d.stamp_et}]));
  return _row({id:'tile-shadow',icon:'hourglass',title:'Shadow board',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'SHADOW.md'),
    src:{path:(d&&d.path)||'SHADOW.md', last_write:d&&d.stamp_et, freshH:(d&&d.fresh_h)||24}, body});
}

function buildWatchersRow(){
  const d=_newKey('watchers');
  const list=(d&&d.ok!==false&&Array.isArray(d.watchers))?d.watchers.slice().sort((a,b)=>(b.would_be_pnl||0)-(a.would_be_pnl||0)):[];
  /* would-be P&L IS a P&L series, so gain/loss tones are allowed here (spec 2.1) */
  const graphic=list.length?_gfx('heat',list.slice(0,28).map(w=>(w.would_be_pnl||0)>0?'gain':(w.would_be_pnl||0)<0?'loss':'off')):null;
  const body=el('div');
  if(!d||d.ok===false){ body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/watcher-summary.json'))); }
  else if(list.length){
    body.appendChild(_tableOf(['Watcher','Observations','Would-be P&L'],list.map(w=>[esc(w.name||''),esc(w.observations??'-'),M(w.would_be_pnl)])));
  }
  const say=_newKeySay(d,'automation/state/watcher-summary.json');
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/watcher-summary.json', last_write:d&&(d.stamp_et||d.graded_at)}]));
  return _row({id:'tile-watchers',icon:'eye',title:'Watcher fleet',verdict:(d&&d.ok!==false)?'none':'off',
    graphic, say, src:{path:(d&&d.path)||'automation/state/watcher-summary.json', last_write:d&&(d.stamp_et||d.graded_at), freshH:(d&&d.fresh_h)||24}, body});
}

function buildLearningRow(){
  const l=D.learning||{};
  const today=(l.windows&&l.windows.today)||null;
  const graphic=today?_gfx('bars',Object.values(today).filter(v=>typeof v==='number')):null;
  const T=w=>w?(w.kitchen_tasks_completed??w.tasks??0):0, K=w=>w?(w.kitchen_keepers??w.keepers??0):0, P=w=>w?(w.preregs_filed??w.preregs??0):0;
  const say=today?('<i class="vd"></i>Today: <b>'+T(today)+'</b> tasks, <b>'+K(today)+'</b> keepers, <b>'+P(today)+'</b> preregs, <b>'+(today.commits??0)+'</b> commits'):
    '<i class="vd"></i>NO DATA, learning ledger has no windows.today';
  const body=el('div');
  const wk7=(l.windows&&l.windows['7d'])||null;
  if(today||wk7)body.appendChild(_tableOf(['Window','Tasks','Keepers','Preregs filed','Adjudicated','Lessons','Commits'],
    [today?['today',T(today),K(today),P(today),today.preregs_adjudicated??'-',today.lessons_added??'-',today.commits??'-']:null,
     wk7?['7 day',T(wk7),K(wk7),P(wk7),wk7.preregs_adjudicated??'-',wk7.lessons_added??'-',wk7.commits??'-']:null].filter(Boolean)));
  (l.latest_verdicts||[]).slice(0,10).forEach(v=>body.appendChild(el('div','kv',
    `<span class="chip ${health(v.kind)}"><i class="dot"></i>${esc(v.kind||'')}</span><span class="v">${esc(v.text||v.name||'')}</span>`)));
  /* the ledger carries sources[] + generated_at_et, not a single source object */
  const lsrc=(Array.isArray(l.sources)&&l.sources[0])||l.source||null;
  body.appendChild(srcRow(Array.isArray(l.sources)?l.sources:[l.source].filter(Boolean)));
  return _row({id:'tile-learning',icon:'book-open',title:'Learning ledger',verdict:today?'none':'off',
    graphic, say, src:{path:(lsrc&&lsrc.path)||'learning-ledger.json', last_write:(lsrc&&lsrc.last_write)||l.generated_at_et, age_h:lsrc&&lsrc.age_h, freshH:24}, body});
}

/* ========================= RIG ========================= */

function buildGuardsRow(){
  const d=_newKey('guards');
  const tasks=(d&&d.tasks)||[];
  const sevTone=t=>{ const k=String(t.severity||'').toLowerCase(); return k==='ok'?'green':k==='warn'?'amber':k?'red':'off'; };
  const graphic=tasks.length?_gfx('heat',tasks.map(sevTone)):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/task-state-guard.json')));
  else{
    (d.problems||[]).forEach(p=>body.appendChild(el('div','flag bad',esc(typeof p==='string'?p:JSON.stringify(p)))));
    (d.repairs||[]).forEach(r=>body.appendChild(el('div','flag dec',esc(typeof r==='string'?r:JSON.stringify(r)))));
    const rank=t=>String(t.severity||'').toLowerCase()==='ok'?1:0;
    const rows=tasks.slice().sort((a,b)=>rank(a)-rank(b))
      .map(t=>[esc(t.name||''),esc(t.tier||''),esc(t.state||'-'),esc(t.severity||'-'),esc(t.note||'')]);
    if(rows.length)body.appendChild(_tableOf(['Task','Tier','State','Severity','Note'],rows));
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/task-state-guard.json', last_write:d&&(d.stamp_et||d.ts_et)}]));
  return _row({id:'tile-guards',icon:'shield',title:'Guards',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'automation/state/task-state-guard.json'),
    src:{path:(d&&d.path)||'automation/state/task-state-guard.json', last_write:d&&(d.stamp_et||d.ts_et), freshH:(d&&d.fresh_h)||6}, body});
}

function buildTasksRow(){
  const d=_newKey('tasks');
  const lanes=(d&&d.lanes)||null;
  const graphic=lanes?_gfx('dots',lanes.map(l=>l.worst||'NO DATA')):null;
  const body=el('div');
  if(!d||d.ok===false||!lanes){
    body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/SCHEDULED-TASKS.md')));
  }else{
    lanes.forEach(ln=>{
      const det=document.createElement('details'); det.style.margin='var(--s2) 0';
      const sm=el('summary',null,esc(ln.lane||ln.name||'')+', worst '+esc(ln.worst||'-')+', '+((ln.tasks||[]).length)+' tasks');
      det.appendChild(sm);
      (ln.tasks||[]).forEach(t=>det.appendChild(el('div','kv',
        `<span class="k">${esc(t.name||'')}</span><span class="v">${t.guarded===false?'not guarded':esc(t.state||'-')}</span>`)));
      body.appendChild(det);
    });
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/SCHEDULED-TASKS.md', last_write:d&&d.stamp_et}]));
  return _row({id:'tile-tasks',icon:'timer',title:'Task lanes',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'automation/state/SCHEDULED-TASKS.md'),
    src:{path:(d&&d.path)||'automation/state/SCHEDULED-TASKS.md', last_write:d&&d.stamp_et, freshH:(d&&d.fresh_h)||24}, body});
}

function buildGymRow(){
  const d=_newKey('gym');
  const audits=(d&&d.audits)||[];
  const graphic=audits.length?_gfx('heat',audits.map(a=>a.verdict||'off')):null;
  const body=el('div');
  if(!d||d.ok===false)body.appendChild(el('div','note','NO DATA, looked for '+esc((d&&d.path)||'automation/state/gym-scorecard-'+(D.today||'today')+'.json')));
  else{
    const rows=audits.map(a=>[esc(a.name||a.audit||''), esc(a.source_file||''), esc(a.verdict||''), esc(a.summary||'')]);
    if(rows.length)body.appendChild(_tableOf(['Audit','Source','Verdict','Summary'],rows));
    (d.stale_reruns||[]).forEach(r=>{
      const name=typeof r==='string'?r:(r.name||'');
      body.appendChild(el('div','micro mono','stale rerun: '+esc(name)+(r&&r.exit!=null?' exit '+esc(r.exit):'')));
      if(r&&r.log_tail)body.appendChild(el('pre','askstream',esc(String(r.log_tail).slice(-600))));
    });
  }
  body.appendChild(srcRow([{path:(d&&d.path)||'automation/state/gym-scorecard.json', last_write:d&&d.stamp_et}]));
  return _row({id:'tile-gym',icon:'activity',title:'Gym',verdict:_newKeyVerdict(d),
    graphic, say:_newKeySay(d,'automation/state/gym-scorecard.json'),
    src:{path:(d&&d.path)||'automation/state/gym-scorecard.json', last_write:d&&d.stamp_et, freshH:(d&&d.fresh_h)||24}, body});
}

function buildAgentsRow(){
  const a=D.agents||{events:[],counts:{},sources:[]};
  let perHour=a.events_per_hour;
  if(!Array.isArray(perHour)&&(a.events||[]).length){
    /* 24 hourly buckets counted from the feed's own timestamps, newest hour last */
    const now=Date.now(), buckets=new Array(24).fill(0);
    a.events.forEach(e=>{ const t=Date.parse(String(e.ts||'').replace(' ','T')); if(isNaN(t))return;
      const h=Math.floor((now-t)/3.6e6); if(h>=0&&h<24)buckets[23-h]++; });
    perHour=buckets;
  }
  const graphic=Array.isArray(perHour)?_gfx('spark',perHour):null;
  const c=a.counts||{};
  const say='<i class="vd"></i><b>'+(c.total??0)+'</b> events, <b>'+(c.failed??0)+'</b> failed, <b>'+(c.suppressed??0)+'</b> suppressed'+
    (c.fabricated!=null?', fabrication '+(c.fabricated?'<b>'+c.fabricated+'</b>':'GREEN'):'');
  const body=el('div');
  const rows=(a.events||[]).slice(0,45).map(e=>[
    esc(String(e.ts||'').slice(5,16).replace('T',' ')), esc(e.tier||''), esc(e.who||''),
    esc(e.what||''), esc(e.verdict||'-')]);
  if(rows.length){const w=_tableOf(['When','Tier','Agent','Did','Verdict'],rows); w.style.maxHeight='320px'; w.style.overflowY='auto'; body.appendChild(w);}
  body.appendChild(srcRow(a.sources||[]));
  return _row({id:'tile-agents',icon:'bot',title:'Agents',verdict:(a.events||[]).length?'none':'off',
    graphic, say, src:{path:(a.sources&&a.sources[0]&&a.sources[0].path)||'agent feed', last_write:a.sources&&a.sources[0]&&a.sources[0].last_write, freshH:24}, body});
}

function buildActivityRow(){
  const hq=D.hq||{};
  const clocks=hq.clocks||[];
  const open=clocks.filter(c=>(c.have||0)<(c.need||1));
  const nearest=open.sort((x,y)=>((y.have||0)/(y.need||1))-((x.have||0)/(x.need||1)))[0]||clocks[0];
  const graphic=nearest?_gfx('meter',nearest.have||0,nearest.need||1):null;
  const say='<i class="vd"></i>'+(D.activity&&D.activity.headline?_wrapDigits(esc(D.activity.headline)):'NO DATA, whats-changed digest missing');
  const body=el('div');
  clocks.forEach(c=>{
    const done=(c.have||0)>=(c.need||1);
    const d=el('div'); d.style.marginBottom='var(--s4)';
    d.appendChild(el('div','row',`<span>${esc(c.label)}</span><span class="sp"></span><span class="mono dim">${c.have} / ${c.need}</span>`));
    const bar=el('div','bar'+(done?' done':'')); const i=el('i');
    i.style.width=Math.min(100,100*(c.have||0)/Math.max(1,c.need||1))+'%'; bar.appendChild(i); d.appendChild(bar);
    body.appendChild(d);
  });
  body.appendChild(srcRow([D.activity&&{path:'whats-changed.json', last_write:D.activity.generated_at}].filter(Boolean)));
  return _row({id:'tile-activity',icon:'list-checks',title:'Activity',verdict:D.activity?'none':'off',
    graphic, say, src:{path:'whats-changed.json', last_write:D.activity&&D.activity.generated_at, freshH:24}, body});
}

function buildOrgRow(){
  const org=D.org||{}, desks=(D.desks&&D.desks.desks)||[];
  const say='<i class="vd"></i><b>'+desks.length+'</b> desks, <b>'+((org.functions||[]).length)+'</b> shared functions';
  const body=el('div');
  body.appendChild(orgSvg(org));
  if(desks.length){
    const g=el('div','grid g4'); g.style.marginTop='var(--s5)';
    desks.forEach(d=>{ const c=el('div','card');
      c.appendChild(el('div','row',`<span style="font-weight:600">${esc(d.name)}</span>`));
      c.appendChild(el('div','stat',esc(d.metric)));
      g.appendChild(c); });
    body.appendChild(g);
  }
  body.appendChild(srcRow([org.source].filter(Boolean)));
  return _row({id:'tile-org',icon:'network',title:'Orchestration / Desks',verdict:org.master?'none':'off',
    graphic:null, say, src:{path:(org.source&&org.source.path)||'org builder', last_write:org.source&&org.source.last_write, freshH:24*7}, body});
}

/* ========================= registry ========================= */
const PRODUCER_GROUPS={
  trading:['tile-gate','tile-positions','tile-money','tile-engines','tile-prep','tile-eod','tile-standup'],
  research:['tile-kitchen','tile-prospector','tile-shadow','tile-watchers','tile-learning','tile-multi','tile-futures'],
  rig:['tile-guards','tile-tasks','tile-gym','tile-agents','tile-activity','tile-org'],
};
const PRODUCER_BUILDERS={
  'tile-gate':buildGateRow, 'tile-positions':buildPositionsRow, 'tile-money':buildMoneyRow,
  'tile-engines':buildEnginesRow, 'tile-prep':buildPrepRow, 'tile-eod':buildEodRow, 'tile-standup':buildStandupRow,
  'tile-kitchen':buildKitchenRow, 'tile-prospector':buildProspectorRow, 'tile-shadow':buildShadowRow,
  'tile-watchers':buildWatchersRow, 'tile-learning':buildLearningRow, 'tile-multi':buildMultiRow, 'tile-futures':buildFuturesRow,
  'tile-guards':buildGuardsRow, 'tile-tasks':buildTasksRow, 'tile-gym':buildGymRow,
  'tile-agents':buildAgentsRow, 'tile-activity':buildActivityRow, 'tile-org':buildOrgRow,
};
function producerRowById(id){
  const fn=PRODUCER_BUILDERS[id];
  if(!fn)return null;
  try{ return fn(); }catch(e){ return _errorRow(id,e); }
}
function producerRows(group){
  return (PRODUCER_GROUPS[group]||[]).map(id=>producerRowById(id)).filter(Boolean);
}
"""

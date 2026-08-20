"""gamma_cockpit_js.py - the cockpit's client-side application.

Held as a Python string so the whole cockpit stays a three-file build
(data -> ui -> js) with no bundler and no external runtime. Everything here is
vanilla ES2020; it must run from a file:// URL with no network.

STRUCTURE
  helpers -> sparkline/svg -> the six views -> drawer -> palette -> boot.

INVARIANTS THIS FILE MUST HOLD (they are the difference between a dashboard and
a liability):
  * Never compute a metric. Every number is read from D, which Python built.
  * Never render a number without a path to its source and its age.
  * Per-desk always; no aggregate-only screen.
  * Red/green mean P&L. Health uses traffic-light dots.
  * The calendar ramp is clamped by D.calendar_scale so one outlier day cannot
    flatten the month, and the true extremes are annotated.
"""
from __future__ import annotations

JS = r"""
/* ============================ helpers ============================ */
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!==undefined)e.innerHTML=h;return e};
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cls=v=>String(v||'').replace(/[^A-Za-z]/g,'').toUpperCase()||'NODATA';
const M=v=>(v==null||isNaN(v))?'—':(v>=0?'+$':'−$')+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:0});
const M2=v=>(v==null||isNaN(v))?'—':(v>=0?'+$':'−$')+Math.abs(v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
const sgn=v=>v>0?'pos':v<0?'neg':'';
const RM=matchMedia('(prefers-reduced-motion:reduce)').matches;
/* HYDRATION: ages are computed at VIEW time, never baked at build time. A static
   page that hard-codes "0.1h" still claims 0.1h six hours later - the silent-
   staleness failure this cockpit exists to avoid. Everything carrying data-ts
   re-renders its age on a 30s timer. */
function agoOf(iso){
  if(!iso)return null;
  const t=Date.parse(String(iso).replace(' ','T')); if(isNaN(t))return null;
  return (Date.now()-t)/3.6e6;
}
function agoTxt(h){
  if(h==null)return 'unknown age';
  if(h<0.0167)return 'just now';
  if(h<1)return Math.round(h*60)+'m ago';
  if(h<48)return h.toFixed(1)+'h ago';
  return (h/24).toFixed(1)+'d ago';
}
function ageEl(iso,warnH){
  const s=el('span','age'); s.dataset.ts=iso||''; s.dataset.warn=warnH||D.stale_hours;
  paintAge(s); return s;
}
function paintAge(s){
  const h=agoOf(s.dataset.ts), w=parseFloat(s.dataset.warn||D.stale_hours);
  s.textContent=agoTxt(h);
  s.className='age'+((h==null||h>w)?' stale':'');
  if(s.dataset.ts)s.title=s.dataset.ts+' ET';
}
setInterval(function(){$$('.age').forEach(paintAge)},30000);

function health(v){const k=cls(v);
  if(['GREEN','OK','EDGE','REALFILLS','LIVEPAPERREALFILLS'].includes(k))return'ok';
  if(['RED','SIGNALKILLED','SHADOWV1SIGNALKILLED','NODATA'].includes(k))return'bad';
  return'warn'}
function srcRow(list){
  const d=el('div','src');
  (list||[]).forEach(s=>{
    const w=el('span',null,(s.ok===false?'⚠ ':'')+esc(s.path)+' · ');
    // Prefer an absolute stamp so the age stays live; fall back to a build-time age.
    if(s.last_write)w.appendChild(ageEl(s.last_write));
    else w.appendChild(el('span',(s.age_h==null||s.age_h>D.stale_hours)?'age stale':'age',
                          s.age_h==null?'unknown age':agoTxt(s.age_h)));
    d.appendChild(w);
  });
  return d;
}
function stag(host,cap=8){[...host.children].forEach((c,i)=>c.style.setProperty('--i',Math.min(i,cap)));host.classList.add('stagger')}
function countUp(node,to,fmt){
  if(RM||to==null||isNaN(to)){node.textContent=fmt(to);return}
  const t0=performance.now(),dur=600,ease=t=>1-Math.pow(1-t,3);
  (function tick(now){const t=Math.min((now-t0)/dur,1);
    node.textContent=fmt(to*ease(t)); if(t<1)requestAnimationFrame(tick); else node.textContent=fmt(to)})(t0);
}
function spot(card){
  if(RM)return; card.classList.add('spot');
  card.addEventListener('pointermove',e=>{const r=card.getBoundingClientRect();
    card.style.setProperty('--mx',(e.clientX-r.left)+'px');card.style.setProperty('--my',(e.clientY-r.top)+'px')});
}
/* cumulative daily series for a desk's sparkline */
function series(arm){
  const v=(D.calendar?.views||{})[arm]; if(!v)return[];
  return Object.keys(v.days).sort().reduce((a,k)=>{a.push((a.length?a[a.length-1]:0)+(v.days[k].n||0));return a},[]);
}
function spark(vals,w=132,h=34){
  if(!vals||vals.length<2)return el('div','micro','no series');
  const mn=Math.min(...vals),mx=Math.max(...vals),rg=(mx-mn)||1;
  const pts=vals.map((v,i)=>[i*(w/(vals.length-1)),h-2-((v-mn)/rg)*(h-4)]);
  const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
  const up=vals[vals.length-1]>=0, col=up?'var(--pos)':'var(--neg)';
  const ns='http://www.w3.org/2000/svg', s=document.createElementNS(ns,'svg');
  s.setAttribute('viewBox',`0 0 ${w} ${h}`); s.setAttribute('width',w); s.setAttribute('height',h);
  s.setAttribute('class','spark'); s.style.overflow='visible';
  const area=document.createElementNS(ns,'path');
  area.setAttribute('d',`${d} L ${w} ${h} L 0 ${h} Z`);
  area.setAttribute('fill',up?'var(--pos-dim)':'var(--neg-dim)');
  const ln=document.createElementNS(ns,'path');
  ln.setAttribute('d',d);ln.setAttribute('fill','none');ln.setAttribute('stroke',col);
  ln.setAttribute('stroke-width','1.6');ln.setAttribute('stroke-linejoin','round');ln.setAttribute('stroke-linecap','round');
  s.append(area,ln); return s;
}

/* ============================ views ============================ */
const VIEWS=[
 {id:'overview',ic:'◎',label:'Overview',key:'o'},
 {id:'desks',ic:'▦',label:'Desks',key:'d'},
 {id:'orchestration',ic:'⛬',label:'Orchestration',key:'g'},
 {id:'engine',ic:'❥',label:'Engine room',key:'e'},
 {id:'agents',ic:'✦',label:'Agents',key:'w'},
 {id:'journal',ic:'▤',label:'Journal',key:'j'},
 {id:'answers',ic:'✔',label:'Answers',key:'a'},
 {id:'activity',ic:'⟡',label:'Activity',key:'v'},
];

function bookSummary(){
  return ((D.calendar?.views||{}).BOOK||{}).summary||{};
}

/* ---------- OVERVIEW: verdict -> desks -> agents -> exceptions ---------- */
function vOverview(h){
  const s=bookSummary(), desks=D.desks?.desks||[];

  // THE BRIEFING leads. J: "command center should be like me talking to an
  // employee" - so the first thing on the page is what I would SAY, not a metric
  // wall. Deterministic templates over real state; never an LLM, which is the
  // fabrication risk this cockpit exists to close.
  const br=D.briefing||{lines:[]};
  if((br.lines||[]).length){
    const b=el('div','card gborder brief');
    const hd=el('div','row wrap');
    hd.innerHTML='<span class="eyebrow">Where we stand</span>';
    hd.appendChild(el('span','chip live '+(D.hq?.state_word?'ok':'bad'),
      '<i class="dot"></i>'+esc(D.hq?.state_word||'NO DATA')));
    const sp=el('span','sp'); hd.appendChild(sp);
    const ag=el('span','dim'); ag.appendChild(el('span',null,'briefed ')); ag.appendChild(ageEl(D.built_at_et,2));
    hd.appendChild(ag);
    b.appendChild(hd);
    const ul=el('div','brieflines');
    br.lines.forEach(l=>ul.appendChild(el('p',null,esc(l))));
    b.appendChild(ul);
    (br.flags||[]).forEach(f=>{
      const fl=el('div','flag '+(f.kind==='broken'?'bad':'dec'));
      fl.innerHTML='<b>'+(f.kind==='broken'?'NOT TICKING':'DECISION WAITING')+'</b> '+esc(f.text);
      b.appendChild(fl);
    });
    if(br.source)b.appendChild(srcRow([br.source]));
    h.appendChild(b);
  }

  // hero
  const hero=el('div','card gborder');
  hero.style.padding='var(--s8)';
  hero.appendChild(el('div','eyebrow','Book — net of fees, real fills, all arms'));
  const rowh=el('div','row wrap'); rowh.style.cssText='align-items:flex-end;gap:var(--s8);margin-top:var(--s4)';
  const big=el('div','big '+sgn(s.total_pnl_net||0),'—');
  const hb=el('div'); hb.appendChild(big);
  hb.appendChild(el('div','dim',`${s.trading_days??'—'} trading days · ${s.total_trades??'—'} trades · ${s.win_rate_by_day_net!=null?Math.round(s.win_rate_by_day_net*100)+'% day win rate':'—'}`));
  rowh.appendChild(hb);
  const bd=el('div'); bd.style.cssText='display:flex;gap:var(--s8);flex-wrap:wrap';
  [['Best day',s.best_day_net],['Worst day',s.worst_day_net]].forEach(([k,v])=>{
    const c=el('div');
    c.appendChild(el('div','micro',k));
    c.appendChild(el('div','stat '+sgn(v?.pnl||0),M(v?.pnl)));
    c.appendChild(el('div','micro',esc(v?.date||'')));
    bd.appendChild(c);
  });
  const fee=el('div'); fee.appendChild(el('div','micro','Fees paid'));
  fee.appendChild(el('div','stat','$'+(s.total_fees||0).toLocaleString(undefined,{maximumFractionDigits:0})));
  bd.appendChild(fee); rowh.appendChild(bd); hero.appendChild(rowh);
  hero.appendChild(srcRow([D.calendar_source]));
  h.appendChild(hero);
  countUp(big,s.total_pnl_net||0,M);

  // desks — per-desk always, never an aggregate-only screen
  const sec=el('section');
  sec.appendChild(el('div','shead','<h2>Desks</h2><span class="dim">four context boundaries · click any tile</span>'));
  const g=el('div','grid g4');
  desks.forEach(d=>{
    const c=el('div','card click'); spot(c);
    c.appendChild(el('div','row',`<span style="font-weight:600">${esc(d.name)}</span>`));
    const chip=el('span','chip '+health(d.chip),`<i class="dot"></i>${esc(d.chip)}`);
    c.querySelector('.row').appendChild(chip);
    c.appendChild(el('div','stat',esc(d.metric)));
    c.appendChild(el('div','micro',esc(d.instrument)));
    const arm=d.id==='spy-0dte'?'BOOK':null;
    if(arm){const sp=spark(series(arm)); sp.style.marginTop='var(--s4)'; c.appendChild(sp);}
    else c.appendChild(el('div','dim',esc((d.sub||'').slice(0,90))));
    c.onclick=()=>deskDrawer(d);
    g.appendChild(c);
  });
  sec.appendChild(g); stag(g); h.appendChild(sec);

  // agent strip (collapsed org — full tree lives in Orchestration)
  const org=D.org||{}, alloc=D.allocation||{};
  const as=el('section');
  as.appendChild(el('div','shead','<h2>Orchestration</h2><span class="dim">master → desks → shared functions</span>'));
  const ac=el('div','card click'); spot(ac);
  const arow=el('div','row wrap');
  arow.innerHTML=`<span class="chip ok"><i class="dot"></i>MASTER ${esc(org.master?.name||'gamma')}</span>
    <span class="dim">${(org.desks||[]).length} desks · ${(org.functions||[]).length} shared functions</span>`;
  ac.appendChild(arow);
  const win=(alloc.desks||[])[0];
  if(win){
    ac.appendChild(el('div','mut',`<b>Next fire →</b> ${esc(win.name)} <span class="dim">(${win.points} pts)</span>`));
    ac.appendChild(el('div','dim',esc((win.why||[])[0]||'')));
  }
  ac.onclick=()=>route('orchestration');
  as.appendChild(ac); h.appendChild(as);

  // exception rail — only things off-nominal
  const bad=(D.answers||[]).filter(a=>['RED','YELLOW','NO DATA','DEGRADED'].includes(String(a.verdict).toUpperCase()));
  const ex=el('section');
  ex.appendChild(el('div','shead','<h2>Needs attention</h2><span class="dim">off-nominal only</span>'));
  if(!bad.length) ex.appendChild(el('div','card','<div class="mut">Nothing off-nominal. Every checked surface is green.</div>'));
  else{
    const eg=el('div','grid g2');
    bad.forEach(a=>{
      const c=el('div','card click'); spot(c);
      c.appendChild(el('div','row',`<span class="chip ${health(a.verdict)}"><i class="dot"></i>${esc(a.verdict)}</span>
        <span style="font-weight:600">${esc(a.q)}</span>`));
      c.appendChild(el('div','mut',esc(a.answer)));
      if(a.detail)c.appendChild(el('div','dim',esc(a.detail)));
      c.onclick=()=>answerDrawer(a);
      eg.appendChild(c);
    });
    ex.appendChild(eg); stag(eg);
  }
  h.appendChild(ex);

  // month calendar
  const cs=el('section');
  cs.appendChild(el('div','shead','<h2>This month</h2><span class="dim">click a day for its trades</span>'));
  const cc=el('div','card'); calendarInto(cc,'BOOK',true); cs.appendChild(cc); h.appendChild(cs);
}

/* ---------- DESKS ---------- */
function vDesks(h){
  const desks=D.desks?.desks||[];
  h.appendChild(el('div','shead','<h2>Trading desks</h2><span class="dim">decomposed by instrument — the context boundary, not by role</span>'));
  const g=el('div','grid g2');
  desks.forEach(d=>{
    const c=el('div','card click'); spot(c);
    const r=el('div','row wrap');
    r.innerHTML=`<span class="mid">${esc(d.name)}</span>`;
    r.appendChild(el('span','chip '+health(d.chip),`<i class="dot"></i>${esc(d.chip)}`));
    c.appendChild(r);
    c.appendChild(el('div','micro',esc(d.instrument)));
    c.appendChild(el('div','stat',esc(d.metric)));
    c.appendChild(el('div','mut',esc(d.sub)));
    const bar=el('div'); bar.style.marginTop='var(--s4)';
    bar.appendChild(el('div','micro','ARMING BAR'));
    bar.appendChild(el('div','dim',esc(d.arming_bar)));
    c.appendChild(bar);
    c.onclick=()=>deskDrawer(d);
    g.appendChild(c);
  });
  h.appendChild(g); stag(g);
  h.appendChild(srcRow([D.desks?.source]));
}
function deskDrawer(d){
  openDrawer(d.name,b=>{
    b.appendChild(el('div','row',`<span class="chip ${health(d.chip)}"><i class="dot"></i>${esc(d.chip)}</span>
      <span class="dim">${esc(d.instrument)}</span>`));
    const k=el('div'); k.style.marginTop='var(--s5)';
    [['Headline',d.metric],['Detail',d.sub],['Arming bar',d.arming_bar]].forEach(([a,v])=>{
      k.appendChild(el('div','kv',`<span class="k">${esc(a)}</span><span class="v">${esc(v||'—')}</span>`)); });
    b.appendChild(k);
    if((d.arms||[]).length){
      b.appendChild(el('h3',null,'Arms / lanes')); b.querySelector('h3').style.cssText='margin:var(--s6) 0 var(--s3);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--tx-3)';
      const ul=el('div'); d.arms.forEach(a=>ul.appendChild(el('div','kv',`<span class="k">${esc(a)}</span>`))); b.appendChild(ul);
    }
    if((d.functions||[]).length){
      const t=el('div','micro','SHARED FUNCTIONS IT INVOKES'); t.style.marginTop='var(--s6)'; b.appendChild(t);
      const r=el('div','row wrap'); r.style.marginTop='var(--s3)';
      d.functions.forEach(f=>r.appendChild(el('span','chip',esc(f)))); b.appendChild(r);
    }
    if(d.id==='spy-0dte'){
      const t=el('div','micro','CUMULATIVE NET'); t.style.marginTop='var(--s6)'; b.appendChild(t);
      const sp=spark(series('BOOK'),620,90); b.appendChild(sp);
    }
  });
}

/* ---------- ORCHESTRATION ---------- */
function vOrch(h){
  const org=D.org||{}, alloc=D.allocation||{};
  h.appendChild(el('div','shead','<h2>Agent orchestration</h2><span class="dim">master coordinates · desks own context · functions are shared</span>'));

  // allocation ranking — the master's ALLOCATE arm
  const ac=el('div','card');
  ac.appendChild(el('h3',null,'Next fire — deterministic desk allocation'));
  (alloc.desks||[]).forEach((r,i)=>{
    const row=el('div'); row.style.cssText='padding:var(--s4) 0;border-bottom:1px solid var(--bd-subtle)';
    row.appendChild(el('div','row',`<span class="chip ${i===0?'ok':''}">${i+1}</span>
      <span style="font-weight:600">${esc(r.name)}</span>
      <span class="dim">${esc(r.headline||'')}</span>
      <span class="sp"></span><span class="stat ${r.points>0?'acc':''}">${r.points} pts</span>`));
    (r.why||[]).forEach(w=>row.appendChild(el('div','micro','· '+esc(w))));
    ac.appendChild(row);
  });
  if(alloc.error) ac.appendChild(el('div','micro warnc','allocator error: '+esc(alloc.error)));
  h.appendChild(ac);

  // org graph
  const gc=el('div','card'); gc.style.marginTop='var(--s5)';
  gc.appendChild(el('h3',null,'Org — edges are delegation, labelled with what the desk owns'));
  gc.appendChild(orgSvg(org));
  h.appendChild(gc);

  // shared functions
  const fc=el('div','card'); fc.style.marginTop='var(--s5)';
  fc.appendChild(el('h3',null,'Shared functions — invoked BY a desk, with that desk’s context'));
  const tb=el('table');
  tb.innerHTML='<thead><tr><th>Agent</th><th>Model</th><th>Owns</th><th>Verified by</th></tr></thead>';
  const bd=el('tbody');
  (org.functions||[]).forEach(f=>{
    const tr=el('tr',null,`<td><b>${esc(f.name)}</b></td><td class="mono dim">${esc(f.model||'')}</td>
      <td>${esc(f.owns||'')}</td><td class="dim">${esc((f.verified_by||'').slice(0,70))}</td>`);
    bd.appendChild(tr);
  });
  tb.appendChild(bd); fc.appendChild(tb); h.appendChild(fc);

  // the delegation contract
  const c=org.contract||{};
  if((c.required_fields||[]).length){
    const cc=el('div','card'); cc.style.marginTop='var(--s5)';
    cc.appendChild(el('h3',null,'Delegation contract — every fan-out must carry these'));
    const r=el('div','row wrap');
    c.required_fields.forEach(f=>r.appendChild(el('span','chip',esc(f))));
    if(c.model_pin_required)r.appendChild(el('span','chip warn','<i class="dot"></i>model pin required'));
    cc.appendChild(r); h.appendChild(cc);
  }
  h.appendChild(srcRow([org.source]));
}
function orgSvg(org){
  const ns='http://www.w3.org/2000/svg', desks=org.desks||[], W=Math.max(780,desks.length*200+80), H=290;
  const s=document.createElementNS(ns,'svg'); s.setAttribute('viewBox',`0 0 ${W} ${H}`);
  s.setAttribute('width','100%'); s.setAttribute('height',H); s.style.minWidth='720px';
  const mk=(t,a)=>{const e=document.createElementNS(ns,t);for(const k in a)e.setAttribute(k,a[k]);return e};
  const txt=(x,y,str,c,sz,w)=>{const e=mk('text',{x,y,fill:c||'var(--tx-2)','font-size':sz||11,
    'font-family':'var(--font)','font-weight':w||500,'text-anchor':'middle'});e.textContent=str;return e};
  // master
  const mx=W/2;
  s.appendChild(mk('rect',{x:mx-84,y:16,width:168,height:52,rx:12,fill:'var(--bg-2)',stroke:'var(--acc)','stroke-width':1.4}));
  s.appendChild(txt(mx,40,'MASTER','var(--tx-4)',10,600));
  s.appendChild(txt(mx,57,(org.master?.name||'gamma'),'var(--tx-1)',15,600));
  desks.forEach((d,i)=>{
    const x=(W/desks.length)*(i+.5), y=170;
    s.appendChild(mk('path',{d:`M ${mx} 68 C ${mx} 120, ${x} 110, ${x} ${y-32}`,
      fill:'none',stroke:'var(--bd-strong)','stroke-width':1.2}));
    const lab=txt((mx+x)/2,124,d.instrument.slice(0,18),'var(--tx-4)',9.5,500); s.appendChild(lab);
    const g=mk('g',{class:'nd'});
    g.appendChild(mk('rect',{x:x-84,y:y-32,width:168,height:64,rx:12,fill:'var(--bg-1)',stroke:'var(--bd)','stroke-width':1}));
    const hs=health(d.status);
    g.appendChild(mk('circle',{cx:x-68,cy:y-14,r:4,
      fill:hs==='ok'?'var(--pos)':hs==='bad'?'var(--neg)':'var(--warn)'}));
    g.appendChild(txt(x+6,y-10,d.name,'var(--tx-1)',12.5,600));
    g.appendChild(txt(x,y+10,(d.status||'').replace(/_/g,' ').toLowerCase().slice(0,26),'var(--tx-4)',9.5,500));
    g.appendChild(txt(x,y+26,(d.functions||[]).join(' · ').slice(0,30)||'—','var(--tx-4)',9,400));
    g.style.cursor='pointer';
    g.onclick=()=>{const full=(D.desks?.desks||[]).find(z=>z.id===d.id); if(full)deskDrawer(full)};
    s.appendChild(g);
  });
  s.appendChild(txt(W/2,H-14,'shared functions: '+(org.functions||[]).map(f=>f.name).join(' · '),'var(--tx-4)',9.5,400));
  const wrap=el('div','org'); wrap.appendChild(s); return wrap;
}

/* ---------- ENGINE ROOM: every engine's heartbeat and its reasons ---------- */
function vEngine(h){
  const er=D.engine_room||{engines:[]};
  h.appendChild(el('div','shead','<h2>Engine room</h2><span class="dim">every engine, its own ledger, its own stated reasons</span>'));
  const g=el('div','grid g2');
  (er.engines||[]).forEach(e=>{
    const c=el('div','card click'); spot(c);
    const age=agoOf(e.last_write), dead=(age==null||age>24);
    const r=el('div','row wrap');
    r.innerHTML='<span style="font-weight:600">'+esc(e.name)+'</span>';
    r.appendChild(el('span','chip '+(dead?'bad':'ok live'),'<i class="dot"></i>'+(dead?'NOT TICKING':'TICKING')));
    c.appendChild(r);
    c.appendChild(el('div','micro',esc(e.cadence)));
    const beat=el('div','row'); beat.style.marginTop='var(--s4)';
    beat.appendChild(el('span','stat',Number(e.total||0).toLocaleString()));
    beat.appendChild(el('span','dim','ticks logged \u00b7 last'));
    beat.appendChild(ageEl(e.last_write,24));
    c.appendChild(beat);
    const vr=el('div','row wrap'); vr.style.marginTop='var(--s4)';
    Object.keys(e.verdicts||{}).forEach(k=>vr.appendChild(el('span','chip',esc(k)+' \u00d7'+e.verdicts[k])));
    c.appendChild(vr);
    const t0=(e.ticks||[])[0];
    if(t0&&t0.why)c.appendChild(el('div','dim','last: '+esc(t0.why)));
    c.onclick=()=>engineDrawer(e);
    g.appendChild(c);
  });
  h.appendChild(g); stag(g);
}
function engineDrawer(e){
  openDrawer(e.name+' \u2014 tick stream',b=>{
    b.appendChild(el('div','micro',esc(e.engine)));
    const k=el('div'); k.style.margin='var(--s4) 0';
    k.appendChild(el('div','kv','<span class="k">Cadence</span><span class="v">'+esc(e.cadence)+'</span>'));
    k.appendChild(el('div','kv','<span class="k">Ticks logged</span><span class="v mono">'+Number(e.total||0).toLocaleString()+'</span>'));
    const lw=el('div','kv','<span class="k">Last tick</span>');
    const vv=el('span','v'); vv.appendChild(ageEl(e.last_write,24)); lw.appendChild(vv); k.appendChild(lw);
    b.appendChild(k);
    (e.ticks||[]).forEach(t=>{
      const row=el('div'); row.style.cssText='padding:var(--s4) 0;border-bottom:1px solid var(--bd-subtle)';
      const top=el('div','row wrap');
      top.innerHTML='<span class="mono dim">'+esc(String(t.ts||'').slice(11,19))+'</span>';
      top.appendChild(el('span','chip',esc(t.verdict)));
      if(t.account)top.appendChild(el('span','micro',esc(t.account)));
      if(t.px!=null)top.appendChild(el('span','mono dim',String(t.px)));
      if(t.scores&&t.scores.bull!=null)top.appendChild(el('span','micro','bull '+t.scores.bull+' / bear '+t.scores.bear));
      if(t.sym)top.appendChild(el('span','micro',esc(t.sym)));
      row.appendChild(top);
      if(t.why)row.appendChild(el('div','mut',esc(t.why)));
      (t.blockers||[]).forEach(x=>row.appendChild(el('div','micro warnc','blocked by '+esc(x))));
      if(t.ctx)row.appendChild(el('div','micro','ribbon '+esc(t.ctx.ribbon||'\u2014')+' \u00b7 15m '+esc(t.ctx.htf||'\u2014')+
        ' \u00b7 VIX '+(t.ctx.vix==null?'\u2014':t.ctx.vix)+' \u00b7 spread '+(t.ctx.spread_c==null?'\u2014':t.ctx.spread_c+'c')));
      b.appendChild(row);
    });
    b.appendChild(srcRow([{path:e.source,last_write:e.last_write}]));
  });
}

/* ---------- AGENTS: who ran, and was the output TRUSTED ---------- */
function vAgents(h){
  const a=D.agents||{events:[],counts:{},sources:[]};
  h.appendChild(el('div','shead','<h2>Agents</h2><span class="dim">what ran \u2014 and whether its output survived the fabrication gate</span>'));
  const g=el('div','grid g4');
  [['Events',a.counts.total,''],['Failed',a.counts.failed,a.counts.failed?'neg':''],
   ['Fabricated',a.counts.fabricated,a.counts.fabricated?'neg':'pos'],
   ['Dupes suppressed',a.counts.suppressed,'']].forEach(row=>{
    const c=el('div','card');
    c.appendChild(el('div','micro',row[0]));
    c.appendChild(el('div','big '+(row[2]||''),String(row[1]==null?0:row[1])));
    g.appendChild(c);
  });
  h.appendChild(g); stag(g);
  const c=el('div','card'); c.style.marginTop='var(--s5)';
  c.appendChild(el('h3',null,'Recent agent activity'));
  const tbl=el('table');
  tbl.innerHTML='<thead><tr><th>When</th><th>Tier</th><th>Agent</th><th>Did</th><th>Artifacts</th></tr></thead>';
  const tb=el('tbody');
  (a.events||[]).forEach(e=>{
    const vd=e.verdict||'';
    const cl=vd==='FABRICATED'?'neg':vd==='VERIFIED'?'pos':'dim';
    const tr=el('tr');
    tr.innerHTML='<td class="mono dim">'+esc(String(e.ts||'').slice(5,16).replace('T',' '))+'</td>'+
      '<td><span class="chip">'+esc(e.tier)+'</span></td>'+
      '<td><b>'+esc(e.who)+'</b>'+(e.lane?'<div class="micro">'+esc(e.lane)+'</div>':'')+'</td>'+
      '<td>'+(e.ok?'':'<span class="neg">\u2715 </span>')+esc(e.what)+
        (e.err?'<div class="micro warnc">'+esc(e.err)+'</div>':'')+'</td>'+
      '<td class="'+cl+'">'+esc(vd||'\u2014')+'</td>';
    tb.appendChild(tr);
  });
  tbl.appendChild(tb); c.appendChild(tbl);
  c.appendChild(srcRow(a.sources));
  h.appendChild(c);
}

/* ---------- JOURNAL ---------- */
let calArm='BOOK', calBasis='n', calMonth=null;
function vJournal(h){
  h.appendChild(el('div','shead','<h2>Journal</h2><span class="dim">per-arm P&amp;L · click a day for its trades</span>'));
  const c=el('div','card'); calendarInto(c,calArm,false); h.appendChild(c);
}
function calendarInto(host,arm,mini){
  host.innerHTML='';
  const views=D.calendar?.views||{}, v=views[arm]||{days:{},summary:{}};
  const ctl=el('div','row wrap'); ctl.style.marginBottom='var(--s5)';
  if(!mini){
    const sel=el('select'); sel.style.cssText='background:var(--bg-2);color:var(--tx-1);border:1px solid var(--bd);border-radius:var(--r-md);padding:6px 10px;font-family:var(--font);font-size:13px';
    Object.keys(views).sort((a,b)=>a==='BOOK'?-1:b==='BOOK'?1:a.localeCompare(b))
      .forEach(k=>{const o=el('option',null,k);o.value=k;if(k===arm)o.selected=true;sel.appendChild(o)});
    sel.onchange=()=>{calArm=sel.value;calendarInto(host,calArm,mini)};
    const bs=el('select'); bs.style.cssText=sel.style.cssText;
    [['n','net of fees'],['g','gross']].forEach(([k,l])=>{const o=el('option',null,l);o.value=k;if(k===calBasis)o.selected=true;bs.appendChild(o)});
    bs.onchange=()=>{calBasis=bs.value;calendarInto(host,arm,mini)};
    ctl.append(sel,bs);
  }
  const dates=Object.keys(v.days).sort();
  const last=calMonth||(dates.length?dates[dates.length-1]:(D.today||''));
  const [Y,Mo]=last.split('-').map(Number);
  const months=[...new Set(dates.map(d=>d.slice(0,7)))].sort();
  const idx=months.indexOf(`${Y}-${String(Mo).padStart(2,'0')}`);
  const nav=el('div','row'); nav.style.marginLeft='auto';
  const mkb=(t,dis,fn)=>{const b=el('button',null,t);
    b.style.cssText='background:var(--bg-2);border:1px solid var(--bd);color:var(--tx-2);border-radius:var(--r-md);padding:5px 11px;cursor:pointer;font-size:13px';
    b.disabled=dis; if(dis)b.style.opacity=.35; else b.onclick=fn; return b};
  nav.appendChild(mkb('‹',idx<=0,()=>{calMonth=months[idx-1]+'-01';calendarInto(host,arm,mini)}));
  nav.appendChild(el('span','mut',`${Y}-${String(Mo).padStart(2,'0')}`));
  nav.appendChild(mkb('›',idx<0||idx>=months.length-1,()=>{calMonth=months[idx+1]+'-01';calendarInto(host,arm,mini)}));
  ctl.appendChild(nav); host.appendChild(ctl);

  const clamp=(D.calendar_scale?.clamp)||500;
  const dow=el('div','cal');
  ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].forEach(d=>dow.appendChild(el('div','dow',d)));
  host.appendChild(dow);
  const grid=el('div','cal'); grid.style.marginTop='6px';
  const first=new Date(Y,Mo-1,1), nd=new Date(Y,Mo,0).getDate();
  for(let i=0;i<first.getDay();i++)grid.appendChild(el('div','cell empty'));
  let tot=0,n=0;
  for(let d=1;d<=nd;d++){
    const iso=`${Y}-${String(Mo).padStart(2,'0')}-${String(d).padStart(2,'0')}`, row=v.days[iso];
    const p=row?row[calBasis]:null;
    const c=el('div','cell'+(row?' has ':' ')+(row?(p>0?'win':p<0?'loss':'flat'):''));
    c.appendChild(el('div','d',String(d)));
    if(row){
      tot+=p;n++;
      // clamped intensity: one blowout day cannot flatten the month
      const k=Math.min(1,Math.abs(p)/clamp);
      c.style.background=`color-mix(in oklch, var(--${p>0?'pos':'neg'}) ${(6+k*22).toFixed(0)}%, var(--bg-1))`;
      c.appendChild(el('div','v',M(p)));
      c.appendChild(el('div','t',row.t+(row.t===1?' trade':' trades')));
      c.title=`${iso} · ${row.t} trades · ${M2(p)}`;
      c.onclick=()=>dayDrawer(iso,arm);
    }
    grid.appendChild(c);
  }
  host.appendChild(grid);
  const s=v.summary||{};
  const foot=el('div','row wrap'); foot.style.marginTop='var(--s5)';
  foot.appendChild(el('div','mut',`<b class="${sgn(tot)}">${M(tot)}</b> this month · ${n} trading days`));
  foot.appendChild(el('div','dim',`all-time <b class="${sgn(calBasis==='n'?s.total_pnl_net:s.total_pnl_gross)}">${M(calBasis==='n'?s.total_pnl_net:s.total_pnl_gross)}</b> over ${s.trading_days??'—'} days`));
  const lg=el('div','legend'); lg.style.marginLeft='auto';
  lg.innerHTML=`<span>${M(-clamp)}</span><span class="ramp"></span><span>${M(clamp)}</span>
    <span class="micro">scale clamped · true extremes ${M(-(D.calendar_scale?.max_abs||0))} / ${M(D.calendar_scale?.max_abs||0)}</span>`;
  foot.appendChild(lg); host.appendChild(foot);
  host.appendChild(srcRow([D.calendar_source]));
}
function dayDrawer(iso,arm){
  const v=(D.calendar_full?.views||{})[arm]||{days:{}}, row=(v.days||{})[iso];
  openDrawer(iso+' · '+arm,b=>{
    if(!row){b.appendChild(el('div','note','No trades recorded for this day.'));return}
    const k=el('div');
    [['Net of fees',M2(row.pnl_net)],['Gross',M2(row.pnl_gross)],['Fees',M2(row.fees_total)],
     ['Trades',row.trade_count],['Wins / losses',`${row.wins_gross} / ${row.losses_gross}`]]
      .forEach(([a,x])=>k.appendChild(el('div','kv',`<span class="k">${esc(a)}</span><span class="v mono">${esc(x)}</span>`)));
    b.appendChild(k);
    const tr=row.trades||[];
    if(!tr.length){b.appendChild(el('div','note','Day totals only — no per-trade rows.'));return}
    const t=el('table'); t.style.marginTop='var(--s6)';
    t.innerHTML='<thead><tr><th>Time</th><th>Arm</th><th>Contract</th><th>Setup</th><th class="n">Qty</th><th class="n">In</th><th class="n">Out</th><th class="n">Net</th></tr></thead>';
    const tb=el('tbody');
    tr.forEach(x=>{
      const net=x.pnl_net_ex_cat!=null?x.pnl_net_ex_cat:x.pnl_gross;
      tb.appendChild(el('tr',null,
        `<td class="mono dim">${esc(String(x.entry_ts_et||'').slice(11,16))}</td>
         <td>${esc(x.arm||'')}</td>
         <td class="mono">${esc(String(x.strike||'')+(x.side||''))}</td>
         <td class="dim">${esc(x.setup||'—')}</td>
         <td class="n">${esc(x.qty??'')}</td>
         <td class="n">${x.entry_premium!=null?x.entry_premium.toFixed(2):'—'}</td>
         <td class="n">${x.exit_premium!=null?x.exit_premium.toFixed(2):(x.exit_premium_avg!=null?x.exit_premium_avg.toFixed(2):'—')}</td>
         <td class="n ${sgn(net)}">${M2(net)}</td>`));
    });
    t.appendChild(tb); b.appendChild(t);
  });
}

/* ---------- ANSWERS ---------- */
function vAnswers(h){
  h.appendChild(el('div','shead','<h2>The answers</h2><span class="dim">you shouldn’t have to ask</span>'));
  const g=el('div','grid g2');
  (D.answers||[]).forEach(a=>{
    const c=el('div','card click'); spot(c);
    c.appendChild(el('div','micro',esc(a.q)));
    const r=el('div','row'); r.style.margin='var(--s3) 0';
    r.appendChild(el('span','chip '+health(a.verdict),`<i class="dot"></i>${esc(a.verdict)}`));
    r.appendChild(el('span','mut',esc(a.answer)));
    c.appendChild(r);
    if(a.detail)c.appendChild(el('div','dim',esc(a.detail)));
    if(a.means){const m=el('div','mut',esc(a.means));
      m.style.cssText='border-left:2px solid var(--acc);padding-left:var(--s4);margin-top:var(--s4);color:var(--tx-2)';
      c.appendChild(m)}
    c.appendChild(srcRow(a.sources));
    c.onclick=()=>answerDrawer(a);
    g.appendChild(c);
  });
  h.appendChild(g); stag(g);
}
function answerDrawer(a){
  openDrawer(a.q,b=>{
    b.appendChild(el('div','row',`<span class="chip ${health(a.verdict)}"><i class="dot"></i>${esc(a.verdict)}</span>`));
    b.appendChild(el('div','mid',esc(a.answer)));
    if(a.detail)b.appendChild(el('div','mut',esc(a.detail)));
    if(a.means)b.appendChild(el('div','dim',esc(a.means)));
    b.appendChild(srcRow(a.sources));
  });
}

/* ---------- ACTIVITY ---------- */
function vActivity(h){
  const hq=D.hq||{};
  h.appendChild(el('div','shead','<h2>Activity</h2><span class="dim">clocks · wants · recent ships</span>'));
  const g=el('div','grid g2');

  const cc=el('div','card'); cc.appendChild(el('h3',null,'Shadow clocks'));
  (hq.clocks||[]).forEach(c=>{
    const d=el('div'); d.style.marginBottom='var(--s5)';
    const done=(c.have||0)>=(c.need||1);
    d.appendChild(el('div','row',`<span style="font-weight:600">${esc(c.label)}</span>
      <span class="sp"></span><span class="mono dim">${c.have} / ${c.need}</span>`));
    const b=el('div','bar'+(done?' done':'')); const i=el('i');
    i.style.width=Math.min(100,100*(c.have||0)/Math.max(1,c.need||1))+'%'; b.appendChild(i); d.appendChild(b);
    if(c.explain)d.appendChild(el('div','micro',esc(c.explain)));
    cc.appendChild(d);
  });
  if(!(hq.clocks||[]).length)cc.appendChild(el('div','note','no clock data'));
  g.appendChild(cc);

  const wc=el('div','card'); wc.appendChild(el('h3',null,'What I want from you'));
  (D.wants_full||[]).forEach((w,i)=>{
    const d=el('div'); d.style.cssText='display:flex;gap:var(--s4);padding:var(--s4) 0;border-bottom:1px solid var(--bd-subtle)';
    d.appendChild(el('div','acc',String(i+1)));
    const tx=el('div','mut',esc(w.text));
    if(w.stale)tx.appendChild(el('span','warnc',' ⚠ unverified'+(w.verified_at?' since '+esc(w.verified_at):'')));
    d.appendChild(tx); wc.appendChild(d);
  });
  if(!(D.wants_full||[]).length)wc.appendChild(el('div','note','nothing outstanding'));
  g.appendChild(wc);
  h.appendChild(g);

  const sc=el('div','card'); sc.style.marginTop='var(--s5)';
  sc.appendChild(el('h3',null,'Recent ships'));
  (hq.recent_ships||[]).forEach(t=>sc.appendChild(el('div','kv',`<span class="k">${esc(t)}</span>`)));
  if(!(hq.recent_ships||[]).length)sc.appendChild(el('div','note','no recent ships'));
  h.appendChild(sc);
}

/* ============================ drawer ============================ */
function openDrawer(title,build){
  $('#dtitle').textContent=title; const b=$('#dbody'); b.innerHTML=''; build(b);
  const d=$('#drawer'); d.classList.remove('closing'); d.classList.add('on'); d.setAttribute('aria-hidden','false');
  $('#scrim').classList.add('on');
}
function closeDrawer(){
  const d=$('#drawer'); d.classList.add('closing'); d.classList.remove('on'); d.setAttribute('aria-hidden','true');
  $('#scrim').classList.remove('on');
}

/* ============================ nav + palette ============================ */
function navBuild(){
  const n=$('#nav'); n.innerHTML='';
  VIEWS.forEach(v=>{
    const a=el('a',null,`<span class="ic">${v.ic}</span><span>${v.label}</span>`);
    a.href='#'+v.id; a.dataset.v=v.id;
    // Route on click as well as on hashchange. Some hosts (the in-app preview
    // serves the file as a data: URL) do not fire hashchange, which would leave
    // the nav visibly dead. Clicking must always work.
    // Route EXPLICITLY, then sync the hash for deep-linking. Routing must not
    // depend on the hash actually changing: some hosts serve this file from a
    // data: URL where hash assignment is a no-op, which left the nav dead.
    a.onclick=e=>{e.preventDefault();route(v.id);try{history.replaceState(null,'','#'+v.id)}catch(_){}};
    if(v.id==='desks')a.appendChild(el('span','badge',String((D.desks?.desks||[]).length)));
    if(v.id==='answers'){
      const bad=(D.answers||[]).filter(x=>['RED','YELLOW','NO DATA','DEGRADED'].includes(String(x.verdict).toUpperCase())).length;
      if(bad)a.appendChild(el('span','badge hot',String(bad)));
    }
    n.appendChild(a);
  });
}
const RENDER={overview:vOverview,desks:vDesks,orchestration:vOrch,engine:vEngine,agents:vAgents,journal:vJournal,answers:vAnswers,activity:vActivity};
let CUR='overview';
function route(want){
  const id=want||(location.hash||'#overview').slice(1).split('?')[0];
  const v=VIEWS.find(x=>x.id===id)||VIEWS[0];
  CUR=v.id;
  $$('#nav a').forEach(a=>a.classList.toggle('on',a.dataset.v===v.id));
  $('#vtitle').textContent=v.label;
  const host=$('#view'); host.innerHTML=''; RENDER[v.id](host);
  host.classList.remove('anim'); void host.offsetWidth; host.classList.add('anim');
  window.scrollTo({top:0,behavior:RM?'auto':'smooth'});
}

const PAL=[];
function palBuild(){
  PAL.length=0;
  VIEWS.forEach(v=>PAL.push({t:v.label,s:'View',go:()=>route(v.id)}));
  (D.desks?.desks||[]).forEach(d=>PAL.push({t:d.name,s:'Desk',go:()=>deskDrawer(d)}));
  (D.org?.functions||[]).forEach(f=>PAL.push({t:f.name,s:'Agent',go:()=>route('orchestration')}));
  (D.answers||[]).forEach(a=>PAL.push({t:a.q,s:'Answer',go:()=>answerDrawer(a)}));
  (D.engine_room?.engines||[]).forEach(e=>PAL.push({t:e.name,s:'Engine',go:()=>engineDrawer(e)}));
  const v=(D.calendar?.views||{}).BOOK||{days:{}};
  Object.keys(v.days).sort().reverse().slice(0,40).forEach(d=>PAL.push({t:d,s:'Day',go:()=>dayDrawer(d,'BOOK')}));
}
let palSel=0;
function palRender(q){
  const res=$('#palres'); res.innerHTML='';
  const hits=PAL.filter(p=>(p.t+' '+p.s).toLowerCase().includes(q.toLowerCase())).slice(0,9);
  palSel=Math.min(palSel,Math.max(0,hits.length-1));
  hits.forEach((p,i)=>{
    const d=el('div',i===palSel?'sel':'',`<span>${esc(p.t)}</span><span class="k">${esc(p.s)}</span>`);
    d.onclick=()=>{palClose();p.go()}; res.appendChild(d);
  });
  return hits;
}
function palOpen(){$('#pal').classList.add('on');$('#palin').value='';palSel=0;palRender('');$('#palin').focus()}
function palClose(){$('#pal').classList.remove('on')}

/* ============================ boot ============================ */
(function boot(){
  const hq=D.hq||{};
  $('#statetxt').textContent=hq.state_word||'NO DATA';
  $('#statechip').className='chip live '+(hq.state_word?'ok':'bad');
  $('#clock').innerHTML=esc(hq.now_et_label||D.generated_et||'')+'<br><span style="opacity:.6">'+esc(hq.tape_headline||'')+'</span>';
  const fs=$('#footstamp'); fs.textContent='built '; fs.appendChild(ageEl(D.built_at_et,2));
  navBuild(); palBuild();
  $('#dclose').onclick=closeDrawer; $('#scrim').onclick=closeDrawer;
  $('#palin').addEventListener('input',e=>{palSel=0;palRender(e.target.value)});
  $('#palin').addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){palSel++;palRender($('#palin').value);e.preventDefault()}
    else if(e.key==='ArrowUp'){palSel=Math.max(0,palSel-1);palRender($('#palin').value);e.preventDefault()}
    else if(e.key==='Enter'){const h=palRender($('#palin').value);if(h[palSel]){palClose();h[palSel].go()}}
  });
  $('#pal').addEventListener('click',e=>{if(e.target.id==='pal')palClose()});
  let gPending=false;
  document.addEventListener('keydown',e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();palOpen();return}
    if(e.key==='Escape'){palClose();closeDrawer();return}
    if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
    if(e.key==='g'){gPending=true;setTimeout(()=>gPending=false,900);return}
    if(gPending){const v=VIEWS.find(x=>x.key===e.key);if(v){route(v.id);try{history.replaceState(null,'','#'+v.id)}catch(_){}};gPending=false;return}
    if(e.key==='?'){openDrawer('Keyboard',b=>{
      b.innerHTML='<div class="kv"><span class="k">⌘K / Ctrl+K</span><span class="v">command palette</span></div>'+
        VIEWS.map(v=>`<div class="kv"><span class="k">g then ${v.key}</span><span class="v">${v.label}</span></div>`).join('')+
        '<div class="kv"><span class="k">Esc</span><span class="v">close</span></div>';})}
  });
  addEventListener('hashchange',()=>route()); route();
})();
"""

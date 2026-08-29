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

from gamma_cockpit_views_js import VIEWS_JS

_RUNTIME = r"""
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

/* ---------- heartbeat strip: one bar per tick, newest pulsing ---------- */
function beatClass(v){
  const s=String(v||'').toUpperCase();
  if(s.includes('ENTER')&&!s.includes('REFUS'))return'act';
  if(s.includes('FLATTEN')||s.includes('EXIT')||s.includes('CLOSE'))return'exit';
  if(s.includes('STOP')||s.includes('KILL')||s.includes('REFUS'))return'stop';
  if(s.includes('HOLD'))return'hold';
  return'';
}
function heartbeat(engine,bars){
  const ticks=(engine.ticks||[]).slice(0,bars||40);
  const age=agoOf(engine.last_write), live=(age!=null&&age<=24);
  const w=el('div');
  const strip=el('div','beat'+(live&&!RM?' live':'')+(live?'':' dead'));
  // Oldest on the left so the strip reads left-to-right like a tape.
  ticks.slice().reverse().forEach((t,i,arr)=>{
    const k=beatClass(t.verdict);
    const b=el('i',k+(i===arr.length-1?' now':''));
    b.style.height=(k==='act'?100:(k==='exit'||k==='stop')?76:34)+'%';
    b.title=(t.ts||'')+' - '+(t.verdict||'')+(t.why?' - '+t.why:'');
    strip.appendChild(b);
  });
  if(!ticks.length)strip.appendChild(el('i','',''));
  w.appendChild(strip);
  const lbl=el('div','beatlbl');
  lbl.appendChild(el('span',null,esc(engine.cadence||'')));
  const rt=el('span'); rt.appendChild(el('span',null,'last beat '));
  rt.appendChild(ageEl(engine.last_write,24)); lbl.appendChild(rt);
  w.appendChild(lbl);
  return w;
}

/* ---------- positions: what we are actually holding right now ---------- */
function positionsCard(){
  const p=D.positions;
  if(!p)return null;
  const c=el('div','card');
  const hd=el('div','row wrap');
  hd.innerHTML='<span class="eyebrow">Positions</span>';
  hd.appendChild(el('span','chip '+(p.flat?'':'ok live'),
    (p.flat?'':'<i class="dot"></i>')+(p.flat?'FLAT':p.open.length+' OPEN')));
  hd.appendChild(el('span','sp'));
  const src=el('span','dim'); src.appendChild(el('span',null,'ledger '));
  src.appendChild(ageEl(p.source.last_write,2)); hd.appendChild(src);
  c.appendChild(hd);
  if(p.flat){
    const w=el('div','poswrap'); w.style.marginTop='var(--s5)';
    w.appendChild(el('div','flatbig','FLAT'));
    const note=el('div');
    note.appendChild(el('div','mut','No open option positions on any arm. Rebuilt from '
      +p.option_fills+' option fills - every symbol nets to zero.'));
    if(p.last_close)note.appendChild(el('div','micro','last close '+esc(p.last_close.symbol)+
      ' - '+esc(p.last_close.arm)+' - '+esc(String(p.last_close.ts||'').slice(0,16).replace('T',' '))));
    w.appendChild(note);
    c.appendChild(w);
  }else{
    const tb=el('table'); tb.style.marginTop='var(--s5)';
    tb.innerHTML='<thead><tr><th>Arm</th><th>Contract</th><th>Side</th><th class="n">Qty</th></tr></thead>';
    const b=el('tbody');
    p.open.forEach(o=>b.appendChild(el('tr',null,
      '<td>'+esc(o.arm)+'</td><td class="mono">'+esc(o.symbol)+'</td>'+
      '<td>'+esc(o.side)+'</td><td class="n">'+o.qty+'</td>')));
    tb.appendChild(b); c.appendChild(tb);
  }
  const pills=el('div','row wrap'); pills.style.marginTop='var(--s5)';
  (p.arms||[]).forEach(a=>pills.appendChild(el('span','armpill',esc(a.arm)+' <b>'+a.fills+'</b> fills')));
  c.appendChild(pills);
  // Naming what was deliberately NOT trusted is part of the answer.
  const ig=(p.ignored_stale||[]).filter(x=>x.age_h>720);
  if(ig.length)c.appendChild(el('div','micro','ignored as stale: '+
    ig.map(x=>x.path.split('/').pop()+' ('+Math.round(x.age_h/24)+'d)').join(' - ')));
  c.appendChild(srcRow([p.source]));
  return c;
}

/* ============================ views ============================ */
const VIEWS=[
 {id:'overview',ic:'◎',label:'Overview',key:'o'},
 {id:'desks',ic:'▦',label:'Desks',key:'d'},
 {id:'orchestration',ic:'⛬',label:'Orchestration',key:'g'},
 {id:'engine',ic:'❥',label:'Engine room',key:'e'},
 {id:'agents',ic:'✦',label:'Agents',key:'w'},
 {id:'army',ic:'⌁',label:'Army',key:'m'},
 {id:'cards',ic:'⚑',label:'Cards',key:'c'},
 {id:'journal',ic:'▤',label:'Journal',key:'j'},
 {id:'answers',ic:'✔',label:'Answers',key:'a'},
 {id:'activity',ic:'⟡',label:'Activity',key:'v'},
];

function bookSummary(){
  return ((D.calendar?.views||{}).BOOK||{}).summary||{};
}

__VIEWS_SLOT__

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
const RENDER={overview:vOverview,desks:vDesks,orchestration:vOrch,engine:vEngine,agents:vAgents,army:vArmy,cards:vCards,journal:vJournal,answers:vAnswers,activity:vActivity};
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

# The views are spliced in AFTER the helpers they call and BEFORE the router
# that dispatches to them — __VIEWS_SLOT__ marks that seam.
JS = _RUNTIME.replace("__VIEWS_SLOT__", VIEWS_JS)

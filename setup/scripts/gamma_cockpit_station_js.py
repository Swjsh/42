"""gamma_cockpit_station_js.py -- Station panel client code (GOAL-GAMMA-STATION-
2026-09-13 item (5), "the TV face").

Exports STATION_JS (function stationPanel(st)) and STATION_CSS. Renders off
gamma_cockpit_station.build() (`st`) -- never computes a verdict or a number itself,
only lays out what Python already decided (OP-33: the page renders truth, it does not
derive it).

DEFENSIVE BY CONSTRUCTION (same contract as gamma_cockpit_costpulse_js.py): `el`/
`esc`/`srcRow`/`ic` are assumed global (gamma_cockpit_js.py's _RUNTIME, always
present); `gcRow`/`gcChip`/`gcNoData` (gamma_cockpit_glow_js.py, a sibling module)
are feature-detected with a local st*-prefixed fallback so a load-order gap never
throws.

A falsy `st`, or any of its four sub-sections with ok===false, renders that ONE
sub-section as a designed NO DATA block naming the file it looked for -- never a
fabricated card, brief line, or ledger row.
"""
from __future__ import annotations

STATION_JS = r"""
/* ============================ Station panel (GAMMA-STATION item 5) ============================ */
function stSafe(fn,fallback){ try{ return fn(); }catch(_){ return fallback; } }
function stEl(t,c,h){
  if(typeof el==='function') return el(t,c,h);
  const e=document.createElement(t); if(c)e.className=c; if(h!==undefined)e.innerHTML=h; return e;
}
function stEsc(s){
  if(typeof esc==='function') return esc(s);
  return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function stIc(name){ return stSafe(()=>(typeof ic==='function')?ic(name):'',''); }
function stSrcRow(list){
  if(typeof srcRow==='function')return srcRow(list);
  const d=stEl('div','src');
  (list||[]).forEach(s=>{ d.appendChild(stEl('span',null,stEsc((s&&s.path)||''))); });
  return d;
}
function stTone(verdict){
  const v=String(verdict||'off').toLowerCase();
  return v==='green'?'good':v==='amber'?'warn':v==='red'?'bad':'info';
}
function stChip(label,tone){
  if(typeof gcChip==='function')return gcChip(label,tone);
  return stEl('span','gc-chip '+(tone||'info'),stEsc(label));
}
function stRow(opts){
  if(typeof gcRow==='function')return gcRow(opts);
  opts=opts||{};
  const row=stEl('div','gc-row');
  const text=stEl('div','gc-row__text');
  text.appendChild(stEl('div','gc-row__title',stEsc(opts.title||'')));
  text.appendChild(stEl('div','gc-row__sub',stEsc(opts.sub==null?'NO DATA':String(opts.sub))));
  row.appendChild(text);
  if(opts.chipLabel)row.appendChild(stChip(opts.chipLabel,opts.chipTone));
  return row;
}
function stNoDataBlock(label,lookedFor){
  if(typeof gcNoData==='function')return gcNoData(label,lookedFor);
  const box=stEl('div','gc-nodata');
  box.appendChild(document.createTextNode('NO DATA'+(lookedFor?(', looked for '+lookedFor):'')));
  return box;
}

function stIdeaCard(card){
  card=card||{};
  const c=stEl('div','gc-idea-card');
  const head=stEl('div','gc-idea-card__head');
  head.appendChild(stEl('div','gc-idea-card__title',stEsc(card.title||'(untitled)')));
  if(card.confidence)head.appendChild(stChip(String(card.confidence).toUpperCase(),
    card.confidence==='high'?'good':card.confidence==='med'?'info':'warn'));
  if(card.status)head.appendChild(stChip(String(card.status).toUpperCase(),
    card.status==='shipped'?'good':card.status==='killed'?'bad':'info'));
  c.appendChild(head);
  if(card.mechanism)c.appendChild(stEl('p',null,stEsc(card.mechanism)));
  const ev=(card.evidence||[]).slice(0,6);
  if(ev.length){
    const ul=stEl('ul','gc-idea-card__evidence');
    ev.forEach(function(e){ul.appendChild(stEl('li',null,stEsc(e)));});
    c.appendChild(ul);
  }
  if(card.proposed_shadow_test)c.appendChild(stEl('p',null,'Shadow test: '+stEsc(card.proposed_shadow_test)));
  const metaBits=[];
  if(card.cost_line)metaBits.push(stEsc(card.cost_line));
  if(card.ts_et)metaBits.push(stEsc(card.ts_et));
  if(metaBits.length)c.appendChild(stEl('div','gc-idea-card__meta',metaBits.join(' · ')));
  return c;
}

function stLedgerRow(row){
  row=row||{};
  const r=stEl('div','gc-station__ledger-row');
  r.appendChild(stEl('span','num',stEsc(row.ts_et||'')));
  const tone=row.status==='ok'?'good':row.status==='yielded'?'info':row.status==='error'?'bad':'info';
  r.appendChild(stChip(String(row.status||'?').toUpperCase(),tone));
  r.appendChild(stEl('span',null,stEsc(row.reason||'')));
  r.appendChild(stEl('span','num',row.duration_s==null?'-':(Number(row.duration_s).toFixed(1)+'s')));
  const toks=(row.prompt_tokens!=null||row.gen_tokens!=null)?
    ((row.prompt_tokens||0)+'/'+(row.gen_tokens||0)):'-';
  r.appendChild(stEl('span','num',toks));
  return r;
}

/* function stationPanel(st) -> HTMLElement
   st = gamma_cockpit_station.build() payload (falsy/ok:false everywhere = no data) */
function stationPanel(st){
  const panel=stEl('div','gc-panel gc-station');
  panel.appendChild(stEl('p','gc-eyebrow',stIc('radio')+' Station'));
  const body=stEl('div','gc-panel__body');
  panel.appendChild(body);

  if(!st){
    body.appendChild(stNoDataBlock('Station','automation/state/station/*'));
    return panel;
  }

  const ideas=st.ideas||{}, brief=st.brief||{}, planner=st.planner||{}, ledger=st.ledger||{};

  const pBlock=stEl('div','gc-station__block');
  pBlock.appendChild(stEl('h4',null,'Planner'));
  if(planner.ok){
    const lr=planner.last_row||{};
    const bits=[];
    bits.push('model '+(planner.model||'unknown'));
    bits.push('mode '+(planner.mode||'work'));
    bits.push(planner.gpu_util_pct==null?'gpu NO DATA':('gpu '+Math.round(planner.gpu_util_pct)+'%'));
    if(lr.duration_s!=null)bits.push(Number(lr.duration_s).toFixed(1)+'s last fire');
    if(lr.cards_added!=null)bits.push(lr.cards_added+' card(s) added');
    pBlock.appendChild(stRow({title:planner.say||'planner',sub:bits.join(' · '),
      chipLabel:String(planner.verdict||'off').toUpperCase(),chipTone:stTone(planner.verdict)}));
  }else{
    pBlock.appendChild(stNoDataBlock('Planner',planner.path||'automation/state/station/config.json'));
  }
  body.appendChild(pBlock);

  const bBlock=stEl('div','gc-station__block');
  bBlock.appendChild(stEl('h4',null,'Latest brief'));
  if(brief.ok&&brief.text){
    bBlock.appendChild(stEl('p','gc-station__brief',stEsc(brief.text)));
  }else{
    bBlock.appendChild(stNoDataBlock('Latest brief',brief.path||'automation/state/station/station-brief.md'));
  }
  body.appendChild(bBlock);

  const iBlock=stEl('div','gc-station__block');
  const cards=ideas.cards||[];
  iBlock.appendChild(stEl('h4',null,'Ideas board ('+cards.length+')'));
  if(ideas.ok&&cards.length){
    const list=stEl('div','gc-station__cards');
    cards.slice().reverse().forEach(function(c){list.appendChild(stIdeaCard(c));});
    iBlock.appendChild(list);
  }else{
    iBlock.appendChild(stNoDataBlock('Ideas board',ideas.path||'automation/state/station/ideas-board.json'));
  }
  body.appendChild(iBlock);

  const lBlock=stEl('div','gc-station__block');
  const rows=ledger.rows||[];
  lBlock.appendChild(stEl('h4',null,'Last '+rows.length+' loop fires'));
  if(ledger.ok&&rows.length){
    const wrap=stEl('div','gc-station__ledger');
    rows.slice().reverse().forEach(function(r){wrap.appendChild(stLedgerRow(r));});
    lBlock.appendChild(wrap);
  }else{
    lBlock.appendChild(stNoDataBlock('Loop ledger',ledger.path||'automation/state/station/loop-ledger.jsonl'));
  }
  body.appendChild(lBlock);

  const sources=[ideas.source,brief.source,planner.source,ledger.source].filter(Boolean);
  if(sources.length)panel.appendChild(stSrcRow(sources));
  return panel;
}
"""

STATION_CSS = r"""
.gc-station .gc-panel__body{display:flex;flex-direction:column;gap:var(--s5,16px)}
.gc-station__block{display:flex;flex-direction:column;gap:6px}
.gc-station__block h4{margin:0;font:600 12px/1.2 var(--font);letter-spacing:.02em;color:var(--gc-ink-3)}
.gc-station__brief{font:400 13px/1.5 var(--font);color:var(--gc-ink-2);white-space:pre-wrap;margin:0}
.gc-station__cards{display:flex;flex-direction:column;max-height:420px;overflow-y:auto}
.gc-idea-card{padding:10px 0;border-top:1px solid var(--gc-line)}
.gc-idea-card:first-child{border-top:none;padding-top:0}
.gc-idea-card__head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.gc-idea-card__title{font:600 13px/1.3 var(--font);color:var(--gc-ink-1);flex:1;min-width:160px}
.gc-idea-card p{margin:4px 0 0;font:400 12px/1.5 var(--font);color:var(--gc-ink-2)}
.gc-idea-card__evidence{margin:4px 0 0;padding-left:16px;font:400 12px/1.5 var(--font);color:var(--gc-ink-3)}
.gc-idea-card__evidence li{margin:2px 0}
.gc-idea-card__meta{margin-top:4px;font:500 12px/1.4 var(--font);color:var(--gc-ink-3)}
.gc-station__ledger{display:flex;flex-direction:column;gap:2px}
.gc-station__ledger-row{display:grid;grid-template-columns:150px 72px 1fr 56px 72px;gap:8px;
  align-items:center;padding:4px 0;font:400 12px/1.4 var(--font);color:var(--gc-ink-2);
  border-top:1px solid var(--gc-line)}
.gc-station__ledger-row:first-child{border-top:none}
.gc-station__ledger-row .num{font-variant-numeric:tabular-nums;color:var(--gc-ink-3)}
"""

"""gamma_cockpit_autonomy_js.py - the Autonomy view's client-side code.

Split out as its own module, same reasoning as gamma_cockpit_army_js.py /
gamma_cockpit_cards_js.py at the repo's 800-line ceiling. Concatenated onto
VIEWS_JS at import time, so it shares every helper defined in
gamma_cockpit_js.py's runtime (el, esc, ageEl, agoOf, srcRow, health, M, M2,
openDrawer, closeDrawer, spot, stag, route, $, ...) exactly like the other
views do -- same invariants, same order-matters concatenation contract.

WHY THIS VIEW EXISTS (GOAL-GAMMA-AUTONOMY-2026-09-03, DONE-WHEN (d)): J, verbatim
-- "we have an entire 'goal' dashboard and nothing is driving it ... i need to
see it happening, on the dashboard". `gamma_home.py` already computed
`payload["autonomy"]` (gamma_autonomy.py) and now `payload["goal"]` /
`payload["learning"]`, but no screen ever rendered them. This is that screen.

Reads D.autonomy, D.goal (== D.autonomy.goal, hoisted for convenience) and
D.learning. Never computes a metric -- every number here was built in Python;
this file only lays it out and names its source.
"""
from __future__ import annotations

AUTONOMY_JS = r"""
/* ---------- AUTONOMY: is Gamma driving, and what is it doing about it ---------- */
const LEARN_COUNT_KEYS=[
  ['kitchen_tasks_completed','Kitchen tasks completed'],
  ['kitchen_analyses','Kitchen analyses'],
  ['kitchen_keepers','Kitchen keepers'],
  ['preregs_filed','Preregs filed'],
  ['preregs_adjudicated','Preregs adjudicated'],
  ['shadow_rows','Shadow rows'],
  ['candidates_filed','Candidates filed'],
  ['conductor_fires','Conductor fires'],
  ['conductor_drained','Conductor drained'],
  ['commits','Commits'],
  ['self_audit_gaps','Self-audit gaps'],
  ['study_topics','Study topics'],
  ['lessons_added','Lessons added'],
];
const AUTONOMY_QUEUE_CHIP={
  todo:['','TODO'], wip:['warn','WIP'], done:['ok','DONE'],
  blocked:['bad','BLOCKED'], blocked_j:['bad','J'],
};
function autonomyQueueChip(state){
  const [cl,lbl]=AUTONOMY_QUEUE_CHIP[state]||['','TODO'];
  return el('span','chip '+cl,'<i class="dot"></i>'+lbl);
}
function autonomyGoalChip(g){
  if(!g||!g.active)return el('span','chip bad','<i class="dot"></i>NO ACTIVE GOAL');
  if(g.days_left!=null&&g.days_left<0)return el('span','chip warn','<i class="dot"></i>EXPIRED');
  return el('span','chip ok live','<i class="dot"></i>ACTIVE');
}
function autonomyFireDrawer(o){
  openDrawer(o.task||'Fire',b=>{
    const k=el('div');
    [['At',o.at],['Task',o.task],['Drained',o.drained],['Lessons',o.lessons],['Regressions',o.regressions]]
      .forEach(([a,v])=>k.appendChild(el('div','kv','<span class="k">'+esc(a)+'</span><span class="v">'+
        esc(v==null?'—':v)+'</span>')));
    b.appendChild(k);
    if(o.note)b.appendChild(el('div','mut',esc(o.note)));
  });
}
function autonomyErrorsDrawer(errs){
  openDrawer('Learning ledger — NO DATA sources',b=>{
    Object.keys(errs).forEach(k=>b.appendChild(el('div','kv',
      '<span class="k">'+esc(k)+'</span><span class="v">'+esc(errs[k])+'</span>')));
  });
}

function vAutonomy(h){
  const A=D.autonomy||{}, g=D.goal||A.goal||null, LN=D.learning||{windows:{},latest_verdicts:[]};

  /* ---------- 1. HERO: Working on ---------- */
  const hero=el('div','card gborder');
  const hd=el('div','row wrap');
  hd.appendChild(el('span','eyebrow','Working on'));
  hd.appendChild(autonomyGoalChip(g));
  hero.appendChild(hd);

  if(g&&g.active){
    const title=el('div','mid'); title.style.marginTop='var(--s4)';
    title.appendChild(document.createTextNode(g.title||g.id||'—'));
    const idsp=el('span','dim mono',esc(g.id||'')); idsp.style.marginLeft='var(--s3)';
    title.appendChild(idsp);
    hero.appendChild(title);
    if(g.verbatim){
      const v=el('div','mut',esc('“'+g.verbatim+'”'));
      v.style.cssText='font-style:italic;margin-top:var(--s3);max-width:78ch';
      hero.appendChild(v);
    }
    const nextTxt=g.next_item||(A.next_move&&A.next_move.text)||null;
    if(nextTxt){
      const nx=el('div','mut'); nx.style.marginTop='var(--s4)';
      nx.innerHTML='<b>Next →</b> '+esc(nextTxt);
      hero.appendChild(nx);
    }
    const meta=el('div','row wrap dim'); meta.style.marginTop='var(--s3)';
    if(g.days_left!=null)meta.appendChild(el('span',null,g.days_left+' days left'));
    if(g.opened_at_et){const a=el('span',null,'opened '); a.appendChild(ageEl(g.opened_at_et,24*400)); meta.appendChild(a);}
    hero.appendChild(meta);

    if((g.done_when||[]).length){
      const dw=el('div'); dw.style.marginTop='var(--s5)';
      dw.appendChild(el('div','micro','DONE-WHEN'));
      g.done_when.forEach(x=>dw.appendChild(el('div','mut','• '+esc(x))));
      hero.appendChild(dw);
    }
    if((g.queue||[]).length){
      const qw=el('div'); qw.style.marginTop='var(--s5)';
      qw.appendChild(el('div','micro','QUEUE'));
      g.queue.forEach(it=>{
        const row=el('div','row wrap'); row.style.cssText='padding:var(--s3) 0;align-items:flex-start';
        row.appendChild(autonomyQueueChip(it.state));
        row.appendChild(el('span','mut',esc(it.text)));
        qw.appendChild(row);
      });
      hero.appendChild(qw);
    }
    if((g.progress_log||[]).length){
      const pl=el('div'); pl.style.marginTop='var(--s5)';
      pl.appendChild(el('div','micro','PROGRESS LOG'));
      g.progress_log.forEach(x=>pl.appendChild(el('div','micro','• '+esc(x))));
      hero.appendChild(pl);
    }
    if(g.honest_state){
      const hs=el('div','mut',esc(g.honest_state));
      hs.style.cssText='border-left:2px solid var(--acc);padding-left:var(--s4);margin-top:var(--s5);color:var(--tx-2)';
      hero.appendChild(hs);
    }
    if(g.source)hero.appendChild(srcRow([{path:g.source,ok:true}]));
  }else{
    const fl=el('div','flag bad'); fl.style.marginTop='var(--s4)';
    const ap=A.autopilot;
    const apTxt=ap?('autopilot: '+esc(ap.action||'?')+(ap.reason?' — '+esc(ap.reason):'')):'autopilot: NO DATA';
    fl.innerHTML='<b>NOT DRIVING</b> no active goal. '+apTxt;
    hero.appendChild(fl);
  }
  h.appendChild(hero);

  /* ---------- 2. Tonight's fires ---------- */
  const fc=el('div','card'); fc.style.marginTop='var(--s5)';
  fc.appendChild(el('h3',null,'Tonight’s fires'));
  const bud=A.budget||{};
  const brow=el('div','row wrap'); brow.style.marginTop='var(--s4)';
  brow.appendChild(el('span','chip '+health(bud.verdict),'<i class="dot"></i>'+esc(bud.verdict||'NO DATA')));
  brow.appendChild(el('span','mut',(bud.fires_used??'—')+' / '+(bud.fires_cap??'—')+' fires'));
  brow.appendChild(el('span','mut',M2(bud.spent_usd)+' / '+M2(bud.cap_usd)));
  fc.appendChild(brow);
  if(bud.reason)fc.appendChild(el('div','dim',esc(bud.reason)));
  const conductor=(A.tasks||{}).Gamma_Conductor||{};
  fc.appendChild(el('div','micro','next Gamma_Conductor run: '+esc(conductor.next_run||'unknown')));
  const fires=A.recent_fires||[];
  if(!fires.length){
    fc.appendChild(el('div','note','no fires recorded'));
  }else{
    const list=el('div'); list.style.marginTop='var(--s4)';
    fires.forEach(o=>{
      const r=el('div','row wrap click'); r.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle);cursor:pointer';
      r.appendChild(el('span','mono dim',esc(o.task||'—')));
      if(o.at)r.appendChild(ageEl(o.at));
      if(o.drained!=null)r.appendChild(el('span','micro',o.drained+' drained'));
      if(o.note)r.appendChild(el('span','mut',esc(o.note)));
      r.onclick=()=>autonomyFireDrawer(o);
      list.appendChild(r);
    });
    fc.appendChild(list);
  }
  h.appendChild(fc);

  /* ---------- 3. What Gamma learned ---------- */
  const lc=el('div','card'); lc.style.marginTop='var(--s5)';
  lc.appendChild(el('h3',null,'What Gamma learned'));
  if(LN.error)lc.appendChild(el('div','flag bad','<b>NO DATA</b> '+esc(LN.error)));
  const tw=(LN.windows||{}).today||{}, w7=(LN.windows||{})['7d']||{};
  const ltab=el('table'); ltab.style.marginTop='var(--s4)';
  ltab.innerHTML='<thead><tr><th>Metric</th><th class="n">Today</th><th class="n">7d</th></tr></thead>';
  const ltb=el('tbody');
  const learnCell=(v)=>(v==null||v==='NO DATA')
    ?'<td class="n"><span class="chip warn">NO DATA</span></td>'
    :'<td class="n mono">'+esc(v)+'</td>';
  LEARN_COUNT_KEYS.forEach(([k,label])=>{
    ltb.appendChild(el('tr',null,'<td>'+esc(label)+'</td>'+learnCell(tw[k])+learnCell(w7[k])));
  });
  ltab.appendChild(ltb); lc.appendChild(ltab);
  const vwrap=el('div'); vwrap.style.marginTop='var(--s5)';
  vwrap.appendChild(el('div','micro','LATEST VERDICTS'));
  const verdicts=LN.latest_verdicts||[];
  if(!verdicts.length)vwrap.appendChild(el('div','note','no verdicts yet'));
  verdicts.forEach(v=>{
    const kind=String(v.kind||'').toUpperCase();
    const kcls=['KILL','FAIL'].includes(kind)?'bad':['SHIP','PASS','KEEPER'].includes(kind)?'ok':'warn';
    const row=el('div','row wrap'); row.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle)';
    row.innerHTML='<span class="chip '+kcls+'"><i class="dot"></i>'+esc(kind||'—')+'</span>'+
      '<span style="font-weight:600">'+esc(v.subject||'')+'</span>'+
      '<span class="mut">'+esc(v.text||'')+'</span>';
    if(v.at_et)row.appendChild(ageEl(v.at_et));
    vwrap.appendChild(row);
    if(v.source)vwrap.appendChild(srcRow([{path:v.source,ok:true}]));
  });
  lc.appendChild(vwrap);
  const errs=LN.errors||{};
  const errKeys=Object.keys(errs);
  if(errKeys.length){
    const eln=el('div','dim click',errKeys.length+' sources NO DATA');
    eln.style.cssText='margin-top:var(--s4);cursor:pointer';
    eln.onclick=()=>autonomyErrorsDrawer(errs);
    lc.appendChild(eln);
  }
  h.appendChild(lc);

  /* ---------- 4. Research engines ---------- */
  h.appendChild(el('div','shead','<h2>Research engines</h2><span class="dim">kitchen · prospector · autofire · quiet mode · goal autopilot</span>'));
  const eng=A.engines||{};
  const grid=el('div','grid g2');

  const kc=el('div','card'); kc.appendChild(el('h3',null,'Kitchen'));
  const k=eng.kitchen;
  if(!k){kc.appendChild(el('div','note','NO DATA'));}
  else{
    const r=el('div','row wrap');
    r.appendChild(el('span','chip '+(k.alive?'ok live':'bad'),'<i class="dot"></i>'+(k.alive?'ALIVE':'DEAD')));
    r.appendChild(el('span','dim',k.idle?'idle':'busy'));
    kc.appendChild(r);
    if(k.current_task_id)kc.appendChild(el('div','micro','current: '+esc(k.current_task_id)));
    kc.appendChild(el('div','row wrap',
      '<span class="stat">'+esc(k.pending??'—')+'</span><span class="dim">pending</span><span class="sp"></span>'+
      '<span class="stat">'+esc(k.completed??'—')+'</span><span class="dim">completed</span>'));
    kc.appendChild(el('div','micro','cost today $'+(k.cost_today!=null?Number(k.cost_today).toFixed(2):'—')+
      ' / cap $'+(k.cost_cap!=null?Number(k.cost_cap).toFixed(2):'—')));
    if(k.updated_at_et){const a=el('div','micro'); a.appendChild(document.createTextNode('updated ')); a.appendChild(ageEl(k.updated_at_et)); kc.appendChild(a);}
    (k.recent||[]).slice(0,3).forEach(t=>kc.appendChild(el('div','micro','• '+esc(t.task||''))));
  }
  grid.appendChild(kc);

  const pc=el('div','card'); pc.appendChild(el('h3',null,'Prospector'));
  const p=eng.prospector;
  if(!p){pc.appendChild(el('div','note','NO DATA'));}
  else{
    pc.appendChild(el('div','row wrap',
      '<span class="stat">'+esc(p.ideas_total??'—')+'</span><span class="dim">ideas</span><span class="sp"></span>'+
      '<span class="stat">'+esc(p.promoted_total??'—')+'</span><span class="dim">promoted</span><span class="sp"></span>'+
      '<span class="stat">'+esc(p.folded_total??'—')+'</span><span class="dim">folded</span>'));
    if(p.last_run_et){const a=el('div','micro'); a.appendChild(document.createTextNode('last run ')); a.appendChild(ageEl(p.last_run_et)); pc.appendChild(a);}
  }
  grid.appendChild(pc);

  const fcard=el('div','card'); fcard.appendChild(el('h3',null,'Autofire'));
  const af=A.autofire||{};
  if(!af.ever_fired){
    const last=af.last||{};
    fcard.appendChild(el('div','flag bad','<b>NEVER FIRED</b> fired today '+esc(af.fired_today??0)+
      (last.decision?' — last decision: '+esc(last.decision)+(last.reason?' ('+esc(String(last.reason).slice(0,120))+')':''):'')));
  }else{
    fcard.appendChild(el('div','row wrap','<span class="chip ok live"><i class="dot"></i>HAS FIRED</span>'+
      '<span class="dim">'+esc(af.fired_today??0)+' today</span>'));
  }
  grid.appendChild(fcard);

  const qc=el('div','card'); qc.appendChild(el('h3',null,'Quiet mode'));
  const q=A.quiet||{};
  qc.appendChild(el('div','row wrap','<span class="chip '+(q.active?'warn':'ok')+'"><i class="dot"></i>'+
    (q.active?'QUIET':'AWAKE')+'</span><span class="dim">'+esc(q.window||'—')+'</span>'));
  if(q.next_loud)qc.appendChild(el('div','micro','next loud '+esc(q.next_loud)));
  grid.appendChild(qc);

  const gac=el('div','card'); gac.appendChild(el('h3',null,'Goal autopilot'));
  const ap2=A.autopilot;
  if(!ap2){gac.appendChild(el('div','note','NO DATA — not wired yet'));}
  else{
    if(ap2.action)gac.appendChild(el('div','mut',esc(ap2.action)));
    if(ap2.reason)gac.appendChild(el('div','dim',esc(ap2.reason)));
    (ap2.ladder||[]).slice(0,5).forEach(l=>{
      const row=el('div','row wrap'); row.style.cssText='padding:var(--s2) 0';
      // ladder states: queued -> todo, active -> wip, done -> done (mirrors the QUEUE chips)
      row.appendChild(autonomyQueueChip(l.state==='queued'?'todo':(l.state==='active'?'wip':(l.state||'todo'))));
      row.appendChild(el('span','micro',esc(l.id||'')+(l.why?' — '+esc(l.why):'')));
      gac.appendChild(row);
    });
  }
  grid.appendChild(gac);

  h.appendChild(grid); stag(grid);
}
"""

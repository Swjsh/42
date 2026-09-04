"""gamma_cockpit_autonomy_js.py - the Autonomy view's client-side code.

Split out as its own module, same reasoning as gamma_cockpit_army_js.py /
gamma_cockpit_cards_js.py at the repo's 800-line ceiling. Concatenated onto
VIEWS_JS at import time, so it shares every helper defined in
gamma_cockpit_js.py's runtime (el, esc, ageEl, agoOf, srcRow, health, M, M2,
openDrawer, closeDrawer, RM, ...) exactly like the other views do -- same
invariants, same order-matters concatenation contract.

QUIET COMMAND REBUILD (COCKPIT-DESIGN-SPEC-2026-09-03, WORKSTREAM
F_command_view, 2026-09-03): the Autonomy view is no longer a second surface.
`vAutonomy(h)` now mounts Command (`gamma_cockpit_command_js.py`'s `vCommand`)
and opens/scrolls the Goal band's tile -- "autonomy" stays a registered
PRIMARY nav id (test_view_wired_into_render_and_nav asserts the literal
string), it just renders visually hidden and is a scrolled-and-opened alias
into Command, same pattern as every other retired view id (vOverview,
vCards, vArmy, ...).

`goalBody(host)` is what survives from the old view: the DONE-WHEN / QUEUE /
PROGRESS LOG / HONEST STATE / source block, tonight's fires, and the learning
counts table -- everything the old hero card showed, now rendered as the Goal
band's `<details>` expansion (spec section 3 band 4, section 4 "Expand") by
`gamma_cockpit_command_js.py`'s `cmdGoalTile()`, which passes `goalBody` in as
`spec.body`. The old "Research engines" grid (kitchen/prospector/autofire/
quiet/goal-autopilot cards) is NOT moved here -- Kitchen and Prospector are
now Research-group producer rows (`gamma_cockpit_producers_js.py`), which is
where that data belongs going forward; carrying the old grid into goalBody
too would just show the same facts twice.

WHY THIS VIEW EXISTS (GOAL-GAMMA-AUTONOMY-2026-09-03, DONE-WHEN (d)): J,
verbatim -- "we have an entire 'goal' dashboard and nothing is driving it ...
i need to see it happening, on the dashboard". `gamma_home.py` already
computed `payload["autonomy"]` (gamma_autonomy.py) and `payload["goal"]` /
`payload["learning"]`; this file (now via Command) is what renders them.

Reads D.autonomy, D.goal (== D.autonomy.goal, hoisted for convenience) and
D.learning. Never computes a metric -- every number here was built in Python;
this file only lays it out and names its source.
"""
from __future__ import annotations

AUTONOMY_JS = r"""
/* ---------- AUTONOMY: Command, scrolled to the goal ---------- */
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
function autonomyFireDrawer(o){
  openDrawer(o.task||'Fire',b=>{
    const k=el('div');
    [['At',o.at],['Task',o.task],['Drained',o.drained],['Lessons',o.lessons],['Regressions',o.regressions]]
      .forEach(([a,v])=>k.appendChild(el('div','kv','<span class="k">'+esc(a)+'</span><span class="v">'+
        esc(v==null?'-':v)+'</span>')));
    b.appendChild(k);
    if(o.note)b.appendChild(el('div','mut',esc(o.note)));
  });
}
function autonomyErrorsDrawer(errs){
  openDrawer('Learning ledger, NO DATA sources',b=>{
    Object.keys(errs).forEach(k=>b.appendChild(el('div','kv',
      '<span class="k">'+esc(k)+'</span><span class="v">'+esc(errs[k])+'</span>')));
  });
}

/* ---------- goalBody: the Goal band's expansion ---------- */
function goalBody(host){
  const A=D.autonomy||{}, g=D.goal||A.goal||null, LN=D.learning||{windows:{},latest_verdicts:[]};

  if(g&&g.active){
    if(g.verbatim){
      const v=el('div','body',esc('"'+g.verbatim+'"'));
      v.style.cssText='font-style:italic;max-width:72ch';
      host.appendChild(v);
    }
    const nextTxt=g.next_item||(A.next_move&&A.next_move.text)||null;
    if(nextTxt){
      const nx=el('div','body'); nx.style.marginTop='var(--s4)';
      nx.innerHTML='<b>Next</b> '+esc(nextTxt);
      host.appendChild(nx);
    }
    if(g.days_left!=null){
      const meta=el('div','meta'); meta.style.marginTop='var(--s3)';
      meta.textContent=g.days_left+' days left';
      host.appendChild(meta);
    }
    if(g.opened_at_et){
      const a=el('div','meta'); a.style.marginTop='var(--s2)';
      a.appendChild(document.createTextNode('opened ')); a.appendChild(ageEl(g.opened_at_et,24*400));
      host.appendChild(a);
    }
    if((g.done_when||[]).length){
      const dw=el('div'); dw.style.marginTop='var(--s5)';
      dw.appendChild(el('div','meta','Done when'));
      g.done_when.forEach(x=>dw.appendChild(el('div','body','- '+esc(x))));
      host.appendChild(dw);
    }
    if((g.queue||[]).length){
      const qw=el('div'); qw.style.marginTop='var(--s5)';
      qw.appendChild(el('div','meta','Queue'));
      g.queue.forEach(it=>{
        const row=el('div','row wrap'); row.style.cssText='padding:var(--s3) 0;align-items:flex-start';
        row.appendChild(autonomyQueueChip(it.state));
        row.appendChild(el('span','body',esc(it.text)));
        qw.appendChild(row);
      });
      host.appendChild(qw);
    }
    if((g.progress_log||[]).length){
      const pl=el('div'); pl.style.marginTop='var(--s5)';
      pl.appendChild(el('div','meta','Progress log'));
      g.progress_log.forEach(x=>pl.appendChild(el('div','meta','- '+esc(x))));
      host.appendChild(pl);
    }
    if(g.honest_state){
      const hs=el('div','body',esc(g.honest_state));
      hs.style.cssText='border-left:2px solid var(--acc-line,var(--acc));padding-left:var(--s4);'+
        'margin-top:var(--s5);color:var(--tx-2)';
      host.appendChild(hs);
    }
    if(g.source)host.appendChild(srcRow([{path:g.source,ok:true}]));
  }else{
    const fl=el('div','body');
    const ap=A.autopilot;
    const apTxt=ap?('autopilot: '+esc(ap.action||'?')+(ap.reason?'. '+esc(ap.reason):'')):'autopilot: NO DATA';
    fl.innerHTML='<b>NOT DRIVING</b> no active goal. '+apTxt;
    host.appendChild(fl);
  }

  /* Tonight's fires */
  const fs=el('div'); fs.style.marginTop='var(--s6)';
  fs.appendChild(el('div','meta',"Tonight's fires"));
  const bud=A.budget||{};
  const brow=el('div','row wrap'); brow.style.marginTop='var(--s4)';
  brow.appendChild(el('span','chip '+health(bud.verdict),'<i class="dot"></i>'+esc(bud.verdict||'NO DATA')));
  brow.appendChild(el('span','body',(bud.fires_used??'-')+' / '+(bud.fires_cap??'-')+' fires'));
  brow.appendChild(el('span','body',M2(bud.spent_usd)+' / '+M2(bud.cap_usd)));
  fs.appendChild(brow);
  if(bud.reason)fs.appendChild(el('div','body',esc(bud.reason)));
  const conductor=(A.tasks||{}).Gamma_Conductor||{};
  fs.appendChild(el('div','meta','next Gamma_Conductor run: '+esc(conductor.next_run||'unknown')));
  const fires=A.recent_fires||[];
  if(!fires.length){
    fs.appendChild(el('div','body','no fires recorded'));
  }else{
    const list=el('div'); list.style.marginTop='var(--s4)';
    fires.forEach(o=>{
      const r=el('div','row wrap'); r.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle);cursor:pointer';
      r.appendChild(el('span','meta',esc(o.task||'-')));
      if(o.at)r.appendChild(ageEl(o.at));
      if(o.drained!=null)r.appendChild(el('span','meta',o.drained+' drained'));
      if(o.note)r.appendChild(el('span','body',esc(o.note)));
      r.onclick=()=>autonomyFireDrawer(o);
      list.appendChild(r);
    });
    fs.appendChild(list);
  }
  host.appendChild(fs);

  /* Learning counts */
  const lc=el('div'); lc.style.marginTop='var(--s6)';
  lc.appendChild(el('div','meta','What Gamma learned'));
  if(LN.error)lc.appendChild(el('div','body','NO DATA '+esc(LN.error)));
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
  vwrap.appendChild(el('div','meta','Latest verdicts'));
  const verdicts=LN.latest_verdicts||[];
  if(!verdicts.length)vwrap.appendChild(el('div','body','no verdicts yet'));
  verdicts.forEach(v=>{
    const kind=String(v.kind||'').toUpperCase();
    const kcls=['KILL','FAIL'].includes(kind)?'bad':['SHIP','PASS','KEEPER'].includes(kind)?'ok':'warn';
    const row=el('div','row wrap'); row.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle)';
    row.innerHTML='<span class="chip '+kcls+'"><i class="dot"></i>'+esc(kind||'-')+'</span>'+
      '<span style="font-weight:600">'+esc(v.subject||'')+'</span>'+
      '<span class="body">'+esc(v.text||'')+'</span>';
    if(v.at_et)row.appendChild(ageEl(v.at_et));
    vwrap.appendChild(row);
    if(v.source)vwrap.appendChild(srcRow([{path:v.source,ok:true}]));
  });
  lc.appendChild(vwrap);
  const errs=LN.errors||{};
  const errKeys=Object.keys(errs);
  if(errKeys.length){
    const eln=el('div','body click',errKeys.length+' sources NO DATA');
    eln.style.cssText='margin-top:var(--s4);cursor:pointer';
    eln.onclick=()=>autonomyErrorsDrawer(errs);
    lc.appendChild(eln);
  }
  host.appendChild(lc);
}

function vAutonomy(h){
  if(typeof vCommand==='function')vCommand(h);
  if(typeof tileOpen==='function')tileOpen('tile-goal',{scroll:true});
}
"""

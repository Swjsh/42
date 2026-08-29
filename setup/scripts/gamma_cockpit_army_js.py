"""gamma_cockpit_army_js.py - the Army view's client-side code.

Split out of gamma_cockpit_views_js.py at the repo's 800-line ceiling (adding
this view pushed that file to 816). Concatenated onto VIEWS_JS at import time,
so it shares every helper defined in gamma_cockpit_js.py's runtime (el, esc,
RM, agoOf, srcRow, openDrawer, ...) exactly like the other seven views do --
same invariants, same order-matters concatenation contract.

Reads payload["army"] (built by setup/scripts/gamma_cockpit_army.py) and, when
served over http instead of file://, polls GET /api/army?since= for new rows.
"""
from __future__ import annotations

ARMY_JS = r"""
/* ---------- ARMY: orchestrator -> sessions -> workers, and the pulse ----------
   file:// -> renderSnapshot only, baked D.army, no polling, no fake animation.
   Served via the companion (127.0.0.1:4317) -> 1s poll of /api/army?since=, real pulses.
   The poll/RAF loops are SELF-TERMINATING: each tick checks that #armysvg is
   still in the document before doing anything else, and stops silently the
   moment the router has replaced #view with a different screen. Nothing here
   hooks the shared router to make that true. */
let armyState=null;

function armySvg(a){
  const ns='http://www.w3.org/2000/svg';
  const mk=(t,attrs)=>{const e=document.createElementNS(ns,t);for(const k in (attrs||{}))e.setAttribute(k,attrs[k]);return e};
  const stxt=(x,y,str,c,sz,w)=>{const e=mk('text',{x,y,fill:c||'var(--tx-2)','font-size':sz||11,
    'font-family':'var(--font)','font-weight':w||500,'text-anchor':'middle'});e.textContent=str;return e};

  const sessions=(a.sessions||[]).slice(0,12), workers=a.workers||[];
  const byWorkerSession={};
  workers.forEach(w=>(byWorkerSession[w.session_id]=byWorkerSession[w.session_id]||[]).push(w));
  const nameToSid={}; sessions.forEach(s=>nameToSid[s.name]=s.session_id);
  // "recently talked" beats plain aliveness for the dot colour -- see build_army()'s
  // last_seen computation; recomputed as pulses arrive via armyDotColour() below.
  const lastSeen={}; (a.pulses||[]).forEach(r=>{if(r.session_id&&r.ts)lastSeen[r.session_id]=r.ts});

  const N=Math.max(1,sessions.length), W=Math.max(880,N*200+140), sessY=210, H=sessY+150;
  const svg=mk('svg',{viewBox:`0 0 ${W} ${H}`,id:'armysvg'});
  svg.setAttribute('width','100%');svg.setAttribute('height',H);svg.style.minWidth='780px';

  const centers={}, edges={};
  const ocx=W/2, ocy=48;
  centers.orc={x:ocx,y:ocy};
  const orc=a.orchestrator;
  const og=mk('g',{class:'army-node',id:'army-orc'});
  og.appendChild(mk('rect',{x:ocx-120,y:ocy-32,width:240,height:64,rx:14,fill:'var(--bg-2)',stroke:'var(--acc)','stroke-width':1.6}));
  og.appendChild(stxt(ocx,ocy-12,'ORCHESTRATOR','var(--tx-4)',10,600));
  og.appendChild(stxt(ocx,ocy+9,orc?orc.name:'—','var(--tx-1)',15,650));
  if(orc&&orc.title)og.appendChild(stxt(ocx,ocy+25,orc.title.slice(0,38),'var(--tx-4)',9.5,400));
  if(orc)og.onclick=()=>armySessionDrawer(orc,byWorkerSession[orc.session_id]||[]);
  svg.appendChild(og);

  // off-box: where a pulse goes when its recipient cannot be resolved on this box
  // (a cloud/Remote Control session, or a name that doesn't match the roster) --
  // dropping it silently would misrepresent a send as never having happened.
  const offx=W-70, offy=H-34;
  centers.off={x:offx,y:offy};
  const offg=mk('g',{class:'army-node',id:'army-off'});
  offg.appendChild(mk('rect',{x:offx-64,y:offy-24,width:128,height:48,rx:10,fill:'var(--bg-inset)',stroke:'var(--bd)','stroke-width':1,'stroke-dasharray':'3 3'}));
  offg.appendChild(stxt(offx,offy-2,'OFF-BOX','var(--tx-4)',9.5,600));
  offg.appendChild(stxt(offx,offy+13,'cloud / unknown','var(--tx-4)',8.5,400));
  svg.appendChild(offg);

  sessions.forEach((s,i)=>{
    const sx=(W/N)*(i+.5), sy=sessY;
    centers['s:'+s.session_id]={x:sx,y:sy};
    const edge=mk('path',{d:`M ${ocx} ${ocy+32} C ${ocx} ${(ocy+sy)/2}, ${sx} ${(ocy+sy)/2}, ${sx} ${sy-38}`,
      fill:'none',stroke:'var(--bd-strong)','stroke-width':1.2,opacity:.12});
    edge.id='armyedge-'+s.session_id;
    svg.appendChild(edge);
    edges[s.session_id]=edge;

    const g=mk('g',{class:'army-node','data-sid':s.session_id});
    g.appendChild(mk('rect',{x:sx-84,y:sy-38,width:168,height:96,rx:12,fill:'var(--bg-1)',stroke:'var(--bd)','stroke-width':1}));
    const dot=mk('circle',{cx:sx-68,cy:sy-20,r:4,fill:armyDotColour(s,lastSeen)});
    dot.id='armydot-'+s.session_id;
    g.appendChild(dot);
    g.appendChild(stxt(sx+6,sy-16,s.name,'var(--tx-1)',13,650));
    if(s.title)g.appendChild(stxt(sx,sy,s.title.slice(0,40),'var(--tx-3)',9.5,500));
    const wc=(byWorkerSession[s.session_id]||[]).length;
    g.appendChild(stxt(sx,sy+16,(wc?wc+' worker'+(wc===1?'':'s'):'no workers')+(s.worker_overflow?' +'+s.worker_overflow:''),'var(--tx-4)',9,500));
    const actEl=stxt(sx,sy+32,'','var(--tx-4)',8.5,400); actEl.id='armyact-'+s.session_id; g.appendChild(actEl);
    g.appendChild(stxt(sx,sy+46,s.started_at?('since '+s.started_at.slice(11,16)):'','var(--tx-4)',8,400));
    g.onclick=()=>armySessionDrawer(s,byWorkerSession[s.session_id]||[]);
    svg.appendChild(g);

    (byWorkerSession[s.session_id]||[]).slice(0,6).forEach((w,j)=>{
      const wx=sx-60+j*24, wy=sy+64;
      centers['w:'+w.agent_id]={x:wx,y:wy};
      const wg=mk('g',{class:'army-node'});
      const wc2=mk('circle',{cx:wx,cy:wy,r:7,
        fill:w.active?'var(--acc-dim)':'var(--bg-3)',stroke:w.active?'var(--acc)':'var(--bd)','stroke-width':1.2});
      wc2.id='armyworker-'+w.agent_id;
      wg.appendChild(wc2);
      const tt=mk('title',{}); tt.textContent=w.task||w.agent_type||'worker'; wg.appendChild(tt);
      wg.onclick=()=>armyWorkerDrawer(w);
      svg.appendChild(wg);
    });
  });

  const wrap=el('div','org armywrap'); wrap.appendChild(svg);
  return {wrap,state:{centers,edges,nameToSid,lastSeen,queue:[],raf:null,cursor:''}};
}

function armyDotColour(s,lastSeen){
  if(!s.alive)return'var(--neg)';
  const seen=lastSeen[s.session_id];
  const age=seen?agoOf(seen):null;                 // hours
  if(age!=null&&age*3600<=300)return'var(--pos)';  // talked within 5 min
  return'var(--warn)';
}

function armyLedgerRow(row){
  const host=document.getElementById('armyledger'); if(!host)return;
  const d=el('div',null,
    `<span class="t">${esc(String(row.ts||'').slice(11,19))}</span>`+
    `<span>${esc(row.event||'')}</span>`+
    `<span class="dim">${esc((row.session_id||'').slice(0,8))}${row.to?' → '+esc(row.to):''}</span>`+
    `<span class="dim">${esc(row.detail||'')}</span>`);
  host.insertBefore(d,host.firstChild);
  while(host.children.length>200)host.removeChild(host.lastChild);
}

function armyGlow(row){
  const node=row.agent_id&&document.getElementById('armyworker-'+row.agent_id)
    ? document.getElementById('armyworker-'+row.agent_id)
    : document.querySelector(`g[data-sid="${row.session_id}"] rect`);
  if(!node||RM)return;
  node.classList.remove('army-glow'); void node.offsetWidth; node.classList.add('army-glow');
}

function armyDim(sid){
  const g=document.querySelector(`g[data-sid="${sid}"]`); if(!g)return;
  const n=Math.min(3,(parseInt(g.dataset.dim||'0',10))+1);
  g.dataset.dim=String(n); if(!RM)g.style.opacity=String(1-0.18*n);
}

function armyQueuePulse(fromKey,toKey,colour){
  const st=armyState; if(!st)return;
  const svg=document.getElementById('armysvg'); if(!svg)return;
  const from=st.centers[fromKey]||st.centers.orc, to=st.centers[toKey]||st.centers.off;
  if(!from||!to)return;
  let path=(fromKey==='orc'&&st.edges[toKey.slice(2)])?st.edges[toKey.slice(2)]
    :(toKey==='orc'&&st.edges[fromKey.slice(2)])?st.edges[fromKey.slice(2)]:null;
  let ephemeral=null;
  if(!path){
    ephemeral=document.createElementNS('http://www.w3.org/2000/svg','path');
    const mx=(from.x+to.x)/2, my=(from.y+to.y)/2-24;
    ephemeral.setAttribute('d',`M ${from.x} ${from.y} Q ${mx} ${my} ${to.x} ${to.y}`);
    ephemeral.setAttribute('fill','none'); ephemeral.setAttribute('opacity','0');
    svg.appendChild(ephemeral); path=ephemeral;
  }
  if(RM){
    // reduced motion: a single-frame edge highlight, no travelling dot -- the
    // ledger row (already written by armyApplyRow) is the record of the event.
    path.setAttribute('stroke',colour); path.setAttribute('opacity',ephemeral?'0':'.75');
    setTimeout(()=>{ if(ephemeral){try{svg.removeChild(ephemeral)}catch(e){}}
      else{path.setAttribute('stroke','var(--bd-strong)');path.setAttribute('opacity','.12')} },400);
    return;
  }
  const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');
  dot.setAttribute('r','4'); dot.setAttribute('fill',colour);
  svg.appendChild(dot);
  const entry={path,ephemeral,dot,len:path.getTotalLength(),start:performance.now(),dur:900};
  st.queue.push(entry);
  if(st.queue.length>40){                            // in-flight cap: drop oldest
    const old=st.queue.shift();
    try{svg.removeChild(old.dot)}catch(e){}
    if(old.ephemeral)try{svg.removeChild(old.ephemeral)}catch(e){}
  }
  if(!st.raf)st.raf=requestAnimationFrame(armyTick);
}

function armyTick(now){
  const st=armyState;
  if(!st||!document.getElementById('armysvg')){if(st)st.raf=null;return}
  const svg=document.getElementById('armysvg');
  const done=[];
  st.queue.forEach(en=>{
    const t=Math.min(1,(now-en.start)/en.dur), ease=1-Math.pow(1-t,3);
    const p=en.path.getPointAtLength(ease*en.len);
    en.dot.setAttribute('cx',p.x); en.dot.setAttribute('cy',p.y);
    en.dot.setAttribute('opacity',t<1?String(1-Math.abs(t-.5)*.3):'0');
    if(t>=1)done.push(en);
  });
  if(done.length){
    st.queue=st.queue.filter(e=>done.indexOf(e)===-1);
    done.forEach(en=>{try{svg.removeChild(en.dot)}catch(e){} if(en.ephemeral)try{svg.removeChild(en.ephemeral)}catch(e){}});
  }
  st.raf=st.queue.length?requestAnimationFrame(armyTick):null;
}

/* one row, always: updates the box's dot/last-action/ledger. animate=false is
   the initial-snapshot seed (baked D.army.pulses) -- deliberately silent, or
   loading the page would replay up to 60 old pulses as if they just happened. */
function armyApplyRow(row,animate){
  const st=armyState; if(!st)return;
  if(row.ts)st.lastSeen[row.session_id]=row.ts;
  const s=(D.army&&D.army.sessions||[]).find(x=>x.session_id===row.session_id);
  const dot=document.getElementById('armydot-'+row.session_id);
  if(dot&&s)dot.setAttribute('fill',armyDotColour(s,st.lastSeen));
  const actEl=document.getElementById('armyact-'+row.session_id);
  if(actEl&&row.detail)actEl.textContent=row.detail.slice(0,34);
  armyLedgerRow(row);
  if(!animate)return;
  if(row.event==='act'){armyGlow(row);return}
  if(row.event==='idle'){armyDim(row.session_id);return}
  const fromKey=st.centers['s:'+row.session_id]?'s:'+row.session_id:'orc';
  let toKey='off', colour='var(--acc)';
  if(row.event==='message'){
    const tsid=st.nameToSid[row.to];
    toKey=(tsid&&st.centers['s:'+tsid])?'s:'+tsid:'off';
  }else if(row.event==='spawn'){
    toKey=st.centers['w:'+row.agent_id]?'w:'+row.agent_id:'off'; colour='#b389f9';
  }else if(row.event==='fail'){
    toKey='orc'; colour='var(--warn)';
  }else{
    return;  // unrecognised event kind: ledger row already written, nothing to animate
  }
  armyQueuePulse(fromKey,toKey,colour);
}

function armyPoll(){
  if(!document.getElementById('armysvg'))return;  // view navigated away -- stop the chain
  const meta=document.querySelector('meta[name="gamma-token"]');
  const tok=meta?meta.content:'';
  fetch('/api/army?since='+encodeURIComponent(armyState?armyState.cursor||'':''),{headers:{'x-gamma-token':tok}})
    .then(r=>r.json())
    .then(j=>{
      if(j&&j.ok&&armyState){
        (j.rows||[]).forEach(row=>armyApplyRow(row,true));
        if(j.cursor)armyState.cursor=j.cursor;
      }
    })
    .catch(()=>{})
    .finally(()=>{setTimeout(armyPoll,1000)});
}

function vArmy(h){
  const a=D.army||{sessions:[],workers:[],pulses:[],orchestrator:null,source:{}};
  const live=location.protocol!=='file:';
  h.appendChild(el('div','shead',
    `<h2>Army</h2><span class="dim">${live?'LIVE':'SNAPSHOT'} · ${esc(a.scope_note||'')}</span>`));
  const card=el('div','card');
  const built=armySvg(a);
  card.appendChild(built.wrap);
  if(a.session_overflow)card.appendChild(el('div','micro',`+${a.session_overflow} more session(s) not shown`));
  const legend=el('div','micro',esc(a.legend||'')); legend.style.marginTop='var(--s5)'; card.appendChild(legend);
  const ledger=el('div','armyledger'); ledger.id='armyledger'; card.appendChild(ledger);
  card.appendChild(srcRow([a.source&&a.source.pulse,a.source&&a.source.sessions].filter(Boolean)));
  if(a.error)card.appendChild(el('div','micro warnc','army payload error: '+esc(a.error)));
  h.appendChild(card);   // attached to the document NOW -- ids below become queryable

  armyState=built.state;
  (a.pulses||[]).forEach(r=>armyApplyRow(r,false));
  armyState.cursor=(a.pulses&&a.pulses.length)?a.pulses[a.pulses.length-1].ts:'';
  if(live)armyPoll();
}
function armySessionDrawer(s,workers){
  openDrawer(s.name,b=>{
    b.appendChild(el('div','row',
      `<span class="chip ${s.alive?'ok':'bad'}"><i class="dot"></i>${s.alive?'ALIVE':'NOT RUNNING'}</span>`+
      (s.is_orchestrator?'<span class="chip">ORCHESTRATOR</span>':'')));
    const k=el('div'); k.style.marginTop='var(--s5)';
    [['Title',s.title||'—'],['Kind',s.kind||'—'],['Entrypoint',s.entrypoint||'—'],
     ['Version',s.version||'—'],['PID',s.pid||'—'],['Session id',s.session_id],
     ['CWD',s.cwd||'—']].forEach(([kk,v])=>k.appendChild(el('div','kv',
      `<span class="k">${esc(kk)}</span><span class="v mono">${esc(v)}</span>`)));
    b.appendChild(k);
    if(workers.length){
      const h3=el('h3',null,'Workers');
      h3.style.cssText='margin:var(--s6) 0 var(--s3);font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--tx-3)';
      b.appendChild(h3);
      workers.forEach(w=>{
        const row=el('div'); row.style.cssText='padding:var(--s3) 0;border-bottom:1px solid var(--bd-subtle)';
        row.appendChild(el('div','row',
          `<span class="chip ${w.active?'ok':''}">${w.active?'ACTIVE':'IDLE'}</span>`+
          `<span class="dim mono">${esc(w.agent_id.slice(0,10))}</span>`));
        row.appendChild(el('div','mut',esc(w.task||w.agent_type||'—')));
        b.appendChild(row);
      });
    }
  });
}
function armyWorkerDrawer(w){
  openDrawer('Worker '+w.agent_id.slice(0,10),b=>{
    b.appendChild(el('div','row',`<span class="chip ${w.active?'ok':''}">${w.active?'ACTIVE':'IDLE'}</span>`));
    const k=el('div'); k.style.marginTop='var(--s5)';
    [['Session',w.session_id],['Agent type',w.agent_type||'—'],['Model',w.model||'—'],
     ['Workflow',w.workflow_id||'—']].forEach(([kk,v])=>k.appendChild(el('div','kv',
      `<span class="k">${esc(kk)}</span><span class="v mono">${esc(v)}</span>`)));
    b.appendChild(k);
    b.appendChild(el('div','mut',esc(w.task||'—')));
  });
}
"""

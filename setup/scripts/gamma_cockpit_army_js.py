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
  const stxt=(x,y,str,c,sz,w,anchor)=>{const e=mk('text',{x,y,fill:c||'var(--tx-2)','font-size':sz||11,
    'font-family':'var(--font)','font-weight':w||500,'text-anchor':anchor||'middle'});e.textContent=str;return e};
  /* Left-aligned label -- reading a box is scanning a short list, not centring a poster. */
  const ltxt=(x,y,str,c,sz,w)=>stxt(x,y,str,c,sz,w,'start');

  const sessions=(a.sessions||[]).slice(0,12), workers=a.workers||[];
  const byWorkerSession={};
  workers.forEach(w=>(byWorkerSession[w.session_id]=byWorkerSession[w.session_id]||[]).push(w));
  const nameToSid={}; sessions.forEach(s=>nameToSid[s.name]=s.session_id);
  // "recently talked" beats plain aliveness for the dot colour -- see build_army()'s
  // last_seen computation; recomputed as pulses arrive via armyDotColour() below.
  const lastSeen={}; (a.pulses||[]).forEach(r=>{if(r.session_id&&r.ts)lastSeen[r.session_id]=r.ts});

  /* LAYOUT -- fixed box size in a GRID, never one scaled row.
     The first version laid every session out in a single row and sized the viewBox to
     fit: W = N*200+140. With 10 sessions that is a 2140-wide viewBox rendered into a
     ~1250px column, so the browser scaled everything to ~58% and 13px labels became
     7.6px. More sessions made the text SMALLER -- exactly backwards. J, seeing it:
     "look how tiny it is... i have no idea what im even looking at."
     Now the viewBox width is FIXED near the real column width and rows wrap, so box
     size and type size never depend on how many sessions are alive. */
  /* COLUMN COUNT IS MEASURED, NOT FIXED. Adding the 340px cards rail cut the canvas to
     ~622px in a narrow window, and a fixed 3-column (1110px) graph squeezed into that
     scales to 0.56 -- which is the exact tininess this layout was rewritten to kill. So
     pick the widest column count that still FITS, and let the graph get taller instead of
     smaller. Falls back to 3 when the width cannot be read (file:// pre-layout). */
  const BW=330, BH=164, GAPX=26, GAPY=26, PAD=34;
  const fitCols=(avail)=>{
    for(let c=3;c>1;c--){ if(PAD*2+c*BW+(c-1)*GAPX<=avail) return c; }
    return 1;
  };
  let availW=0;
  try{
    const host=document.getElementById('view')||document.body;
    availW=host.clientWidth-380;               // rail (340) + grid gap + card padding
  }catch(_){}
  const COLS=availW>200?fitCols(availW):3;
  const MAX_BOXES=9;
  /* The orchestrator was ALSO drawn in the grid below itself, so 42-dd appeared twice and
     the page silently implied there was one more window than exists. J: "wtf is 42-dd?
     does that mean i have 9 subagnts open right now??" -- no, and the duplicate was a big
     part of why that was unanswerable. */
  const orcSid=(a.orchestrator||{}).session_id;
  /* STALE CHATS ARE HIDDEN BY DEFAULT. J: "i dont have any claude windows open besides this
     one they are just old chats... maybe they shouldnt be pulled in if they are not active."
     Every registry PID is a live `claude` process because Desktop leaves one running per
     closed chat, so aliveness proved nothing; transcript recency does. Stale is >2h since
     the last write -- four of his were between 22 and 50 HOURS old. */
  const allPeers=sessions.filter(s=>s.session_id!==orcSid);
  const staleCount=allPeers.filter(s=>s.activity==='stale').length;
  const peers=armyShowStale?allPeers:allPeers.filter(s=>s.activity!=='stale');
  const shown=peers.slice(0,MAX_BOXES);
  const hiddenCount=Math.max(0,peers.length-shown.length);
  const rows=Math.max(1,Math.ceil(shown.length/COLS));
  const W=PAD*2+COLS*BW+(COLS-1)*GAPX;
  const ocy=62, SESS_TOP=196;
  const H=SESS_TOP+rows*(BH+GAPY)+56;
  /* Bleed the viewBox by 8px on every side. Measured after the grid rewrite: the content
     bbox started at (-6,-6) because strokes and text ascenders sit outside their nominal
     box, so a 0-origin viewBox shaved the top-left edge of the orchestrator. */
  const BLEED=8;
  const svg=mk('svg',{viewBox:`${-BLEED} ${-BLEED} ${W+BLEED*2} ${H+BLEED*2}`,id:'armysvg'});
  // height is a CSS concern, not an SVG attribute: setAttribute('height','auto') is
  // invalid per spec and threw "Expected length" in the console. The viewBox plus
  // width:100% already gives proportional scaling; CSS height:auto completes it.
  svg.setAttribute('width','100%');
  svg.style.cssText='display:block;margin:0 auto;height:auto;max-width:'+W+'px';

  const centers={}, edges={};
  const ocx=W/2;
  centers.orc={x:ocx,y:ocy};
  const orc=a.orchestrator;
  const og=mk('g',{class:'army-node',id:'army-orc'});
  og.appendChild(mk('rect',{x:ocx-190,y:ocy-44,width:380,height:88,rx:16,fill:'var(--bg-2)',stroke:'var(--acc)','stroke-width':2}));
  og.appendChild(mk('circle',{cx:ocx-166,cy:ocy-14,r:6,fill:'var(--acc)',class:'army-ring'}));
  og.appendChild(ltxt(ocx-150,ocy-8,orc?orc.name:'—','var(--tx-1)',21,700));
  og.appendChild(ltxt(ocx-166,ocy+16,'ORCHESTRATOR — this page. The session you are talking to.','var(--acc)',11.5,600));
  if(orc&&orc.title)og.appendChild(ltxt(ocx-166,ocy+34,orc.title.slice(0,52),'var(--tx-4)',11,400));
  if(orc){og.style.cursor='pointer';og.onclick=()=>armySessionDrawer(orc,byWorkerSession[orc.session_id]||[]);}
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

  shown.forEach((s,i)=>{
    const col=i%COLS, row=Math.floor(i/COLS);
    const sx=PAD+col*(BW+GAPX)+BW/2;
    const sy=SESS_TOP+row*(BH+GAPY)+BH/2;
    const L=sx-BW/2, T=sy-BH/2;                    // box left / top, for readable labels
    centers['s:'+s.session_id]={x:sx,y:sy};
    const edge=mk('path',{d:`M ${ocx} ${ocy+44} C ${ocx} ${(ocy+T)/2}, ${sx} ${(ocy+T)/2}, ${sx} ${T}`,
      fill:'none',stroke:'var(--bd-strong)','stroke-width':1.4,opacity:.16});
    edge.id='armyedge-'+s.session_id;
    svg.appendChild(edge);
    edges[s.session_id]=edge;

    const g=mk('g',{class:'army-node','data-sid':s.session_id});
    g.style.cursor='pointer';
    g.appendChild(mk('rect',{x:L,y:T,width:BW,height:BH,rx:14,fill:'var(--bg-1)',stroke:'var(--bd)','stroke-width':1.4}));
    const dot=mk('circle',{cx:L+22,cy:T+27,r:6,fill:armyDotColour(s,lastSeen)});
    dot.id='armydot-'+s.session_id;
    g.appendChild(dot);
    /* TITLE FIRST, handle second. `42-dd` is auto-derived from the project folder plus a
       hash -- it identifies a session to the machine and to nobody else. What J recognises
       is what the window is ABOUT. So the big line is the title and the handle drops to a
       small monospace tag. */
    const bigLabel=(s.title||s.name||'untitled').slice(0,34);
    g.appendChild(ltxt(L+38,T+33,bigLabel,'var(--tx-1)',17,700));
    const tag=ltxt(L+18,T+56,s.name,'var(--tx-4)',11,600);
    tag.setAttribute('font-family','var(--mono, ui-monospace, monospace)');
    g.appendChild(tag);
    /* Say WHEN, not just what. "a Claude window YOU have open" was flatly untrue for a
       chat closed two days ago whose process merely lingered. */
    const lw=s.last_write_min;
    const ago=(lw==null)?'':(lw<1?'just now':(lw<60?Math.round(lw)+'m ago':
      (lw<1440?Math.round(lw/60)+'h ago':Math.round(lw/1440)+'d ago')));
    const act=s.activity||'unknown';
    const actWord=act==='active'?'ACTIVE NOW':(act==='idle'?'idle':(act==='stale'?'old chat':'unknown'));
    const actCol=act==='active'?'var(--pos)':(act==='idle'?'var(--tx-3)':'var(--tx-4)');
    g.appendChild(ltxt(L+18,T+76,actWord+(ago?' · '+ago:''),actCol,12,act==='active'?700:500));
    const wc=(byWorkerSession[s.session_id]||[]).length;
    g.appendChild(ltxt(L+18,T+100,(wc?wc+' worker'+(wc===1?'':'s'):'no workers')+
      (s.worker_overflow?' +'+s.worker_overflow:''),'var(--tx-4)',11,500));
    const actEl=ltxt(L+18,T+120,'','var(--tx-4)',11,400); actEl.id='armyact-'+s.session_id; g.appendChild(actEl);
    /* CONTEXT GAUGE along the base of the card. J asked for "a context bar that changes in
       real time for every card that is a session".

       Drawn only when gamma_cockpit_army.py could actually compute it: context_source is the
       literal string "unknown" when either the token count or the limit was unresolvable, and
       a fabricated percentage on a progress bar is worse than an absent bar -- the bar is the
       one element here a person reads without reading any words.

       The denominator is autoCompactWindow, not the raw model window, because compaction is
       the event that actually costs the user something. */
    const cpct=(typeof s.context_pct==='number')?s.context_pct:null;
    const cknown=cpct!==null&&s.context_source&&s.context_source!=='unknown';
    if(cknown){
      const frac=Math.max(0,Math.min(100,cpct))/100;
      const cy=T+BH-6;
      g.appendChild(mk('rect',{x:L+1,y:cy,width:BW-2,height:4,rx:2,
        fill:'color-mix(in oklch,white 8%,transparent)'}));
      // warn/neg rather than the accent: nearing a compact is a STATE, and severity is not
      // what the purple means anywhere else on this page.
      const col=cpct>=90?'var(--neg)':(cpct>=75?'var(--warn)':'var(--acc)');
      const fill=mk('rect',{x:L+1,y:cy,width:Math.max(2,(BW-2)*frac),height:4,rx:2,fill:col});
      fill.id='armyctx-'+s.session_id;
      g.appendChild(fill);
      const lab=stxt(L+BW-16,T+56,Math.round(cpct)+'% ctx',col,10.5,600,'end');
      lab.id='armyctxlab-'+s.session_id;
      g.appendChild(lab);
    }

    // Explicit affordance: the whole box was already clickable but nothing said so.
    // Bottom-right, not beside the title: at 17px a 34-char title runs to ~L+320 and
    // collided with an affordance sitting at the same baseline (seen in a headless shot).
    g.appendChild(stxt(L+BW-16,T+BH-12,'open ▸','var(--acc)',11,600,'end'));
    g.onclick=()=>armySessionDrawer(s,byWorkerSession[s.session_id]||[]);
    svg.appendChild(g);

    /* Worker chips INSIDE the card. They used to sit at T+BH+17 -- in the GAP between
       grid rows -- so they read as loose confetti belonging to nothing, which a headless
       screenshot made obvious immediately. */
    (byWorkerSession[s.session_id]||[]).slice(0,5).forEach((w,j)=>{
      const wx=L+26+j*24, wy=T+BH-30;
      centers['w:'+w.agent_id]={x:wx,y:wy};
      const wg=mk('g',{class:'army-node'});
      wg.style.cursor='pointer';
      const wc2=mk('circle',{cx:wx,cy:wy,r:9,
        fill:w.active?'var(--acc-dim)':'var(--bg-3)',stroke:w.active?'var(--acc)':'var(--bd)','stroke-width':1.4});
      wc2.id='armyworker-'+w.agent_id;
      wg.appendChild(wc2);
      const tt=mk('title',{}); tt.textContent=w.task||w.agent_type||'worker'; wg.appendChild(tt);
      wg.onclick=()=>armyWorkerDrawer(w);
      g.appendChild(wg);
    });
    if(wc)g.appendChild(ltxt(L+26+Math.min(wc,5)*24,T+BH-26,'workers','var(--tx-4)',10,500));
  });

  if(hiddenCount){
    svg.appendChild(stxt(W/2,H-18,'+'+hiddenCount+' more session'+(hiddenCount===1?'':'s')+
      ' not shown — the roster is capped so the boxes stay readable','var(--tx-4)',11,500));
  }

  /* TOOLBAR -- J on the first screenshot: "there is no butotns or anything". The graph
     was fully interactive (every box opened a drawer) but advertised none of it, and the
     only place with real actions -- the Cards view -- was reachable only from the nav. */
  const wrap=el('div','org armywrap');
  const bar=el('div','armybar');
  bar.style.cssText='display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 14px';
  const mkbtn=(label,title,fn,primary)=>{
    const b=document.createElement('button');
    b.type='button'; b.textContent=label; b.title=title;
    b.style.cssText='font:600 12px/1 var(--font);padding:9px 14px;border-radius:8px;cursor:pointer;'+
      'border:1px solid '+(primary?'var(--acc)':'var(--bd)')+';'+
      'background:'+(primary?'var(--acc-dim)':'var(--bg-2)')+';color:'+(primary?'var(--acc)':'var(--tx-2)')+';';
    b.onclick=fn;
    return b;
  };
  bar.appendChild(mkbtn('Refresh now','Re-read the session roster and pulse log immediately',
    ()=>{try{route('army')}catch(_){}} ,true));
  bar.appendChild(mkbtn('Action cards ▸','Go to the Cards view -- that is where the fire buttons live',
    ()=>{try{route('cards');history.replaceState(null,'','#cards')}catch(_){}}));
  const staleN=((a.sessions||[]).filter(x=>x.activity==='stale'&&x.session_id!==(a.orchestrator||{}).session_id)).length;
  if(staleN){
    const t=mkbtn(armyShowStale?('Hide '+staleN+' old chat'+(staleN===1?'':'s')):('Show '+staleN+' old chat'+(staleN===1?'':'s')),
      'Sessions with no transcript write for over 2 hours. Their process is still running because Claude Desktop keeps one per closed chat.',
      ()=>{ armyShowStale=!armyShowStale; try{route('army')}catch(_){} });
    bar.appendChild(t);
  }
  const pauseBtn=mkbtn('Pause pulses','Stop the travelling dots without stopping the data',()=>{
    if(!armyState)return;
    armyState.paused=!armyState.paused;
    pauseBtn.textContent=armyState.paused?'Resume pulses':'Pause pulses';
  });
  bar.appendChild(pauseBtn);
  wrap.appendChild(bar);

  /* LEGEND -- the page has to answer "how do I read this" without J asking a human.
     Counts are computed, never hard-coded, so the sentence cannot drift from the graph. */
  const wct=(a.workers||[]).length;
  const legend=el('div','armylegend');
  legend.style.cssText='display:flex;flex-wrap:wrap;gap:18px;align-items:baseline;margin:0 0 16px;'+
    'padding:12px 16px;border:1px solid var(--bd);border-radius:10px;background:var(--bg-inset);'+
    'font:500 12.5px/1.6 var(--font);color:var(--tx-3)';
  const li=(strong,rest)=>{
    const d=document.createElement('div');
    d.innerHTML='<b style="color:var(--tx-1);font-weight:700">'+strong+'</b> '+rest;
    return d;
  };
  legend.appendChild(li('Top box = this page.',
    'The Claude session you are talking to right now.'));
  legend.appendChild(li(shown.length+' box'+(shown.length===1?'':'es')+' below =',
    'other Claude sessions on this machine. Not subagents.'+
    (staleCount&&!armyShowStale?' <em>'+staleCount+' old chat'+(staleCount===1?'':'s')+' hidden.</em>':'')));
  legend.appendChild(li(wct+' worker'+(wct===1?'':'s')+' =',
    'the small circles. <em>Those</em> are the subagents.'));
  legend.appendChild(li('Click any box',
    'to see what it is doing.'));
  wrap.appendChild(legend);
  wrap.appendChild(svg);
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
  // Paused means "stop the motion", never "stop the data": the ledger and the state dots
  // keep updating underneath, so pausing to read the graph cannot hide a live event.
  if(st.paused)return;
  const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');
  dot.setAttribute('r','6'); dot.setAttribute('fill',colour); dot.setAttribute('class','army-pulse');
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

/* ---------- cards rail: list on the right, promote into the canvas ----------
   J: "put the Cards in a vertical column on the right side of the army page, then when I
   click a card, we see the card go from the column on to the actual page itself."

   The card is NOT moved through the DOM. The rail and the canvas are two independent
   render targets reading one selected-id, and the visual morph is the View Transitions
   API: the same `view-transition-name` is on the rail item while collapsed and on the
   promoted panel while open -- never both at once -- so the browser interpolates position
   and size between them by itself. Chromium 111+, which is the only target this page has,
   so there is no FLIP math and no fallback branch beyond reduced-motion. */
let armyCardSel=null;
let armyShowStale=false;

function armyCardVtName(id){ return 'acard-'+String(id||'').replace(/[^A-Za-z0-9_-]/g,''); }

function armyPaintCards(){
  const rail=document.getElementById('armyrail');
  const stage=document.getElementById('armystage');
  if(!rail||!stage)return;
  const cards=((D.cards&&D.cards.cards)||D.action_cards||[]);
  rail.innerHTML='';
  stage.innerHTML='';

  const sel=cards.find(c=>c.id===armyCardSel)||null;
  if(sel){
    const p=el('div','card acard-open');
    p.style.viewTransitionName=armyCardVtName(sel.id);
    p.style.cssText+=';border-color:var(--acc);margin:0 0 16px';
    const head=el('div','row');
    head.innerHTML='<span class="chip">RANK '+esc(String(sel.rank))+'</span>'+
      (sel.gated?'<span class="chip warn">GATED</span>':'')+
      '<span class="chip">'+esc(sel.model||'sonnet')+'</span>';
    const close=document.createElement('button');
    close.type='button'; close.textContent='Close ✕';
    close.style.cssText='margin-left:auto;font:600 12px/1 var(--font);padding:7px 12px;border-radius:6px;'+
      'border:1px solid var(--bd);background:var(--bg-2);color:var(--tx-2);cursor:pointer';
    close.onclick=()=>armySelectCard(sel.id);
    head.appendChild(close);
    p.appendChild(head);
    const t=el('h3'); t.textContent=sel.title; t.style.cssText='margin:12px 0 8px;font-size:20px;line-height:1.2';
    p.appendChild(t);
    (sel.why||[]).slice(0,4).forEach(w=>p.appendChild(el('div','micro','• '+esc(String(w).slice(0,220)))));
    p.appendChild(srcRow([sel.source_path].filter(Boolean)));
    const act=el('div','row'); act.style.marginTop='12px';
    const btn=document.createElement('button');
    btn.type='button'; btn.className='btn'; btn.dataset.state='idle';
    btn.textContent=cardFireLabel(rthNowClient()); btn.disabled=rthNowClient();
    btn.style.cssText='font:700 13px/1 var(--font);padding:11px 18px;border-radius:8px;cursor:pointer;'+
      'border:1px solid var(--acc);background:var(--acc-dim);color:var(--acc)';
    const msg=el('div','micro');
    btn.onclick=()=>fireCard(sel,btn,msg);
    act.appendChild(btn); p.appendChild(act); p.appendChild(msg);
    stage.appendChild(p);
  }

  const head=el('div','micro'); head.textContent='ACTION CARDS · '+cards.length+' ranked, worst first';
  head.style.cssText='letter-spacing:.1em;margin:0 0 10px;color:var(--tx-4)';
  rail.appendChild(head);

  cards.forEach(c=>{
    const open=(c.id===armyCardSel);
    const it=el('div','card acard-item');
    // Radius/padding from the two independently-sourced token scales the research found
    // agreeing (Linear + Geist): 12px container radius, 4px-base spacing, hairline border
    // for elevation rather than a shadow.
    it.style.cssText='padding:12px 14px 12px 18px;margin:0 0 8px;cursor:pointer;border-radius:12px;'+
      'border:1px solid '+(open?'var(--acc)':'var(--bd)')+';background:var(--bg-1);'+
      (open?'opacity:.45;':'');
    if(!open)it.style.viewTransitionName=armyCardVtName(c.id);
    it.onclick=()=>armySelectCard(c.id);
    /* Severity is encoded in the leading edge, not just the number. Cards sourced from
       STATUS.md are things that are BROKEN; queue items are things that are QUEUED. A rail
       where every row looks identical makes "ranked, worst first" a claim the eye cannot
       verify. Semantic colour only -- the purple accent is never used to mean severity. */
    const src=(c.source_path||'').split('/').pop();
    const sev=/STATUS/i.test(src)?'var(--neg)':(/unattended/i.test(src)?'var(--warn)':'var(--acc)');
    const edge=document.createElement('i');
    edge.style.cssText='position:absolute;left:0;top:0;bottom:0;width:3px;background:'+sev+';opacity:.85';
    it.appendChild(edge);
    const r=el('div','micro'); r.textContent='#'+c.rank+' · '+src;
    r.style.color='var(--tx-4)';
    const t=el('div'); t.textContent=String(c.title||'').slice(0,84);
    t.style.cssText='font:600 13.5px/1.35 var(--font);color:var(--tx-1);margin-top:4px';
    it.appendChild(r); it.appendChild(t);
    rail.appendChild(it);
  });

  if(!cards.length)rail.appendChild(el('div','micro','No cards right now — nothing is flagged.'));
}

function armySelectCard(id){
  const go=()=>{ armyCardSel=(armyCardSel===id?null:id); armyPaintCards(); };
  if(document.startViewTransition && !RM){ document.startViewTransition(go); } else { go(); }
}

function vArmy(h){
  const a=D.army||{sessions:[],workers:[],pulses:[],orchestrator:null,source:{}};
  const live=location.protocol!=='file:';
  h.appendChild(el('div','shead',
    `<h2>Army</h2><span class="dim">${live?'LIVE':'SNAPSHOT'} · ${esc(a.scope_note||'')}</span>`));

  /* Two-column shell. align-self:start is load-bearing, not cosmetic: grid's default
     `stretch` makes the short rail column match its taller sibling's height, which
     silently defeats position:sticky. */
  const shell=el('div','armyshell');
  shell.style.cssText='display:grid;grid-template-columns:1fr minmax(300px,340px);'+
    'gap:20px;align-items:start';

  const main=el('div');
  const stage=el('div'); stage.id='armystage'; main.appendChild(stage);

  const card=el('div','card');
  const built=armySvg(a);
  card.appendChild(built.wrap);
  const ledger=el('div','armyledger'); ledger.id='armyledger'; card.appendChild(ledger);
  card.appendChild(srcRow([a.source&&a.source.pulse,a.source&&a.source.sessions].filter(Boolean)));
  if(a.error)card.appendChild(el('div','micro warnc','army payload error: '+esc(a.error)));
  main.appendChild(card);
  shell.appendChild(main);

  const rail=el('div'); rail.id='armyrail';
  rail.style.cssText='position:sticky;top:16px;align-self:start;max-height:calc(100vh - 32px);overflow:auto';
  shell.appendChild(rail);

  h.appendChild(shell);   // attached to the document NOW -- ids below become queryable

  armyPaintCards();
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

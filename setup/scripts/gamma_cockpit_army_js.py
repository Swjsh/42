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
let armyState_offboxSpec=null;
function armyEnsureOffbox(){
  if(document.getElementById('army-off'))return;
  const sp=armyState_offboxSpec; if(!sp)return;
  const {svg,mk,stxt,offx,offy}=sp;
  const offg=mk('g',{class:'army-node army-enter',id:'army-off'});
  offg.appendChild(mk('rect',{x:offx-64,y:offy-24,width:128,height:48,rx:10,fill:'var(--bg-inset)',stroke:'var(--bd)','stroke-width':1,'stroke-dasharray':'3 3'}));
  offg.appendChild(stxt(offx,offy-2,'OFF-BOX','var(--tx-4)',9.5,600));
  offg.appendChild(stxt(offx,offy+13,'cloud / unknown','var(--tx-4)',8.5,400));
  svg.appendChild(offg);
}

function armyHumanAct(detail){
  /* A raw "Ran: cd C:/Users/jackw/Desktop/42 && backtest/.venv/..." is developer noise on
     a glance-surface. Reduce it to what a person reads: the verb + the object. */
  const d=String(detail||'').trim();
  if(/^Editing /.test(d))return d;                      // already clean
  const m=d.match(/^Ran:\s*(.+)/);
  if(!m)return d;
  let cmd=m[1].replace(/^cd\s+\S+\s*(?:&&|;)\s*/,'');  // drop a leading cd
  const tool=cmd.split(/\s+/)[0].split(/[\/]/).pop();  // basename of the exe
  if(/python|pythonw/.test(tool)){
    const script=(cmd.match(/([\w./\-]+\.py)/)||[])[1];
    return script?('Running '+script.split(/[\/]/).pop()):'Running python';
  }
  if(/pytest/.test(cmd))return 'Running tests';
  if(/^git/.test(cmd))return 'git '+(cmd.split(/\s+/)[1]||'');
  return tool ? ('Running '+tool) : d;
}

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
  // preserveAspectRatio defaults to xMidYMid meet, so height:100% + width:100% makes the
  // graph shrink to fit its row rather than pushing the page taller.
  /* Scale to fit, but never below legible. Shooting at 900px tall showed the honest cost of
     "one page": the graph shrank until the labels were unreadable again -- trading the
     original complaint for itself. A min-height floor means the graph stays readable and the
     CARD scrolls internally on a short screen, instead of the whole page scrolling on a tall
     one. One page where it fits; legible everywhere. */
  const MIN_GRAPH_H=Math.min(H, 300);
  svg.style.cssText='display:block;margin:0 auto;width:100%;height:100%;'+
    'min-height:'+MIN_GRAPH_H+'px;max-width:'+W+'px';

  /* Paint defs, once per render. cardGrad is Linear's measured top-light (a 2-4% white
     wash fading by mid-card) as an SVG gradient; orcGrad is the same idea with the deep
     accent bleeding in from the top so the hero box reads as LIT, not outlined. */
  const defs=mk('defs',{});
  const g1=mk('linearGradient',{id:'cardGrad',x1:'0',y1:'0',x2:'0',y2:'1'});
  g1.appendChild(mk('stop',{offset:'0%','stop-color':'rgba(255,255,255,.035)'}));
  g1.appendChild(mk('stop',{offset:'45%','stop-color':'rgba(255,255,255,0)'}));
  defs.appendChild(g1);
  const g2=mk('linearGradient',{id:'orcGrad',x1:'0',y1:'0',x2:'0',y2:'1'});
  g2.appendChild(mk('stop',{offset:'0%','stop-color':'color-mix(in oklch,var(--acc-deep) 55%,transparent)'}));
  g2.appendChild(mk('stop',{offset:'70%','stop-color':'rgba(255,255,255,0)'}));
  defs.appendChild(g2);
  svg.appendChild(defs);

  const centers={}, edges={};
  const ocx=W/2;
  centers.orc={x:ocx,y:ocy};
  /* Meridian rings: two faint circles centred on the hero give the stage a command-map
     structure the eye reads instantly; the aura beneath the hero breathes on the ambient
     clock -- the rig's heartbeat, literally. */
  const aura=mk('ellipse',{cx:ocx,cy:ocy,rx:260,ry:96,fill:'url(#orcAura)',class:'army-aura'});
  svg.appendChild(aura);
  [150,260].forEach(r=>svg.appendChild(mk('circle',{cx:ocx,cy:ocy,r,fill:'none',
    stroke:'var(--tx-1)','stroke-width':1,opacity:.04})));
  const ag=mk('radialGradient',{id:'orcAura'});
  ag.appendChild(mk('stop',{offset:'0%','stop-color':'#6344F5','stop-opacity':'.16'}));
  ag.appendChild(mk('stop',{offset:'100%','stop-color':'#6344F5','stop-opacity':'0'}));
  defs.appendChild(ag);
  const orc=a.orchestrator;
  const og=mk('g',{class:'army-node army-enter',id:'army-orc'});
  og.appendChild(mk('rect',{x:ocx-190,y:ocy-44,width:380,height:88,rx:16,fill:'var(--bg-2)',stroke:'var(--bd-strong)','stroke-width':1}));
  og.appendChild(mk('rect',{x:ocx-190,y:ocy-44,width:380,height:88,rx:16,fill:'url(#orcGrad)',stroke:'var(--bd-strong)','stroke-width':1,opacity:.9}));
  /* Tracing border: an ~80px accent comet orbits the hero's ~895px perimeter -- lit and
     alive without a static heavy stroke shouting. */
  og.appendChild(mk('rect',{x:ocx-190,y:ocy-44,width:380,height:88,rx:16,fill:'none',
    stroke:'var(--acc)','stroke-width':1.6,class:'army-trace','stroke-linecap':'round'}));
  og.appendChild(mk('circle',{cx:ocx-166,cy:ocy-14,r:6,fill:'var(--st-live)',class:'army-ring'}));
  og.appendChild(ltxt(ocx-150,ocy-8,orc?orc.name:'—','var(--tx-1)',21,700));
  og.appendChild(ltxt(ocx-166,ocy+16,'ORCHESTRATOR — this page. The session you are talking to.','var(--acc)',11.5,600));
  if(orc&&orc.title)og.appendChild(ltxt(ocx-166,ocy+34,orc.title.slice(0,52),'var(--tx-4)',11,400));
  if(orc){og.style.cursor='pointer';og.onclick=()=>armySessionDrawer(orc,byWorkerSession[orc.session_id]||[]);}
  svg.appendChild(og);

  // off-box: where a pulse goes when its recipient cannot be resolved on this box
  // (a cloud/Remote Control session, or a name that doesn't match the roster) --
  // dropping it silently would misrepresent a send as never having happened.
  /* OFF-BOX is born LAZILY: permanent furniture for an occasional event is clutter
     (J: "too busy"). armyEnsureOffbox() creates it on the first pulse that actually
     needs an unresolvable destination; until then the corner stays empty sky. */
  const offx=W-70, offy=H-34;
  centers.off={x:offx,y:offy};
  armyState_offboxSpec={svg,mk,stxt,offx,offy};

  shown.forEach((s,i)=>{
    const col=i%COLS, row=Math.floor(i/COLS);
    const sx=PAD+col*(BW+GAPX)+BW/2;
    const sy=SESS_TOP+row*(BH+GAPY)+BH/2;
    const L=sx-BW/2, T=sy-BH/2;                    // box left / top, for readable labels
    centers['s:'+s.session_id]={x:sx,y:sy};
    const dPath=`M ${ocx} ${ocy+44} C ${ocx} ${(ocy+T)/2}, ${sx} ${(ocy+T)/2}, ${sx} ${T}`;
    /* Ghost rail: Aceternity's measured base -- ~.5px stroke at 5% -- wiring that is
       present but silent until something moves along it. */
    const edge=mk('path',{d:dPath,fill:'none',stroke:'var(--tx-1)','stroke-width':.6,opacity:.055});
    edge.id='armyedge-'+s.session_id;
    svg.appendChild(edge);
    edges[s.session_id]=edge;
    /* Beam comet: per-edge userSpaceOnUse gradient with their exact stops (cyan head,
       #6344F5 at 32.5%, purple tail to 0) + a slow travelling dash that samples the
       spatial gradient as it moves. Ambient class -- the rig's own activity, never
       feedback to a click. */
    const gid='beam-'+i;
    const bg=mk('linearGradient',{id:gid,gradientUnits:'userSpaceOnUse',
      x1:ocx,y1:ocy+44,x2:sx,y2:T});
    [['0%','#18CCFC','0'],['12%','#18CCFC','.9'],['32.5%','#6344F5','.9'],['100%','#AE48FF','0']]
      .forEach(([o,c,op])=>bg.appendChild(mk('stop',{offset:o,'stop-color':c,'stop-opacity':op})));
    defs.appendChild(bg);
    const beam=mk('path',{d:dPath,fill:'none',stroke:'url(#'+gid+')','stroke-width':1.6,
      class:'army-beam','stroke-linecap':'round'});
    beam.style.animationDelay=(i*1.1)+'s';
    svg.appendChild(beam);

    const g=mk('g',{class:'army-node army-enter','data-sid':s.session_id});
    g.style.cursor='pointer';
    g.style.animationDelay=(120+i*70)+'ms';
    /* Hover lights this box's OWN beam to full -- the wiring answers "which line is mine"
       exactly when the question is being asked, and never otherwise. */
    g.addEventListener('mouseenter',()=>{beam.classList.add('lit');edge.style.opacity=.18;});
    g.addEventListener('mouseleave',()=>{beam.classList.remove('lit');edge.style.opacity=.055;});
    g.appendChild(mk('rect',{x:L,y:T,width:BW,height:BH,rx:14,fill:'var(--bg-1)',stroke:'var(--bd)','stroke-width':1}));
    g.appendChild(mk('rect',{x:L,y:T,width:BW,height:BH,rx:14,fill:'url(#cardGrad)','pointer-events':'none'}));
    const dot=mk('circle',{cx:L+22,cy:T+27,r:6,fill:armyDotColour(s,lastSeen)});
    dot.id='armydot-'+s.session_id;
    g.appendChild(dot);
    /* TITLE FIRST, handle second. `42-dd` is auto-derived from the project folder plus a
       hash -- it identifies a session to the machine and to nobody else. What J recognises
       is what the window is ABOUT. So the big line is the title and the handle drops to a
       small monospace tag. */
    /* A just-spawned session has no title yet, so the label fell back to the 8-hex session
       id -- reproducing the exact "wtf is 42-dd" unreadability this view was fixed for. Say
       what it IS instead until it names itself. */
    const untitled=!s.title&&/^[0-9a-f]{6,}$/i.test(String(s.name||''));
    const bigLabel=untitled?'New session — starting up':(s.title||s.name||'untitled').slice(0,34);
    g.appendChild(ltxt(L+38,T+33,bigLabel,'var(--tx-1)',17,700));
    // handle (42-xx) lives in the drawer now -- five text rows read as a form, not a card
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
    const actEl=ltxt(L+18,T+120,'','var(--tx-4)',11,400); actEl.id='armyact-'+s.session_id;
    actEl.setAttribute('data-humanize','1');   // armyApplyRow reads this and trims shell noise
    g.appendChild(actEl);
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
  bar.style.cssText='display:flex;gap:6px;align-items:center;margin:0 0 10px;'+
    'position:absolute;top:10px;right:12px;z-index:5';
  bar.appendChild(mkbtn('↻','Re-read the roster and pulse log now',
    ()=>{try{route('army')}catch(_){}}));
  const staleN=((a.sessions||[]).filter(x=>x.activity==='stale'&&x.session_id!==(a.orchestrator||{}).session_id)).length;
  if(staleN){
    const t=mkbtn(armyShowStale?'−'+staleN:'+'+staleN,
      (armyShowStale?'Hide ':'Show ')+staleN+' idle chats (no transcript write for 2h+)',
      ()=>{ armyShowStale=!armyShowStale; try{route('army')}catch(_){} });
    bar.appendChild(t);
  }
  const pauseBtn=mkbtn('⏸','Stop the travelling dots without stopping the data',()=>{
    if(!armyState)return;
    armyState.paused=!armyState.paused;
    pauseBtn.textContent=armyState.paused?'▶':'⏸';
  });
  bar.appendChild(pauseBtn);
  const helpBtn=mkbtn('?','What am I looking at?',()=>{
    const lg=wrap.querySelector('.armylegend');
    if(lg)lg.style.display=(lg.style.display==='none'?'':'none');
  });
  bar.appendChild(helpBtn);
  wrap.appendChild(bar);

  /* LEGEND -- the page has to answer "how do I read this" without J asking a human.
     Counts are computed, never hard-coded, so the sentence cannot drift from the graph. */
  const wct=(a.workers||[]).length;
  const legend=el('div','armylegend');
  legend.style.cssText='display:flex;flex-wrap:wrap;gap:14px;align-items:baseline;margin:0 0 10px;'+
    'padding:8px 12px;border:1px solid var(--bd);border-radius:8px;background:var(--bg-inset);'+
    'font:500 11.5px/1.4 var(--font);color:var(--tx-3);flex:none';
  const li=(strong,rest)=>{
    const d=document.createElement('div');
    d.innerHTML='<b style="color:var(--tx-1);font-weight:700">'+strong+'</b> '+rest;
    return d;
  };
  /* Two glanceable lines, not four. J: "am i gonna read 30 lines of text and know what to
     do?" The old legend was a paragraph; this is a scan. */
  legend.appendChild(li('Boxes = Claude sessions.',
    'Top one is this page. Small circles inside a box are its subagents ('+wct+' total).'+
    (staleCount&&!armyShowStale?' '+staleCount+' idle chat'+(staleCount===1?'':'s')+' hidden.':'')));
  legend.appendChild(li('Cards on the right = things to do.',
    'Click one to open it, then Fire to spawn a worker that handles it.'));
  legend.style.display='none';   // furniture on demand, not permanent -- J: "too busy"
  wrap.appendChild(legend);
  const stars=document.createElement('canvas');
  stars.className='army-stars'; stars.width=W; stars.height=H;
  wrap.appendChild(stars);
  armyStars(stars,W,H);
  wrap.appendChild(svg);
  return {wrap,state:{centers,edges,nameToSid,lastSeen,queue:[],raf:null,cursor:''}};
}

function armyStars(canvas,W,H){
  /* Stage backdrop. Deterministic placement (golden-angle scatter, no RNG), two depth
     layers, slow drift + sine twinkle. Self-terminating like every army loop: stops when
     the canvas leaves the document. Reduced motion gets one static paint. */
  const ctx=canvas.getContext('2d'); if(!ctx)return;
  const N=90, dots=[];
  for(let k=0;k<N;k++){
    const deep=k%3!==0;
    dots.push({x:(k*137.508)%W, y:(k*91.7)%H, r:deep?0.8:1.4,
               v:deep?0.006:0.014, tw:(k%17)/17*6.2832});
  }
  let t=0;
  function frame(){
    if(!canvas.isConnected)return;
    ctx.clearRect(0,0,W,H); t+=1;
    for(const d of dots){
      d.x+=d.v; if(d.x>W+2)d.x=-2;
      const a=0.10+0.16*(0.5+0.5*Math.sin(t*0.008+d.tw));
      ctx.beginPath(); ctx.arc(d.x,d.y,d.r,0,6.2832);
      ctx.fillStyle='rgba(200,190,255,'+a.toFixed(3)+')'; ctx.fill();
    }
    if(!RM)requestAnimationFrame(frame);
  }
  if(RM){ frame(); return; }
  requestAnimationFrame(frame);
}

function armyDotColour(s,lastSeen){
  /* Spec move #3: ALIVE is cyan (--st-live), its own hue. Green is reserved for P&L, and
     "recently talked" was borrowing it -- a canvas of green dots also hides the one that
     matters. Quiet-but-alive is a neutral, not amber: quiet is not degraded. */
  if(!s.alive)return'var(--neg)';
  const seen=lastSeen[s.session_id];
  const age=seen?agoOf(seen):null;                 // hours
  if(age!=null&&age*3600<=300)return'var(--st-live)';  // talked within 5 min
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
  if(toKey==='off'||!st.centers[toKey])armyEnsureOffbox();   // the node is born on first use
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
  if(actEl&&row.detail)actEl.textContent=armyHumanAct(row.detail).slice(0,36);
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
    /* WHAT HAPPENS WHEN I CLICK GO. J: "am i going to realize what happens when I click go?"
       The fire button is now a two-step confirm that SAYS the consequence before it happens,
       and the second click plays a spawn animation so the cause (this card) and the effect
       (a new box on the graph) are visibly the same event. */
    const rth=rthNowClient();
    const act=el('div'); act.style.marginTop='14px';
    const what=el('div','firewhat');
    what.innerHTML=rth
      ? 'Market hours (09:30-15:55 ET) - firing is disabled so cockpit work never competes with the heartbeat.'
      : 'Clicking spawns a <b>'+esc(sel.model||'sonnet')+'</b> worker to do this. '+
        'It appears as a new box on the graph above and streams its work into Chat.';
    act.appendChild(what);
    const btn=document.createElement('button');
    btn.type='button'; btn.className='firebtn'; btn.dataset.state='idle'; btn.disabled=rth;
    btn.textContent=rth?'Disabled during market hours':'Fire this worker';
    const msg=el('div','micro'); msg.style.marginTop='8px';
    btn.onclick=()=>{
      if(btn.dataset.state==='idle'){
        btn.dataset.state='armed';
        btn.textContent='Click again to confirm — spawns a worker';
        btn.classList.add('armed');
        msg.textContent='One more click actually starts it. Click anywhere else to cancel.';
        return;
      }
      armyFireAnimation(sel.id);          // the visible cause->effect
      fireCard(sel,btn,msg);
    };
    // Clicking away from an armed button cancels it -- an armed destructive control that
    // stays armed silently is a foot-gun.
    p.addEventListener('click',(e)=>{ if(e.target!==btn && btn.dataset.state==='armed'){
      btn.dataset.state='idle'; btn.classList.remove('armed');
      btn.textContent='Fire this worker'; msg.textContent=''; } });
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
    it.style.cssText='padding:11px 13px 11px 17px;margin:0 0 8px;cursor:pointer;border-radius:12px;'+
      'border:1px solid '+(open?'var(--acc)':'var(--bd)')+';'+
      'background:linear-gradient(rgba(255,255,255,.02),rgba(255,255,255,0) 45%),var(--bg-1);'+
      'box-shadow:var(--topline),var(--ring);'+
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
    const r=el('div'); r.style.cssText='display:flex;align-items:center;gap:8px';
    const rk=el('span'); rk.textContent=String(c.rank);
    rk.style.cssText='font:700 10.5px/1 var(--mono);min-width:20px;height:20px;display:inline-grid;'+
      'place-items:center;border-radius:6px;background:rgba(255,255,255,.06);color:var(--tx-2);'+
      'border:1px solid var(--bd-subtle)';
    const srcEl=el('span'); srcEl.textContent=src.replace(/\.(md|json)$/,'');
    srcEl.style.cssText='font:600 9.5px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--tx-4)';
    r.appendChild(rk); r.appendChild(srcEl);
    const t=el('div'); t.textContent=String(c.title||'').slice(0,84);
    t.style.cssText='font:600 13.5px/1.35 var(--font);color:var(--tx-1);margin-top:4px';
    it.appendChild(r); it.appendChild(t);
    rail.appendChild(it);
  });

  if(!cards.length)rail.appendChild(el('div','micro','No cards right now — nothing is flagged.'));
}

function armyFireAnimation(id){
  /* Make the cause visible. A pulse leaves the fired card panel and travels to the
     orchestrator node, which flashes -- so "I clicked this card" and "a worker is being
     born up there" read as one motion, not two disconnected events. A toast says it in
     words for anyone who missed the motion, and both respect prefers-reduced-motion. */
  try{
    const panel=document.querySelector('.acard-open');
    const orc=document.getElementById('army-orc');
    const svg=document.getElementById('armysvg');
    // toast, always (this is the words-fallback and the reduced-motion path)
    let toast=document.getElementById('firetoast');
    if(!toast){ toast=el('div'); toast.id='firetoast'; toast.className='firetoast'; document.body.appendChild(toast); }
    toast.textContent='Spawning a worker — watch the top box';
    toast.classList.add('show');
    setTimeout(()=>toast.classList.remove('show'),2600);
    if(orc){ orc.classList.add('orc-spawn'); setTimeout(()=>orc.classList.remove('orc-spawn'),1400); }
    if(RM||!panel||!svg)return;
    const a=panel.getBoundingClientRect(), b=svg.getBoundingClientRect();
    const dot=el('div'); dot.className='firecomet';
    dot.style.left=(a.left+20)+'px'; dot.style.top=(a.top+20)+'px';
    document.body.appendChild(dot);
    requestAnimationFrame(()=>{
      dot.style.transform='translate('+((b.left+b.width/2)-(a.left+20))+'px,'+((b.top+70)-(a.top+20))+'px) scale(.4)';
      dot.style.opacity='0';
    });
    setTimeout(()=>{ try{dot.remove()}catch(_){}} ,900);
  }catch(_){/* animation must never break the actual fire */}
}

function armySelectCard(id){
  const go=()=>{ armyCardSel=(armyCardSel===id?null:id); armyPaintCards(); };
  if(document.startViewTransition && !RM){ document.startViewTransition(go); } else { go(); }
}

function vArmy(h){
  const a=D.army||{sessions:[],workers:[],pulses:[],orchestrator:null,source:{}};
  const live=location.protocol!=='file:';
  /* The topbar already says "Army" -- repeating it as an h2 directly underneath was the
     view introducing itself twice. One slim status line carries what is actually new. */
  const shead=el('div','shead',
    `<span class="chip ${live?'ok':''}" title="${esc(a.scope_note||'')}"><i class="dot"></i>${live?'LIVE':'SNAPSHOT'}</span>`);
  h.appendChild(shead);

  /* Two-column shell. align-self:start is load-bearing, not cosmetic: grid's default
     `stretch` makes the short rail column match its taller sibling's height, which
     silently defeats position:sticky. */
  /* ONE SCREEN, NO SCROLL. J: "make it one page i dont want to ahve to scroll."
     The page was a growing document; it is now a fixed-height viewport grid. The graph gets
     the elastic row (flex:1, min-height:0) and the SVG scales to FIT that box rather than
     dictating it, so adding a session makes the boxes smaller instead of making the page
     longer. min-height:0 is load-bearing -- without it a flex child refuses to shrink below
     its content and the whole thing overflows anyway. */
  const shell=el('div','armyshell');
  shell.style.cssText='display:grid;grid-template-columns:1fr minmax(280px,320px);'+
    'gap:16px;align-items:stretch;height:calc(100vh - 150px);min-height:520px';

  const main=el('div');
  main.style.cssText='display:flex;flex-direction:column;gap:12px;min-height:0;overflow:hidden';
  const stage=el('div'); stage.id='armystage'; stage.style.flex='none'; main.appendChild(stage);

  const card=el('div','card');
  card.style.cssText='flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto';
  const built=armySvg(a);
  built.wrap.style.cssText='flex:1;min-height:0;display:flex;flex-direction:column';
  card.appendChild(built.wrap);
  /* BOTTOM PANEL: chat first, the raw event ledger behind a tab. J asked for the terminal
     to BE the orchestrator window; the ledger is still useful telemetry, so it moves rather
     than dies. */
  const tabs=el('div','chattabs'); tabs.style.flex='none';
  const ledger=el('div','armyledger'); ledger.id='armyledger'; ledger.style.display='none';
  const chat=chatPane();
  const mkTab=(label,on)=>{
    const b=document.createElement('button');
    b.type='button'; b.textContent=label; b.className='chattab'+(on?' on':'');
    return b;
  };
  const tChat=mkTab('Chat',true), tAct=mkTab('Activity',false);
  const pick=(chatOn)=>{
    chat.style.display=chatOn?'':'none';
    ledger.style.display=chatOn?'none':'';
    tChat.className='chattab'+(chatOn?' on':'');
    tAct.className='chattab'+(chatOn?'':' on');
  };
  tChat.onclick=()=>pick(true); tAct.onclick=()=>pick(false);
  tabs.appendChild(tChat); tabs.appendChild(tAct);
  card.appendChild(tabs);
  chat.style.cssText='flex:none';
  ledger.style.maxHeight='150px';
  card.appendChild(chat);
  card.appendChild(ledger);
  card.appendChild(srcRow([a.source&&a.source.pulse,a.source&&a.source.sessions].filter(Boolean)));
  if(a.error)card.appendChild(el('div','micro warnc','army payload error: '+esc(a.error)));
  main.appendChild(card);
  shell.appendChild(main);

  const rail=el('div'); rail.id='armyrail';
  rail.style.cssText='min-height:0;overflow:auto;padding-right:4px';
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

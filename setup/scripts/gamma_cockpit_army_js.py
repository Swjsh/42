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
function wrapStars(){ try{ return document.querySelector('.army-stars'); }catch(_){ return null; } }
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
  if(/^git\b/.test(cmd))return 'git '+(cmd.split(/\s+/)[1]||'');
  return tool ? ('Running '+tool) : d;
}

function armySvg(a){
  const ns='http://www.w3.org/2000/svg';
  const mk=(t,attrs)=>{const e=document.createElementNS(ns,t);for(const k in (attrs||{}))e.setAttribute(k,attrs[k]);return e};
  const stxt=(x,y,str,c,sz,w,anchor)=>{const e=mk('text',{x,y,fill:c||'var(--tx-2)','font-size':Math.max(12,sz||12),  /* 12px floor: spec 2.2, nothing visible below it */
    'font-family':'var(--font)','font-weight':w||500,'text-anchor':anchor||'middle'});e.textContent=str;return e};
  /* Left-aligned label -- reading a box is scanning a short list, not centring a poster. */
  const ltxt=(x,y,str,c,sz,w)=>stxt(x,y,str,c,sz,w,'start');
  /* Mono variant -- the orchestrator id (42-98) reads as an identifier, not a
     headline; a monospace face says so at a glance the way it does everywhere
     else an id/path appears on this page. */
  const lmono=(x,y,str,c,sz,w)=>{const e=ltxt(x,y,str,c,sz,w);e.setAttribute('font-family','var(--mono)');return e;};

  const sessions=(a.sessions||[]).slice(0,12), workers=a.workers||[];
  const byWorkerSession={};
  workers.forEach(w=>(byWorkerSession[w.session_id]=byWorkerSession[w.session_id]||[]).push(w));
  const nameToSid={}; sessions.forEach(s=>nameToSid[s.name]=s.session_id);
  // "recently talked" beats plain aliveness for the dot colour -- see build_army()'s
  // last_seen computation; recomputed as pulses arrive via armyDotColour() below.
  const lastSeen={}; (a.pulses||[]).forEach(r=>{if(r.session_id&&r.ts)lastSeen[r.session_id]=r.ts});

  /* LAYOUT -- fixed box size in a GRID, never one scaled row. v1 sized the viewBox to
     N sessions (W=N*200+140): 10 sessions scaled the SVG to ~58%, 13px labels to 7.6px.
     J: "look how tiny it is". Now the viewBox width is FIXED near the real column width
     and rows wrap, so box/type size never depend on how many sessions are alive. */
  /* COLUMN COUNT IS MEASURED, NOT FIXED. Adding the 340px cards rail cut the canvas to
     ~622px in a narrow window, and a fixed 3-column (1110px) graph squeezed into that
     scales to 0.56 -- which is the exact tininess this layout was rewritten to kill. So
     pick the widest column count that still FITS, and let the graph get taller instead of
     smaller. Falls back to 3 when the width cannot be read (file:// pre-layout). */
  /* SCALE PASS (J: "do u see how fkn tiny it is"). At 1920 the stage column is ~1500px
     and the old 330px boxes + 380px hero used barely 40% of it -- a postage stamp on a
     billboard. Boxes 430x200, hero 560x120, type up a full step. fitCols() already adapts
     column count to what fits, so smaller windows degrade to 2/1 columns, never to tiny. */
  /* Box width flexes between BW_MIN and BW_MAX so the 1360px Command column
     (spec 3) still seats 3 columns at 1:1 scale: 430px boxes need 1422px for
     three, which forced 2 columns + 2 rows and a 760px stage; 398px boxes fit.
     Type size is unaffected (the viewBox stays at the real column width). */
  const BW_MAX=430, BW_MIN=340, GAPX=32, GAPY=32, PAD=34;   // BW_MIN 340: two columns still fit the Glow 2/3-width stage (~790px) at 1:1
  const fitCols=(avail)=>{
    for(let c=3;c>1;c--){ if(PAD*2+c*BW_MIN+(c-1)*GAPX<=avail) return c; }
    return 1;
  };
  let availW=0;
  try{
    const sh=document.getElementById('stagehost');   // Glow Command seats the stage in a 2/3 column
    const host=(sh&&sh.clientWidth>200)?sh:(document.getElementById('view')||document.body);
    availW=host.clientWidth-32;                // card padding only -- the cards rail is gone
  }catch(_){}
  const COLS=availW>200?fitCols(availW):3;
  const BW=availW>200?Math.max(BW_MIN,Math.min(BW_MAX,Math.floor((availW-PAD*2-(COLS-1)*GAPX)/COLS))):BW_MAX;
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
  /* COMPACT MODE (Fable review 2026-09-03, "first-viewport density"): <=3 live sessions
     drops the card to a title/status/context-meter face (per-agent lines -> drawer) and
     skips the featured double-width seat so seating never wraps for the crown alone.
     armyMount toggles .stage--compact (CSS: max-height 300px, was 480) off this flag. */
  const compact=shown.length<=3;
  const BH=compact?112:200;
  const rows=1; // recomputed below once bento seats exist
  const W=PAD*2+COLS*BW+(COLS-1)*GAPX;
  const ocy=52, ORCH_H=146, SESS_TOP=218;
  // H depends on bento rows, which depend on which tile is featured -- computed after
  // seating, so declared with let and patched below.
  let H=SESS_TOP+1*(BH+GAPY)+40;
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
  g1.appendChild(mk('stop',{offset:'0%','stop-color':'rgba(255,255,255,.05)'}));
  g1.appendChild(mk('stop',{offset:'45%','stop-color':'rgba(255,255,255,0)'}));
  defs.appendChild(g1);
  const g2=mk('linearGradient',{id:'orcGrad',x1:'0',y1:'0',x2:'0',y2:'1'});
  g2.appendChild(mk('stop',{offset:'0%','stop-color':'color-mix(in oklch,var(--gc-indigo, var(--acc-deep)) 55%,transparent)'}));
  g2.appendChild(mk('stop',{offset:'70%','stop-color':'rgba(255,255,255,0)'}));
  defs.appendChild(g2);
  /* Shared beam gradient (objectBoundingBox): every .army-beam and the orchestrator's
     .army-trace sample it (painted via ARMY_GLOW_CSS); replaces the old per-edge loop. */
  const g3=mk('linearGradient',{id:'gc-beam-grad',x1:'0',y1:'0',x2:'0',y2:'1'});
  [['0%','var(--gc-cyan,#22d3ee)','0'],['12%','var(--gc-cyan,#22d3ee)','.9'],
   ['32.5%','var(--gc-indigo,#6366f1)','.9'],['100%','var(--gc-violet,#8b5cf6)','0']]
    .forEach(([o,c,op])=>g3.appendChild(mk('stop',{offset:o,'stop-color':c,'stop-opacity':op})));
  defs.appendChild(g3);
  svg.appendChild(defs);

  const centers={}, edges={};
  const ocx=W/2;
  centers.orc={x:ocx,y:ocy};
  /* Meridian rings: two faint circles centred on the hero give the stage a command-map
     structure the eye reads instantly; the aura beneath the hero breathes on the ambient
     clock -- the rig's heartbeat, literally. */
  const aura=mk('ellipse',{cx:ocx,cy:54,rx:Math.min(520,W*.38),ry:95,fill:'url(#orcAura)',class:'army-aura'});
  svg.appendChild(aura);
  const ag=mk('radialGradient',{id:'orcAura'});
  ag.appendChild(mk('stop',{offset:'0%','stop-color':'#6344F5','stop-opacity':'.16'}));
  ag.appendChild(mk('stop',{offset:'100%','stop-color':'#6344F5','stop-opacity':'0'}));
  defs.appendChild(ag);
  const orc=a.orchestrator;
  const og=mk('g',{class:'army-node army-enter',id:'army-orc'});
  const OW=W-PAD*2;
  [{fill:'var(--gc-panel,var(--bg-2))',stroke:'var(--gc-line,var(--bd-strong))','stroke-width':1,class:'gc-glass'},
   {fill:'url(#orcGrad)',stroke:'var(--gc-line,var(--bd-strong))','stroke-width':1,opacity:.9}]
    .forEach(o=>og.appendChild(mk('rect',Object.assign({x:PAD,y:16,width:OW,height:ORCH_H,rx:16},o))));
  /* Tracing border comet on the ORCHESTRATOR only (.army-trace), sampling gc-beam-grad. */
  og.appendChild(mk('rect',{x:PAD,y:16,width:OW,height:ORCH_H,rx:16,fill:'none',
    stroke:'url(#gc-beam-grad)','stroke-width':2,class:'army-trace','stroke-linecap':'round','pathLength':'1000'}));
  og.appendChild(mk('circle',{cx:PAD+30,cy:52,r:9,fill:'none',stroke:'var(--st-live)','stroke-width':1.5,class:'army-ping'}));
  og.appendChild(mk('circle',{cx:PAD+30,cy:52,r:8,fill:'var(--st-live)',class:'army-ring'}));
  /* DEMOTED (Fable review, 2026-09-03, item 2 "hero hierarchy"): "42-98" was
     the largest, boldest text on the page -- meaningful to nobody. The state
     SENTENCE above the stage is the hero now; this becomes a plain 15px mono
     id + 13px label, same line, same slot. */
  og.appendChild(lmono(PAD+52,58,orc?orc.name:'—','var(--tx-1)',15,600));
  og.appendChild(ltxt(PAD+130,58,'ORCHESTRATOR — this page. The session you are talking to.','var(--acc)',13,600));
  if(orc&&orc.title)og.appendChild(stxt(W-PAD-20,60,orc.title.slice(0,48),'var(--tx-4)',12,400,'end'));

  /* THE ORCHESTRATOR'S OWN AGENTS. This strip is the session J is actually talking to,
     and it was the ONE box on the page that showed nothing about its subagents -- so
     "what are my subagents doing" was unanswerable for the only session he was in.
     The strip is ~1340px wide, so its agents get TWO columns and four of them fit at
     full width: the same row grammar as the tiles, so there is one pattern to learn. */
  if(orc){
    const ow=(byWorkerSession[orc.session_id]||[]).slice()
      .sort((x,y)=>(y.active?1:0)-(x.active?1:0)||String(y.last_write||'').localeCompare(String(x.last_write||'')));
    const oLive=orc.worker_active||0, oEver=orc.worker_count||0;
    og.appendChild(mk('line',{x1:PAD+22,y1:78,x2:PAD+OW-22,y2:78,
      stroke:'var(--bd)','stroke-width':1,opacity:.5}));
    const ohead=oLive?(oLive+' agent'+(oLive===1?'':'s')+' running now')
      :(oEver?'no agents running · '+oEver+' finished earlier':'no agents');
    og.appendChild(ltxt(PAD+22,98,ohead,oLive?'var(--st-live)':'var(--tx-3)',12.5,oLive?700:500));
    if(oLive)og.appendChild(stxt(PAD+OW-22,98,'click any row for its full prompt','var(--tx-4)',11,500,'end'));
    const colW=(OW-52)/2;
    ow.slice(0,4).forEach((w,j)=>{
      const cx0=PAD+22+(j%2)*colW, ry=118+Math.floor(j/2)*19;
      const rg=mk('g',{class:'army-node'}); rg.style.cursor='pointer';
      centers['w:'+w.agent_id]={x:cx0+5,y:ry-4};
      const rdot=mk('circle',{cx:cx0+5,cy:ry-4,r:3.5,fill:w.active?'var(--st-live)':'var(--tx-4)'});
      rdot.id='armyworker-'+w.agent_id;
      rg.appendChild(rdot);
      const tag=armyTypeWord(w.agent_type)+(w.model?'·'+w.model:'');
      rg.appendChild(ltxt(cx0+16,ry,fitTxt(tag,120,12,true),
        w.active?'var(--tx-2)':'var(--tx-4)',10.5,600));
      rg.appendChild(ltxt(cx0+144,ry,fitTxt(armyGist(w.purpose||w.task),colW-160,12),
        w.active?'var(--tx-3)':'var(--tx-4)',11.5,400));
      const tt=mk('title',{}); tt.textContent=(w.agent_type||'agent')+' · '+(w.model||'?')+
        ' · '+(w.active?'running':'finished')+'\n'+(w.task||''); rg.appendChild(tt);
      rg.onclick=(e)=>{e.stopPropagation();armyWorkerDrawer(w);};
      og.appendChild(rg);
    });
    if(oEver>4)og.appendChild(ltxt(PAD+22,157,'+'+(oEver-4)+' more this session','var(--tx-4)',11,500));
  }
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

  /* BENTO SEATING (21st.dev bento family: Stats/Analytics/Cybernetic grids): the busiest
     session earns the DOUBLE-WIDTH cell; everything else flows around it in a tight grid.
     Importance gets area -- that is the entire bento idea. Seats are computed first so
     render code just reads its cell. */
  const seats=[];
  {
    let fi=-1;
    /* compact skips the featured double-width crown entirely: with <=3 cards
       a 2-col seat was the one thing that could still push a card onto a
       second row even when every card would otherwise fit in one. */
    if(!compact&&shown.length>=2&&COLS>=2){
      let best=-1;
      shown.forEach((s,k)=>{const sc=(s.worker_count||0)*1000+(s.context_pct||0);
        if(sc>best){best=sc;fi=k;}});
    }
    /* Featured seats FIRST (row 0, cols 0-1) -- seating it in arrival order left a hole
       in row 0 and pushed a lone wide tile to row 1, which the screenshot made obvious. */
    const order=fi>=0?[fi,...shown.map((_,k)=>k).filter(k=>k!==fi)]:shown.map((_,k)=>k);
    const seatByIdx={};
    let col=0,row=0;
    order.forEach(k=>{
      const span=(k===fi)?2:1;
      if(col+span>COLS){col=0;row++;}
      seatByIdx[k]={col,row,span};
      col+=span; if(col>=COLS){col=0;row++;}
    });
    shown.forEach((_,k)=>seats.push(seatByIdx[k]));
  }
  const rowsUsed=seats.length?Math.max(...seats.map(t=>t.row))+1:1;
  H=SESS_TOP+rowsUsed*(BH+GAPY)+40;
  svg.setAttribute('viewBox',`${-BLEED} ${-BLEED} ${W+BLEED*2} ${H+BLEED*2}`);
  document.querySelectorAll('.army-stars').forEach(c=>{c.width=W;c.height=H;});
  shown.forEach((s,i)=>{
    const seat=seats[i];
    const w=seat.span*BW+(seat.span-1)*GAPX;
    const L=PAD+seat.col*(BW+GAPX);
    const T=SESS_TOP+seat.row*(BH+GAPY);
    const CW=w-44;                      // usable content width inside the card padding
    const sx=L+w/2, sy=T+BH/2;
    centers['s:'+s.session_id]={x:sx,y:sy};
    const dPath=`M ${sx} ${ORCH_H+16} C ${sx} ${(ORCH_H+16+T)/2}, ${sx} ${(ORCH_H+16+T)/2}, ${sx} ${T}`;
    /* Ghost rail: Aceternity's measured base -- ~.5px stroke at 5% -- wiring that is
       present but silent until something moves along it. */
    const edge=mk('path',{d:dPath,fill:'none',stroke:'var(--tx-1)','stroke-width':.6,opacity:.055});
    edge.id='armyedge-'+s.session_id;
    svg.appendChild(edge);
    edges[s.session_id]=edge;
    /* Beam comet: stroke = shared gc-beam-grad via ARMY_GLOW_CSS (.army-beam), themed;
       a slow travelling dash. Ambient -- the rig's own activity, never click feedback. */
    const beam=mk('path',{d:dPath,fill:'none','stroke-width':2.2,class:'army-beam','stroke-linecap':'round'});
    // Two comma-separated delays, one per animation in the class: the dash comet keeps
    // its per-edge phase; the power-on waits for this tile's entrance to land first.
    // A single inline delay would clobber both.
    beam.style.animationDelay=(i*1.1)+'s,'+(550+i*120)+'ms';
    svg.appendChild(beam);

    const g=mk('g',{class:'army-node army-enter','data-sid':s.session_id});
    g.style.cursor='pointer';
    g.style.animationDelay=(120+i*70)+'ms';
    /* Hover lights this box's OWN beam to full -- the wiring answers "which line is mine"
       exactly when the question is being asked, and never otherwise. */
    g.addEventListener('mouseenter',()=>{beam.classList.add('lit');edge.style.opacity=.18;});
    g.addEventListener('mouseleave',()=>{beam.classList.remove('lit');edge.style.opacity=.055;});
    g.appendChild(mk('rect',{x:L,y:T,width:w,height:BH,rx:14,fill:'var(--gc-panel,var(--bg-1))',stroke:'var(--gc-line,var(--bd))','stroke-width':1,class:'gc-glass'}));
    g.appendChild(mk('rect',{x:L,y:T,width:w,height:BH,rx:14,fill:'url(#cardGrad)','pointer-events':'none'}));
    if(seat.span===2){
      // The featured cell earned its area; the crown makes the earning visible.
      g.appendChild(mk('rect',{x:L,y:T,width:w,height:BH,rx:14,fill:'none',stroke:'var(--acc)',
        'stroke-width':1.5,class:'army-trace2','stroke-linecap':'round','pathLength':'1000',
        'pointer-events':'none'}));
    }
    const dot=mk('circle',{cx:L+26,cy:T+33,r:7.5,fill:armyDotColour(s)});
    dot.id='armydot-'+s.session_id;
    if(s.activity==='active'){
      /* radar ping: an expanding fading ring says LIVE without a single word */
      g.appendChild(mk('circle',{cx:L+26,cy:T+33,r:8,fill:'none',stroke:'var(--st-live)',
        'stroke-width':1.5,class:'army-ping'}));
    }
    g.appendChild(dot);
    /* TITLE FIRST, handle second. `42-dd` is auto-derived from the project folder plus a
       hash -- it identifies a session to the machine and to nobody else. What J recognises
       is what the window is ABOUT. So the big line is the title and the handle drops to a
       small monospace tag. */
    /* A just-spawned session has no title yet, so the label fell back to the 8-hex session
       id -- reproducing the exact "wtf is 42-dd" unreadability this view was fixed for. Say
       what it IS instead until it names itself. */
    const untitled=!s.title;
    /* "Untitled chat" was a lie of omission -- it read as a broken/empty window
       rather than what it actually is (Fable review, 2026-09-03). The id+kind
       line below already answers "which one, what kind" honestly; say the same
       true thing here instead of a placeholder. */
    const bigLabel=untitled?fitTxt(s.name+' · '+armyKindWord(s),CW-96,19):fitTxt(s.title,CW-96,19);
    g.appendChild(ltxt(L+42,T+34,bigLabel,untitled?'var(--tx-3)':'var(--tx-1)',19,untitled?500:700));
    /* HANDLE + KIND, always in the same slot. The heading used to mean two different
       things -- a window title when one existed, the id-name when it didn't -- so
       "Engine performance today" read as a metric panel rather than a Claude window.
       Title is now always the heading and this line always answers "which one, and
       what kind of thing is it". */
    g.appendChild(ltxt(L+42,T+53,s.name+' · '+armyKindWord(s),'var(--tx-4)',11.5,500));
    /* Say WHEN, not just what. "a Claude window YOU have open" was flatly untrue for a
       chat closed two days ago whose process merely lingered. */
    const lw=s.last_write_min;
    const ago=(lw==null)?'':(lw<1?'just now':(lw<60?Math.round(lw)+'m ago':
      (lw<1440?Math.round(lw/60)+'h ago':Math.round(lw/1440)+'d ago')));
    const act=s.activity||'unknown';
    const actWord=act==='active'?'ACTIVE NOW':(act==='idle'?'idle':(act==='stale'?'old chat':'unknown'));
    // ALIVE is cyan. This read var(--pos) -- GREEN -- which the ratified spec reserves
    // for P&L; a green "ACTIVE NOW" beside a red one would have read as a winning desk.
    const actCol=act==='active'?'var(--st-live)':(act==='idle'?'var(--tx-3)':'var(--tx-4)');
    g.appendChild(ltxt(L+22,T+76,actWord+(ago?' · '+ago:''),actCol,13,act==='active'?700:500));

    /* ── THE AGENT BLOCK ── J, third ask: "i still dont know what im looking at like
       subagent wise on the screen." Every field he needed -- agent_type, model, the
       full task prompt, live-or-done -- was already in the payload and was being
       rendered as five identical grey circles labelled "workers". The data was one
       click away behind a dot that announced neither its clickability nor its
       contents, so he was never going to find it. Now it is on the face of the card. */
    const wl=(byWorkerSession[s.session_id]||[]).slice()
      .sort((x,y)=>(y.active?1:0)-(x.active?1:0)||String(y.last_write||'').localeCompare(String(x.last_write||'')));
    const liveN=s.worker_active||0, everN=s.worker_count||0;
    /* HONEST HEADLINE. The old line said "8 workers +43", where 8 was
       MAX_WORKERS_PER_SESSION -- the display cap, not a quantity -- so it read
       cap+overflow and implied a standing army. 42-c9 showed it while all 51 of its
       agents had been finished for 9.3 hours. Present tense comes from worker_active
       ONLY; worker_count is spoken of strictly in the past.
       COMPACT (<=3 live sessions) drops this whole block from the card face --
       title/status/context-meter only, per-agent lines live in the drawer only
       (armySessionDrawer already lists every worker on click). */
    if(!compact){
    const headline=liveN?(liveN+' agent'+(liveN===1?'':'s')+' running now')
      :(everN?'no agents running':'no agents');
    g.appendChild(ltxt(L+22,T+119,headline,liveN?'var(--st-live)':'var(--tx-3)',12.5,liveN?700:500));
    if(!liveN&&everN)
      g.appendChild(ltxt(L+22+armyTextW(headline,12.5)+8,T+119,
        '· '+everN+' finished earlier','var(--tx-4)',12.5,500));

    /* One row per agent: status, what KIND of agent, which model, and what it was
       actually told to do. Three rows at rest; the drawer holds the full prompt. */
    const rows=wl.slice(0,2);
    rows.forEach((w,j)=>{
      const ry=T+138+j*19;
      const rg=mk('g',{class:'army-node'}); rg.style.cursor='pointer';
      /* The pulse layer addresses workers by BOTH of these: centers['w:id'] is where a
         message travelling to this agent lands, and #armyworker-id is what flashes on
         arrival. Dropping them with the old circles would have rerouted every
         worker-bound pulse to the off-box -- rendering a delivered message as
         undeliverable, which is a lie, not a layout change. */
      centers['w:'+w.agent_id]={x:L+27,y:ry-4};
      const rdot=mk('circle',{cx:L+27,cy:ry-4,r:3.5,
        fill:w.active?'var(--st-live)':'var(--tx-4)'});
      rdot.id='armyworker-'+w.agent_id;
      rg.appendChild(rdot);
      const tag=armyTypeWord(w.agent_type)+(w.model?'·'+w.model:'');
      rg.appendChild(ltxt(L+38,ry,fitTxt(tag,120,12,true),
        w.active?'var(--tx-2)':'var(--tx-4)',10.5,600));
      /* `purpose` is derived in the payload, where the full prompt and the agent's
         sibling set are both in hand -- the browser can see neither. */
      rg.appendChild(ltxt(L+166,ry,fitTxt(armyGist(w.purpose||w.task),CW-144,12),
        w.active?'var(--tx-3)':'var(--tx-4)',11.5,400));
      const tt=mk('title',{}); tt.textContent=(w.agent_type||'agent')+' · '+(w.model||'?')+
        ' · '+(w.active?'running':'finished')+'\n'+(w.task||''); rg.appendChild(tt);
      rg.onclick=(e)=>{e.stopPropagation();armyWorkerDrawer(w);};
      g.appendChild(rg);
    });
    if(wl.length>rows.length||s.worker_overflow)
      g.appendChild(ltxt(L+38,T+175,
        '+'+(everN-rows.length)+' more not shown','var(--tx-4)',11,500));
    }
    const actEl=ltxt(L+22,T+97,'','var(--tx-4)',11.5,400); actEl.id='armyact-'+s.session_id;
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
      const cy=T+BH-8;
      // warn/neg rather than the accent: nearing a compact is a STATE, and severity is not
      // what the purple means anywhere else on this page.
      const col=cpct>=90?'var(--neg)':(cpct>=75?'var(--warn)':'var(--acc)');
      /* SEGMENTED meter, not a continuous bar: discrete square-ended blocks with visible
         gaps read as an instrument with a resolution -- a loading bar reads as waiting.
         (nothing-design-skill's signature data-viz; 2-3px gaps, no pill radius.) */
      const segs=14, sgap=3, sbw=((w-2)-sgap*(segs-1))/segs;
      const lit=frac>0?Math.max(1,Math.round(frac*segs)):0;
      const meter=mk('g',{id:'armyctx-'+s.session_id});
      for(let i=0;i<segs;i++){
        meter.appendChild(mk('rect',{x:L+1+i*(sbw+sgap),y:cy,width:sbw,height:6,rx:1,
          fill:i<lit?col:'color-mix(in oklch,white 8%,transparent)'}));
      }
      g.appendChild(meter);
      /* The numeral now sits WITH the meter it labels, at the foot of the card, and is
         demoted from 24px to 15px. It was the biggest thing on the tile while the
         subagents -- the thing J has asked about three times -- were 11px anonymous
         dots: the least-asked-about number had the most ink. "memory used" rather than
         "context", because context% is jargon for a window J never chose. */
      const lab=stxt(L+w-22,T+BH-14,Math.round(cpct)+'% memory used',col,11,600,'end');
      setTimeout(()=>{ if(lab.isConnected)countUp(lab,cpct,v=>Math.round(v)+'% memory used'); },380);
      lab.id='armyctxlab-'+s.session_id;
      g.appendChild(lab);
    }

    // Explicit affordance: the whole box was already clickable but nothing said so.
    // Bottom-right, not beside the title: at 17px a 34-char title runs to ~L+320 and
    // collided with an affordance sitting at the same baseline (seen in a headless shot).
    // Rides the status line: the card's foot now belongs to the memory meter, and two
    // right-anchored labels 6px apart overprinted each other.
    g.appendChild(stxt(L+w-22,T+76,'open ▸','var(--acc)',12.5,600,'end'));
    g.onclick=()=>armySessionDrawer(s,byWorkerSession[s.session_id]||[]);
    svg.appendChild(g);

    /* The five anonymous grey circles that used to sit here are GONE. They carried no
       type, no model, no purpose and no honest live/done state -- five identical dots
       were the entire visual vocabulary for 66 subagents. Their replacement is the
       named agent rows above, which say all four things on the face of the card. */
  });

  if(hiddenCount){
    svg.appendChild(stxt(W/2,H-18,'+'+hiddenCount+' more session'+(hiddenCount===1?'':'s')+
      ' not shown — the roster is capped so the boxes stay readable','var(--tx-4)',11,500));
  }

  /* CONTROLS -- a 28px icon row, top-right of the stage (Quiet Command spec sec 3 band 3).
     Was a row of labelled text buttons; icons now, with ic() feature-detected so the row
     never goes blank while gamma_cockpit_vendor.py's icon helper is still landing. Refresh
     routes to 'command' first -- the new home for this stage -- and falls back to the old
     'army' route while that view has not shipped yet. */
  const wrap=el('div','org armywrap');
  const icOr=(name,glyph)=>(typeof ic==='function')?ic(name):esc(glyph);
  const routeStage=()=>{ try{route('command')}catch(_){ try{route('army')}catch(__){} } };
  const bar=el('div','stage__controls');
  bar.style.cssText='display:flex;gap:6px;align-items:center;margin:0 0 10px;'+
    'position:absolute;top:10px;right:12px;z-index:5';
  const mkctl=(html,title,fn)=>{
    const b=document.createElement('button');
    b.type='button'; b.title=title; b.className='stage__ctlbtn';
    b.style.cssText='min-width:28px;height:28px;padding:0 8px;display:inline-grid;place-items:center;'+
      'font:600 12px/1 var(--font);border-radius:8px;cursor:pointer;'+
      'border:1px solid var(--bd);background:var(--bg-2);color:var(--tx-2);';
    b.innerHTML=html; b.onclick=fn;
    return b;
  };
  bar.appendChild(mkctl(icOr('refresh-cw','↻'),'Re-read the roster and pulse log now',routeStage));
  const staleN=((a.sessions||[]).filter(x=>x.activity==='stale'&&x.session_id!==(a.orchestrator||{}).session_id)).length;
  if(staleN){
    /* round-2 review (major): this was bare text ("+3") beside three icon-only
       buttons -- "four different visual treatments in a few inches". The eye
       glyph (already vendored) plus the count reads as one family with
       refresh/pause/help, and still says show-vs-hide via its title + the
       glyph itself rather than a naked +/- sign. */
    bar.appendChild(mkctl(icOr('eye','◉')+'<span style="margin-left:4px">'+esc(staleN)+'</span>',
      (armyShowStale?'Hide ':'Show ')+staleN+' idle chats (no transcript write for 2h+)',
      ()=>{ armyShowStale=!armyShowStale; routeStage(); }));
  }
  const pauseBtn=mkctl(icOr('pause','⏸'),'Stop the travelling dots without stopping the data',()=>{
    if(!armyState)return;
    armyState.paused=!armyState.paused;
    pauseBtn.innerHTML=armyState.paused?icOr('play','▶'):icOr('pause','⏸');
  });
  bar.appendChild(pauseBtn);
  /* Hand-authored (not a vendored Lucide asset -- none of the 59 vendored names is a
     help glyph, spec section 5's own note: "circle-help are deliberately absent"),
     but drawn with the SAME contract every vendored icon uses (16x16, stroke
     currentColor, stroke-width 2, round caps) so it reads as the fourth member of one
     icon family instead of a plain "?" character next to three SVGs. */
  const helpIcon='<svg class="ic" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" '+
    'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+
    '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.2a2.6 2.6 0 0 1 5 1c0 1.8-2.5 2-2.5 3.8"/>'+
    '<circle cx="12" cy="17.2" r=".1"/></svg>';
  const helpBtn=mkctl(helpIcon,'What am I looking at?',()=>{
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
    'font:500 12px/1.4 var(--font);color:var(--tx-3);flex:none';
  const li=(strong,rest)=>{
    const d=document.createElement('div');
    d.innerHTML='<b style="color:var(--tx-1);font-weight:700">'+strong+'</b> '+rest;
    return d;
  };
  /* Two glanceable lines, not four. J: "am i gonna read 30 lines of text and know what to
     do?" The old legend was a paragraph; this is a scan. */
  legend.appendChild(li('Boxes = Claude sessions.',
    'Top one is this page. Small circles inside a box are its subagents ('+wct+' total).'+
    (staleCount&&!armyShowStale?' '+staleCount+' idle chat'+(staleCount===1?'':'s')+' hidden.':'')+
    ' The bottom bar is memory used before a compact -- cyan is fine, amber near one, red past it.'));
  legend.appendChild(li('Cards on the right = things to do.',
    'Click one to open it, then Fire to spawn a worker that handles it.'));
  legend.style.display='none';   // furniture on demand, not permanent -- J: "too busy"
  wrap.appendChild(legend);
  const stars=document.createElement('canvas');
  stars.className='army-stars'; stars.width=W; stars.height=H;
  wrap.appendChild(stars);
  armyStars(stars,W,H);
  /* Compute-field: a faint cyan cell-grid winking under the stage (magicui
     FlickeringGrid, tuned down). Cyan is the ALIVE hue -- the field says the SYSTEM
     is alive, ambiently, the way rack activity lights do. Own canvas so reduced
     motion can kill it wholesale (.army-flick{display:none}). */
  const flick=document.createElement('canvas');
  flick.className='army-stars army-flick'; flick.width=W; flick.height=H;
  wrap.appendChild(flick);
  if(!RM)armyFlicker(flick);
  wrap.appendChild(svg);
  /* Cursor spotlight: one soft violet film that follows the pointer across the stage.
     getScreenCTM maps client px -> viewBox units so the CSS scale can't desync it. */
  const sg2=mk('radialGradient',{id:'spotGrad'});
  sg2.appendChild(mk('stop',{offset:'0%','stop-color':'#8b5cf6','stop-opacity':'.09'}));
  sg2.appendChild(mk('stop',{offset:'100%','stop-color':'#8b5cf6','stop-opacity':'0'}));
  defs.appendChild(sg2);
  const spotC=mk('circle',{r:230,fill:'url(#spotGrad)','pointer-events':'none',
    opacity:0,class:'army-spot'});
  svg.appendChild(spotC);
  svg.addEventListener('pointermove',(e)=>{
    const m=svg.getScreenCTM(); if(!m)return;
    spotC.setAttribute('cx',(e.clientX-m.e)/m.a);
    spotC.setAttribute('cy',(e.clientY-m.f)/m.d);
    spotC.setAttribute('opacity','1');
  });
  svg.addEventListener('pointerleave',()=>spotC.setAttribute('opacity','0'));
  return {wrap,compact,state:{centers,edges,nameToSid,lastSeen,queue:[],raf:null,cursor:''}};
}

function armyStars(canvas,W,H){
  /* Stage backdrop. Deterministic placement (golden-angle scatter, no RNG), two depth
     layers, slow drift + sine twinkle. Self-terminating like every army loop: stops when
     the canvas leaves the document. Reduced motion gets one static paint. Colour = the
     themed --star token (plain colour, so alpha goes via globalAlpha), violet-white fallback. */
  const ctx=canvas.getContext('2d'); if(!ctx)return;
  let starColor='#c8beff';
  try{ const v=getComputedStyle(document.documentElement).getPropertyValue('--star').trim(); if(v)starColor=v; }catch(_){}
  const N=90, dots=[];
  for(let k=0;k<N;k++){
    const deep=k%3!==0;
    dots.push({x:(k*137.508)%W, y:(k*91.7)%H, r:deep?0.8:1.4,
               v:deep?0.006:0.014, tw:(k%17)/17*6.2832});
  }
  let t=0;
  ctx.fillStyle=starColor;
  function frame(){
    if(!canvas.isConnected)return;
    ctx.clearRect(0,0,W,H); t+=1;
    for(const d of dots){
      d.x+=d.v; if(d.x>W+2)d.x=-2;
      const a=0.10+0.16*(0.5+0.5*Math.sin(t*0.008+d.tw));
      ctx.globalAlpha=a; ctx.beginPath(); ctx.arc(d.x,d.y,d.r,0,6.2832); ctx.fill();
    }
    ctx.globalAlpha=1; if(!RM)requestAnimationFrame(frame);
  }
  if(RM){ frame(); return; }
  requestAnimationFrame(frame);
}

function armyFlicker(canvas){
  /* magicui FlickeringGrid, retuned for a backdrop (theirs is a hero): 3px cells on a
     12px pitch, max alpha .09. DETERMINISTIC winks -- each cell pulses on its own
     hashed phase/speed (sin^8 gives a short blink in a long dark period), no RNG, so
     two renders of the same second look the same and screenshot diffs stay honest.
     30fps cap; self-terminating like every army loop; skips hidden tabs. Colour = the
     themed --beam token, resolved once (alive-cyan fallback). */
  const ctx=canvas.getContext('2d'); if(!ctx)return;
  let beamColor='#67e8f9';
  try{ const v=getComputedStyle(document.documentElement).getPropertyValue('--beam').trim(); if(v)beamColor=v; }catch(_){}
  const STEP=12,SQ=3;
  let even=false;
  function frame(){
    if(!canvas.isConnected)return;
    requestAnimationFrame(frame);
    even=!even; if(even||document.hidden)return;   // 30fps + tab-hidden skip
    const W=canvas.width,H=canvas.height,cols=Math.ceil(W/STEP),rows=Math.ceil(H/STEP);
    const t=performance.now()/1000;
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle=beamColor;   // the ALIVE cyan family, themed via --beam
    for(let cx=0;cx<cols;cx++)for(let cy=0;cy<rows;cy++){
      const h=Math.sin(cx*127.1+cy*311.7)*43758.5453;
      const ph=(h-Math.floor(h))*6.2832, sp=.25+((cx*7+cy*13)%10)/22;
      const s=Math.sin(t*sp+ph);
      if(s<=0)continue;
      const a=Math.pow(s,8)*.09;
      if(a<.008)continue;
      ctx.globalAlpha=a;
      ctx.fillRect(cx*STEP,cy*STEP,SQ,SQ);
    }
    ctx.globalAlpha=1;
  }
  requestAnimationFrame(frame);
}

/* ── Text fitting for SVG ──────────────────────────────────────────────────────
   SVG <text> does not wrap or ellipsize, so a label that overflows silently paints
   across its neighbour. These estimate advance width from the font size (the page
   ships no webfont, so the system stack's metrics are stable enough for a cap) and
   cut on a word boundary. Deliberately conservative: under-filling leaves a gap,
   over-filling corrupts the card. */
function armyTextW(str,size,mono){ return String(str||'').length*size*(mono?0.60:0.52); }
function fitTxt(str,px,size,mono){
  const s=String(str||''); if(armyTextW(s,size,mono)<=px)return s;
  const per=size*(mono?0.60:0.52), cap=Math.max(1,Math.floor(px/per)-1);
  const cut=s.slice(0,cap);
  const sp=cut.lastIndexOf(' ');
  return (sp>cap*0.6?cut.slice(0,sp):cut).replace(/[ ,;:.\-]+$/,'')+'…';
}

/* What KIND of thing is this box? J has asked three times. "interactive" +
   "claude-desktop" is how the session registry says it, which answers the machine's
   question, not his: he wants to know whether HE opened it or the rig spawned it. */
function armyKindWord(s){
  const ep=String(s.entrypoint||''), k=String(s.kind||'');
  if(/desktop|cli|vscode|jetbrains|terminal/i.test(ep)||k==='interactive')return 'your window';
  if(/cron|schedule|task/i.test(ep+k))return 'scheduled task';
  if(/sdk|headless|api/i.test(ep+k))return 'headless run';
  return ep||k||'session';
}

/* "general-purpose"/"workflow-subagent" are the spawn API's words. The row has ~120px
   for type AND model, and the full type name ate the model -- so J could not see whether
   an agent was on opus or haiku, which is the part that costs him money. */
function armyTypeWord(t){
  const s=String(t||'agent');
  if(s==='general-purpose')return 'general';
  if(s==='workflow-subagent')return 'workflow';
  return s;
}

/* A worker's task is the FULL prompt -- hundreds of characters that usually open with
   a role preamble ("You are a design researcher. Deep-research GitHub repos ..."). The
   preamble is identical across agents and carries no information about THIS one, so it
   is dropped and the real instruction shown. The untouched prompt stays in the drawer;
   this is a label, never a substitute for the source. */
function armyPurpose(task){
  let t=String(task||'').replace(/\s+/g,' ').trim();
  const pre=t.match(/^You are [^.]{0,80}\.\s+/i);
  if(pre&&t.length-pre[0].length>24)t=t.slice(pre[0].length);
  return t||'(no task recorded)';
}

/* round-2 review (major): the hero row printed armyPurpose() verbatim -- full CLI
   invocations ('after-r2 --views command,overview,cards,journal --sizes...') and
   prompts truncated mid-word by fitTxt's char-level fallback ('...design-taste/re...')
   -- "the opposite of visual not textual". A short verb-phrase gist by default; the
   untouched task/prompt is still one click away (armySessionDrawer/armyWorkerDrawer)
   and still sits in the row's <title> tooltip, so nothing is lost, only deferred. */
function armyGist(task){
  const t=armyPurpose(task);
  // CLI-shaped tasks ("tool --flag a --flag b ...") read as command noise on a
  // glance surface -- same reduction armyHumanAct already applies to a pulse
  // event's "Ran: ..." detail, applied here to a task string instead.
  const cli=t.match(/^(\S+)\s+--?\S/);
  const gist=cli?('Running '+cli[1].replace(/^\.?\/*/,'').split(/[\\/]/).pop()):t;
  const CAP=52;
  if(gist.length<=CAP)return gist;
  // grow word-by-word so the cut always lands on a space, never mid-word/mid-path
  const words=gist.split(' ');
  let out='';
  for(const w of words){
    const next=out?out+' '+w:w;
    if(next.length>CAP)break;
    out=next;
  }
  return (out||gist.slice(0,CAP)).replace(/[ ,;:.\-]+$/,'')+'…';
}

/* THE ANSWER BAR. J has asked three times what he is looking at. The page could only
   answer by being read tile-by-tile; this says it in one sentence, at the first place
   the eye lands, before he clicks anything.

   Present tense comes from worker_active ONLY. worker_count is a lifetime count of
   transcript files and may be spoken of strictly in the past -- that distinction is the
   whole reason the old "8 workers +43" was a lie. */
function armyAnswerBar(a,live){
  const S=a.sessions||[];
  const sum=(f)=>S.reduce((n,s)=>n+(s[f]||0),0);
  const liveAg=sum('worker_active'), everAg=sum('worker_count');
  const working=S.filter(s=>s.activity==='active').length;
  const idle=S.filter(s=>s.activity==='idle').length;
  const closed=S.filter(s=>s.activity==='stale'||s.activity==='unknown').length;
  const orcLive=(a.orchestrator||{}).worker_active||0;
  const where=!liveAg?'':(orcLive===liveAg?' — <b>all in this window</b>'
    :' — <b>'+orcLive+' in this window</b>');
  const head=liveAg
    ? '<b class="live">'+liveAg+'</b> agent'+(liveAg===1?'':'s')+' running right now'+where
    : '<b>Nothing</b> is running right now';
  const sep='<s> · </s>';
  const bar=el('div','ansbar');
  bar.appendChild(el('p','ansbar__say',head+sep+
    '<b>'+working+'</b> chat'+(working===1?'':'s')+' working'+sep+
    '<b>'+idle+'</b> waiting for you'+sep+
    '<b>'+closed+'</b> closed'+
    (everAg?sep+'<b>'+everAg+'</b> agents finished earlier':'')));
  bar.appendChild(el('div','ansbar__key',
    '<span class="k"><i class="ag__dot" data-s="live"></i>running</span>'+
    '<span class="k"><i class="ag__dot" data-s="done"></i>finished</span>'+
    '<span class="k">boxes are chat windows — agents live <em>inside</em> them</span>'));
  /* FRESHNESS, honestly. A page opened from file:// is a snapshot, and so is a served
     page whose payload has aged out: "running right now" is only supportable while the
     data is fresh. generated_epoch shares worker.last_write's clock; built_at_et is an
     ET wall-clock string on a Mountain-time box, so parsing THAT would be 2h wrong. */
  const ageS=a.generated_epoch?(Date.now()/1000-a.generated_epoch):Infinity;
  const snap=!live||ageS>120;
  bar.appendChild(el('span','chip'+(snap?'':' ok'),'<i class="dot"></i>'+
    (snap?'SNAPSHOT '+esc(String(a.generated_at||'').slice(11,16)):'LIVE')));
  if(snap)bar.setAttribute('title','Taken '+esc(String(a.generated_at||'unknown'))+
    ' — counts describe that moment, not this one.');
  return bar;
}

function armyDotColour(s){
  /* ALIVE is cyan (--st-live), its own hue. Green is reserved for P&L, and quiet is not
     degraded -- that was always the intent, and the code did the opposite.

     THE BUG (verified 2026-08-30): the dot keyed off `lastSeen`, which is built purely
     from pulses[], and ALL 60 pulse rows belong to the orchestrator -- which is the
     command strip and has no tile. So lastSeen held exactly one key that no tile could
     ever match, and EVERY peer tile fell through to amber: a "something is degraded"
     dot sitting beside its own grey "idle" text, on every card, forever. Red was worse
     still -- a dead process is not a loss, and red belongs to P&L.

     The fix is to colour the dot from the SAME fields as the words next to it, so the
     two can never disagree again. */
  if(!s.alive)return'var(--tx-4)';                 // process gone: dim, never red
  if((s.worker_active||0)>0)return'var(--st-live)';
  if(s.activity==='active')return'var(--st-live)';
  if(s.activity==='idle')return'var(--tx-3)';
  return'var(--tx-4)';
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
  if(dot&&s)dot.setAttribute('fill',armyDotColour(s));
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

/* ---------- cards rail: DELETED (Quiet Command redesign, 2026-09-03) ----------
   J's "cards in a column, click to promote onto the canvas" rail -- the right-hand list,
   the promoted panel inside the stage, and the view-transition morph between them -- is
   gone. Action cards now live as rows in Command's "Needs you" group
   (gamma_cockpit_cards_js.py's vCommand path), Fire button on the row itself.
   armyShowStale survives: the stale-chat toggle is still read by armySvg() above. */
let armyShowStale=false;

/* ---------- armyMount: the stage, self-contained ----------
   Everything vArmy() used to assemble inline (armySvg's wrap -- itself already bundling
   the SVG, stars/flicker canvases, legend and the controls row above -- plus the hidden
   diagnostic ledger, armyState wiring, the baked-pulse replay and the live poll) now lives
   here so any host (Command's stage band, or this file's own fallback below) can mount the
   whole stage with one call. Keeps ids #armystage and #armyledger. */
function armyMount(host){
  const a=D.army||{sessions:[],workers:[],pulses:[],orchestrator:null,source:{}};
  const live=location.protocol!=='file:';
  const built=armySvg(a);
  built.wrap.id='armystage';
  built.wrap.style.cssText='flex:1;min-height:0;display:flex;flex-direction:column;position:relative';
  host.appendChild(built.wrap);
  /* .stage (the host's own parent, cmdStage()) carries the max-height cap --
     toggled here rather than baked into that div, since only armySvg() knows
     the live roster size (spec item 1, first-viewport density). */
  try{ if(host.parentElement&&host.parentElement.classList){
    host.parentElement.classList.toggle('stage--compact',!!built.compact);
    host.parentElement.classList.add('gc-panel');   // Glow panel + dot texture (.stage.gc-panel only)
  } }catch(_){}

  // Diagnostic event ledger -- HIDDEN by default now that chat owns the bottom panel
  // (chat lives in #chatdock, mounted by the runtime, not here). Still populated by
  // armyApplyRow/armyLedgerRow so the data exists for a future disclosure affordance.
  const ledger=el('div','armyledger'); ledger.id='armyledger'; ledger.style.display='none';
  host.appendChild(ledger);
  host.appendChild(srcRow([a.source&&a.source.pulse,a.source&&a.source.sessions].filter(Boolean)));
  if(a.error)host.appendChild(el('div','micro warnc','army payload error: '+esc(a.error)));

  armyState=built.state;
  (a.pulses||[]).forEach(r=>armyApplyRow(r,false));
  armyState.cursor=(a.pulses&&a.pulses.length)?a.pulses[a.pulses.length-1].ts:'';
  if(live)armyPoll();
}

function vArmy(h){
  /* The Army stage now lives inside Command (spec sec 3 band 3); this route is an alias
     that mounts Command and scrolls its stage into view -- same pattern as the other old
     view ids (vOverview etc. in gamma_cockpit_views_js.py). Feature-detected: until
     gamma_cockpit_command_js.py's vCommand() lands, fall back to mounting the stage
     directly here so the page never throws on a missing function. */
  if(typeof vCommand==='function'){
    vCommand(h);
    try{
      const sh=document.getElementById('stagehost');
      if(sh)sh.scrollIntoView({behavior:RM?'auto':'smooth'});
    }catch(_){}
    return;
  }
  const a=D.army||{sessions:[],workers:[],pulses:[],orchestrator:null,source:{}};
  const live=location.protocol!=='file:';
  /* The topbar already says "Army" -- repeating it as an h2 directly underneath was the
     view introducing itself twice. One slim status line carries what is actually new. */
  h.appendChild(armyAnswerBar(a,live));
  const card=el('div','card');
  card.style.cssText='display:flex;flex-direction:column;gap:12px;min-height:520px';
  armyMount(card);
  h.appendChild(card);
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
      h3.className='gc-eyebrow';   // the shared Glow Command section-label class
      h3.style.cssText='margin:var(--s6) 0 var(--s3);color:var(--tx-3)';
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

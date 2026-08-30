"""gamma_cockpit_chat_js.py - the cockpit's orchestrator chat pane.

J: "the terminal looking thing at the bottom thats printing out lines needs to just be the
main claude opus orchestrator window that i can type into and its an actual claude chat just
like any other powershell window i would open claude in... i need this all on one page."

WHAT THIS IS: a real Claude session driven through the companion's Agent SDK path -- the same
query() the card-fire path uses, the same claude_code preset, the same soul appended to the
SYSTEM prompt, the same canUseTool guard and halt flag. `resume` carries the sessionId between
turns, so it is a continuous conversation rather than a queue of amnesiac one-shots.

WHAT THIS IS NOT, stated here because the UI must never imply otherwise: it is NOT attached to
one of J's open Desktop windows. A web page cannot join another process's session. It is its
own session -- and it appears in the Army view as its own box, which is the thing actually
asked for: everything on one page.

Structure follows the block model rather than a character stream: every turn is an object in
an array with its own id and status, rendered as one node. Appending to a single growing
string is what makes a "terminal" feel like a log tail instead of a conversation.
"""
from __future__ import annotations

CHAT_JS = r"""
/* ---------- COCKPIT CHAT: a real orchestrator session, in the page ---------- */
let chatState={turns:[],session:null,busy:false,es:null,pinned:true,model:'opus'};

function chatEl(){ return document.getElementById('chatbody'); }

/* Autoscroll that respects intent. The documented trap (hit repeatedly in Vercel's own
   ai-chatbot): a programmatic scrollTo fires the SAME scroll event a human scroll does, so
   naive code reads its own action as "the user scrolled away" and then stops following. We
   therefore never listen to `scroll` for intent -- only `wheel` and `touchmove`, which only
   a person can produce. */
function chatWatchScroll(box){
  const unpin=()=>{ chatState.pinned=(box.scrollHeight-box.scrollTop-box.clientHeight)<28; };
  box.addEventListener('wheel',unpin,{passive:true});
  box.addEventListener('touchmove',unpin,{passive:true});
}
function chatScroll(box){ if(chatState.pinned)box.scrollTop=box.scrollHeight; }

function chatTurnNode(t){
  const wrap=el('div','chatturn chatturn-'+t.role);
  const who=el('div','chatwho');
  who.textContent=t.role==='user'?'You':('Gamma · '+(t.model||chatState.model));
  wrap.appendChild(who);
  const body=el('div','chattext'); body.id='chattext-'+t.id;
  body.textContent=t.text||'';
  wrap.appendChild(body);
  if(t.role==='gamma'){
    const steps=el('div','chatsteps'); steps.id='chatsteps-'+t.id;
    wrap.appendChild(steps);
  }
  return wrap;
}

function chatPush(role,text,model){
  const em=document.getElementById('chatempty'); if(em)em.remove();
  const t={id:'t'+Date.now()+Math.random().toString(36).slice(2,6),role,text:text||'',model,status:'live'};
  chatState.turns.push(t);
  const box=chatEl(); if(box){ box.appendChild(chatTurnNode(t)); chatScroll(box); }
  return t;
}

/* Streamed text is buffered and flushed once per animation frame. One DOM write per token on
   a fast stream causes visible jank; one per frame does not, and the user cannot tell. */
/* setTimeout, NOT requestAnimationFrame: RAF never fires in a hidden/backgrounded tab, so a
   pure-RAF flush froze the reply text whenever the pane was not visible -- found 2026-08-30
   when every completed turn read back with EMPTY text while the tab was hidden. 16ms keeps
   the one-write-per-tick batching that was the point of the buffer. */
let chatBuf={}, chatTick=null;
function chatFlush(){
  chatTick=null;
  for(const id in chatBuf){
    const node=document.getElementById('chattext-'+id);
    if(node)node.textContent+=chatBuf[id];
  }
  chatBuf={};
  const box=chatEl(); if(box)chatScroll(box);
}
function chatAppendText(turnId,chunk){
  chatBuf[turnId]=(chatBuf[turnId]||'')+chunk;
  if(!chatTick)chatTick=setTimeout(chatFlush,16);
}
function chatAppendStep(turnId,label,cls){
  const host=document.getElementById('chatsteps-'+turnId);
  if(!host)return;
  const row=el('div','chatstep'+(cls?' '+cls:'')); row.textContent=label;
  host.appendChild(row);
  const box=chatEl(); if(box)chatScroll(box);
}

function chatSetBusy(on){
  chatState.busy=on;
  const send=document.getElementById('chatsend');
  const ta=document.getElementById('chatinput');
  if(send){ send.disabled=on; send.textContent=on?'Working…':'Send'; }
  if(ta)ta.disabled=on;
}

function chatStop(){
  if(chatState.es){ try{chatState.es.close()}catch(_){ } chatState.es=null; }
  chatSetBusy(false);
}

function chatSend(){
  const ta=document.getElementById('chatinput');
  if(!ta||chatState.busy)return;
  const msg=(ta.value||'').trim();
  if(!msg)return;
  if(location.protocol==='file:'){
    // Schemeless on purpose: the self-contained guard greps the emitted page for URL
    // schemes to catch real external references, and this comment SHIPS in the page --
    // naming the scheme here re-tripped the guard the fix was for. 127.0.0.1:4317 is
    // just as pasteable.
    chatPush('gamma','This page was opened from a file, so it cannot reach the companion. '+
      'Open 127.0.0.1:4317/cockpit.html to chat.');
    return;
  }
  ta.value=''; ta.style.height='auto';
  chatPush('user',msg);
  const turn=chatPush('gamma','',chatState.model);
  chatSetBusy(true);

  fetch('/api/orchestrator-chat',{
    method:'POST',
    headers:{'content-type':'application/json','x-gamma-token':cardsGammaToken()},
    body:JSON.stringify({message:msg,model:chatState.model,resume:chatState.session||undefined}),
  }).then(r=>r.json()).then(j=>{
    if(!j||j.ok===false){
      chatAppendStep(turn.id,'✕ '+((j&&j.error)||'failed'),'bad');
      chatSetBusy(false); return;
    }
    const url='/api/ask-stream?id='+encodeURIComponent(j.ask_id)+'&tok='+encodeURIComponent(j.stream_token);
    let es=null;
    try{ es=new EventSource(url); }catch(e){ chatAppendStep(turn.id,'✕ stream unavailable','bad'); chatSetBusy(false); return; }
    chatState.es=es;
    es.onmessage=(ev)=>{
      let d=null; try{ d=JSON.parse(ev.data); }catch(_){ return; }
      if(!d||!d.step)return;
      if(d.step==='session'&&d.sessionId){
        // Captured so the NEXT turn resumes this session instead of starting cold.
        chatState.session=d.sessionId;
        chatAppendStep(turn.id,(j.resumed?'↻ resumed':'● session')+' '+String(d.sessionId).slice(0,8),'dim');
      } else if(d.step==='delta'){
        turn.sawDelta=true;
        chatAppendText(turn.id,d.text||'');
      } else if(d.step==='text'){
        // The server emits BOTH streamed deltas and the final assembled text block for the
        // same words; rendering both doubled every reply ("chat workschat works"). Deltas
        // win when they streamed; the text frame is the fallback when they did not.
        if(!turn.sawDelta)chatAppendText(turn.id,d.text||'');
      } else if(d.step==='thinking'){
        chatAppendStep(turn.id,'thinking…','dim');
      } else if(d.step==='tool'||d.step==='tool_start'){
        chatAppendStep(turn.id,'▸ '+(d.label||d.name||'tool'));
      } else if(d.step==='tool_result'){
        chatAppendStep(turn.id,'   '+(d.preview||(d.ok?'ok':'error')),'dim');
      } else if(d.step==='result'){
        chatAppendStep(turn.id,(d.ok===false?'✕ ':'✓ ')+(d.summary||''),d.ok===false?'bad':'ok');
        chatStop();
      }
    };
    es.onerror=()=>{ /* EventSource retries on its own; the durable feed replays on reconnect */ };
  }).catch(()=>{ chatAppendStep(turn.id,'✕ network error','bad'); chatSetBusy(false); });
}

function chatPane(){
  const wrap=el('div','chatpane');

  const head=el('div','chathead');
  const title=el('div',null,'<b>Orchestrator</b> <span class="dim">— a real Claude session, in this page</span>');
  head.appendChild(title);
  const sel=document.createElement('select');
  sel.id='chatmodel';
  ['opus','sonnet','haiku'].forEach(m=>{
    const o=document.createElement('option'); o.value=m; o.textContent=m; if(m===chatState.model)o.selected=true;
    sel.appendChild(o);
  });
  sel.onchange=()=>{
    chatState.model=sel.value;
    // Switching model starts a NEW session: resume ties a conversation to the model it began
    // on, and silently resuming a different one would be a lie about continuity.
    chatState.session=null;
    chatAppendStep((chatState.turns[chatState.turns.length-1]||{}).id||'','model → '+sel.value+' (new session)','dim');
  };
  head.appendChild(sel);
  wrap.appendChild(head);

  const box=el('div','chatbody'); box.id='chatbody';
  /* Empty state: a black void reads as broken. Say what this is and hand J three one-click
     starters; each chip fills the input so the first message costs one click + Enter. */
  const empty=el('div','chatempty'); empty.id='chatempty';
  empty.appendChild(el('div','chatempty-t','Talk to the orchestrator'));
  empty.appendChild(el('div','chatempty-s','A real Claude session that runs in this page and remembers the conversation.'));
  const sug=el('div','chatempty-chips');
  ['What changed while I was away?','Status of the September freeze?','What should I look at first?']
    .forEach(t=>{
      const c=document.createElement('button'); c.type='button'; c.className='sugchip'; c.textContent=t;
      c.onclick=()=>{ const ta=document.getElementById('chatinput'); if(ta){ta.value=t; ta.focus();} };
      sug.appendChild(c);
    });
  empty.appendChild(sug);
  box.appendChild(empty);
  wrap.appendChild(box);
  chatWatchScroll(box);

  const foot=el('div','chatfoot');
  const ta=document.createElement('textarea');
  ta.id='chatinput'; ta.rows=1; ta.placeholder='Ask the orchestrator…  (Enter to send, Shift+Enter for a newline)';
  ta.oninput=()=>{ ta.style.height='auto'; ta.style.height=Math.min(160,ta.scrollHeight)+'px'; };
  ta.onkeydown=(e)=>{ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); chatSend(); } };
  foot.appendChild(ta);
  const send=document.createElement('button');
  send.id='chatsend'; send.type='button'; send.textContent='Send'; send.onclick=chatSend;
  foot.appendChild(send);
  wrap.appendChild(foot);

  const note=el('div','micro chatnote');
  note.textContent=location.protocol==='file:'
    ? 'Snapshot mode — open 127.0.0.1:4317/cockpit.html to chat.'
    : 'Its own session, not one of your Desktop windows. It appears above as its own box.';
  wrap.appendChild(note);
  return wrap;
}
"""

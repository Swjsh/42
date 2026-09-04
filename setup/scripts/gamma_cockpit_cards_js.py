"""gamma_cockpit_cards_js.py - the Action Cards view's client-side code.

Split out of gamma_cockpit_views_js.py at the repo's 800-line ceiling, same
reasoning as gamma_cockpit_army_js.py. Concatenated onto VIEWS_JS at import
time, so it shares every helper defined in gamma_cockpit_js.py's runtime (el,
esc, RM, ageEl, srcRow, openDrawer, closeDrawer, $, ...).

Reads payload["cards"] (built by setup/scripts/gamma_cockpit_cards.py, which
ALSO wrote automation/state/action-cards.json -- the file server.js treats as
authoritative over whatever a client POSTs, see that module's docstring).

THE RTH GATE HERE IS COSMETIC, NOT THE ENFORCEMENT (spec sec 4 security note
2). The load-bearing check is server-side in gamma-companion/server.js's
POST /api/approve, which shells out to setup/scripts/et_clock.py -- the ONE
DST-aware ET source on this box. This file's rthNowClient() is a same-answer,
independent computation (Intl with an explicit IANA zone, not a system-TZ
read, so it does NOT carry the "Bash TZ=America/New_York returns UTC here"
bug) used only to greyed-out the button promptly; a stale client guess that
briefly under- or over-shows the disabled state costs nothing, because the
server refuses the fire either way.
"""
from __future__ import annotations

CARDS_JS = r"""
/* ---------- CARDS: ranked, deterministic, fire-or-read ---------- */
function rthNowClient(){
  try{
    const fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',
      weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false});
    const parts={}; fmt.formatToParts(new Date()).forEach(p=>parts[p.type]=p.value);
    const wd=parts.weekday, hhmm=parseInt(parts.hour,10)*100+parseInt(parts.minute,10);
    if(wd==='Sat'||wd==='Sun')return false;
    return hhmm>=930&&hhmm<1555;
  }catch(e){ return true; }  // can't tell -> assume RTH, the safe (disabled) direction
}

function cardsGammaToken(){
  const m=document.querySelector('meta[name="gamma-token"]');
  return m?m.content:'';
}

function cardFireLabel(rth){ return rth?'Fire, disabled 09:30-15:55 ET':'Fire'; }

function paintCardButtons(){
  const rth=rthNowClient();
  $$('.fire-btn').forEach(b=>{
    if(b.dataset.state==='pending'||b.dataset.state==='done')return;  // mid-flight, leave alone
    b.disabled=rth; b.textContent=cardFireLabel(rth);
  });
}
setInterval(function(){ if($('#cardsview'))paintCardButtons(); },30000);

function vCards(h){
  /* Action cards now render as rows in Command's "Needs you" group (spec sec 5, 5a) --
     this route is an alias that mounts Command and scrolls that group into view, same
     pattern as the other retired view ids. Feature-detected: until
     gamma_cockpit_command_js.py's vCommand() lands, fall back to the old card-grid markup
     below so the page never throws on a missing function. */
  if(typeof vCommand==='function'){
    vCommand(h);
    try{
      const g=document.querySelector('.tgroup');
      if(g)g.scrollIntoView({behavior:RM?'auto':'smooth'});
    }catch(_){}
    return;
  }
  const c=D.cards||{cards:[],rth_now:false,quiet_active:false,legend:'',source:{}};
  const live=location.protocol!=='file:';
  const rth=rthNowClient();
  h.appendChild(el('div','shead',
    `<h2>Action cards</h2><span class="dim">${live?'LIVE':'SNAPSHOT'} · deterministic, no LLM`+
    (c.quiet_active?' · quiet mode active — held-down producers render as quiesced':'')+`</span>`));
  const host=el('div','stack'); host.id='cardsview';

  if(!(c.cards||[]).length){
    host.appendChild(el('div','card','<div class="mut">Nothing needs firing. Every ranked source (engine-health, '
      +'STATUS.md, task_scorer, the active goal, unattended-health) is clear or quiesced.</div>'));
  }
  (c.cards||[]).forEach(card=>{
    const cd=el('div','card actioncard');
    const top=el('div','row wrap');
    top.innerHTML=`<span class="chip">#${card.rank}</span><span style="font-weight:600">${esc(card.title)}</span>`+
      (card.gated?'<span class="chip warn"><i class="dot"></i>J-GATED</span>':'');
    cd.appendChild(top);
    const why=el('div'); why.style.marginTop='var(--s3)';
    (card.why||[]).forEach(w=>why.appendChild(el('div','micro','· '+esc(w))));
    cd.appendChild(why);
    const meta=el('div','row wrap'); meta.style.marginTop='var(--s4)';
    meta.appendChild(el('span','chip',esc(card.model||'sonnet')));
    cd.appendChild(meta);
    cd.appendChild(srcRow([{path:card.source_path,age_h:card.source_age_h}]));

    const bar=el('div','row wrap'); bar.style.marginTop='var(--s5)';
    if(!live){
      bar.appendChild(el('div','micro','Open via the companion (127.0.0.1:4317) to fire — a file:// snapshot cannot reach it.'));
    }else{
      const btn=el('button','fire-btn',cardFireLabel(rth));
      btn.disabled=rth;
      btn.dataset.state='idle';
      btn.style.cssText='background:var(--acc-dim);color:var(--tx-1);border:1px solid var(--acc);'+
        'border-radius:var(--r-md);padding:8px 16px;cursor:pointer;font:600 13px var(--font)';
      const msg=el('span','micro'); msg.style.marginLeft='var(--s4)';
      btn.onclick=()=>fireCard(card,btn,msg);
      bar.append(btn,msg);
    }
    cd.appendChild(bar);
    host.appendChild(cd);
  });
  const legend=el('div','micro',esc(c.legend||'')); legend.style.marginTop='var(--s5)'; host.appendChild(legend);
  host.appendChild(srcRow(Object.values(c.source||{})));
  if(c.error)host.appendChild(el('div','micro warnc','cards payload error: '+esc(c.error)));
  h.appendChild(host);
}

function fireCard(card,btn,msg){
  if(rthNowClient()){ msg.textContent='Fire is disabled 09:30–15:55 ET.'; msg.className='micro warnc'; return; }
  btn.disabled=true; btn.dataset.state='pending'; btn.textContent='Firing…'; msg.textContent=''; msg.className='micro';
  fetch('/api/approve',{
    method:'POST',
    headers:{'content-type':'application/json','x-gamma-token':cardsGammaToken()},
    body:JSON.stringify({id:card.id,decision:'approve',
      action:{type:'escalate',model:card.model,task:card.prompt}}),
  }).then(r=>r.json()).then(j=>{
    if(!j||j.ok===false){
      btn.dataset.state='idle'; btn.disabled=rthNowClient(); btn.textContent=cardFireLabel(rthNowClient());
      msg.textContent=(j&&j.error)||'fire failed'; msg.className='micro warnc';
      return;
    }
    if(!j.escalated){
      // resolveApproval says this id already won its decision (a double-tap) --
      // exactly the idempotency guard server.js's own comment names (r.already).
      btn.dataset.state='done'; btn.textContent='Already fired';
      msg.textContent='This card was already actioned — no second session spawned.'; msg.className='micro';
      return;
    }
    btn.dataset.state='done'; btn.textContent='Fired — watching…';
    msg.textContent='ask '+j.escalated.slice(0,12);
    if(j.stream_token)cardsAskDrawer(card.title,'/api/ask-stream?id='+encodeURIComponent(j.escalated)+
      '&tok='+encodeURIComponent(j.stream_token));
  }).catch(()=>{
    btn.dataset.state='idle'; btn.disabled=rthNowClient(); btn.textContent=cardFireLabel(rthNowClient());
    msg.textContent='network error'; msg.className='micro warnc';
  });
}

/* One line per SSE frame -- humanizes the same {step,...} shape escalate.js
   emits for the companion's own chat transcript, so this drawer reads the
   real, live build instead of a synthetic status string. */
function askFrameLine(d){
  if(!d||!d.step)return '';
  if(d.step==='queued')return 'Queued: '+(d.task||'')+' ('+(d.model||'')+')';
  if(d.step==='session')return 'Session started ('+(d.model||'')+')';
  if(d.step==='tool_start'||d.step==='tool')return (d.label||d.name||'tool')+'…';
  if(d.step==='tool_result')return '  -> '+(d.preview||(d.ok?'ok':'error'));
  if(d.step==='text'||d.step==='delta')return d.text||'';
  if(d.step==='thinking')return d.text||'';
  if(d.step==='result')return (d.ok===false?'FAILED: ':'DONE: ')+(d.summary||'');
  return '';
}
function cardsAskDrawer(title,url){
  let es=null;
  try{ es=new EventSource(url); }catch(e){ /* SSE unsupported/blocked -- drawer still opens, just static */ }
  openDrawer(title+' — live build',b=>{
    const pre=el('div','askstream'); pre.id='askstreambody';
    b.appendChild(pre);
    const append=(line)=>{ if(!line)return; const row=el('div',null,esc(line)); pre.appendChild(row);
      pre.scrollTop=pre.scrollHeight; };
    append('(connecting…)');
    const stopEs=()=>{ if(es){ try{es.close()}catch(_){} es=null; } };
    if(es){
      es.onmessage=(ev)=>{ try{ append(askFrameLine(JSON.parse(ev.data))); }catch(_){ /* ignore one bad frame */ } };
      es.onerror=()=>{ /* EventSource auto-retries; the durable feed replay on reconnect covers gaps */ };
    }
    const origDclose=$('#dclose').onclick, origScrim=$('#scrim').onclick;
    $('#dclose').onclick=()=>{ stopEs(); closeDrawer(); $('#dclose').onclick=origDclose; $('#scrim').onclick=origScrim; };
    $('#scrim').onclick=()=>{ stopEs(); closeDrawer(); $('#dclose').onclick=origDclose; $('#scrim').onclick=origScrim; };
  });
}
"""

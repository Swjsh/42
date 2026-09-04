"""gamma_cockpit_tiles_js.py - the tile row component + graphics for the cockpit.

Workstream C (Tile system). Owns ONLY this module. Held as a Python string, same
convention as gamma_cockpit_js.py, so the whole cockpit stays a bundler-free
build. Vanilla ES2020, no network calls, no external libraries beyond what the
vendor bundle already inlines (countUp, optionally). Must run from a file://
URL and must never throw even if a sibling module (vendor icons, new payload
keys) is not wired yet - every external symbol this file touches is either
already present in gamma_cockpit_js.py (el, esc, agoOf, agoTxt, paintAge, RM,
openDrawer - all verified present in that file this session) or is
feature-detected before use (the vendor icon() helper, window.countUp).

TILE SPEC CONTRACT (agreed in writing with WS-D before either wrote rendering
code; this is the literal shape `tileRow()` accepts):

    {
      "id": "tile-gate",
      "icon": "gauge",
      "title": "Go-live gate",
      "gfx": "<svg viewBox=\"0 0 160 24\">...</svg>",
      "verdict": "red",
      "say": "<i class=\"vd\"></i>RED. PF CI-lower <b>0.42</b> vs <b>1.0</b>",
      "src": {"path": "analysis/go-live-gate.json", "stamp": "2026-09-03T14:43:34"},
      "fresh_h": 24,
      "body": null,
      "act": null
    }

API surface (exact names other builders code against):
  tileRow(spec) -> HTMLDetailsElement
  groupRows({id,title,rows}) -> HTMLDivElement
  tileOpen(id, {scroll}) -> void
  tileFigure(node, value, fmt) -> void
  tilesKey(e) -> bool
  tilesInit() -> void
  gfxGauge(v,bar,min,max) / gfxMeter(n,of) / gfxSpark(vals,{pnl}) / gfxHeat(cells)
  gfxRings(arms) / gfxFunnel(stages) / gfxDots(states) / gfxBars(vals)
  gfxRingBig(n,of)
  gfxDemo()

INVARIANT: "if it cannot be drawn it is not a tile." Every gfx* function returns
the empty string when its input is null/empty/degenerate - callers then render
an empty graphic slot rather than a fabricated one. `verdict==='off'` always
renders "NO DATA, looked for <path>" and an empty graphic, regardless of what a
caller passed in gfx, so a payload-builder bug can never fake a graphic.
"""
from __future__ import annotations

TILES_JS = r"""
/* ============================ tiles: state ============================ */
/* CAN_INTERP: true when the browser supports the CSS interpolate-size primary
   expand path (WS-A's ::details-content rule). When false, or when the URL
   carries ?nointerp=1 (WS-C's own forced-fallback test hook), this module
   drives the open/close animation itself via WAAPI instead of relying on the
   CSS-only path. */
function tilesSupportsInterp(){
  try{
    if(/[?&]nointerp=1(&|$)/.test(location.search))return false;
    return !!(window.CSS&&CSS.supports&&CSS.supports('interpolate-size','allow-keywords'));
  }catch(_){return false;}
}
const CAN_INTERP=tilesSupportsInterp();

function tilesSafeIc(name){
  try{ if(typeof ic==='function')return ic(name); }catch(_){}
  return '';
}
function tilesBaseName(p){
  if(!p)return '';
  const parts=String(p).split(/[\\/]/);
  return parts[parts.length-1];
}
function tilesDotColor(state){
  const k=String(state||'').toLowerCase();
  if(k==='green'||k==='ok'||k==='live'||k==='gain')return'var(--dot-green)';
  if(k==='red'||k==='bad'||k==='loss')return'var(--dot-red)';
  if(k==='amber'||k==='warn'||k==='yellow'||k==='caution')return'var(--dot-amber)';
  return'var(--dot-off)';
}

/* ---------- localStorage: open rows + collapsed groups (both try/catch) ---------- */
function tilesLoadOpen(){
  try{return JSON.parse(localStorage.getItem('gamma-open')||'[]');}catch(_){return[];}
}
function tilesSaveOpen(list){
  try{localStorage.setItem('gamma-open',JSON.stringify(list));}catch(_){}
}
function tilesPersistOpen(id,isOpen){
  if(!id)return;
  const list=tilesLoadOpen();
  const idx=list.indexOf(id);
  if(isOpen&&idx===-1)list.push(id);
  if(!isOpen&&idx!==-1)list.splice(idx,1);
  tilesSaveOpen(list);
}
function tilesLoadGroups(){
  try{return JSON.parse(localStorage.getItem('gamma-groups')||'{}');}catch(_){return{};}
}
function tilesGroupCollapsed(id){
  if(!id)return false;
  return !!tilesLoadGroups()[id];
}
function tilesSetGroupCollapsed(id,collapsed){
  if(!id)return;
  try{
    const st=tilesLoadGroups();
    if(collapsed)st[id]=true; else delete st[id];
    localStorage.setItem('gamma-groups',JSON.stringify(st));
  }catch(_){}
}

/* ============================ tileRow ============================ */
/* The producers module (gamma_cockpit_producers_js.py) was written in parallel
   against a near-identical spelling of this contract: `graphic` for `gfx`,
   `src.last_write` / `src.freshH` for `src.stamp` / `fresh_h`, a pre-built
   body Node instead of a body(host) function, and a `say` that already
   carries the verdict dot. One adapter here, so neither side needs to know. */
function tilesNormalize(spec){
  const s=Object.assign({},spec||{});
  if(s.gfx==null&&s.graphic!=null)s.gfx=(typeof s.graphic==='string')?s.graphic:'';
  if(s.src&&typeof s.src==='object'){
    const src=Object.assign({},s.src);
    if(src.stamp==null&&src.last_write!=null)src.stamp=src.last_write;
    /* some sources carry only a build-time age_h (srcRow's own fallback); the
       row's age needs an absolute stamp to keep ticking on the 30s timer, so
       derive one from that age at build time (D.built_at_et), never from now */
    if(src.stamp==null&&src.age_h!=null&&!isNaN(src.age_h)){
      const built=Date.parse(String(D.built_at_et||'').replace(' ','T'));
      if(!isNaN(built))src.stamp=new Date(built-src.age_h*3.6e6).toISOString().slice(0,19);
    }
    if(s.fresh_h==null&&src.freshH!=null)s.fresh_h=src.freshH;
    s.src=src;
  }
  if(s.body&&typeof s.body!=='function'){
    const node=s.body;
    s.body=function(host){host.appendChild(node);};
  }
  if(typeof s.say==='string')s.say=s.say.replace(/^\s*<i class="vd"><\/i>\s*/,'');
  return s;
}
function tileRow(spec){
  spec=tilesNormalize(spec);
  const isOff=spec.verdict==='off';
  const tile=document.createElement('details');
  tile.className='tile'+(spec.act?' tile--act':'');
  if(spec.id)tile.id=spec.id;
  tile.dataset.verdict=spec.verdict||'none';
  if(spec.src&&spec.src.path)tile.dataset.src=spec.src.path;
  if(spec.src&&spec.src.stamp)tile.dataset.stamp=spec.src.stamp;
  if(spec.fresh_h!=null)tile.dataset.fresh=String(spec.fresh_h);

  const summary=document.createElement('summary');
  summary.className='tile__head';

  const icSpan=el('span','tile__ic',tilesSafeIc(spec.icon));
  const titleSpan=el('span','tile__title',esc(spec.title||''));
  const gfxSpan=el('span','tile__gfx',isOff?'':(spec.gfx||''));

  let sayHtml;
  if(isOff){
    sayHtml='<i class="vd"></i>'+esc('NO DATA, looked for '+((spec.src&&spec.src.path)||'unknown source'));
  }else{
    sayHtml='<i class="vd"></i>'+(spec.say||'');
  }
  const saySpan=el('span','tile__say',sayHtml);

  const srcSpan=el('span','tile__src');
  if(spec.src&&spec.src.path){
    srcSpan.appendChild(document.createTextNode(tilesBaseName(spec.src.path)+' '));
    const t=document.createElement('time');
    t.className='age';
    t.setAttribute('datetime',spec.src.stamp||'');
    t.dataset.ts=spec.src.stamp||'';
    if(spec.fresh_h!=null)t.dataset.warn=String(spec.fresh_h);
    srcSpan.appendChild(t);
    try{paintAge(t);}catch(_){}
  }

  const chev=el('span','tile__chev',tilesSafeIc('chevron-down'));

  summary.appendChild(icSpan);
  summary.appendChild(titleSpan);
  summary.appendChild(gfxSpan);
  summary.appendChild(saySpan);
  if(spec.act&&spec.act.label){
    const btn=document.createElement('button');
    btn.type='button';
    btn.className='tile__fire';
    btn.textContent=spec.act.label;
    btn.addEventListener('click',function(ev){
      ev.preventDefault();ev.stopPropagation();
      tilesFire(btn,spec.act);
    });
    summary.appendChild(btn);
  }
  summary.appendChild(srcSpan);
  summary.appendChild(chev);
  tile.appendChild(summary);

  const body=document.createElement('div');
  body.className='tile__body';
  tile.appendChild(body);

  let bodyBuilt=false;
  tile.addEventListener('toggle',function(){
    try{
      if(tile.open){
        if(!bodyBuilt){
          bodyBuilt=true;
          if(typeof spec.body==='function'){
            try{spec.body(body);}
            catch(err){body.appendChild(document.createTextNode('NO DATA, body failed to render'));}
          }
        }
        tilesPersistOpen(tile.id,true);
      }else{
        tilesPersistOpen(tile.id,false);
      }
    }catch(_){}
  });

  if(!CAN_INTERP){
    summary.addEventListener('click',function(e){
      if(RM)return; /* reduced motion: let the native instant toggle happen */
      e.preventDefault();
      if(tile.open){
        const h=body.scrollHeight;
        let anim=null;
        try{
          anim=body.animate(
            [{height:h+'px',opacity:1},{height:'0px',opacity:0}],
            {duration:200,easing:'cubic-bezier(.4,0,1,1)'});
        }catch(_){}
        const closeNow=function(){tile.open=false;};
        if(anim)anim.onfinish=closeNow; else closeNow();
      }else{
        tile.open=true;
        requestAnimationFrame(function(){
          try{
            const h=body.scrollHeight;
            body.animate(
              [{height:'0px',opacity:0},{height:h+'px',opacity:1}],
              {duration:320,easing:'cubic-bezier(0,0,.2,1)'});
          }catch(_){}
        });
      }
    });
  }

  return tile;
}

/* ============================ groupRows ============================ */
function groupRows(opts){
  opts=opts||{};
  const rows=opts.rows||[];
  const g=document.createElement('div');
  g.className='tgroup';
  if(opts.id)g.id=opts.id;

  const collapsed=tilesGroupCollapsed(opts.id);
  g.classList.toggle('tgroup--collapsed',collapsed);

  const head=document.createElement('div');
  head.className='tgroup__head';
  head.appendChild(el('span',null,esc(opts.title||'')));
  head.appendChild(el('span','tgroup__count',String(rows.length)));
  const expand=document.createElement('a');
  expand.href='#';
  expand.className='tgroup__expand';
  expand.textContent=collapsed?'Expand all':'Collapse all';
  expand.addEventListener('click',function(e){
    e.preventDefault();
    const willCollapse=!g.classList.contains('tgroup--collapsed');
    g.classList.toggle('tgroup--collapsed',willCollapse);
    tilesSetGroupCollapsed(opts.id,willCollapse);
    expand.textContent=willCollapse?'Expand all':'Collapse all';
  });
  head.appendChild(expand);
  g.appendChild(head);

  const body=document.createElement('div');
  body.className='tgroup__body';
  rows.forEach(function(r){body.appendChild(r);});
  g.appendChild(body);
  return g;
}

/* ============================ tileOpen / tileFigure ============================ */
function tileOpen(id,opts){
  opts=opts||{};
  const t=document.getElementById(id);
  if(!t)return;
  if(!t.open)t.open=true;
  if(opts.scroll!==false){
    try{t.scrollIntoView({behavior:RM?'auto':'smooth',block:'center'});}
    catch(_){try{t.scrollIntoView();}catch(__){}}
  }
}

function tileFigure(node,value,fmt){
  if(!node)return;
  const fn=fmt||function(v){return(v==null||isNaN(v))?'--':String(v);};
  const wash=function(){
    node.classList.remove('wash');
    void node.offsetWidth;
    node.classList.add('wash');
    setTimeout(function(){try{node.classList.remove('wash');}catch(_){}},650);
  };
  try{
    if(!RM&&typeof window!=='undefined'&&window.countUp&&window.countUp.CountUp
       &&value!=null&&!isNaN(value)){
      const inst=new window.countUp.CountUp(node,value,{duration:0.24,formattingFn:fn});
      if(!inst.error){inst.start(wash);return;}
    }
  }catch(_){}
  node.textContent=fn(value);
  wash();
}

/* ============================ keyboard ============================ */
function tilesAllSummaries(){
  return Array.prototype.slice.call(document.querySelectorAll('.tile > summary'));
}
function tilesFocusedTile(){
  const a=document.activeElement;
  if(!a)return null;
  if(a.tagName==='SUMMARY'&&a.parentElement&&a.parentElement.classList.contains('tile'))return a.parentElement;
  if(a.classList&&a.classList.contains('tile__fire'))return a.closest('.tile');
  return null;
}
function tilesMoveFocus(dir){
  const list=tilesAllSummaries();
  if(!list.length)return;
  const cur=document.activeElement;
  let idx=list.indexOf(cur);
  if(idx===-1)idx=dir>0?-1:list.length;
  idx=(idx+dir+list.length)%list.length;
  list[idx].focus();
}
function tilesKey(e){
  try{
    if(e.metaKey||e.ctrlKey||e.altKey)return false;
    const tag=(e.target&&e.target.tagName)||'';
    if(tag==='INPUT'||tag==='TEXTAREA'||tag==='SELECT')return false;
    const key=e.key;
    if(key==='j'||key==='k'){
      tilesMoveFocus(key==='j'?1:-1);
      e.preventDefault();
      return true;
    }
    if(key==='o'){
      const t=tilesFocusedTile();
      if(t&&t.dataset.src){
        e.preventDefault();
        const path=t.dataset.src, stamp=t.dataset.stamp||'';
        try{
          openDrawer(tilesBaseName(path),function(host){
            host.appendChild(el('div','mono',esc(path)));
            if(stamp)host.appendChild(el('div','micro',esc(stamp)+' ET'));
          });
        }catch(_){}
        return true;
      }
      return false;
    }
    if(key==='e'||key==='E'){
      const t=tilesFocusedTile();
      const grp=t&&t.closest('.tgroup');
      if(grp){
        e.preventDefault();
        const willCollapse=e.shiftKey;
        grp.classList.toggle('tgroup--collapsed',willCollapse);
        tilesSetGroupCollapsed(grp.id,willCollapse);
        const link=grp.querySelector('.tgroup__expand');
        if(link)link.textContent=willCollapse?'Expand all':'Collapse all';
        return true;
      }
      return false;
    }
    if(key==='f'){
      const t=tilesFocusedTile();
      if(t){
        const btn=t.querySelector('.tile__fire');
        if(btn){e.preventDefault();btn.click();return true;}
      }
      return false;
    }
  }catch(_){return false;}
  return false;
}

/* ============================ fire ============================ */
function tilesFire(btn,act){
  try{
    btn.disabled=true;
    const result=act&&act.onclick?act.onclick(btn):null;
    const finish=function(){
      try{
        const now=new Date();
        const hh=String(now.getHours()).padStart(2,'0');
        const mm=String(now.getMinutes()).padStart(2,'0');
        const rep=document.createElement('span');
        rep.className='tile__fire tile__fire--done mono';
        rep.textContent='Fired '+hh+':'+mm;
        if(btn.parentNode)btn.parentNode.replaceChild(rep,btn);
        rep.classList.add('wash');
        setTimeout(function(){try{rep.classList.remove('wash');}catch(_){}},1500);
      }catch(_){}
    };
    if(result&&typeof result.then==='function'){
      result.then(finish).catch(function(){try{btn.disabled=false;}catch(_){}});
    }else{
      finish();
    }
  }catch(_){try{btn.disabled=false;}catch(__){}}
}

/* ============================ init ============================ */
let tilesStaleStarted=false;
function tilesRefreshStale(){
  try{
    document.querySelectorAll('.tile').forEach(function(t){
      const stamp=t.dataset.stamp;
      if(!stamp)return;
      let h=null;
      try{h=agoOf(stamp);}catch(_){h=null;}
      const warn=parseFloat(t.dataset.fresh||'');
      const stale=(h!=null)&&!isNaN(warn)&&(h>warn);
      t.classList.toggle('tile--stale',!!stale);
    });
  }catch(_){}
}
function tilesInit(){
  try{
    (tilesLoadOpen()||[]).forEach(function(id){
      const t=document.getElementById(id);
      if(t&&!t.open)t.open=true;
    });
    document.querySelectorAll('.tgroup').forEach(function(g){
      const collapsed=tilesGroupCollapsed(g.id);
      g.classList.toggle('tgroup--collapsed',collapsed);
      const link=g.querySelector('.tgroup__expand');
      if(link)link.textContent=collapsed?'Expand all':'Collapse all';
    });
    tilesRefreshStale();
    if(!tilesStaleStarted){
      tilesStaleStarted=true;
      setInterval(tilesRefreshStale,30000);
      document.addEventListener('keydown',function(e){tilesKey(e);});
    }
  }catch(_){}
}

/* ============================ graphics ============================ */
/* Every gfx* returns '' for null/empty/degenerate input - "if it cannot be
   drawn it is not a tile" - so a caller never has to special-case a fake
   graphic. Colour budget: currentColor, var(--ink-2), var(--dot-*),
   var(--accent-fill); var(--pos)/var(--neg) ONLY when the series is P&L. */

function gfxGauge(v,bar,min,max){
  if(v==null||isNaN(v))return'';
  const lo=(min==null)?0:min, hi=(max==null)?1:max;
  if(hi<=lo)return'';
  const w=160,h=24,pad=3,barY=h/2;
  const clampv=function(x){return Math.max(lo,Math.min(hi,x));};
  const scale=function(x){return pad+(clampv(x)-lo)/(hi-lo)*(w-2*pad);};
  const vx=scale(v);
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-gauge">';
  s+='<line x1="'+pad+'" y1="'+barY+'" x2="'+(w-pad)+'" y2="'+barY+'" stroke="var(--ink-2)" stroke-width="2" stroke-linecap="round"/>';
  if(bar!=null&&!isNaN(bar)){
    const bx=scale(bar);
    s+='<line x1="'+bx.toFixed(1)+'" y1="'+(barY-6)+'" x2="'+bx.toFixed(1)+'" y2="'+(barY+6)+'" stroke="currentColor" stroke-width="1"/>';
  }
  s+='<circle cx="'+vx.toFixed(1)+'" cy="'+barY+'" r="6" fill="var(--accent-fill)"/>';
  s+='</svg>';
  return s;
}

function gfxMeter(n,of){
  if(of==null||of<=0||n==null||isNaN(n))return'';
  const w=160,h=24,gap=2;
  const count=Math.max(1,Math.round(of));
  const bw=(w-(count-1)*gap)/count;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-meter">';
  for(let i=0;i<count;i++){
    const x=i*(bw+gap);
    const filled=i<n;
    s+='<rect x="'+x.toFixed(1)+'" y="4" width="'+bw.toFixed(1)+'" height="16" rx="1" '
      +'fill="'+(filled?'var(--accent-fill)':'var(--ink-2)')+'" opacity="'+(filled?'1':'.35')+'"/>';
  }
  s+='</svg>';
  return s;
}

function gfxSpark(vals,opts){
  opts=opts||{};
  if(!vals||vals.length<2)return'';
  const w=160,h=24,pad=2;
  const mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals);
  const rg=(mx-mn)||1;
  const pts=vals.map(function(v,i){
    const x=pad+i*((w-2*pad)/(vals.length-1));
    const y=h-pad-((v-mn)/rg)*(h-2*pad);
    return[x,y];
  });
  const d=pts.map(function(p,i){return(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1);}).join(' ');
  const last=vals[vals.length-1];
  let color='var(--ink-2)';
  if(opts.pnl)color=(last>=0)?'var(--pos)':'var(--neg)';
  const lp=pts[pts.length-1];
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-spark">';
  s+='<path d="'+d+'" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>';
  s+='<circle cx="'+lp[0].toFixed(1)+'" cy="'+lp[1].toFixed(1)+'" r="2.2" fill="'+color+'"/>';
  s+='</svg>';
  return s;
}

function gfxHeat(cells){
  if(!cells||!cells.length)return'';
  const cols=7,size=8,gap=2;
  const rows=Math.ceil(cells.length/cols);
  const w=160,h=32;
  const totalW=cols*size+(cols-1)*gap, totalH=rows*size+(rows-1)*gap;
  const ox=(w-totalW)/2, oy=(h-totalH)/2;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-heat">';
  cells.forEach(function(c,i){
    const r=Math.floor(i/cols),col=i%cols;
    const x=ox+col*(size+gap),y=oy+r*(size+gap);
    s+='<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+size+'" height="'+size+'" rx="1" fill="'+tilesDotColor(c)+'"/>';
  });
  s+='</svg>';
  return s;
}

function gfxRings(arms){
  if(!arms||!arms.length)return'';
  const list=arms.slice(0,6);
  const w=160,h=24,d=12;
  const gap=(w-list.length*d)/(list.length+1);
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-rings">';
  list.forEach(function(a,i){
    const cx=gap+i*(d+gap)+d/2, cy=h/2, r=5;
    const frac=Math.max(0,Math.min(1,(a&&a.share!=null)?a.share:0));
    const circ=2*Math.PI*r;
    s+='<circle cx="'+cx.toFixed(1)+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="var(--ink-2)" stroke-width="2"/>';
    if(frac>0){
      const dash=(circ*frac).toFixed(1)+' '+circ.toFixed(1);
      const stroke=(a&&a.open)?'var(--accent-fill)':'var(--ink-2)';
      s+='<circle cx="'+cx.toFixed(1)+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+stroke+'" stroke-width="2" '
        +'stroke-dasharray="'+dash+'" transform="rotate(-90 '+cx.toFixed(1)+' '+cy+')"/>';
    }
  });
  s+='</svg>';
  return s;
}

function gfxFunnel(stages){
  if(!stages||stages.length<2)return'';
  const w=160,h=24,gap=4;
  const n=stages.length;
  const mx=Math.max.apply(null,stages)||1;
  const bw=(w-(n-1)*gap)/n;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-funnel">';
  stages.forEach(function(v,i){
    const frac=Math.max(0,Math.min(1,v/mx));
    const bh=Math.max(2,frac*h);
    const x=i*(bw+gap), y=h-bh;
    s+='<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+bh.toFixed(1)+'" rx="1" '
      +'fill="var(--accent-fill)" opacity="'+(1-i*0.15).toFixed(2)+'"/>';
  });
  s+='</svg>';
  return s;
}

function gfxDots(states){
  if(!states||!states.length)return'';
  const list=states.slice(0,9);
  const w=160,h=24,r=4;
  const gap=(w-list.length*r*2)/(list.length+1);
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-dots">';
  list.forEach(function(st,i){
    const cx=gap+i*(r*2+gap)+r, cy=h/2;
    s+='<circle cx="'+cx.toFixed(1)+'" cy="'+cy+'" r="'+r+'" fill="'+tilesDotColor(st)+'"/>';
  });
  s+='</svg>';
  return s;
}

function gfxBars(vals){
  if(!vals||!vals.length)return'';
  const w=160,h=24,gap=4;
  const n=Math.min(vals.length,7);
  const list=vals.slice(0,n);
  const mx=Math.max.apply(null,list.map(Math.abs))||1;
  const bw=(w-(n-1)*gap)/n;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-bars">';
  list.forEach(function(v,i){
    const frac=Math.abs(v)/mx;
    const bh=Math.max(1,frac*(h-2));
    const x=i*(bw+gap), y=h-bh;
    s+='<rect x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+bh.toFixed(1)+'" rx="1" fill="var(--ink-2)"/>';
  });
  s+='</svg>';
  return s;
}

function gfxRingBig(n,of){
  if(of==null||of<=0)return'';
  const w=40,h=40,r=16,cx=20,cy=20;
  const frac=Math.max(0,Math.min(1,(n||0)/of));
  const circ=2*Math.PI*r;
  let s='<svg viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" class="gfx gfx-ringbig">';
  s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="var(--ink-2)" stroke-width="4"/>';
  if(frac>0){
    const dash=(circ*frac).toFixed(1)+' '+circ.toFixed(1);
    s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="var(--accent-fill)" stroke-width="4" '
      +'stroke-dasharray="'+dash+'" stroke-linecap="round" transform="rotate(-90 '+cx+' '+cy+')"/>';
  }
  s+='</svg>';
  return s;
}

/* ============================ screenshot fixture ============================ */
/* Renders one fixture tile per gfx kind into #view when the URL hash is
   #gfx, so cockpit_screenshot.py --tag gfx can capture every graphic kind in
   one pass without needing live payload data. */
function gfxDemo(){
  try{
    if(location.hash!=='#gfx')return;
    const host=document.getElementById('view');
    if(!host)return;
    host.innerHTML='';
    const nowIso=new Date().toISOString();
    const fixtures=[
      {id:'demo-gauge',icon:'gauge',title:'Gauge demo',
        gfx:gfxGauge(0.42,1,0,3),verdict:'red',
        say:'RED. demo <b>0.42</b> vs <b>1.0</b>',
        src:{path:'demo/gauge.json',stamp:nowIso},fresh_h:24},
      {id:'demo-meter',icon:'flame',title:'Meter demo',
        gfx:gfxMeter(3,14),verdict:'amber',say:'demo <b>3</b> of <b>14</b>'},
      {id:'demo-spark',icon:'dollar-sign',title:'Spark demo',
        gfx:gfxSpark([1,3,2,5,4,7,6],{pnl:true}),verdict:'green',
        say:'demo net <b>+$1,916</b>'},
      {id:'demo-heat',icon:'activity',title:'Heat demo',
        gfx:gfxHeat(['green','green','amber','red','off','green','green']),
        verdict:'amber',say:'demo heat'},
      {id:'demo-rings',icon:'layers',title:'Rings demo',
        gfx:gfxRings([{share:.5,open:true},{share:0,open:false},{share:1,open:true}]),
        verdict:'none',say:'demo rings'},
      {id:'demo-funnel',icon:'radar',title:'Funnel demo',
        gfx:gfxFunnel([72,18,3]),verdict:'none',say:'demo funnel'},
      {id:'demo-dots',icon:'eye',title:'Dots demo',
        gfx:gfxDots(['green','green','red','amber','off']),verdict:'none',say:'demo dots'},
      {id:'demo-bars',icon:'timer',title:'Bars demo',
        gfx:gfxBars([1,2,3,2,1,2,3]),verdict:'none',say:'demo bars'},
      {id:'demo-ringbig',icon:'target',title:'Ring big demo',
        gfx:gfxRingBig(5,7),verdict:'none',say:'demo ring big'},
      {id:'demo-off',icon:'gauge',title:'No-data demo',
        gfx:'',verdict:'off',say:''}
    ];
    const rows=fixtures.map(function(f){return tileRow(f);});
    host.appendChild(groupRows({id:'demo-group',title:'Graphics fixtures',rows:rows}));
    tilesInit();
  }catch(_){}
}
"""

"""gamma_cockpit_shell.py -- the cockpit's HTML skeleton, split out of
gamma_cockpit_ui.py so that module stays under the repo's 800-line ceiling
(Glow Command build, 2026-09-04, WS-A).

Owns exactly one export: `SHELL`, the same page-frame string that used to
live inline in gamma_cockpit_ui.py -- moved verbatim, ONE edit only: the root
`<div class="app">` gained a second class, `gc-app`, so gamma_cockpit_glow_ui's
CSS has a layout hook for the rail-grid shell (spec section 3) without
touching a single id, class or script-tag order any other module depends on.

Every id/class downstream JS reads is unchanged: .app, header.cmdbar.topbar,
#nav, #statechip, #statetxt, #phase, #clock, #themebtn, .kbd-hint, main.main,
#vtitle, #view, #footstamp, #footline, #chatdock, #chathandle, #scrim,
#drawer, #dtitle, #dbody, #dclose, #pal, #palin, #palres. Theme bootstrap
script, <title> before the first <style>, and the script order (const D=...
then vendor JS then app JS) are all unchanged. gamma_cockpit_ui.py imports
this module and re-exports `SHELL` so `gamma_cockpit_ui.SHELL` and
`gamma_cockpit_ui.render()` behave exactly as before.
"""
from __future__ import annotations

SHELL = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Gamma Cockpit</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script>(function(){
  try{
    var q=new URL(location.href).searchParams.get('theme');
    var t=q||localStorage.getItem('gamma-theme')||
      (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
    document.documentElement.dataset.theme=t;
  }catch(e){document.documentElement.dataset.theme='dark';}
  window.gammaSetTheme=function(v){
    try{document.documentElement.dataset.theme=v;localStorage.setItem('gamma-theme',v);}catch(e){}
  };
})();</script>
<style>__VENDOR_HEAD__</style>
<style>__CSS__</style>
</head>
<body>
<!-- THE BRIDGE. One operator, one primary surface: a strip of text tabs on a
     single top bar; everything else is one keystroke away (Cmd-K). -->
<div class="app gc-app">
  <header class="cmdbar topbar">
    <div class="mark topbar__mark"></div>
    <div class="word">Gamma</div>
    <nav class="tabs topbar__tabs" id="nav"></nav>
    <div class="sp"></div>
    <div class="ticker">
      <span class="chip live" id="statechip"><i class="dot"></i><span id="statetxt"></span></span>
      <span class="topbar__phase" id="phase"></span>
      <div class="clock topbar__clock" id="clock"></div>
      <button class="topbar__theme" id="themebtn" aria-label="Toggle theme" type="button"></button>
      <span class="kbd-hint"><kbd class="kbd">&#8984;K</kbd></span>
    </div>
  </header>
  <main class="main">
    <h1 id="vtitle" class="sr">Overview</h1>
    <div class="view anim" id="view"></div>
  </main>
  <span id="footstamp" class="sr"></span>
  <footer id="footline" class="foot"></footer>
</div>
<div id="chatdock" class="chatdock">
  <div id="chathandle" class="chatdock__handle">Chat</div>
</div>
<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <header><h2 id="dtitle"></h2><button class="x" id="dclose" aria-label="Close">&times;</button></header>
  <div class="body" id="dbody"></div>
</aside>
<div class="pal" id="pal">
  <div class="box"><input id="palin" placeholder="Jump to a view, desk, agent or day&hellip;" autocomplete="off">
  <div class="res" id="palres"></div></div>
</div>
<script>const D=__DATA_JSON__;</script>
<script>__VENDOR_JS__</script>
<script>__JS__</script>
</body>
</html>
"""

/* chat.js — the orchestrator, ported from the ai-assistat component J chose.
 *
 * Its anatomy kept: a tinted header bar, a deep body, a centred empty state with
 * a floating glyph, and a pill composer with a round send. What is NOT kept is
 * the pretence: this talks to a real Claude session through the companion's
 * /api/orchestrator-chat, resumes the same session across reloads, and streams
 * its tool steps. If the companion is down it says so instead of pretending to
 * think. */
(function (G) {
  'use strict';
  const D = G.data, esc = D.esc, el = D.el;
  const st = { turns: [], session: null, busy: false, es: null, model: 'opus', pinned: true };

  const SPARK = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" ' +
    'width="100%" height="100%"><path d="M12 2l1.9 5.7a4 4 0 0 0 2.4 2.4L22 12l-5.7 1.9a4 4 0 0 0-2.4 2.4L12 22l-1.9-5.7a4 4 0 0 0-2.4-2.4L2 12l5.7-1.9a4 4 0 0 0 2.4-2.4L12 2z"/>' +
    '<path d="M19 3l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7.7-2z" opacity=".65"/></svg>';
  const SEND = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" width="19" height="19" aria-hidden="true">' +
    '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';

  try {
    const saved = JSON.parse(localStorage.getItem('gamma-app-chat') || 'null');
    if (saved) {
      st.session = saved.session || null;
      st.model = saved.model || 'opus';
      st.turns = (saved.turns || []).filter((t) => t && t.text);
    }
  } catch (_) { /* private window / cleared storage is an empty chat, not a broken one */ }

  function save() {
    try {
      localStorage.setItem('gamma-app-chat', JSON.stringify({
        session: st.session, model: st.model,
        turns: st.turns.slice(-30).map((t) => ({ role: t.role, text: t.text })),
      }));
    } catch (_) { /* never let telemetry break the chat */ }
  }

  function body() { return document.getElementById('cbody'); }
  function scroll() { const b = body(); if (b && st.pinned) b.scrollTop = b.scrollHeight; }

  function push(role, text) {
    const empty = document.getElementById('cempty');
    if (empty) empty.remove();
    const t = { id: 't' + st.turns.length + '-' + Date.now(), role, text: text || '' };
    st.turns.push(t);
    const b = body(); if (!b) return t;
    const n = el('div', '');
    n.className = 'turn' + (role === 'me' ? ' turn--me' : '');
    n.innerHTML = '<span class="turn__w">' + (role === 'me' ? 'You' : 'Gamma · ' + esc(st.model)) +
      '</span><div class="turn__b" id="b-' + t.id + '"></div>' +
      (role === 'me' ? '' : '<div class="turn__steps" id="s-' + t.id + '"></div>');
    b.appendChild(n);
    const bb = document.getElementById('b-' + t.id);
    if (bb) bb.textContent = t.text;
    scroll();
    return t;
  }

  /* One DOM write per tick, not per token. setTimeout not rAF: rAF never fires in
     a hidden tab, which froze replies whenever the pane was not visible. */
  let buf = {}, tick = null;
  function flush() {
    tick = null;
    for (const id in buf) {
      const n = document.getElementById('b-' + id);
      if (n) n.textContent += buf[id];
    }
    buf = {}; scroll();
  }
  function append(id, chunk) {
    buf[id] = (buf[id] || '') + chunk;
    const t = st.turns.find((x) => x.id === id);
    if (t) t.text += chunk;              // the turn object, not the DOM, is what gets saved
    if (!tick) tick = setTimeout(flush, 16);
  }
  function step(id, label, tone) {
    const host = document.getElementById('s-' + id);
    if (!host) return;
    const r = el('div', esc(label)); r.className = 'turn__step';
    if (tone) r.setAttribute('data-t', tone);
    host.appendChild(r); scroll();
  }

  function busy(on) {
    st.busy = on;
    const b = document.getElementById('csend'), i = document.getElementById('cin');
    if (b) b.disabled = on;
    if (i) i.disabled = on;
  }

  function send() {
    const i = document.getElementById('cin');
    if (!i || st.busy) return;
    const msg = (i.value || '').trim();
    if (!msg) return;
    if (location.protocol === 'file:') {
      push('gamma', 'This page was opened from a file, so it cannot reach the companion. ' +
        'Open it over 127.0.0.1:4317 to chat.');
      return;
    }
    i.value = ''; i.style.height = 'auto';
    push('me', msg);
    const turn = push('gamma', '');
    save(); busy(true);

    const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
    fetch('/api/orchestrator-chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-gamma-token': tok },
      body: JSON.stringify({ message: msg, model: st.model, resume: st.session || undefined }),
    }).then((r) => r.json()).then((j) => {
      if (!j || j.ok === false) {
        step(turn.id, '✕ ' + ((j && j.error) || 'the companion refused this'), 'bad');
        busy(false); return;
      }
      if (j.resumed_from === 'store') step(turn.id, '↻ continuing the stored session');
      const url = '/api/ask-stream?id=' + encodeURIComponent(j.ask_id) +
        '&tok=' + encodeURIComponent(j.stream_token);
      let es;
      try { es = new EventSource(url); }
      catch (e) { step(turn.id, '✕ stream unavailable', 'bad'); busy(false); return; }
      st.es = es;
      es.onmessage = (ev) => {
        let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
        if (!d || !d.step) return;
        if (d.step === 'session' && d.sessionId) {
          st.session = d.sessionId; save();
          step(turn.id, (j.resumed ? '↻ resumed ' : '● session ') + String(d.sessionId).slice(0, 8));
        } else if (d.step === 'delta') { turn.sawDelta = true; append(turn.id, d.text || ''); }
        else if (d.step === 'text') { if (!turn.sawDelta) append(turn.id, d.text || ''); }
        else if (d.step === 'tool' || d.step === 'tool_start') step(turn.id, '▸ ' + (d.label || d.name || 'tool'));
        else if (d.step === 'tool_result') step(turn.id, '   ' + (d.preview || (d.ok ? 'ok' : 'error')));
        else if (d.step === 'result') {
          step(turn.id, (d.ok === false ? '✕ ' : '✓ ') + (d.summary || ''), d.ok === false ? 'bad' : 'ok');
          if (d.ok === false && /error|timeout/.test(d.subtype || '') && j.resumed) st.session = null;
          save(); stop();
        }
      };
    }).catch(() => { step(turn.id, '✕ could not reach the companion', 'bad'); busy(false); });
  }

  function stop() {
    if (st.es) { try { st.es.close(); } catch (_) { /* already closed */ } st.es = null; }
    busy(false);
  }

  function view() {
    const s = G.views.page('The <b>orchestrator</b>',
      'A real Claude session running inside this page. It remembers the conversation ' +
      'across reloads and can read and change the repo.');
    const c = el('div'); c.className = 'chat';
    c.innerHTML =
      '<div class="chat__bar"><span class="chat__spark">' + SPARK + '</span>' +
        '<h3>Gamma</h3>' +
        '<span class="pill" id="cstate"><i class="pill__dot"></i><span>ready</span></span>' +
      '</div>' +
      '<div class="chat__body" id="cbody"></div>' +
      '<div class="chat__foot">' +
        '<textarea class="chat__in" id="cin" rows="1" ' +
          'placeholder="Ask about the desk, the engine, or tonight&#39;s work…"></textarea>' +
        '<button class="chat__send" id="csend" type="button" aria-label="Send">' + SEND + '</button>' +
      '</div>';
    s.appendChild(c);

    const b = c.querySelector('#cbody');
    if (st.turns.length) {
      st.turns.forEach((t) => {
        const n = el('div'); n.className = 'turn' + (t.role === 'me' ? ' turn--me' : '');
        n.innerHTML = '<span class="turn__w">' + (t.role === 'me' ? 'You' : 'Gamma') +
          '</span><div class="turn__b"></div>';
        n.querySelector('.turn__b').textContent = t.text;
        b.appendChild(n);
      });
      const mark = el('div', '— restored · same session continues —');
      mark.className = 'turn__step'; mark.style.textAlign = 'center';
      b.appendChild(mark);
    } else {
      const e = el('div'); e.id = 'cempty'; e.className = 'chat__empty';
      e.innerHTML = '<div class="g">' + SPARK + '</div>' +
        '<h4>What do you want to know?</h4>' +
        '<p>It can read the repo, run checks and change things. Ask in plain language.</p>' +
        '<div class="chips"></div>';
      const chips = e.querySelector('.chips');
      ['What changed while I was away?', 'How did the desk do this week?',
       'What should I look at first?'].forEach((t) => {
        const b2 = document.createElement('button');
        b2.className = 'chip'; b2.type = 'button'; b2.textContent = t;
        b2.onclick = () => {
          const i = document.getElementById('cin');
          if (i) { i.value = t; i.focus(); }
        };
        chips.appendChild(b2);
      });
      b.appendChild(e);
    }

    const i = c.querySelector('#cin');
    i.oninput = () => { i.style.height = 'auto'; i.style.height = Math.min(150, i.scrollHeight) + 'px'; };
    i.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
    c.querySelector('#csend').onclick = send;
    /* Only a person can produce these, so they are the honest signal for "the
       reader scrolled away" — a programmatic scrollTo fires `scroll` too. */
    b.addEventListener('wheel', () => {
      st.pinned = (b.scrollHeight - b.scrollTop - b.clientHeight) < 30;
    }, { passive: true });
    setTimeout(() => { const x = document.getElementById('cin'); if (x) x.focus(); }, 60);
    return s;
  }

  G.chat = { view, send };
})(window.G = window.G || {});

/* app.js — boot, routing, and the few things that live above a view.
 *
 * Routing is hash-based on purpose: this is served as static files from the
 * companion, and a history-API router would 404 on refresh without a server
 * rewrite rule that does not exist here. */
(function (G) {
  'use strict';
  const D = G.data;

  G.RM = matchMedia('(prefers-reduced-motion:reduce)').matches;

  const ROUTES = {
    '': () => G.views.hero(),
    '/': () => G.views.hero(),
    '/profit': (arg) => G.views.profit(arg),
    '/cards': () => G.views.cards(),
    '/agents': () => G.views.agents(),
    '/chat': () => G.chat.view(),
    '/signin': () => G.views.signin(),
  };

  function route() {
    const h = String(location.hash || '').replace(/^#/, '');
    return ROUTES[h] ? h : (h ? '' : '');
  }

  function render(force, arg) {
    const host = document.getElementById('view');
    const key = force ? '/' + String(force).replace(/^\//, '') : route();
    const fn = ROUTES[key] || ROUTES[''];
    const node = fn(arg);
    host.replaceChildren(node);
    /* The sign-in screen is the only view without the app chrome. */
    document.getElementById('top').hidden = (key === '/signin');
    if (key === '/signin') {
      const c = document.getElementById('authart');
      if (c && G.signinArt) G.signinArt(c);
      wireAuth();
    }
    window.scrollTo({ top: 0, behavior: G.RM ? 'auto' : 'smooth' });
  }
  G.render = render;

  /* --- sign-in: honest about not being wired -------------------------------
     There is no identity provider configured on this box. A login form that
     accepts anything and lets you in is worse than no form, so these controls
     say what is missing and name the one thing that would fix it. */
  function wireAuth() {
    const note = document.getElementById('authnote');
    const say = (msg) => {
      if (!note) return;
      note.innerHTML = '<b>Not wired yet.</b> ' + D.esc(msg);
      note.style.color = 'var(--warn)';
    };
    const f = document.getElementById('authform');
    if (f) f.onsubmit = (e) => {
      e.preventDefault();
      say('Email sign-in needs a Firebase project id and web API key in the companion ' +
        'config. Nothing was sent anywhere.');
    };
    document.querySelectorAll('.oauth button').forEach((b) => {
      b.onclick = () => say(b.dataset.p.replace(/^./, (c) => c.toUpperCase()) +
        ' sign-in needs the Firebase web config and that provider enabled in the console. ' +
        'Nothing was sent anywhere.');
    });
  }

  /* --- firing a card -------------------------------------------------------- */
  G.fireCard = function (card, btn) {
    const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
    fetch('/api/ask', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-gamma-token': tok },
      body: JSON.stringify({ task: card.prompt || card.title, model: card.model || 'sonnet',
                             card_id: card.id, origin: 'app-card' }),
    }).then((r) => r.json()).then((j) => {
      const ok = j && j.ok !== false;
      btn.textContent = ok ? 'Working…' : 'Failed';
      btn.style.color = ok ? 'var(--live)' : 'var(--neg)';
      if (ok) setTimeout(() => { btn.textContent = 'Sent'; }, 1500);
    }).catch(() => {
      btn.textContent = 'No companion'; btn.disabled = false;
      btn.style.color = 'var(--neg)';
    });
  };

  /* --- chrome --------------------------------------------------------------- */
  function clock() {
    const n = document.getElementById('clock');
    if (!n) return;
    /* This box runs Mountain time and the desk runs on ET, so the clock is
       computed in the market's zone explicitly. Reading local time and calling
       it ET is the exact bug this project has been bitten by. */
    try {
      n.textContent = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', weekday: 'short', hour: '2-digit',
        minute: '2-digit', hour12: false,
      }).format(new Date()) + ' ET';
    } catch (_) { n.textContent = ''; }
  }

  function engineState() {
    const n = document.getElementById('engine');
    if (!n) return;
    const a = D.S.army || {};
    const live = (a.sessions || []).reduce((x, s) => x + (s.worker_active || 0), 0);
    const label = live ? live + (live === 1 ? ' agent live' : ' agents live') : 'standing by';
    n.querySelector('span').textContent = label;
    if (live) n.setAttribute('data-on', ''); else n.removeAttribute('data-on');
  }

  const kb = () => { const b = document.getElementById('kbtn');
    if (b && G.palette) b.onclick = () => G.palette.show(); };

  addEventListener('hashchange', () => render());
  addEventListener('scroll', () => {
    const t = document.getElementById('top');
    if (t) { if (scrollY > 8) t.setAttribute('data-scrolled', ''); else t.removeAttribute('data-scrolled'); }
  }, { passive: true });

  D.load().then(() => {
    render();
    clock(); engineState(); kb();
    setInterval(clock, 20000);
    /* Refresh the live half only. The payload is regenerated by a scheduled task,
       so re-fetching it every few seconds would be pure waste. */
    setInterval(() => { D.load().then(engineState); }, 30000);
  });
})(window.G = window.G || {});

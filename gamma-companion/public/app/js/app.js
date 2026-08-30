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
    /* ONE page for the orchestrator AND its agents. J: "orchestratort doesnt need
       to be its own page it can be a chat on the same page as the agents". /agents
       and /chat stay as aliases so old links and the palette keep working. */
    '/desk': () => G.desk.view(),
    '/agents': () => G.desk.view(),
    '/chat': () => G.desk.view(),
    /* Deep link straight to the P&L sheet. The desk renders underneath, then the
       sheet opens over it — so the link lands on the same one page rather than a
       separate report, and back/Escape returns to the desk instead of nowhere. */
    '/pnl': () => {
      const node = G.desk.view();
      // Synchronous: the sheet appends to <body>, so it does not need the desk node
      // mounted first. The deferred version flashed the bare desk for a frame and
      // was invisible to any capture that finished inside that window.
      if (G.glass && G.glass.openCalendar) G.glass.openCalendar();
      return node;
    },
    '/console': () => G.chat.view(),
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

  /* --- firing a card --------------------------------------------------------
     THE ENDPOINT IS /api/approve, NOT /api/ask. There is no POST /api/ask on the
     companion at all -- this button was wired to a route that does not exist and
     would have 404'd on J's first real click. It read plausible because the cockpit
     "already fires cards", but the cockpit posts an APPROVAL decision, and the
     server distinguishes a card fire from every other caller of that route by `id`
     naming a row in action-cards.json. Caught by grepping the routes rather than
     trusting the shape.

     Two server behaviours the cockpit honours and this must too:
       · RTH GATE — fires are refused 09:30-15:55 ET (rth-fire-disabled), checked
         BEFORE the idempotency slot is consumed so a refused card can be retried.
       · IDEMPOTENCY — a second approve for the same id returns ok WITHOUT an
         `escalated` id. That is a double-tap being absorbed, not a failure, and
         reporting it as success would imply a second session that never spawned. */
  /* The card's title reaches the console the same way it reaches the rail: as a
     sentence, not as the guard code it was emitted with. Without this the console
     was the one place on the page still printing "EARNINGS-CALENDAR STALE (RED):". */
  function cardLabel(card) {
    const raw = String((card && card.title) || 'action card');
    return (G.human && G.human.broken) ? G.human.broken(raw).text : raw;
  }

  /* What did the earlier fire of this card actually do? The companion keeps a
     small in-memory registry of recent escalations, each tagged with the card_id
     that spawned it, and /api/state exposes it as `claude`. Look the run up and
     print its outcome into the console, so the answer lands where J is already
     looking instead of in a refusal he cannot act on.

     NOTE: a still-running prior fire is reported, not re-attached. Attaching
     would need a stream token for an ask this page did not start, and there is no
     endpoint that mints one — inventing `/api/ask-token` here would have been a
     fabricated API, so this says "still running" honestly instead. */
  function showPriorRun(card, btn, tok, say) {
    fetch('/api/state', { cache: 'no-store', headers: { 'x-gamma-token': tok } })
      .then((r) => r.json()).then((st) => {
        const c = (st && st.claude) || {};
        const mine = [].concat(c.running || [], c.recent || [])
          .filter((t) => t && t.card_id === card.id);
        if (!mine.length) {
          btn.title = 'This card already fired, but its run is no longer in the ' +
            'companion’s recent list.';
          return;
        }
        const t = mine[0];
        if (!G.chat || !G.chat.note) return;
        if (t.status === 'running') {
          G.chat.note(cardLabel(card),
            'still running — started ' + String(t.started || '').slice(11, 16) +
            (t.lastStep ? ' · ' + t.lastStep : ''), null);
          say('Still running ↓', 'live');
          return;
        }
        G.chat.note(cardLabel(card),
          t.summary || t.lastStep || ('finished ' + (t.ok ? 'ok' : 'with an error')),
          t.ok !== false);
        say('Ran ↓', 'warn');
      }).catch(function () { /* leave the plain "already ran" message */ });
  }

  G.fireCard = function (card, btn) {
    const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
    const say = (text, tone) => {
      btn.textContent = text;
      btn.style.color = tone ? 'var(--' + tone + ')' : '';
    };
    fetch('/api/approve', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-gamma-token': tok },
      body: JSON.stringify({
        id: card.id,
        decision: 'approve',
        action: { type: 'escalate', model: card.model, task: card.prompt },
      }),
    }).then((r) => r.json()).then((j) => {
      if (!j || j.ok === false) {
        const rth = j && j.error === 'rth-fire-disabled';
        say(rth ? 'Market hours' : 'Failed', 'neg');
        btn.disabled = false;
        btn.title = rth
          ? 'Fires are disabled 09:30-15:55 ET so a card cannot edit the repo mid-session.'
          : ((j && j.error) || 'the companion refused this');
        return;
      }
      if (!j.escalated) {
        /* "Already fired" was a dead end: J clicked Run, got a message, and still
           could not see what the earlier run DID. The run is in the companion's
           task registry keyed by card_id, so look it up and show its outcome
           instead of just refusing. */
        say('Already ran', 'warn');
        btn.title = 'This card already fired — no second session was spawned.';
        showPriorRun(card, btn, tok, say);
        return;
      }
      /* HAND THE RUN TO THE CONSOLE. The ask id used to go into a tooltip, which
         is the same as nowhere: J clicked Run and had no way to see what the
         session was doing. The server already returns a stream_token here and
         chat.js already renders that stream as a live tool timeline. */
      const watching = G.chat && G.chat.adopt &&
        G.chat.adopt(j.escalated, j.stream_token, cardLabel(card), j.model || card.model);
      say(watching ? 'Running ↓' : 'Working…', 'live');
      btn.title = watching
        ? 'Running now — watch it in the console below.'
        : 'ask ' + String(j.escalated).slice(0, 14);
      if (watching) {
        const c = document.querySelector('.deskmain__chat');
        if (c && c.scrollIntoView) c.scrollIntoView({ block: 'nearest', behavior: G.RM ? 'auto' : 'smooth' });
      }
    }).catch(() => {
      say('No companion', 'neg');
      btn.disabled = false;
      btn.title = 'Could not reach the companion on 127.0.0.1:4317.';
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

  /* OFFLINE BANNER. A dashboard whose data source is gone must say so on its face.
     Without this the app keeps rendering the last payload it loaded and every number
     silently becomes a claim about a moment that has passed -- exactly the failure
     the cockpit's staleness badges exist to prevent. */
  function offlineBanner() {
    const have = document.getElementById('offbar');
    if (D.S.up !== false) { if (have) have.remove(); return; }
    if (have) return;
    const b = document.createElement('div');
    b.id = 'offbar'; b.className = 'offbar';
    const when = D.S.at
      ? new Date(D.S.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : null;
    b.innerHTML = '<b>The companion is not answering.</b> ' + (when
      ? 'Everything below is from ' + D.esc(when) + ' and is not being updated.'
      : 'No data has loaded at all — start it with the Gamma_CompanionKeepalive task.') +
      ' <span class="mono">127.0.0.1:4317</span>';
    document.body.insertBefore(b, document.getElementById('view'));
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

  /* The desk console is sized as "viewport minus the top bar", so --top has to be
     the bar's REAL height. Hard-coding it looked right at one zoom level and left
     a scrollbar or a dead strip at every other, which on a page whose whole point
     is not scrolling is the bug rather than a rounding error. Measured instead,
     and re-measured on resize because the bar wraps at narrow widths. */
  function topVar() {
    const t = document.getElementById('top');
    const h = t ? Math.round(t.getBoundingClientRect().height) : 0;
    if (h > 0) document.documentElement.style.setProperty('--top', h + 'px');
    // The trading band sits between the top bar and the columns, so the shell has
    // to subtract BOTH or the page scrolls again. Measured, never assumed: the band
    // reflows with the viewport and a hard-coded height is a scrollbar waiting to
    // happen -- the same defect --top was introduced to fix, one element lower.
    const b = document.querySelector('.gstrip');
    document.documentElement.style.setProperty('--band',
      (b ? Math.round(b.getBoundingClientRect().height) : 0) + 'px');
  }

  addEventListener('gamma:data', () => { engineState(); offlineBanner(); });
  addEventListener('hashchange', () => { render(); topVar(); });
  addEventListener('scroll', () => {
    const t = document.getElementById('top');
    if (t) { if (scrollY > 8) t.setAttribute('data-scrolled', ''); else t.removeAttribute('data-scrolled'); }
  }, { passive: true });

  D.load().then(() => {
    render();
    clock(); engineState(); kb(); offlineBanner(); topVar();
    addEventListener('resize', topVar, { passive: true });
    setInterval(clock, 20000);
    /* Refresh the live half only. The payload is regenerated by a scheduled task,
       so re-fetching it every few seconds would be pure waste. */
    setInterval(() => { D.load(); }, 30000);   // the gamma:data listener does the rest
  });
})(window.G = window.G || {});

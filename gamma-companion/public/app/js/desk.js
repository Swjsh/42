/* desk.js — THE ONE PAGE. J, after the first build:
 *
 *   "orchestratort doesnt need to be its own page it can be a chat on the same page
 *    as the agents. remember the html guide you made that i said i liked ... with
 *    orch on top and the pulsing lines for the agents he was talking to back and
 *    forth ... the goal is 1 unified place to control and see the trading platform
 *    and have gamma be autonomous, i dont see anywhere what gamma did all night"
 *
 * So this page is: the orchestrator on top, pulsing beams down to every session it
 * talks to, the console on the SAME page, and a feed of what actually happened
 * while he was asleep. Splitting those across three routes was the mistake — each
 * answered a third of one question.
 *
 * WHY THE GRAPH IS SVG AND HAND-ROLLED: no CDN is allowed here, and the thing being
 * drawn is a fixed two-tier hierarchy (one orchestrator, N sessions), not a general
 * graph. A layout library would be more code than the twelve lines of arithmetic
 * below and would still need the beam animation written by hand. */
(function (G) {
  'use strict';
  const D = G.data, esc = D.esc, el = D.el;

  const NS = 'http://www.w3.org/2000/svg';
  const mk = (t, a) => {
    const e = document.createElementNS(NS, t);
    for (const k in (a || {})) e.setAttribute(k, a[k]);
    return e;
  };
  const shortType = (t) => t === 'general-purpose' ? 'general'
    : t === 'workflow-subagent' ? 'workflow' : (t || 'agent');

  /* ---- the org: orchestrator hero + agent cards, wired by live beams -------
   *
   * REBUILT 2026-08-30 against dossier R1 (Magic UI AnimatedBeam). Root cause of
   * J's "literally size two font", stated once: the old stage drew every label as
   * SVG <text> inside viewBox="0 0 1000 H", and the CSS height cap made
   * preserveAspectRatio meet-scale the whole drawing by the letterbox ratio, so a
   * "10.5px" label rendered ~6 real pixels. That is structural -- text inside a
   * scaled viewBox cannot hold a size -- so the nodes are HTML now (text lays out
   * at real pixel sizes, can never shrink) and SVG keeps only what it is good at:
   * beam strokes drawn BETWEEN the DOM rects, AnimatedBeam-style.
   *
   * The beams are also no longer decoration: packet() sends a dot down a beam,
   * and the pulse poller below fires it from REAL companion pulse rows -- the
   * same event that writes the feed sentence. One event, two faces (dossier rule
   * 4: message flow = beam packet + feed sentence from the SAME event). */
  let orgRef = null;   // the mounted org box; packet() needs its live paths

  function orgCard(s, workers) {
    const live = (s.worker_active || 0) > 0 || s.activity === 'active';
    const card = document.createElement('article');
    card.className = 'org__card' + (live ? ' is-live' : '');
    card.setAttribute('data-sid', s.session_id || '');

    const liveN = s.worker_active || 0, everN = s.worker_count || 0;
    const mine = workers.filter((w) => w.session_id === s.session_id)
      .sort((x, y) => (y.active ? 1 : 0) - (x.active ? 1 : 0) ||
        String(y.last_write || '').localeCompare(String(x.last_write || '')));

    let agRows = '';
    mine.slice(0, 3).forEach((w) => {
      // scrub: workflow rows fall back to task text that is often a raw path --
      // the hover title keeps the record, the glass gets English (dossier rule 3)
      const what = G.human.scrub(w.purpose || w.description || w.task || '') || 'working';
      agRows += '<div class="org__ag' + (w.active ? ' is-on' : '') + '" title="' +
        esc(w.task || '') + '"><i></i><b>' + esc(shortType(w.agent_type)) + '</b>' +
        '<span>' + esc(what) + '</span></div>';
    });
    if (everN > 3) agRows += '<div class="org__agmore">+' + (everN - 3) + ' more</div>';

    let mem = '';
    if (typeof s.context_pct === 'number' && s.context_source !== 'unknown') {
      const pct = Math.max(0, Math.min(100, s.context_pct));
      const tone = pct >= 90 ? 'neg' : (pct >= 75 ? 'warn' : '');
      mem = '<div class="org__mem" data-t="' + tone + '">' +
        '<i style="width:' + Math.round(pct) + '%"></i>' +
        '<span class="num">' + Math.round(pct) + '%</span></div>';
    }

    card.innerHTML =
      '<header class="org__ch"><span class="org__dot"></span>' +
        '<b class="org__ct">' + esc(s.title || 'Untitled chat') + '</b></header>' +
      '<span class="org__ck">' + esc(s.name || '') +
        (s.entrypoint || s.kind ? ' · ' + esc(s.entrypoint || s.kind) : '') + '</span>' +
      '<div class="org__cs' + (liveN ? ' is-on' : '') + '">' +
        (liveN ? liveN + ' agent' + (liveN === 1 ? '' : 's') + ' working'
               : (everN ? 'resting · ' + everN + ' finished' : 'no agents yet')) + '</div>' +
      '<div class="org__ags">' + agRows + '</div>' + mem;
    return card;
  }

  function drawWire(box) {
    const wire = box.querySelector('.org__wire');
    const hero = box.querySelector('.org__orc');
    if (!wire || !hero || !box.isConnected) return;
    const bb = box.getBoundingClientRect();
    if (!bb.width) return;
    wire.setAttribute('viewBox', '0 0 ' + bb.width + ' ' + bb.height);
    wire.setAttribute('width', bb.width); wire.setAttribute('height', bb.height);
    while (wire.firstChild) wire.removeChild(wire.firstChild);
    const defs = mk('defs'); wire.appendChild(defs);
    box._paths = {};

    const hb = hero.getBoundingClientRect();
    const cards = box.querySelectorAll('.org__card');
    cards.forEach((card, i) => {
      const cb = card.getBoundingClientRect();
      const x2 = cb.left + cb.width / 2 - bb.left;
      const y2 = cb.top - bb.top - 2;
      // fan the start anchors along the hero's bottom edge toward each card, so
      // the beams read as separate conversations rather than one bus bar
      const x1 = Math.max(hb.left - bb.left + 28,
        Math.min(hb.right - bb.left - 28, x2));
      const y1 = hb.bottom - bb.top + 2;
      const midY = (y1 + y2) / 2;
      const d = 'M ' + x1 + ' ' + y1 + ' C ' + x1 + ' ' + midY + ', ' +
        x2 + ' ' + midY + ', ' + x2 + ' ' + y2;

      wire.appendChild(mk('path', { d: d, fill: 'none',
        stroke: 'var(--ink)', 'stroke-width': 1, opacity: '.09' }));

      const live = card.classList.contains('is-live');
      const gid = 'wb' + i;
      const g = mk('linearGradient', { id: gid, gradientUnits: 'userSpaceOnUse',
        x1: x1, y1: y1, x2: x2, y2: y2 });
      [['0%', 'var(--live)', '0'], ['18%', 'var(--live)', '.95'],
       ['55%', 'var(--acc)', '.95'], ['100%', 'var(--acc)', '0']]
        .forEach(function (st) { g.appendChild(mk('stop',
          { offset: st[0], 'stop-color': st[1], 'stop-opacity': st[2] })); });
      defs.appendChild(g);
      const beam = mk('path', { d: d, fill: 'none', stroke: 'url(#' + gid + ')',
        'stroke-width': 2.2, 'stroke-linecap': 'round', class: 'beam' });
      beam.style.animationDuration = live ? '2.4s' : '6.5s';
      beam.style.animationDelay = (i * 0.5) + 's';
      beam.style.opacity = live ? '1' : '.35';
      wire.appendChild(beam);
      box._paths[card.getAttribute('data-sid')] = d;
    });
  }

  /* One dot, one journey. reverse=true is the agent REPORTING BACK up the wire.
     SMIL animateMotion: starts on insert, needs no rAF bookkeeping, and is
     removed once the trip is over. */
  function packet(sessionId, reverse) {
    // Resolve from the DOCUMENT, not module memory: refreshDesk swaps the org
    // box on every data tick, and a packet aimed at the pre-swap reference
    // lands on a detached node -- fired into nothing, invisibly. The direct-
    // call mechanism test passed while natural traffic showed no dots; this
    // removes that whole class of stale-reference loss.
    const box = document.querySelector('.org') || orgRef;
    if (!box || !box.isConnected || !box._paths || !box._paths[sessionId]) return false;
    const wire = box.querySelector('.org__wire');
    const dot = mk('circle', { r: 3.4, class: 'org__pkt',
      fill: reverse ? 'var(--live)' : 'var(--acc)' });
    const mo = mk('animateMotion', { dur: '1.1s', fill: 'freeze',
      path: box._paths[sessionId],
      keyPoints: reverse ? '1;0' : '0;1', keyTimes: '0;1', calcMode: 'linear' });
    dot.appendChild(mo);
    wire.appendChild(dot);
    setTimeout(function () { try { wire.removeChild(dot); } catch (_) { /* gone */ } }, 1300);
    return true;
  }

  function stage(army) {
    const sessions = (army.sessions || []).filter(function (x) {
      return !x.is_orchestrator && x.activity !== 'stale'; }).slice(0, 4);
    const orc = army.orchestrator;
    const workers = army.workers || [];

    const box = el('org');
    const orcLive = (orc && orc.worker_active) || 0;

    /* The hero. The ONE glowing element on the page (dossier R3 restraint rule):
       Gamma itself, big enough to read from across the room. */
    const hero = el('org__orc' + (orcLive ? ' is-live' : ''));
    let memHtml = '';
    if (orc && typeof orc.context_pct === 'number' && orc.context_source !== 'unknown') {
      const pct = Math.round(orc.context_pct);
      const tone = pct >= 90 ? 'neg' : (pct >= 75 ? 'warn' : '');
      memHtml = '<span class="org__omem num" data-t="' + tone + '">' + pct + '% memory</span>';
    }
    hero.innerHTML =
      '<span class="org__beacon' + (orcLive ? ' is-on' : '') + '"></span>' +
      '<div class="org__id">' +
        '<b class="org__name">' + esc(orc ? orc.name : 'Gamma') + '</b>' +
        '<span class="org__role">Gamma · the orchestrator</span>' +
        '<p class="org__doing">' + esc(orc && orc.title ? orc.title : 'quiet right now') + '</p>' +
      '</div>' +
      '<div class="org__ostats">' + memHtml +
        '<span class="org__oag' + (orcLive ? ' is-on' : '') + '">' +
        (orcLive ? orcLive + ' agent' + (orcLive === 1 ? '' : 's') + ' out working'
                 : 'no agents out') + '</span></div>';
    box.appendChild(hero);

    const wire = mk('svg', { class: 'org__wire', 'aria-hidden': 'true' });
    box.appendChild(wire);

    if (sessions.length) {
      const grid = el('org__grid');
      sessions.forEach(function (x) { grid.appendChild(orgCard(x, workers)); });
      box.appendChild(grid);
    } else {
      box.appendChild(el('org__none',
        'No other Claude windows are open — Gamma is working alone right now.'));
    }

    orgRef = box;
    /* The box is built BEFORE the router mounts it, so the first rAF sees a
       disconnected 0-width element and the ResizeObserver's initial fire does
       too — measured live: beams=0 forever. Retry until real layout exists,
       then let the observer own resizes. */
    let tries = 0;
    (function arm() {
      if (box.isConnected && box.getBoundingClientRect().width) return drawWire(box);
      if (++tries < 25) setTimeout(arm, 80);
    })();
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(function () { drawWire(box); });
      ro.observe(box);
    }
    return box;
  }

  /* ---- the live wire: real pulses -> packet on the beam + feed sentence ----
   * Polls the companion's pulse delta feed (7s, only while the desk is the
   * visible route -- a hidden tab spends nothing). Each fresh row is ONE event
   * rendered twice from the same source: a dot travelling the session's beam,
   * and an actor-verb line at the top of the activity rail. Throttled per
   * session so a busy agent reads as a heartbeat, not a machine gun. */
  const pulseSt = { cursor: '', lastPkt: {}, lastLine: {}, timer: 0 };

  function feedLine(sentence, whenIso, raw) {
    const feed = document.querySelector('.rail--r .feed');
    if (!feed) return;
    const n = el('ev ev--wire');
    if (raw) n.title = raw;
    n.innerHTML = '<span class="ev__k">mail</span>' +
      '<span class="ev__t">' + esc(sentence) + '</span>' +
      '<span class="ev__w mono">' + esc(G.human.ago(whenIso)) + '</span>';
    const head = feed.querySelector('.feed__h');
    feed.insertBefore(n, head ? head.nextSibling : feed.firstChild);
    const rows = feed.querySelectorAll('.ev--wire');
    if (rows.length > 8) feed.removeChild(rows[rows.length - 1]);
  }

  async function pollPulses() {
    if ((location.hash || '#/desk') !== '#/desk') return;
    // A hidden tab cannot show the wire, so it does not poll for it. __wireForce
    // is the verification override -- headless checks have no visible tab.
    if (document.hidden && !window.__wireForce) return;
    try {
      const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content;
      const r = await fetch('/api/army?since=' + encodeURIComponent(pulseSt.cursor),
        { cache: 'no-store', headers: tok ? { 'x-gamma-token': tok } : {} });
      if (!r.ok) return;
      const j = await r.json();
      if (!j || !j.ok) return;
      const first = !pulseSt.cursor;
      pulseSt.cursor = j.cursor || pulseSt.cursor;
      if (first) return;                        // baseline only; no replay flood
      const names = {};
      (((D.S.army || {}).sessions) || []).forEach(function (x) {
        names[x.session_id] = x.name; });
      const orcId = ((D.S.army || {}).orchestrator || {}).session_id;
      (j.rows || []).slice(-12).forEach(function (row) {
        const sid = row.session_id || '';
        const now = Date.now();
        if (sid && sid !== orcId && (now - (pulseSt.lastPkt[sid] || 0)) > 4000) {
          if (packet(sid, row.event === 'done' || row.event === 'result')) {
            pulseSt.lastPkt[sid] = now;
          }
        }
        if ((now - (pulseSt.lastLine[sid] || 0)) > 20000) {
          const who = sid === orcId ? 'Gamma' : (names[sid] || 'an agent');
          const h = G.human.pulse(row, who);
          feedLine(h.text, row.ts, h.raw);
          pulseSt.lastLine[sid] = now;
        }
      });
    } catch (_) { /* the 30s desk poll still keeps the page truthful */ }
  }
  if (!pulseSt.timer) pulseSt.timer = setInterval(pollPulses, 7000);

  /* ---- IS GAMMA AWAKE, AND WHAT IS IT ABOUT TO DO -------------------------
     J: "where is the autonomy, how do we have gamma be alive and on the page and
     give it the ability to do actions like choose recc action cards, theorize
     whats next".

     The loop was real the whole time -- 48 commits landed unattended overnight --
     and reached no surface, so from here it looked like nothing was happening.
     This panel is that loop's face. It reports state; it never acts. */
  function autonomy(au) {
    const wrap = el('div'); wrap.className = 'auto';
    if (!au || au.error) {
      wrap.appendChild(D.miss('Autonomy status unavailable',
        au && au.error ? 'gamma_autonomy.py: ' + au.error : 'setup/scripts/gamma_autonomy.py'));
      return wrap;
    }
    const q = au.quiet || {}, af = au.autofire || {}, w = au.watcher || {};
    const bud = au.budget || {};
    const until = q.next_loud ? String(q.next_loud).slice(11, 16) : null;
    /* THREE STATES, not two. `awake` reports only whether quiet-mode is muting the
       SCHEDULER -- it says nothing about whether work is happening right now. Under a
       real load test the header read "RESTING" while three agents were running and
       the strip below it said "3 agents running now", which is the page contradicting
       itself. Live work outranks the schedule. */
    const liveNow = ((D.S.army || {}).sessions || [])
      .reduce((n, x) => n + (x.worker_active || 0), 0);
    const scheduled = au.awake === true;
    const awake = liveNow > 0 || scheduled;

    /* The headline is a STATE, not a number: asleep-by-schedule and asleep-because-
       something-broke look identical from a task list and mean opposite things. */
    const head = el('div'); head.className = 'auto__head';
    head.innerHTML =
      '<span class="auto__dot"' + (awake ? ' data-on' : '') + '></span>' +
      '<span class="auto__state">' + (liveNow ? 'WORKING'
        : (scheduled ? 'AWAKE — idle' : 'RESTING')) + '</span>' +
      '<span class="auto__sub">' + (liveNow
        ? '<b>' + liveNow + '</b> agent' + (liveNow === 1 ? '' : 's') + ' running right now' +
          (scheduled ? '.' : ' — and its scheduled jobs are muted, so this is work you or ' +
           'the console started, not the overnight loop.')
        : scheduled
        ? 'Scheduled jobs are live; nothing is running this second.'
        : 'Quiet hours' + (until ? ' until <b>' + esc(until) + ' ET</b>' : '') +
          (q.held_down ? ' · ' + esc(String(q.held_down)) + ' scheduled jobs held down' : '') +
          '. This is on purpose, not a fault — it works through the night.') + '</span>';
    wrap.appendChild(head);

    const grid = el('div'); grid.className = 'auto__grid';

    /* NEXT MOVE — the goal's own top open item IS the conductor's next pick, so
       this is what it will actually do, not a guess about what it might. */
    const nm = au.next_move;
    grid.appendChild(cell('Next move', nm
      ? esc(nm.text)
      : '<span class="dim">Nothing queued for itself — every open item is waiting on you.</span>',
      nm ? '' : 'dim'));

    /* CAN IT CHOOSE CARDS BY ITSELF — the exact thing J asked about, answered
       without flattery. Built, set to --live on weekdays, never once executed. */
    const fireState = af.ever_fired
      ? (af.fired_today ? af.fired_today + ' fired today' : 'armed · none needed today')
      : 'has never fired';
    const t = af.task || {};
    grid.appendChild(cell('Fires action cards itself', esc(fireState) +
      '<div class="auto__why">' +
      (af.ever_fired
        ? 'Guards: refuses during market hours, obeys quiet mode, capped per run and per day.'
        : 'Built and set to <span class="mono">--live</span> on weekdays, but its task is ' +
          esc(t.schedule || 'unscheduled') + ' and has <b>never executed</b>' +
          (t.state ? ' (currently ' + esc(t.state) + ')' : '') + '. ' +
          (af.last ? 'Last decision: <b>' + esc(af.last.decision || '?') + '</b> — ' +
            esc(af.last.reason || '') + '.' : '')) +
      '</div>', af.ever_fired ? '' : 'warn'));

    /* Why it stopped. A throttle and a breakdown look identical from outside, and
       here the throttle is the fire COUNT while only a fraction of the money cap
       was spent — which is a tuning decision for J, not a fault to fix. */
    if (bud.verdict) {
      const done = String(bud.verdict).toUpperCase() === 'EXHAUSTED';
      grid.appendChild(cell('Today’s budget',
        (done ? 'Used up — <b>' + esc(String(bud.fires_used)) + ' runs</b> of ' +
          esc(String(bud.fires_cap)) + ' allowed'
              : esc(String(bud.fires_used || 0)) + ' of ' + esc(String(bud.fires_cap)) + ' runs used') +
        '<div class="auto__why">' +
        (bud.spent_usd != null && bud.cap_usd
          ? 'Spent <b>$' + esc(Number(bud.spent_usd).toFixed(2)) + '</b> of a $' +
            esc(String(bud.cap_usd)) + ' cap — it is the RUN COUNT that stopped it, not the money. ' +
            'Raising <span class="mono">max_fires</span> in conductor-budget.json is your call.'
          : esc(bud.reason || '')) +
        '</div>', done ? 'warn' : ''));
    }

    grid.appendChild(cell('Self-check', w.checked_at
      ? esc(String(w.checked_at).slice(11, 16)) + ' · ' +
        (w.ok ? 'all clear' : (w.findings || []).length + ' finding(s)') +
        '<div class="auto__why">' +
        ((w.findings || []).map((f) => esc(f.message)).join('<br>') || 'Nothing flagged.') +
        '</div>'
      : '<span class="dim">never run</span>', w.ok === false ? 'warn' : ''));

    /* The four detail cells fold away by default (2026-08-30). Measured: the
       autonomy block ran 680px inside a 657px column, so on its own it pushed the
       console off the screen -- and its content is diagnostic prose, which is
       exactly the kind of thing you read when something looks wrong and never
       when it does not. The STATE line above stays permanently visible, so the
       glance still works; the paragraph behind it is one click away.

       <details> rather than a JS toggle: it is keyboard-operable, findable by the
       browser's own in-page search even while closed, and needs no state of its
       own to get out of sync. */
    // document.createElement, NOT el(): el's first argument is a CLASS NAME and it
    // always builds a <div>, so el('details') produced <div class="details"> -- a
    // fold that rendered its contents permanently open and reported .open as
    // undefined. Real <details> is the entire point here.
    const fold = document.createElement('details'); fold.className = 'auto__fold';
    const sum = document.createElement('summary'); sum.className = 'auto__foldt';
    sum.textContent = 'Detail — next move, card firing, budget, self-check';
    fold.appendChild(sum); fold.appendChild(grid);
    wrap.appendChild(fold);

    /* CONTROLS. J: "give it the ability to do actions". Watching a loop you cannot
       touch makes the panel a poster. Both buttons drive mechanisms that already
       exist -- the same halt flag guard.js refuses every escalation on, and the same
       autofire runner the 23:30 trigger invokes -- so neither can do anything the
       schedule could not already have done. Nothing here can raise a cap or bypass a
       guard: a page that widens its own limits is how a glance becomes an accident. */
    const bar = el('div'); bar.className = 'auto__bar';
    const halt = document.createElement('button');
    halt.className = 'ghost'; halt.type = 'button'; halt.textContent = 'checking…';
    halt.disabled = true;
    const runb = document.createElement('button');
    runb.className = 'ghost'; runb.type = 'button'; runb.textContent = 'Run a card pass now';
    const say = el('span', ''); say.className = 'auto__say';

    const tok = () => (document.querySelector('meta[name="gamma-token"]') || {}).content || '';
    const post = (action) => fetch('/api/autonomy', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-gamma-token': tok() },
      body: JSON.stringify({ action }),
    }).then((r) => r.json());

    const paintHalt = (halted) => {
      halt.disabled = false;
      halt.textContent = halted ? 'Resume Gamma' : 'Halt everything';
      halt.style.color = halted ? 'var(--warn)' : '';
      say.textContent = halted
        ? 'HALTED — every escalation and every card fire is refused until you resume.'
        : '';
    };
    fetch('/api/autonomy', { headers: { 'x-gamma-token': tok() } })
      .then((r) => r.json()).then((j) => paintHalt(j && j.halted))
      .catch(() => { halt.textContent = 'no companion'; });

    halt.onclick = () => {
      const goingDown = halt.textContent.indexOf('Halt') === 0;
      halt.disabled = true;
      post(goingDown ? 'halt' : 'resume')
        .then((j) => paintHalt(j && j.halted))
        .catch(() => { halt.disabled = false; say.textContent = 'could not reach the companion'; });
    };
    /* Two-step. This spawns the same runner the 23:30 trigger does, so a single
       stray click starts real autonomous work; the audit flagged that it read like a
       status/preview control. */
    runb.onclick = () => {
      if (!runb.dataset.armed) {
        runb.dataset.armed = '1';
        runb.textContent = 'Confirm — this fires cards';
        runb.style.color = 'var(--warn)';
        setTimeout(() => {
          if (runb.dataset.armed) {
            delete runb.dataset.armed;
            runb.textContent = 'Run a card pass now';
            runb.style.color = '';
          }
        }, 4000);
        return;
      }
      delete runb.dataset.armed; runb.style.color = '';
      runb.disabled = true; runb.textContent = 'Running…';
      say.textContent = '';
      post('run-autofire').then((j) => {
        runb.disabled = false; runb.textContent = 'Run a card pass now';
        /* The runner's own words, refusal included -- refusing IS the common and
           correct outcome, and paraphrasing it into "done" would be the lie. */
        say.textContent = (j && j.output
          ? String(j.output).trim().split('\n').pop()
          : 'no output').slice(0, 200);
      }).catch(() => {
        runb.disabled = false; runb.textContent = 'Run a card pass now';
        say.textContent = 'could not reach the companion';
      });
    };
    bar.appendChild(halt); bar.appendChild(runb); bar.appendChild(say);
    wrap.appendChild(bar);

    // The "what it did on its own" list used to hang off the bottom of this panel.
    // It moved to the activity rail (2026-08-30): it is PAST tense, and leaving it
    // in the centre column pushed the console — the one thing J types into — below
    // the fold, which is the ordering complaint that prompted the rebuild. The
    // centre answers "what now", the right rail answers "what already happened".
    return wrap;
  }

  /* Gamma's own autonomous fires, rendered for the activity rail. Kept separate
     from the git/commit feed above it because the two answer different questions:
     the feed is what LANDED, this is what Gamma decided to do unprompted. */
  function fires(au) {
    const rows = ((au || {}).recent_fires) || [];
    if (!rows.length) return null;
    const f = el('div'); f.className = 'auto__fires';
    f.innerHTML = '<h4>What Gamma did on its own · last ' + rows.length + ' runs</h4>';
    rows.forEach((r) => {
      const row = el('div'); row.className = 'auto__f';
      const h = G.human.fire(String(r.note || r.task || ''));
      row.title = h.raw;
      row.innerHTML = '<span class="mono">' + esc(String(r.at || '').slice(11, 16)) + '</span>' +
        '<span class="auto__fn">' + esc(h.text) + '</span>' +
        '<span class="auto__fd">' + esc(String(r.drained == null ? '' : r.drained)) + '</span>';
      f.appendChild(row);
    });
    return f;
  }

  function cell(label, html, tone) {
    const c = el('div'); c.className = 'auto__c';
    if (tone) c.setAttribute('data-t', tone);
    c.innerHTML = '<span class="auto__l">' + esc(label) + '</span>' +
      '<div class="auto__v">' + html + '</div>';
    return c;
  }

  /* ---- what happened while he slept ---------------------------------------- */
  function activity(a) {
    const wrap = el('div'); wrap.className = 'feed';
    const act = a || {};
    const sec = act.sections || {};
    if (act.error || !act.total_changes) {
      wrap.appendChild(D.miss('No activity digest',
        act.error ? 'whats_changed.py: ' + act.error : 'setup/scripts/whats_changed.py'));
      return wrap;
    }

    const head = el('div', '<b>' + esc(String(act.total_changes)) + '</b> things happened' +
      (act.since_label ? ' · ' + esc(act.since_label.replace(/^no stored marker -- /, '')) : ''));
    head.className = 'feed__h';
    wrap.appendChild(head);

    const rows = [];
    const push = (kind, when, text, tone, raw) =>
      rows.push({ kind, when, text, tone, raw });

    /* Every row through the humanizer (dossier R2): the glass gets an
       actor-verb sentence, the raw record survives one hover away in title. */
    (((sec.commits || {}).top) || []).slice(0, 14).forEach((c) => {
      const t = String(c.subject || '');
      const auto = /^chore: auto-commit/.test(t);
      if (auto) {
        // machine bookkeeping, labelled rather than hidden -- and translated:
        // "chore: auto-commit 19 strategy/candidates/ changes" is not English.
        const n = (/auto-commit (\d+)/.exec(t) || [])[1];
        push('auto', String(c.date || '').slice(11, 16),
          'Auto-saved research work' + (n ? ' (' + n + ' files)' : ''), null, t);
      } else {
        const h = G.human.commit(t);
        push(h.verb, String(c.date || '').slice(11, 16), h.text, null, h.raw);
      }
    });
    (((sec.known_broken || {}).top) || []).slice(0, 4).forEach((b) => {
      const h = G.human.broken(String(b.text || ''));
      push('broken', String(b.ts || '').slice(11, 16), h.text, 'neg', h.raw);
    });
    (((sec.scheduled_task_failures || {}).top) || []).slice(0, 4).forEach((f) => {
      const h = G.human.task(f.name || f.id || 'task', f.status || 'failed');
      push('task', '', h.text, 'warn', h.raw);
    });

    if (!rows.length) { wrap.appendChild(D.miss('Nothing recorded', 'whats_changed.py')); return wrap; }

    rows.forEach((r) => {
      const n = el('div'); n.className = 'ev';
      if (r.tone) n.setAttribute('data-t', r.tone);
      if (r.kind === 'auto') n.setAttribute('data-auto', '');
      if (r.raw && r.raw !== r.text) n.title = r.raw;
      n.innerHTML = '<span class="ev__k">' + esc(r.kind) + '</span>' +
        '<span class="ev__t">' + esc(r.text) + '</span>' +
        '<span class="ev__w mono">' + esc(r.when || '') + '</span>';
      wrap.appendChild(n);
    });
    return wrap;
  }

  /* ---- the LANES rail ------------------------------------------------------
   * J, 2026-08-30: "wheres the kitchen? ... wheres the futures, wheres the tech
   * analyiss on tickets non spy, etc that should be in activity feed and like 1
   * agent per or somthing".
   *
   * The page had a session roster (who is typing) and a commit feed (what
   * landed), and nothing at all for the firm's standing lines of work. This is
   * that missing middle. One row per lane, and the row leads with STATE because
   * the only question worth answering at a glance is "is this alive".
   *
   * The state comes from each lane's own artefacts, never from whether its
   * scheduled task is enabled — see gamma_lanes.py. A row can therefore read
   * STALE while its tasks are all Ready, which is exactly what the multi-symbol
   * lane looked like the day this shipped, and exactly what a task-derived
   * roster would have drawn green. */
  const LANE_TONE = { WORKING: 'ok', HELD: 'warn', STALE: 'warn',
                      BROKEN: 'neg', ERROR: 'neg', 'NO DATA': null };

  function ago(iso) {
    if (!iso) return '';
    const t = Date.parse(iso);
    if (!isFinite(t)) return '';
    const m = Math.round((Date.now() - t) / 60000);
    if (m < 1) return 'now';
    if (m < 60) return m + 'm';
    const h = Math.round(m / 60);
    return h < 48 ? h + 'h' : Math.round(h / 24) + 'd';
  }

  function lanes(payload) {
    const wrap = el('div'); wrap.className = 'rail__body';
    const rows = ((payload || {}).lanes) || [];
    if (!rows.length) {
      wrap.appendChild(D.miss('No lanes', 'setup/scripts/gamma_lanes.py'));
      return wrap;
    }
    rows.forEach((l) => {
      const n = document.createElement('article'); n.className = 'lane';
      const tone = LANE_TONE[l.state];
      if (tone) n.setAttribute('data-t', tone);
      n.innerHTML =
        '<header class="lane__h">' +
          '<span class="lane__dot"></span>' +
          '<b class="lane__n">' + esc(l.label || l.id || '?') + '</b>' +
          '<span class="lane__k">' + esc(l.kind || '') + '</span>' +
          '<span class="lane__w mono">' + esc(ago(l.last_at)) + '</span>' +
        '</header>' +
        '<div class="lane__s">' + esc(l.state || '?') + '</div>' +
        '<p class="lane__d">' + esc(l.detail || '') + '</p>' +
        (l.doing ? '<p class="lane__do" title="' + esc(l.doing) + '">' +
                     esc(l.doing) + '</p>' : '') +
        '<footer class="lane__f">' +
          '<span class="lane__m mono">' + esc(String(l.metric == null ? '' : l.metric)) + '</span>' +
          '<span class="lane__ml">' + esc(l.metric_label || '') + '</span>' +
        '</footer>';
      wrap.appendChild(n);
    });
    return wrap;
  }

  /* ---- the page ------------------------------------------------------------ */
  function view() {
    const army = D.S.army || {};
    const s = document.createElement('section'); s.className = 'view deskv';

    /* THE CONSOLE SHELL (rebuilt 2026-08-30). J: "why are you not making use of
     * side bars, its all good panels kind of but the ordering os not intuitive
     * for me at all and id rather not scroll".
     *
     * The old desk was one long column — autonomy, then the graph, then a
     * chat/feed split — so every question below the fold cost a scroll, and the
     * three things he checks most were stacked in the order they happened to be
     * built. This is a fixed-height console instead: three columns that each
     * scroll INSIDE themselves, so the page never moves.
     *
     * Column order is by question, not by history:
     *   left   WHAT IS THE FIRM WORKING ON   (lanes — the thing he asked for)
     *   centre WHAT IS GAMMA DOING, AND TALK TO IT  (state + graph + console)
     *   right  WHAT ALREADY HAPPENED         (activity)
     * Present tense in the middle where the eye lands; standing work and past
     * work in the rails on either side. */
    const shell = el('div'); shell.className = 'deskshell';

    /* --- left rail: the lanes --- */
    const L = document.createElement('aside'); L.className = 'rail rail--l';
    L.innerHTML = '<h3 class="rail__t">Lanes' +
      '<span class="rail__s">standing work</span></h3>';
    L.appendChild(lanes((D.S.payload || {}).lanes));

    /* --- centre: Gamma itself, then the console --- */
    const C = el('div'); C.className = 'deskmain';
    C.appendChild(autonomy((D.S.payload || {}).autonomy));
    if (!(army.sessions || []).length) {
      C.appendChild(D.miss('No sessions found', '~/.claude/sessions/*.json'));
    } else {
      C.appendChild(stage(army));
    }
    const chatBox = el('div'); chatBox.className = 'deskmain__chat';
    chatBox.appendChild(G.chat.panel());
    C.appendChild(chatBox);

    /* --- right rail: what happened --- */
    const R = document.createElement('aside'); R.className = 'rail rail--r';
    R.innerHTML = '<h3 class="rail__t">Activity' +
      '<span class="rail__s">while you were away</span></h3>';
    const rbody = el('div'); rbody.className = 'rail__scroll';
    rbody.appendChild(activity((D.S.payload || {}).activity));
    const fr = fires((D.S.payload || {}).autonomy);
    if (fr) rbody.appendChild(fr);
    R.appendChild(rbody);

    shell.appendChild(L); shell.appendChild(C); shell.appendChild(R);
    s.appendChild(shell);
    return s;
  }

  /* ---- keep the desk ALIVE between route changes ---------------------------
   * Found verifying the wire (2026-08-30): the view rendered ONCE, so the org
   * chart froze at load-time state -- two long-dead sessions wore cards while
   * the sessions actually pulsing had none. A dashboard whose roster is a
   * screenshot of load time is the 32-minute-stale payload bug wearing a new
   * face. On every data refresh the org, autonomy strip and lanes rail are
   * rebuilt IN PLACE; the chat pane is deliberately left alone -- rebuilding it
   * would wipe J's conversation mid-typing. */
  function refreshDesk() {
    const root = document.querySelector('.deskv');
    if (!root) return;
    const army = D.S.army || {};
    const oldOrg = root.querySelector('.org, .empty--org');
    if (oldOrg) {
      let next;
      if ((army.sessions || []).length) {
        next = stage(army);
      } else {
        next = D.miss('No sessions found', '~/.claude/sessions/*.json');
        next.classList.add('empty--org');
      }
      oldOrg.replaceWith(next);
    }
    const oldAuto = root.querySelector('.auto');
    if (oldAuto) oldAuto.replaceWith(autonomy((D.S.payload || {}).autonomy));
    const oldLanes = document.querySelector('.rail--l .rail__body');
    if (oldLanes) {
      const next = lanes((D.S.payload || {}).lanes);
      oldLanes.replaceWith(next);
    }
  }
  addEventListener('gamma:data', refreshDesk);

  // _packet: debug affordance -- lets a verification session fire the SMIL
  // mechanism directly instead of waiting for traffic timing to line up.
  G.desk = { view, _packet: packet };
})(window.G = window.G || {});

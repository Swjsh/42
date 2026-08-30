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
  const txt = (x, y, str, fill, size, weight, anchor) => {
    const e = mk('text', {
      x, y, fill: fill || 'var(--ink-2)', 'font-size': size || 12,
      'font-weight': weight || 500, 'text-anchor': anchor || 'start',
      'font-family': 'var(--sans)', 'letter-spacing': '-0.01em',
    });
    e.textContent = str == null ? '' : String(str);
    return e;
  };

  /* SVG <text> neither wraps nor ellipsizes, so an overlong label paints straight
     across its neighbour. Estimate from the font size and cut on a word boundary. */
  function fit(str, px, size, mono) {
    const s = String(str || ''), per = size * (mono ? 0.6 : 0.52);
    if (s.length * per <= px) return s;
    const cap = Math.max(1, Math.floor(px / per) - 1), cut = s.slice(0, cap);
    const sp = cut.lastIndexOf(' ');
    return (sp > cap * 0.6 ? cut.slice(0, sp) : cut).replace(/[ ,;:.\-]+$/, '') + '…';
  }

  const shortType = (t) => t === 'general-purpose' ? 'general'
    : t === 'workflow-subagent' ? 'workflow' : (t || 'agent');

  function stage(army) {
    const sessions = (army.sessions || []).filter((s) => !s.is_orchestrator &&
      s.activity !== 'stale').slice(0, 4);
    const orc = army.orchestrator;
    const workers = army.workers || [];

    const PAD = 24, ORC_H = 84, GAP = 18, TOP = 214, BH = 168;
    const cols = Math.max(1, sessions.length || 1);
    const W = 1000;                               // viewBox units; scales to the box
    const bw = (W - PAD * 2 - GAP * (cols - 1)) / cols;
    const H = sessions.length ? TOP + BH + PAD : ORC_H + PAD * 2;

    const svg = mk('svg', {
      viewBox: '0 0 ' + W + ' ' + H, width: '100%',
      // height is set from the viewBox ratio by CSS aspect-ratio; preserve keeps
      // the strip full-width rather than letterboxing it on a wide card.
      preserveAspectRatio: 'xMidYMid meet', class: 'stage__svg',
    });

    const defs = mk('defs');
    svg.appendChild(defs);

    /* ---- the orchestrator strip ---- */
    const og = mk('g', { class: 'nodein' });
    og.appendChild(mk('rect', {
      x: PAD, y: 16, width: W - PAD * 2, height: ORC_H, rx: 16,
      fill: 'var(--bg-2)', stroke: 'var(--line-2)', 'stroke-width': 1,
    }));
    const grad = mk('linearGradient', { id: 'orcg', x1: '0', y1: '0', x2: '0', y2: '1' });
    grad.appendChild(mk('stop', { offset: '0%', 'stop-color': 'var(--acc-deep)', 'stop-opacity': '.55' }));
    grad.appendChild(mk('stop', { offset: '75%', 'stop-color': 'var(--acc-deep)', 'stop-opacity': '0' }));
    defs.appendChild(grad);
    og.appendChild(mk('rect', {
      x: PAD, y: 16, width: W - PAD * 2, height: ORC_H, rx: 16,
      fill: 'url(#orcg)', 'pointer-events': 'none',
    }));
    const orcLive = (orc && orc.worker_active) || 0;
    og.appendChild(mk('circle', {
      cx: PAD + 28, cy: 46, r: 7, fill: orcLive ? 'var(--live)' : 'var(--ink-3)',
      class: orcLive ? 'beacon' : '',
    }));
    og.appendChild(txt(PAD + 48, 51, orc ? orc.name : '—', 'var(--ink)', 20, 700));
    og.appendChild(txt(PAD + 48 + (orc ? orc.name.length * 12 + 14 : 30), 51,
      'ORCHESTRATOR — your Claude window. The console below is its own session.',
      'var(--acc)', 11.5, 600));
    og.appendChild(txt(PAD + 48, 74,
      fit(orc && orc.title ? orc.title : 'no title yet', W - PAD * 2 - 300, 12.5),
      'var(--ink-4)', 12.5, 500));
    /* Its own load, on its own face — J asked to see context without hunting. */
    if (orc && typeof orc.context_pct === 'number' && orc.context_source !== 'unknown') {
      og.appendChild(txt(W - PAD - 20, 46, Math.round(orc.context_pct) + '% memory',
        orc.context_pct >= 90 ? 'var(--neg)' : (orc.context_pct >= 75 ? 'var(--warn)' : 'var(--ink-3)'),
        12.5, 600, 'end'));
    }
    og.appendChild(txt(W - PAD - 20, 70,
      orcLive ? orcLive + ' agent' + (orcLive === 1 ? '' : 's') + ' running now' : 'no agents running',
      orcLive ? 'var(--live)' : 'var(--ink-4)', 12, 600, 'end'));
    svg.appendChild(og);

    /* ---- a beam per session, then the session card ---- */
    sessions.forEach((s, i) => {
      const L = PAD + i * (bw + GAP), T = TOP, cx = L + bw / 2;
      const y0 = 16 + ORC_H;
      const d = 'M ' + cx + ' ' + y0 + ' C ' + cx + ' ' + ((y0 + T) / 2) + ', ' +
        cx + ' ' + ((y0 + T) / 2) + ', ' + cx + ' ' + T;

      // the rail: present but silent until something moves along it
      svg.appendChild(mk('path', {
        d, fill: 'none', stroke: 'var(--ink)', 'stroke-width': 1, opacity: '.09',
      }));

      // the comet. A per-edge gradient in user space so the dash samples real colour
      // as it travels, rather than a flat stroke sliding along.
      const gid = 'beam' + i;
      const bg = mk('linearGradient', {
        id: gid, gradientUnits: 'userSpaceOnUse', x1: cx, y1: y0, x2: cx, y2: T,
      });
      [['0%', 'var(--live)', '0'], ['18%', 'var(--live)', '.95'],
       ['55%', 'var(--acc)', '.95'], ['100%', 'var(--acc)', '0']]
        .forEach(([o, c, op]) => bg.appendChild(
          mk('stop', { offset: o, 'stop-color': c, 'stop-opacity': op })));
      defs.appendChild(bg);
      const beam = mk('path', {
        d, fill: 'none', stroke: 'url(#' + gid + ')', 'stroke-width': 2.2,
        'stroke-linecap': 'round', class: 'beam',
      });
      // Live sessions get a fast, bright beam; quiet ones a slow dim one, so the
      // motion itself encodes who is actually talking rather than decorating all.
      const live = (s.worker_active || 0) > 0 || s.activity === 'active';
      beam.style.animationDuration = live ? '2.4s' : '6.5s';
      beam.style.animationDelay = (i * 0.5) + 's';
      beam.style.opacity = live ? '1' : '.4';
      svg.appendChild(beam);

      const g = mk('g', { class: 'node nodein' });
      g.style.animationDelay = (140 + i * 70) + 'ms';
      g.appendChild(mk('rect', {
        x: L, y: T, width: bw, height: BH, rx: 14,
        fill: 'var(--bg-1)', stroke: 'var(--line)', 'stroke-width': 1,
      }));
      g.appendChild(mk('circle', {
        cx: L + 22, cy: T + 26, r: 5.5,
        fill: live ? 'var(--live)' : 'var(--ink-4)', class: live ? 'beacon' : '',
      }));
      g.appendChild(txt(L + 38, T + 31, fit(s.title || 'Untitled chat', bw - 60, 14),
        'var(--ink)', 14, 600));
      g.appendChild(txt(L + 38, T + 49, s.name + ' · ' + (s.entrypoint || s.kind || ''),
        'var(--ink-4)', 10.5, 500));

      const liveN = s.worker_active || 0, everN = s.worker_count || 0;
      g.appendChild(txt(L + 18, T + 76,
        liveN ? liveN + ' agent' + (liveN === 1 ? '' : 's') + ' running'
              : (everN ? 'idle · ' + everN + ' finished' : 'no agents'),
        liveN ? 'var(--live)' : 'var(--ink-3)', 11.5, liveN ? 700 : 500));

      // the agents themselves, named — the thing J asked about three times
      const mine = workers.filter((w) => w.session_id === s.session_id)
        .sort((a, b) => (b.active ? 1 : 0) - (a.active ? 1 : 0) ||
          String(b.last_write || '').localeCompare(String(a.last_write || '')));
      mine.slice(0, 3).forEach((w, j) => {
        const ry = T + 98 + j * 17;
        g.appendChild(mk('circle', {
          cx: L + 22, cy: ry - 4, r: 2.8,
          fill: w.active ? 'var(--live)' : 'var(--ink-4)',
        }));
        g.appendChild(txt(L + 32, ry, fit(shortType(w.agent_type), 58, 9.5, true),
          w.active ? 'var(--ink-2)' : 'var(--ink-4)', 9.5, 600));
        g.appendChild(txt(L + 96, ry, fit(w.purpose || w.task || '', bw - 114, 10.5),
          w.active ? 'var(--ink-3)' : 'var(--ink-4)', 10.5, 400));
      });
      if (everN > 3) {
        g.appendChild(txt(L + 32, T + 98 + 3 * 17, '+' + (everN - Math.min(3, mine.length)) +
          ' more', 'var(--ink-4)', 10, 500));
      }

      // memory meter across the foot
      if (typeof s.context_pct === 'number' && s.context_source !== 'unknown') {
        const pct = Math.max(0, Math.min(100, s.context_pct));
        const col = pct >= 90 ? 'var(--neg)' : (pct >= 75 ? 'var(--warn)' : 'var(--acc)');
        const segs = 12, lit = Math.max(1, Math.round((pct / 100) * segs));
        const sw = (bw - 36 - 2 * (segs - 1)) / segs;
        for (let k = 0; k < segs; k++) {
          g.appendChild(mk('rect', {
            x: L + 18 + k * (sw + 2), y: T + BH - 16, width: sw, height: 5, rx: 1,
            fill: k < lit ? col : 'color-mix(in oklch,white 9%,transparent)',
          }));
        }
        g.appendChild(txt(L + bw - 18, T + BH - 22, Math.round(pct) + '%',
          col, 10, 600, 'end'));
      }
      svg.appendChild(g);
    });

    const box = el('div', ''); box.className = 'stage';
    box.appendChild(svg);
    if (!sessions.length) {
      box.appendChild(el('div', 'No other sessions are open — this is the only one running.'))
        .className = 'stage__none';
    }
    return box;
  }

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

    wrap.appendChild(grid);

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

    const fires = au.recent_fires || [];
    if (fires.length) {
      const f = el('div'); f.className = 'auto__fires';
      f.innerHTML = '<h4>What it did on its own, last ' + fires.length + ' runs</h4>';
      fires.forEach((r) => {
        const row = el('div'); row.className = 'auto__f';
        row.innerHTML = '<span class="mono">' + esc(String(r.at || '').slice(11, 16)) + '</span>' +
          '<span class="auto__fn">' + esc(String(r.note || r.task || '').slice(0, 150)) + '</span>' +
          '<span class="auto__fd">' + esc(String(r.drained == null ? '' : r.drained)) + '</span>';
        f.appendChild(row);
      });
      wrap.appendChild(f);
    }
    return wrap;
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
    const push = (kind, when, text, tone) => rows.push({ kind, when, text, tone });

    (((sec.commits || {}).top) || []).slice(0, 14).forEach((c) => {
      const t = String(c.subject || '');
      // auto-commits are noise in a "what did you do" feed; they are machine
      // bookkeeping, not decisions, so they are labelled rather than hidden.
      push(/^chore: auto-commit/.test(t) ? 'auto' : 'shipped',
        String(c.date || '').slice(11, 16), t, null);
    });
    (((sec.known_broken || {}).top) || []).slice(0, 4).forEach((b) => {
      push('broken', String(b.ts || '').slice(11, 16), String(b.text || ''), 'neg');
    });
    (((sec.scheduled_task_failures || {}).top) || []).slice(0, 4).forEach((f) => {
      push('task', '', (f.name || f.id || 'task') + ' — ' + (f.status || 'failed'), 'warn');
    });

    if (!rows.length) { wrap.appendChild(D.miss('Nothing recorded', 'whats_changed.py')); return wrap; }

    rows.forEach((r) => {
      const n = el('div'); n.className = 'ev';
      if (r.tone) n.setAttribute('data-t', r.tone);
      if (r.kind === 'auto') n.setAttribute('data-auto', '');
      n.innerHTML = '<span class="ev__k">' + esc(r.kind) + '</span>' +
        '<span class="ev__t">' + esc(r.text) + '</span>' +
        '<span class="ev__w mono">' + esc(r.when || '') + '</span>';
      wrap.appendChild(n);
    });
    return wrap;
  }

  /* ---- the page ------------------------------------------------------------ */
  function view() {
    const army = D.S.army || {};
    const s = el('section'); s.className = 'view wrap';
    s.innerHTML = '<a class="back" href="#/">‹ Back</a>' +
      '<div class="vhead"><h2 class="vhead__t">The <b>desk</b></h2>' +
      '<p class="vhead__p">Everything Gamma is doing, and everything it did. The ' +
      'orchestrator is on top; a line runs to every session it is working with, and ' +
      'the agents inside each one are named.</p></div>';

    /* Autonomy first: "is it alive and what is it about to do" outranks the
       roster, because the roster is meaningless if the loop is off. */
    s.appendChild(autonomy((D.S.payload || {}).autonomy));

    if (!(army.sessions || []).length) {
      s.appendChild(D.miss('No sessions found', '~/.claude/sessions/*.json'));
    } else {
      s.appendChild(stage(army));
    }

    const split = el('div'); split.className = 'desk__split';
    const left = el('div'); left.className = 'desk__chat';
    left.appendChild(G.chat.panel());
    const right = el('div'); right.className = 'desk__feed';
    right.innerHTML = '<h3 class="desk__ft">While you were away</h3>';
    right.appendChild(activity((D.S.payload || {}).activity));
    split.appendChild(left); split.appendChild(right);
    s.appendChild(split);
    return s;
  }

  G.desk = { view };
})(window.G = window.G || {});

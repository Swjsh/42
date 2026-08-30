/* views.js — every screen except the chat.
 *
 * Ported from the five components J chose on 21st.dev. The ports keep each
 * original's ANATOMY (what sits where, what earns emphasis) and replace its
 * palette and copy with this rig's, because the originals sell a template and
 * this has to report on real money. */
(function (G) {
  'use strict';
  const D = G.data, esc = D.esc, el = D.el;

  const svg = (d, w) => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="' + (w || 2) + '" stroke-linecap="round" stroke-linejoin="round" ' +
    'width="16" height="16" aria-hidden="true">' + d + '</svg>';
  const ARROW = svg('<path d="M7 17 17 7M9 7h8v8"/>');
  const BACK = svg('<path d="M15 18l-6-6 6-6"/>');
  const GO = svg('<path d="M5 12h14M13 6l6 6-6 6"/>');

  /* --- HERO ---------------------------------------------------------------
     The jelly-animated-hero's shape: an eyebrow, a very large ultralight
     headline, a short paragraph, one primary control, and stat panels riding
     the bottom. Those panels are this app's navigation — J asked for hero
     panels instead of a nav rail, with Total Profit opening the calendar. */
  function hero() {
    const wrap = el('div');
    const p = D.profit(), a = D.agents(), c = D.cards();
    const cal = D.calendar();

    const head = el('section', '');
    head.className = 'hero wrap';
    const liveN = a ? Number(a.v) : 0;
    head.innerHTML =
      '<span class="eyebrow rise" style="animation-delay:40ms">' +
        '<span class="eyebrow__tag">' + (liveN ? 'RUNNING' : 'STANDING BY') + '</span>' +
        (liveN ? '<b>' + liveN + '</b> agent' + (liveN === 1 ? '' : 's') + ' working right now'
               : 'the engine is deterministic and never sleeps') +
      '</span>' +
      '<h1 class="hero__h rise" style="animation-delay:110ms">Your desk runs ' +
        '<em>while you sleep.</em></h1>' +
      '<p class="hero__p rise" style="animation-delay:190ms">Gamma trades 0DTE SPY on paper, ' +
        'grades every fill against the ten rules, and spends the night researching what to ' +
        'change next. Everything below is measured, never estimated.</p>' +
      '<div class="hero__act rise" style="animation-delay:260ms">' +
        '<a class="cta" href="#/chat">Talk to the orchestrator ' +
          '<span class="cta__arrow">' + ARROW + '</span></a>' +
        '<a class="cta cta--quiet" href="#/agents">See the agents</a>' +
      '</div>';
    wrap.appendChild(head);

    const panels = el('div');
    panels.className = 'panels wrap rise';
    panels.style.animationDelay = '340ms';

    panels.appendChild(panel({
      href: '#/profit', label: 'Total profit', delta: p ? p.delta : '',
      tone: p ? p.tone : '', value: p ? p.v : null,
      unit: p ? 'net' : '', sub: p ? p.sub : 'analysis/journal/calendar-data.json',
      go: 'Open the calendar', spark: cal ? cal.rows.map((r) => r.net) : null,
    }));
    panels.appendChild(panel({
      href: '#/agents', label: 'Agents running', delta: a ? a.delta : '',
      tone: a ? a.tone : '', value: a ? a.v : null, unit: a ? a.unit : '',
      sub: a ? a.sub : '~/.claude/sessions + the companion', go: 'See what each is doing',
    }));
    panels.appendChild(panel({
      href: '#/cards', label: 'Needs a decision', delta: c ? c.delta : '',
      tone: c ? c.tone : '', value: c ? c.v : null, unit: c ? c.unit : '',
      sub: c ? c.sub : 'automation/state/cards.json', go: 'Review the cards',
    }));
    wrap.appendChild(panels);
    return wrap;
  }

  function panel(o) {
    const a = document.createElement('a');
    a.className = 'panel'; a.href = o.href;
    /* A panel with no number must not pretend: it shows the file it wanted. */
    const val = o.value == null
      ? '<div class="panel__v" style="font-size:19px;font-weight:500;color:var(--ink-4)">no data yet</div>'
      : '<div class="panel__v num">' + esc(o.value) +
        (o.unit ? '<small>' + esc(o.unit) + '</small>' : '') + '</div>';
    a.innerHTML =
      '<div class="panel__k"><span class="panel__label">' + esc(o.label) + '</span>' +
        (o.delta ? '<span class="panel__delta"' + (o.tone ? ' data-t="' + esc(o.tone) + '"' : '') +
          '>' + esc(o.delta) + '</span>' : '') + '</div>' +
      val +
      '<div class="panel__sub">' + esc(o.sub || '') + '</div>' +
      '<span class="panel__go">' + esc(o.go) + GO + '</span>';
    if (o.spark && o.spark.length > 2) a.appendChild(spark(o.spark));
    /* cursor-follow wash — one listener, CSS does the painting */
    a.addEventListener('pointermove', (e) => {
      const r = a.getBoundingClientRect();
      a.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      a.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
    return a;
  }

  /* cumulative equity sparkline — hand-rolled SVG, no chart library */
  function spark(series) {
    const W = 400, H = 38;
    let cum = 0; const pts = series.map((v) => (cum += v));
    const lo = Math.min.apply(null, pts), hi = Math.max.apply(null, pts);
    const span = (hi - lo) || 1;
    const d = pts.map((v, i) =>
      (i ? 'L' : 'M') + ((i / (pts.length - 1)) * W).toFixed(1) + ' ' +
      (H - ((v - lo) / span) * (H - 6) - 3).toFixed(1)).join(' ');
    const up = pts[pts.length - 1] >= 0;
    const col = up ? 'var(--pos)' : 'var(--neg)';
    const n = document.createElement('div');
    n.className = 'panel__spark';
    n.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" ' +
      'width="100%" height="100%" aria-hidden="true">' +
      '<path d="' + d + ' L' + W + ' ' + H + ' L0 ' + H + ' Z" fill="' + col + '" opacity=".10"/>' +
      '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.6" ' +
      'stroke-linejoin="round" opacity=".85"/></svg>';
    return n;
  }

  /* --- shared page furniture ---------------------------------------------- */
  function page(title, lead) {
    const s = el('section'); s.className = 'view wrap';
    s.innerHTML =
      '<a class="back" href="#/">' + BACK + 'Back</a>' +
      '<div class="vhead"><h2 class="vhead__t">' + title + '</h2>' +
      (lead ? '<p class="vhead__p">' + esc(lead) + '</p>' : '') + '</div>';
    return s;
  }

  /* --- PROFIT / CALENDAR (behind Total Profit) ----------------------------- */
  function profit() {
    const cal = D.calendar();
    const s = page('Total <b>profit</b>',
      cal ? 'Net of costs, by trading day. Green finished up, red finished down, and the ' +
            'stronger the colour the bigger the day. Faded squares had no scored trades — ' +
            'an absence, not a flat session.'
          : '');
    if (!cal) { s.appendChild(D.miss('No scored days yet', 'analysis/journal/calendar-data.json')); return s; }

    const stat = (k, v, tone) =>
      '<div class="tile"><div class="tile__k">' + esc(k) + '</div>' +
      '<div class="tile__v num" ' + (tone ? 'style="color:var(--' + tone + ')"' : '') + '>' +
      esc(v) + '</div></div>';
    const band = el('div');
    band.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:var(--s3)';
    band.innerHTML =
      stat('Net', D.money(cal.net), cal.net >= 0 ? 'pos' : 'neg') +
      stat('Scored days', String(cal.days)) +
      stat('Day win rate', cal.wr.toFixed(0) + '%') +
      stat('Best day', D.money(cal.best), 'pos') +
      stat('Worst day', D.money(cal.worst), 'neg');
    s.appendChild(band);

    // arm switcher — the book and each arm, because an aggregate that hides a
    // weak desk behind a strong one is the anti-pattern J named himself.
    const sw = el('div');
    sw.style.cssText = 'margin-top:var(--s5);display:flex;gap:8px;flex-wrap:wrap';
    cal.arms.forEach((n) => {
      const b = document.createElement('button');
      b.className = 'chip'; b.textContent = n;
      if (n === cal.arm) { b.style.borderColor = 'var(--acc-line)'; b.style.color = 'var(--ink)'; }
      b.onclick = () => { G.render('profit', n); };
      sw.appendChild(b);
    });
    s.appendChild(sw);

    s.appendChild(calendarGrid(cal));
    return s;
  }

  /* --- THE CALENDAR, behind Total Profit -----------------------------------
     J asked for "the calendar page" behind Total Profit; the first pass shipped a
     day-bar strip, which answers "how big were the days" but not "WHICH days" --
     and the day of the week is half of what a 0DTE desk reads a month for.

     THE RAMP IS CLAMPED, deliberately. One +$2,813 day against a median near zero
     would flatten every other day to the same near-black if the scale were linear
     to the max, so the month would look like one green square and 38 empty ones.
     The clamp is the 80th percentile of |net|, days past it are drawn at full
     intensity, and the true extremes are annotated underneath -- the same contract
     the cockpit calendar already honours, so the two surfaces cannot disagree. */
  /* A day cell is about 50px wide, so -$2,067 clipped to "-$2,06" -- worse than
     useless, because a clipped number still reads as a number. Thousands collapse to
     one decimal; the exact figure is in the cell's title and in the stat band above. */
  function compactMoney(n) {
    const a = Math.abs(n), sign = n < 0 ? '-' : '';
    if (a >= 1000) return sign + '$' + (a / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
    return sign + '$' + Math.round(a);
  }

  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December'];

  function calendarGrid(cal) {
    const wrap = el('div');
    wrap.style.cssText = 'margin-top:var(--s5);display:grid;gap:var(--s5);' +
      'grid-template-columns:repeat(auto-fit,minmax(300px,1fr))';

    const by = {};
    cal.rows.forEach((r) => {
      const key = r.date.slice(0, 7);
      (by[key] = by[key] || {})[r.date] = r;
    });

    // clamp = 80th percentile of |net|, so a single outlier cannot own the scale
    const mags = cal.rows.map((r) => Math.abs(r.net)).sort((a, b) => a - b);
    const clamp = mags[Math.floor(mags.length * 0.8)] || mags[mags.length - 1] || 1;

    Object.keys(by).sort().forEach((key, mi) => {
      const [y, m] = key.split('-').map(Number);
      const first = new Date(y, m - 1, 1);
      const days = new Date(y, m, 0).getDate();
      // Monday-first: a trading week reads Mon-Fri, so a Sunday-first grid puts the
      // weekend in the middle of the eye's path for no reason.
      const lead = (first.getDay() + 6) % 7;

      const box = el('div');
      box.style.cssText = 'padding:var(--s5);border-radius:var(--r2);background:var(--bg-1);' +
        'border:1px solid var(--line);animation:rise .5s var(--jelly) backwards;' +
        'animation-delay:' + (mi * 90) + 'ms';
      const monthNet = Object.values(by[key]).reduce((n, r) => n + r.net, 0);
      box.innerHTML =
        '<div style="display:flex;align-items:baseline;gap:10px;margin-bottom:var(--s4)">' +
          '<b style="font-size:15px;letter-spacing:-.02em">' + MONTHS[m - 1] + ' ' + y + '</b>' +
          '<span class="num" style="margin-left:auto;font-size:14px;font-weight:600;color:var(--' +
            (monthNet >= 0 ? 'pos' : 'neg') + ')">' + D.money(monthNet) + '</span>' +
        '</div>';

      const grid = el('div'); grid.className = 'cal';
      ['M', 'T', 'W', 'T', 'F', 'S', 'S'].forEach((d, i) => {
        const h = el('div', d); h.className = 'cal__hd';
        h.style.gridColumn = String(i + 1);
        grid.appendChild(h);
      });
      for (let i = 0; i < lead; i++) grid.appendChild(el('div'));

      for (let d = 1; d <= days; d++) {
        const iso = key + '-' + String(d).padStart(2, '0');
        const row = by[key][iso];
        const cell = el('div'); cell.className = 'cal__d';
        if (!row) {
          // A day with no scored trades is NOT a zero day -- it is an absence, and
          // painting it neutral-green would invent a flat session that never happened.
          cell.style.opacity = '.32';
          cell.innerHTML = '<span class="cal__n">' + d + '</span>';
        } else {
          const t = Math.min(1, Math.abs(row.net) / clamp);
          const hue = row.net >= 0 ? 'var(--pos)' : 'var(--neg)';
          /* ALPHA, not a mix toward the card colour. Mixing a bright green
             (oklch 72% .19 152) toward near-black drags lightness down through a
             low-light mid-chroma region that renders OLIVE -- every winning day
             under about $600 read brown. Compositing the same hue at partial alpha
             over the card keeps the hue and only varies presence. */
          cell.style.background = 'color-mix(in oklch,' + hue + ' ' +
            (14 + t * 58).toFixed(0) + '%,transparent)';
          cell.style.borderColor = 'color-mix(in oklch,' + hue + ' ' +
            (24 + t * 40).toFixed(0) + '%,transparent)';
          cell.innerHTML = '<span class="cal__n">' + d + '</span>' +
            '<span class="cal__v num" style="color:' +
              (t > 0.45 ? 'var(--ink)' : 'var(--ink-2)') + '">' +
              esc(compactMoney(row.net)) + '</span>';
          cell.title = iso + '  ' + D.money(row.net) + '  ·  ' + row.trades +
            ' trade' + (row.trades === 1 ? '' : 's');
        }
        grid.appendChild(cell);
      }
      box.appendChild(grid);
      wrap.appendChild(box);
    });

    const note = el('div');
    note.className = 'srcrow';
    note.style.gridColumn = '1/-1';
    note.innerHTML = 'Colour is clamped at ' + esc(D.money(clamp).replace('+', '')) +
      ' so one outlier cannot flatten the month · true range ' +
      '<b style="color:var(--neg)">' + esc(D.money(cal.worst)) + '</b> to ' +
      '<b style="color:var(--pos)">' + esc(D.money(cal.best)) + '</b> · ' +
      'faded days had no scored trades · <span class="mono">' +
      'analysis/journal/calendar-data.json</span>';
    wrap.appendChild(note);
    return wrap;
  }

  /* --- ACTION CARDS (prediction-market-card port) --------------------------- */
  function cards() {
    const c = D.cards();
    const s = page('Needs a <b>decision</b>',
      'Ranked worst first. Each card names the file that raised it and what firing it ' +
      'would actually run.');
    if (!c) { s.appendChild(D.miss('No open cards', 'automation/state/cards.json')); return s; }
    const grid = el('div'); grid.className = 'cards';
    c.list.forEach((card, i) => grid.appendChild(cardNode(card, i)));
    s.appendChild(grid);
    return s;
  }

  function cardNode(c, i) {
    const sev = D.cardSev(c);
    const n = el('article'); n.className = 'card rise';
    n.style.animationDelay = Math.min(i * 45, 400) + 'ms';
    const age = c.source_age_h == null ? '—'
      : (c.source_age_h < 1 ? Math.round(c.source_age_h * 60) + 'm'
        : (c.source_age_h < 48 ? c.source_age_h.toFixed(0) + 'h'
          : Math.round(c.source_age_h / 24) + 'd'));
    const why = Array.isArray(c.why) ? (c.why[0] || '') : String(c.why || '');
    n.innerHTML =
      '<div class="card__top">' +
        '<span class="tag" data-sev="' + sev + '">#' + (c.rank || i + 1) + '</span>' +
        '<span class="tag">' + esc(D.cardKind(c)) + '</span>' +
        '<span class="card__age mono">' + esc(age) + '</span>' +
      '</div>' +
      '<h3 class="card__h">' + esc(String(c.title || '').slice(0, 130)) + '</h3>' +
      '<div class="card__band">' +
        '<div class="card__stat"><b>Model</b><i>' + esc(c.model || '—') + '</i></div>' +
        '<div class="card__stat"><b>Can auto-run</b><i style="color:var(--' +
          (c.autofire_safe ? 'pos' : 'ink-3') + ')">' + (c.autofire_safe ? 'yes' : 'no') + '</i></div>' +
        '<div class="card__stat"><b>Gate</b><i>' + (c.gated ? 'held' : 'open') + '</i></div>' +
      '</div>' +
      '<div class="card__foot">' +
        '<span class="card__why" title="' + esc(why) + '">' + esc(why.slice(0, 90)) + '</span>' +
        '<button class="card__fire" type="button">Fire</button>' +
      '</div>' +
      '<div class="card__rail" data-sev="' + sev + '"></div>';
    /* Two-step confirm. Firing spawns a real Claude session that edits this repo,
       so a single stray click must never be enough. */
    const btn = n.querySelector('.card__fire');
    btn.onclick = () => {
      if (!btn.dataset.armed) {
        btn.dataset.armed = '1'; btn.textContent = 'Confirm?';
        setTimeout(() => {
          if (btn.dataset.armed) { delete btn.dataset.armed; btn.textContent = 'Fire'; }
        }, 4000);
        return;
      }
      delete btn.dataset.armed;
      btn.textContent = 'Sending…'; btn.disabled = true;
      G.fireCard(c, btn);
    };
    return n;
  }

  /* --- AGENTS (dashboard-1 port) -------------------------------------------- */
  function agents() {
    const a = (D.S.army || {});
    const ss = (a.sessions || []);
    const s = page('The <b>agents</b>',
      'One card per Claude session on this box. The rows inside a card are its ' +
      'subagents — what each one is, which model it runs on, and what it was told to do.');
    if (!ss.length) { s.appendChild(D.miss('No sessions found', '~/.claude/sessions/*.json')); return s; }
    const workers = a.workers || [];
    const grid = el('div'); grid.className = 'agrid';
    ss.filter((x) => x.activity !== 'stale')
      .sort((x, y) => (y.worker_active || 0) - (x.worker_active || 0) ||
                      (y.worker_count || 0) - (x.worker_count || 0))
      .forEach((sess, i) => grid.appendChild(agentCard(sess, workers, i)));
    s.appendChild(grid);
    return s;
  }

  function agentCard(sess, workers, i) {
    const mine = workers.filter((w) => w.session_id === sess.session_id)
      .sort((x, y) => (y.active ? 1 : 0) - (x.active ? 1 : 0) ||
        String(y.last_write || '').localeCompare(String(x.last_write || '')));
    const live = sess.worker_active || 0, ever = sess.worker_count || 0;
    const pct = (typeof sess.context_pct === 'number' &&
      sess.context_source && sess.context_source !== 'unknown') ? sess.context_pct : null;
    const n = el('article'); n.className = 'ac rise';
    n.style.animationDelay = Math.min(i * 60, 400) + 'ms';

    const segs = 16, lit = pct == null ? 0 : Math.max(1, Math.round((pct / 100) * segs));
    const tone = pct == null ? '' : (pct >= 90 ? 'neg' : (pct >= 75 ? 'warn' : 'true'));
    let bar = '';
    for (let k = 0; k < segs; k++) {
      bar += '<i' + (k < lit ? ' data-on' + (tone && tone !== 'true' ? '="' + tone + '"' : '') : '') + '></i>';
    }
    const kind = sess.is_orchestrator ? 'you are here'
      : (/cron|schedule|task/i.test(String(sess.entrypoint || '') + sess.kind) ? 'scheduled'
        : 'your window');

    n.innerHTML =
      '<div class="ac__head">' +
        '<span class="ac__dot"' + (live || sess.activity === 'active' ? ' data-on' : '') + '></span>' +
        '<span class="ac__t"><h3>' + esc(sess.title || 'Untitled chat') + '</h3>' +
          '<p>' + esc(sess.name) + ' · ' + esc(sess.entrypoint || sess.kind || 'session') + '</p></span>' +
        '<span class="ac__kind">' + esc(kind) + '</span>' +
      '</div>' +
      '<div class="ac__tiles">' +
        '<div class="tile' + (live ? ' tile--lit' : '') + '">' +
          '<div class="tile__k"><span>Running now</span></div>' +
          '<div class="tile__v num">' + live + '<small>' + (live === 1 ? 'agent' : 'agents') + '</small></div>' +
        '</div>' +
        '<div class="tile"><div class="tile__k"><span>Memory used</span></div>' +
          '<div class="tile__v num">' + (pct == null ? '—' : Math.round(pct) + '<small>%</small>') + '</div>' +
          '<div class="seg">' + bar + '</div>' +
        '</div>' +
      '</div>';

    const rows = el('div'); rows.className = 'ac__rows';
    if (!mine.length) {
      rows.innerHTML = '<div class="arow"><span class="arow__d"></span>' +
        '<span class="arow__p">' + (ever ? 'no agents running · ' + ever + ' finished earlier'
                                         : 'no agents') + '</span></div>';
    } else {
      mine.slice(0, 4).forEach((w) => {
        const r = el('div'); r.className = 'arow';
        if (w.active) r.setAttribute('data-on', '');
        const tag = (w.agent_type === 'general-purpose' ? 'general'
          : w.agent_type === 'workflow-subagent' ? 'workflow' : (w.agent_type || 'agent')) +
          (w.model ? '·' + w.model : '');
        r.innerHTML = '<span class="arow__d"' + (w.active ? ' data-on' : '') + '></span>' +
          '<span class="arow__tag mono">' + esc(tag) + '</span>' +
          '<span class="arow__p">' + esc(w.purpose || w.task || '') + '</span>';
        r.title = tag + ' · ' + (w.active ? 'running' : 'finished') + '\n' + (w.task || '');
        rows.appendChild(r);
      });
      if (ever > mine.slice(0, 4).length) {
        const more = el('div'); more.className = 'arow';
        more.innerHTML = '<span class="arow__d"></span><span class="arow__p">+' +
          (ever - Math.min(4, mine.length)) + ' more this session</span>';
        rows.appendChild(more);
      }
    }
    n.appendChild(rows);

    const banner = el('div'); banner.className = 'ac__banner';
    banner.innerHTML = '<p>' + (live ? 'Working right now' : 'Idle — nothing running') +
      '</p><a class="ghost" href="#/chat">Ask the orchestrator</a>';
    n.appendChild(banner);
    return n;
  }

  /* --- SIGN IN (sign-in-page port) ------------------------------------------ */
  function signin() {
    const s = el('section'); s.className = 'auth';
    const p = D.profit(), cal = D.calendar();
    s.innerHTML =
      '<div class="auth__art"><canvas id="authart"></canvas>' +
        '<div class="auth__artin">' +
          '<h2>An options desk that <em>keeps its own books.</em></h2>' +
          '<p>Every fill graded against the ten rules. Every claim carries the file it ' +
            'came from. Nothing on this page is estimated.</p>' +
          '<div class="auth__stats">' +
            '<span class="auth__stat"><b class="num">' +
              (cal ? D.money(cal.net) : '—') + '</b><span>net, paper</span></span>' +
            '<span class="auth__stat"><b class="num">' +
              (cal ? cal.days : '—') + '</b><span>scored days</span></span>' +
            '<span class="auth__stat"><b class="num">' +
              (cal ? cal.wr.toFixed(0) + '%' : '—') + '</b><span>day win rate</span></span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<div class="auth__form"><div class="auth__box">' +
        '<h1>Welcome back</h1>' +
        '<p class="sub">Sign in to your desk.</p>' +
        '<form id="authform" novalidate>' +
          '<div class="field"><label for="em">Email address</label>' +
            '<input id="em" type="email" autocomplete="email" placeholder="you@example.com"></div>' +
          '<div class="field"><label for="pw">Password</label>' +
            '<input id="pw" type="password" autocomplete="current-password" placeholder="••••••••"></div>' +
          '<div class="auth__row"><label style="display:flex;gap:8px;align-items:center">' +
            '<input type="checkbox" style="accent-color:var(--acc)"> Remember me</label>' +
            '<a href="#/">Forgot password?</a></div>' +
          '<button class="cta auth__sub" type="submit">Sign in</button>' +
        '</form>' +
        '<div class="auth__or">or</div>' +
        '<div class="oauth">' +
          '<button type="button" data-p="google">' + GOOGLE + 'Google</button>' +
          '<button type="button" data-p="github">' + GITHUB + 'GitHub</button>' +
        '</div>' +
        '<p class="auth__note" id="authnote"><b>Not wired yet.</b> These controls are the ' +
          'real sign-in surface, but no identity provider is configured, so nothing here ' +
          'can authenticate anyone. Firebase needs a project id and web key before this ' +
          'does anything — until then it would be a login box that lies.</p>' +
        '<p class="auth__note"><a href="#/" style="color:var(--acc)">Continue without ' +
          'signing in →</a> · single-user on this box today; accounts land when Firebase does.</p>' +
      '</div></div>';
    return s;
  }

  const GOOGLE = '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path fill="#4285F4" d="M22.6 12.2c0-.7-.1-1.4-.2-2H12v3.9h6a5 5 0 0 1-2.2 3.3v2.7h3.6c2-1.9 3.2-4.7 3.2-7.9z"/>' +
    '<path fill="#34A853" d="M12 23c2.9 0 5.4-1 7.2-2.6l-3.6-2.7c-1 .7-2.2 1-3.6 1-2.8 0-5.2-1.9-6-4.4H2.3v2.8A11 11 0 0 0 12 23z"/>' +
    '<path fill="#FBBC05" d="M6 14.3a6.6 6.6 0 0 1 0-4.2V7.3H2.3a11 11 0 0 0 0 9.8L6 14.3z"/>' +
    '<path fill="#EA4335" d="M12 5.4c1.6 0 3 .5 4.1 1.6l3.1-3.1A11 11 0 0 0 2.3 7.3L6 10.1c.8-2.5 3.2-4.7 6-4.7z"/></svg>';
  const GITHUB = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
    '<path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1.1-.7 0-.7 0-.7 1.2.1 1.9 1.2 1.9 1.2 1.1 1.9 2.9 1.3 3.6 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.7 1.7.3 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .5z"/></svg>';

  G.views = { hero, profit, cards, agents, signin, page };
})(window.G = window.G || {});

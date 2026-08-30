/* data.js — the app's only source of facts.
 *
 * Everything rendered here comes from payload.json (written by
 * setup/scripts/gamma_home.py, same object the cockpit renders) plus the
 * companion's live /api/army. Nothing is computed twice and nothing is invented:
 * a missing source renders a named empty state rather than a plausible default.
 * That rule is why this file exposes `miss()` and never a fallback number. */
(function (G) {
  'use strict';

  const S = { payload: null, army: null, err: null, at: 0 };

  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

  const el = (cls, html) => {
    const d = document.createElement('div');
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    return d;
  };

  /* A named absence. The whole point: the page must say WHICH file it wanted. */
  const miss = (what, where) =>
    el('empty', '<b>' + esc(what) + '</b>No data yet — expected <span class="mono">' +
      esc(where) + '</span>. Nothing is being guessed here.');

  async function load() {
    try {
      const r = await fetch('../payload.json?t=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error('payload ' + r.status);
      S.payload = await r.json();
      S.at = Date.now();
      S.err = null;
      S.up = true;
    } catch (e) {
      /* The companion is down, or the payload has never been generated. Either way
         the app keeps whatever it last had and SAYS the numbers are from then --
         it must never silently present a stale figure as current, and it must never
         blank a view it could still draw. */
      S.err = String((e && e.message) || e);
      S.up = false;
    }
    /* The session/worker ROSTER lives in the payload. /api/army is NOT a roster
       endpoint -- it returns {ok, rows, cursor}, a delta feed of pulses since a
       cursor -- and assigning it here clobbered the real roster with an object
       that has no `sessions`, so the Agents panel read "no data yet" while the
       data sat in memory. Verified against the live endpoint 2026-08-30. */
    S.army = (S.payload || {}).army || null;

    /* LIVE OVERLAY. payload.json is only rewritten when gamma_home.py runs on its
       schedule, and that task is disabled during quiet hours -- measured at 32
       minutes stale while this polled twice a minute. The roster and the autonomy
       state are the two things that change minute to minute, so they come fresh from
       the companion and overwrite the baked copies. Failure is silent BY DESIGN here
       and only here: the payload copy is a real answer, just an older one, and
       S.live_at records which it is so the page can say so. */
    try {
      const tok = (document.querySelector('meta[name="gamma-token"]') || {}).content;
      const r = await fetch('/api/desk', { cache: 'no-store',
        headers: tok ? { 'x-gamma-token': tok } : {} });
      if (r.ok) {
        const j = await r.json();
        if (j && j.ok) {
          if (j.army) S.army = j.army;
          if (j.autonomy && S.payload) S.payload.autonomy = j.autonomy;
          // Lanes ride the same live slice: a lane row exists to say whether a
          // lane is alive RIGHT NOW, and that answer is worthless at payload age.
          if (j.lanes && S.payload) S.payload.lanes = j.lanes;
          // The trading slice. Rides the live path rather than the baked payload for the
          // same reason as the others, only more so: an equity or a position served at
          // payload age is not stale data, it is a wrong answer to "am I in something".
          if (j.glass && S.payload) S.payload.glass = j.glass;
          // DURABLE half of a card's history: that it ran at all, from the ledger,
          // which survives a companion restart. The in-memory registry below adds
          // HOW it went, and only for runs still in memory.
          G.cardRunsDurable = j.card_runs || {};
          S.live_at = Date.now();
        }
      }
      /* The companion's task registry, keyed by the card that spawned each run.
         This is what lets a card say "ran 12:19, still open" instead of showing a
         live-looking Run button over work that already happened. Cheap (in-memory
         on the server) and independently failable: no registry just means the
         cards fall back to their unrun appearance, never to a wrong claim. */
      try {
        const r2 = await fetch('/api/state', { cache: 'no-store',
          headers: tok ? { 'x-gamma-token': tok } : {} });
        if (r2.ok) {
          const st = await r2.json();
          const c = (st && st.claude) || {};
          const byCard = {};
          [].concat(c.running || [], c.recent || []).forEach(function (t) {
            if (t && t.card_id && !byCard[t.card_id]) byCard[t.card_id] = t;
          });
          /* SESSION -> JOB. The companion knows which Claude session is running
             which task (sessionId <-> card_id <-> task), and the org card was
             printing "Untitled chat" over a session actively root-causing a
             STATUS.md entry. Every fact needed to name it was one join away. */
          const jobs = {};
          [].concat(c.running || [], c.recent || []).forEach(function (t) {
            if (!t || !t.sessionId) return;
            const prev = jobs[t.sessionId];
            // a RUNNING job always wins over a finished one for the same session
            if (prev && prev.status === 'running' && t.status !== 'running') return;
            jobs[t.sessionId] = {
              id: t.id, task: t.task, card_id: t.card_id || null,
              model: t.model, status: t.status, ok: t.ok,
              started: t.started, finished: t.finished,
              lastStep: t.lastStep, lastTool: t.lastTool, origin: t.origin,
            };
          });
          G.sessionJobs = jobs;

          // Merge: durable says IT RAN (survives restarts), memory says HOW IT WENT.
          // A card whose run is only in the ledger shows "ran <time>" with no
          // outcome rather than pretending it never happened.
          const merged = {};
          Object.keys(G.cardRunsDurable || {}).forEach(function (cid) {
            const d0 = G.cardRunsDurable[cid];
            merged[cid] = { id: d0.id, started: d0.ts, finished: d0.ts,
                            status: 'done', ok: null, fromLedger: true };
          });
          Object.keys(byCard).forEach(function (cid) { merged[cid] = byCard[cid]; });
          G.cardRuns = merged;
        }
      } catch (_) { /* cards simply show as unrun */ }
    } catch (_) { /* fall back to the baked copy, which is old but true */ }
    /* Announce every load so the chrome reacts to THIS load rather than to the next
       poll tick. Polling for the answer meant the offline banner could linger up to
       30s after the companion came back -- a stale "we are down" is the same class
       of lie as a stale number. */
    try { dispatchEvent(new CustomEvent('gamma:data', { detail: { up: S.up } })); }
    catch (_) { /* CustomEvent is ancient; a failure here must not break loading */ }
    return S;
  }

  /* ---- derived readouts. Each returns {v, sub, delta, tone} or null. -------
     null means "no honest number exists", and the caller renders miss(). */

  function profit() {
    const desks = ((S.payload || {}).desks || {}).desks || [];
    const spy = desks.find((d) => d.id === 'spy-0dte');
    if (!spy || !spy.metric) return null;
    const m = String(spy.metric);                       // e.g. "+$1,815 net"
    const n = parseFloat(m.replace(/[^0-9.\-]/g, ''));
    const neg = /^-|\-\$/.test(m);
    return {
      v: m.replace(/\s*net$/, ''),
      sub: String(spy.sub || ''),
      tone: isNaN(n) ? '' : (neg ? 'neg' : 'pos'),
      delta: spy.chip || '',
      raw: n,
    };
  }

  function agents() {
    const a = S.army || {};
    const ss = a.sessions || [];
    if (!ss.length) return null;
    const live = ss.reduce((n, s) => n + (s.worker_active || 0), 0);
    const ever = ss.reduce((n, s) => n + (s.worker_count || 0), 0);
    const chats = ss.filter((s) => s.activity === 'active').length;
    return {
      v: String(live), unit: live === 1 ? 'agent' : 'agents',
      sub: chats + ' chat' + (chats === 1 ? '' : 's') + ' working · ' + ever + ' finished earlier',
      delta: live ? 'LIVE' : '', tone: live ? 'live' : '',
    };
  }

  /* A card carries no `severity` field — verified against the live payload. Its
     urgency has to be read off what IS there: the title's own RED/YELLOW verdict
     (health checks write it), and `gated`, which means a human bar stands in the
     way. Deriving beats inventing a field the producer never wrote. */
  function cardSev(c) {
    const t = String(c.title || '');
    if (/\bRED\b|CRITICAL|FAIL/i.test(t)) return 'red';
    if (/\bYELLOW\b|STALE|WARN/i.test(t)) return 'amber';
    return c.gated ? 'amber' : 'act';
  }
  /* Its label is the file that raised it: automation/overnight/STATUS.md -> STATUS. */
  function cardKind(c) {
    const base = String(c.source_path || '').split(/[\\/]/).pop() || 'card';
    return base.replace(/\.[a-z]+$/i, '').replace(/[_-]/g, ' ').toUpperCase().slice(0, 22);
  }

  function cards() {
    const c = ((S.payload || {}).cards || {}).cards || [];
    if (!c.length) return null;
    const red = c.filter((x) => cardSev(x) === 'red').length;
    return {
      v: String(c.length), unit: c.length === 1 ? 'to review' : 'to review',
      sub: red ? red + ' need attention first' : 'nothing critical open',
      delta: red ? red + ' RED' : '', tone: red ? 'neg' : '',
      list: c.slice().sort((a, b) => (a.rank || 99) - (b.rank || 99)),
    };
  }

  /* Calendar: the surface behind Total Profit. Shape is
     {views:{<arm>:{days:{'YYYY-MM-DD':{g,n,t}}}}} with a BOOK view across arms.
     `n` is NET (after costs) and is the only number worth showing. */
  function calendar(arm) {
    const cal = (S.payload || {}).calendar || {};
    const views = cal.views || {};
    const names = Object.keys(views);
    if (!names.length) return null;
    const pick = (arm && views[arm]) ? arm : (views.BOOK ? 'BOOK' : names[0]);
    const days = (views[pick] || {}).days || {};
    const rows = Object.keys(days).sort().map((d) => ({
      date: d, net: Number(days[d].n), trades: Number(days[d].t) || 0,
    })).filter((r) => !isNaN(r.net));
    if (!rows.length) return null;
    const net = rows.reduce((n, r) => n + r.net, 0);
    const win = rows.filter((r) => r.net > 0).length;
    return {
      arm: pick, arms: names, rows, net, days: rows.length, wins: win,
      wr: rows.length ? (win / rows.length) * 100 : 0,
      best: Math.max.apply(null, rows.map((r) => r.net)),
      worst: Math.min.apply(null, rows.map((r) => r.net)),
      max: Math.max.apply(null, rows.map((r) => Math.abs(r.net))) || 1,
    };
  }

  const money = (n) => (n < 0 ? '-' : '+') + '$' +
    Math.abs(Math.round(n)).toLocaleString('en-US');

  G.data = { S, load, esc, el, miss, profit, agents, cards, calendar, cardSev, cardKind, money };
})(window.G = window.G || {});

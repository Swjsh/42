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
    } catch (e) {
      S.err = String(e && e.message || e);
    }
    /* The session/worker ROSTER lives in the payload. /api/army is NOT a roster
       endpoint -- it returns {ok, rows, cursor}, a delta feed of pulses since a
       cursor -- and assigning it here clobbered the real roster with an object
       that has no `sessions`, so the Agents panel read "no data yet" while the
       data sat in memory. Verified against the live endpoint 2026-08-30. */
    S.army = (S.payload || {}).army || null;
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

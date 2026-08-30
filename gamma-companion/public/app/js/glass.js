/* glass.js — the TRADING half of the single pane of glass.
 *
 * J (2026-08-30): "make my dashboard like single pane of glass ai trading command
 * center". Before this file the desk rendered 3 of 18 payload sections and dropped
 * every trading one — the live DOM had hasEquity:false, hasPosition:false.
 *
 * DESIGN LAW OBEYED HERE (dossier, markdown/infra/COCKPIT-DESIGN-SPEC.md):
 *  R8 Refactoring UI — the VALUE is big and bright, the LABEL small and muted. Never
 *     the reverse. Hierarchy comes from size and weight, not from colour alone.
 *  R9 Trading-terminal convention — green/red are RESERVED for P&L direction. Machine
 *     state (alive / held / stale / broken) uses cyan-amber-violet and never borrows
 *     the money colours, so a red thing on this page always means money lost.
 *  R1 — text is HTML at real pixel sizes; SVG carries strokes only. The sparkline has
 *     no <text> in it at all.
 *
 * EVERY NUMBER IS SOURCED OR ABSENT. `dash()` renders an em-dash with the reason in a
 * title attribute rather than a zero. A fabricated 0.00 P&L is indistinguishable from
 * a flat session, which is the one lie this surface must never tell.
 */
(function (G) {
  'use strict';
  const D = G.data, esc = D.esc, el = D.el;

  /* ---- money formatting ---------------------------------------------------
   * Signed, grouped, and always with the sign for a delta — "+1,815" and "-459"
   * read as directions at a glance where "1815" and "-459" read as two unrelated
   * quantities. Whole dollars on the glass: cents are noise at this size and the
   * exact figure lives one hover away. */
  function money(v, opts) {
    const o = opts || {};
    if (v == null || !isFinite(v)) return null;
    const n = Math.abs(v);
    const s = n >= 1000 ? Math.round(n).toLocaleString('en-US')
                        : n.toFixed(o.cents ? 2 : 0);
    const sign = o.signed ? (v > 0 ? '+' : (v < 0 ? '−' : '')) : (v < 0 ? '−' : '');
    return sign + '$' + s;
  }

  /* A named absence. The title says which file was wanted, so "no number" is a
     lead rather than a shrug. */
  function dash(why) {
    return '<span class="g-dash" title="' + esc(why || 'no data') + '">—</span>';
  }

  function tone(v) {
    if (v == null || !isFinite(v) || v === 0) return '';
    return v > 0 ? 'pos' : 'neg';
  }

  /* ---- the sparkline ------------------------------------------------------
   * Cumulative equity curve, vanilla SVG, no text inside. Area fill under the
   * line plus an emphasized endpoint dot — the endpoint is where the eye should
   * land because it is the only value that is true right now.
   *
   * preserveAspectRatio="none" is correct HERE and nowhere else on the page: this
   * is a pure trend shape with no glyphs, so stretching it to the container is
   * exactly right, and it is the reason the strip can be any width. */
  function spark(series, w, h) {
    const pts = (series || []).filter((r) => r && isFinite(r.cum));
    if (pts.length < 2) return null;
    const W = w || 240, H = h || 34, P = 3;
    const vals = pts.map((r) => r.cum);
    let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi === lo) { hi += 1; lo -= 1; }
    const x = (i) => P + (i * (W - P * 2)) / (pts.length - 1);
    const y = (v) => H - P - ((v - lo) / (hi - lo)) * (H - P * 2);

    let d = '';
    pts.forEach((r, i) => { d += (i ? ' L ' : 'M ') + x(i).toFixed(1) + ' ' + y(r.cum).toFixed(1); });
    const area = d + ' L ' + x(pts.length - 1).toFixed(1) + ' ' + (H - P) +
                 ' L ' + x(0).toFixed(1) + ' ' + (H - P) + ' Z';
    const up = vals[vals.length - 1] >= 0;
    const id = 'sk' + Math.abs(Math.round(lo + hi + pts.length));
    const stroke = up ? 'var(--pos)' : 'var(--neg)';

    // The zero line only appears when the curve actually crosses it — a baseline
    // drawn off-scale is decoration that implies a threshold that is not in view.
    let zero = '';
    if (lo < 0 && hi > 0) {
      zero = '<line x1="' + P + '" x2="' + (W - P) + '" y1="' + y(0).toFixed(1) +
             '" y2="' + y(0).toFixed(1) + '" stroke="var(--ink)" stroke-opacity=".18" ' +
             'stroke-dasharray="2 3"/>';
    }
    return '<svg class="g-spark" viewBox="0 0 ' + W + ' ' + H + '" width="' + W +
      '" height="' + H + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">' +
        '<stop offset="0%" stop-color="' + stroke + '" stop-opacity=".30"/>' +
        '<stop offset="100%" stop-color="' + stroke + '" stop-opacity="0"/>' +
      '</linearGradient></defs>' +
      zero +
      '<path d="' + area + '" fill="url(#' + id + ')"/>' +
      '<path d="' + d + '" fill="none" stroke="' + stroke +
        '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + x(pts.length - 1).toFixed(1) + '" cy="' + y(vals[vals.length - 1]).toFixed(1) +
        '" r="2.6" fill="' + stroke + '"/></svg>';
  }

  /* ---- one cell of the strip ---------------------------------------------- */
  function cell(label, valueHtml, sub, cls) {
    return '<div class="g-cell' + (cls ? ' ' + cls : '') + '">' +
      '<span class="g-lab">' + esc(label) + '</span>' +
      '<div class="g-val">' + valueHtml + '</div>' +
      (sub ? '<span class="g-sub">' + sub + '</span>' : '') + '</div>';
  }

  /* ---- POSITION: the first thing a trader looks for ----------------------- */
  function positionCell(p) {
    const st = (p && p.state) || 'unknown';
    const word = st === 'open' ? 'IN A TRADE' : (st === 'flat' ? 'FLAT' : 'UNKNOWN');
    // `unknown` is amber, not red: nobody lost money, the engine simply is not
    // writing the file. Red here would read as a loss (R9).
    const t = st === 'open' ? 'live' : (st === 'flat' ? 'calm' : 'warn');
    const fills = p && p.fills_today;
    const sub = st === 'unknown'
      ? esc(p && p.note ? p.note : 'no fresh position file')
      : (fills ? fills + ' fill' + (fills === 1 ? '' : 's') + ' today' : 'no fills today');
    return cell('Position',
      '<b class="g-state" data-t="' + t + '">' + word + '</b>', sub, 'g-cell--pos');
  }

  /* ---- THE STRIP ---------------------------------------------------------- */
  function strip(glass) {
    const g = glass || {};
    const wrap = el('gstrip');
    if (!g.equity && !g.pnl) {
      wrap.appendChild(D.miss('No trading data', 'setup/scripts/gamma_glass.py'));
      return wrap;
    }
    const eq = g.equity || {}, pnl = g.pnl || {}, bias = g.bias || {}, pos = g.position || {};

    /* BOOK — the biggest number on the page, because it is the score. */
    const bookVal = eq.total != null
      ? '<b class="g-big num">' + esc(money(eq.total)) + '</b>'
      : dash((eq.source || {}).path || 'book-equity-snapshot.json');
    const armCount = (eq.arms || []).length;

    /* NET — all-time, with the curve. */
    const netVal = pnl.net_all != null
      ? '<b class="g-big num" data-t="' + tone(pnl.net_all) + '">' +
          esc(money(pnl.net_all, { signed: true })) + '</b>'
      : dash((pnl.source || {}).path || 'calendar-data.json');
    const sk = spark(pnl.series, 230, 34);

    /* TODAY — None means NO SESSION, which is not a flat day. Saying "$0" on a
       Sunday would be a fabricated fact; the sub-line says which it is. */
    let todayVal, todaySub;
    if (pnl.traded_today && pnl.today != null) {
      todayVal = '<b class="g-big num" data-t="' + tone(pnl.today) + '">' +
        esc(money(pnl.today, { signed: true })) + '</b>';
      todaySub = 'across the book';
    } else {
      todayVal = '<b class="g-big g-quiet">' + (g.market_open ? 'no trade yet' : 'no session') + '</b>';
      todaySub = g.market_open ? 'market open · nothing filled'
        : 'last session ' + esc(pnl.last_session || '—');
    }

    /* THE TAPE — live SPY, and how old it is. An age is not decoration here: a
       price with no age is a price you cannot act on. */
    let tapeVal, tapeSub;
    if (bias.spy != null) {
      const age = bias.tape_age_s;
      const fresh = age != null && age < 120;
      tapeVal = '<b class="g-big num">' + esc(Number(bias.spy).toFixed(2)) + '</b>' +
        (bias.ribbon ? '<span class="g-rib" data-t="' + esc(String(bias.ribbon).toLowerCase()) +
          '">' + esc(bias.ribbon) + '</span>' : '');
      tapeSub = (fresh ? '<i class="g-live"></i>live · ' : 'stale · ') +
        (age != null ? esc(age < 90 ? age + 's old' : Math.round(age / 60) + 'm old') : '') +
        (bias.vix != null ? ' · VIX ' + esc(Number(bias.vix).toFixed(2)) : '');
    } else {
      tapeVal = dash((bias.tape_source || {}).path || 'sight-beacon.json');
      tapeSub = 'beacon not reporting';
    }

    wrap.innerHTML =
      cell('Book', bookVal, armCount ? armCount + ' arms · ' +
        esc(String(eq.as_of || '').slice(11, 16)) + ' ET' : null, 'g-cell--book') +
      cell('Net · all time', netVal,
        (pnl.days ? pnl.days + ' sessions' : null), 'g-cell--net') +
      (sk ? '<div class="g-cell g-cell--spark"><span class="g-lab">Equity curve</span>' +
        '<div class="g-sparkwrap">' + sk + '</div>' +
        '<span class="g-sub">' + esc(pnl.days ? 'last ' + Math.min(60, pnl.days) + ' sessions' : '') +
        '</span></div>' : '') +
      cell('Today', todayVal, todaySub, 'g-cell--today') +
      positionCell(pos) +
      cell('SPY', tapeVal, tapeSub, 'g-cell--tape');
    return wrap;
  }

  /* ---- THE ENGINE'S MIND --------------------------------------------------
   * Bias, the last verdict, and — the part that matters — WHY it held. "HOLD"
   * alone reads as apathy. "HOLD · bear blocked by gate 8, bull by 5/7/10/11"
   * reads as a machine that looked and declined, which is the honest picture and
   * the thing J actually wants to see while the market is open. */
  function mind(glass) {
    const b = (glass || {}).bias || {};
    const wrap = el('gmind');
    if (!b.ok) {
      wrap.appendChild(D.miss('No engine read', 'automation/state/today-bias.json'));
      return wrap;
    }
    const v = String(b.verdict || '').toUpperCase();
    const vt = v === 'HOLD' ? 'calm' : (v ? 'live' : '');
    const blockers = [];
    if (b.bear_blockers && b.bear_blockers.length) blockers.push('bear ' + b.bear_blockers.join('·'));
    if (b.bull_blockers && b.bull_blockers.length) blockers.push('bull ' + b.bull_blockers.join('·'));

    wrap.innerHTML =
      '<header class="gmind__h">' +
        '<span class="gmind__t">Engine</span>' +
        (b.bias ? '<b class="gmind__bias">' + esc(String(b.bias).replace(/-/g, ' ')) + '</b>' : '') +
        (v ? '<span class="gmind__v" data-t="' + vt + '">' + esc(v) + '</span>' : '') +
        (b.engine_health ? '<span class="gmind__hp" data-t="' +
          esc(String(b.engine_health).toLowerCase()) + '">' + esc(b.engine_health) + '</span>' : '') +
      '</header>' +
      (b.why ? '<p class="gmind__why">' + esc(G.human ? G.human.cap(b.why) : b.why) + '</p>' : '') +
      ((b.bear_score != null || b.bull_score != null)
        ? '<div class="gmind__scores">' +
            '<span>bear <b class="num">' + esc(String(b.bear_score == null ? '—' : b.bear_score)) + '</b></span>' +
            '<span>bull <b class="num">' + esc(String(b.bull_score == null ? '—' : b.bull_score)) + '</b></span>' +
            (blockers.length ? '<span class="gmind__blk" title="numbered gates that vetoed the setup">' +
              'blocked · ' + esc(blockers.join(' / ')) + '</span>' : '') +
          '</div>'
        : '') +
      (b.claim ? '<p class="gmind__claim" title="the falsifiable prediction the engine wrote this morning">' +
        esc(b.claim) + '</p>' : '');
    return wrap;
  }

  /* ---- THE ARMS ----------------------------------------------------------
   * One row per arm that holds real money. Bar width encodes net P&L against the
   * biggest absolute mover, so the reader compares arms by SHAPE before reading a
   * single digit — the small-multiples idea applied to five rows. */
  function arms(glass) {
    const g = glass || {};
    const rows = ((g.arms || {}).arms) || [];
    const wrap = el('garms');
    if (!rows.length) {
      wrap.appendChild(D.miss('No arms', 'automation/state/fleet/accounts.json'));
      return wrap;
    }
    const peak = Math.max.apply(null, rows.map((r) => Math.abs(r.net || 0)).concat([1]));
    let html = '';
    rows.forEach((r) => {
      const t = tone(r.net);
      const pct = Math.round((Math.abs(r.net || 0) / peak) * 100);
      const wr = (r.days_traded ? Math.round((r.wins / r.days_traded) * 100) : null);
      html +=
        '<div class="garm" title="' + esc(r.label || r.arm) + '">' +
          '<div class="garm__top">' +
            '<b class="garm__n">' + esc(r.arm) + '</b>' +
            '<span class="garm__eq num">' + (r.equity != null ? esc(money(r.equity)) : dash('no equity row')) + '</span>' +
          '</div>' +
          '<div class="garm__bar"><i data-t="' + t + '" style="width:' + pct + '%"></i></div>' +
          '<div class="garm__bot">' +
            '<span class="garm__net num" data-t="' + t + '">' +
              (r.net != null ? esc(money(r.net, { signed: true })) : dash('never traded')) + '</span>' +
            '<span class="garm__wr">' + (wr != null
              ? esc(wr + '% of ' + r.days_traded + ' days') : '') + '</span>' +
          '</div>' +
        '</div>';
    });
    wrap.innerHTML = html;
    return wrap;
  }

  G.glass = { strip, mind, arms, spark, money, dash, tone };
})(window.G = window.G || {});

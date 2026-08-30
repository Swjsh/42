/* motion.js — motion that ENCODES STATE. Nothing here moves for decoration.
 *
 * From the research spec's motion plan (2026-08-30): every animation on this page
 * maps to a real state change — a number changed, in this direction, by this much;
 * a session just started working; these feed rows arrived together in this order.
 * Anything that would move without a corresponding event is not implemented, and
 * must not be added.
 *
 * TWO RULES THIS FILE OBEYS, both learned the hard way in this repo:
 *
 * 1. NEVER ANIMATE A PROPERTY WHOSE FROM-STATE IS INVISIBLE. During an animation's
 *    active period the animated value applies regardless of fill-mode, and a
 *    SUSPENDED animation (hidden tab, headless capture, a paused compositor) never
 *    leaves that period — so `from{opacity:0}` pins the element at invisible
 *    forever. The P&L sheet shipped with exactly that and measured opacity 0 in
 *    three separate checks. Entrances here start at 0.25 opacity, never 0.
 *
 * 2. A CSS ANIMATION DOES NOT RESTART when a class already present is re-added —
 *    the browser no-ops it, so two consecutive up-ticks would flash once. The fix
 *    is byte-identical keyframe PAIRS, swapped on each tick.
 */
(function (G) {
  'use strict';

  const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- M2: the number roll -------------------------------------------------
   * Interpolates between the previous and next value so the SIZE of a change is
   * readable as motion before the digits are read. tabular-nums in the stylesheet
   * stops the width jitter that would otherwise make this feel broken. */
  function roll(node, from, to, fmt, ms) {
    if (RM || !node || from == null || from === to) {
      if (node && to != null) node.textContent = fmt(to);
      return;
    }
    const dur = ms || 420;

    /* WRITE THE FINAL VALUE FIRST. Measured 2026-08-30: with the tab hidden, rAF is
       suspended, the interpolation never ran, and the cell kept displaying the OLD
       number — a stale figure on a trading surface, which is worse than no animation
       at all and is the exact class of lie this project forbids. The roll then
       overwrites frame by frame from the previous value; if it never runs, the
       correct number is already there. Same principle as the CSS rule above: the
       base state must BE the truth, with motion as pure enhancement. */
    node.textContent = fmt(to);

    let t0 = null;
    function step(ts) {
      // Guard the first frame: on a desynced clock rAF can hand back a timestamp
      // BEFORE the one we captured, which produced a negative progress and briefly
      // rendered -114% for 88% the last time this pattern was written here.
      if (t0 === null) t0 = ts;
      const p = Math.min(1, Math.max(0, (ts - t0) / dur));
      const e = 1 - Math.pow(1 - p, 3);            // easeOutCubic
      node.textContent = fmt(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step);
      else node.textContent = fmt(to);             // land on the exact value, never the lerp
    }
    requestAnimationFrame(step);
  }

  /* ---- M1: the tick flash --------------------------------------------------
   * Byte-identical keyframe pairs, alternated, so a repeated move in the same
   * direction still flashes every time. */
  const flipped = new WeakMap();
  function flash(node, dir) {
    if (RM || !node || !dir) return;
    const n = (flipped.get(node) || 0) ^ 1;
    flipped.set(node, n);
    const cls = 'flash-' + dir + (n + 1);
    node.classList.remove('flash-up1', 'flash-up2', 'flash-dn1', 'flash-dn2');
    // Force a reflow between removal and re-add, or the browser coalesces the two
    // style changes into no change at all and the animation never runs.
    void node.offsetWidth;
    node.classList.add(cls);
    setTimeout(function () { node.classList.remove(cls); }, 760);
  }

  /* ---- the tracker ---------------------------------------------------------
   * Remembers what each named value was on the previous render, so a re-render
   * can tell "changed" from "same" — which is the only thing that licenses any
   * of the motion above. Keyed by a stable name, NOT by node identity, because
   * refreshDesk() replaces the nodes on every data tick. */
  const last = Object.create(null);

  function track(key, value, node, fmt) {
    const prev = last[key];
    last[key] = value;
    if (value == null || !node) return;
    if (prev == null || prev === value) {
      node.textContent = fmt(value);
      return;
    }
    roll(node, prev, value, fmt);
    flash(node, value > prev ? 'up' : 'dn');
  }

  /* Has this value moved since the last render? Used for state words, which flip
     rather than count. */
  function changed(key, value) {
    const prev = last[key];
    last[key] = value;
    return prev !== undefined && prev !== value;
  }

  /* ---- M9: staggered entrance ---------------------------------------------
   * Sets --i on each child so the stylesheet can delay them in order. Capped:
   * past ~10 rows the stagger stops reading as sequence and starts reading as lag. */
  function stagger(nodes, step) {
    if (RM) return;
    const s = step || 45;
    [].slice.call(nodes, 0, 12).forEach(function (n, i) {
      n.style.setProperty('--i', i);
      n.style.animationDelay = (i * s) + 'ms';
    });
  }

  G.motion = { roll, flash, track, changed, stagger, RM };
})(window.G = window.G || {});

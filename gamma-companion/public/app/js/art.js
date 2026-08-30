/* art.js — the sign-in panel's artwork, generated rather than downloaded.
 *
 * The component J picked puts a photograph in the left panel. A stock photo of a
 * person in a VR headset says nothing true about this rig, and the repo forbids
 * remote assets anyway. So the panel draws the only picture that IS about Gamma:
 * a price path with the levels it watches, rendered as an instrument trace.
 *
 * DETERMINISTIC by construction — a seeded PRNG, never Math.random(). Two loads
 * paint the same curve, so a screenshot diff means a real change and the page
 * cannot flash a different "market" every refresh.
 * Self-terminating: the loop stops as soon as the canvas leaves the document. */
(function (G) {
  'use strict';

  /* mulberry32 — small, fast, and stable across engines. */
  function rng(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function signinArt(canvas) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    let W = 0, H = 0, path = [], levels = [];

    function build() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth || 700; H = canvas.clientHeight || 900;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // A random walk with drift and a couple of regime breaks — the shape of a
      // session, not a decorative sine.
      const r = rng(20260830);
      const N = 190;
      let v = H * 0.62;
      path = [];
      for (let i = 0; i < N; i++) {
        const shock = (i === 58 || i === 126) ? (r() - 0.35) * H * 0.13 : 0;
        v += (r() - 0.5) * H * 0.028 + shock - (H * 0.00042);
        v = Math.max(H * 0.16, Math.min(H * 0.86, v));
        path.push({ x: (i / (N - 1)) * W, y: v });
      }
      // Levels = where the path turned more than once, which is what a level IS.
      levels = [H * 0.30, H * 0.52, H * 0.74];
    }

    let t = 0;
    function frame() {
      if (!canvas.isConnected) return;
      ctx.clearRect(0, 0, W, H);

      // ground wash
      const g = ctx.createLinearGradient(0, 0, W * 0.4, H);
      g.addColorStop(0, 'rgba(124,92,255,0.16)');
      g.addColorStop(0.55, 'rgba(20,20,26,0.0)');
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

      // level zones — bands, not hairlines: a level is a ZONE (J, 2026-07-17)
      levels.forEach((y, i) => {
        const band = 13 + i * 3;
        ctx.fillStyle = 'rgba(255,255,255,0.028)';
        ctx.fillRect(0, y - band / 2, W, band);
        ctx.strokeStyle = 'rgba(255,255,255,0.075)';
        ctx.setLineDash([2, 7]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
        ctx.setLineDash([]);
      });

      /* THE WHOLE PATH, ALWAYS. This used to reveal left-to-right over ~150
         frames, which meant a screenshot taken early caught an empty panel --
         the same failure this repo already scarred on with a fading entrance.
         An animation may never own whether content EXISTS; it only decorates
         content that is already there. The head marker below carries the life. */
      const upto = path.length;
      ctx.beginPath();
      ctx.moveTo(path[0].x, path[0].y);
      for (let i = 1; i < upto; i++) ctx.lineTo(path[i].x, path[i].y);

      const stroke = ctx.createLinearGradient(0, 0, W, 0);
      stroke.addColorStop(0, 'rgba(103,232,249,0.85)');
      stroke.addColorStop(0.6, 'rgba(124,92,255,0.95)');
      stroke.addColorStop(1, 'rgba(174,72,255,0.9)');
      ctx.strokeStyle = stroke; ctx.lineWidth = 2; ctx.lineJoin = 'round';
      ctx.shadowColor = 'rgba(124,92,255,0.55)'; ctx.shadowBlur = 16;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // fill under the curve
      ctx.lineTo(path[upto - 1].x, H); ctx.lineTo(path[0].x, H); ctx.closePath();
      const fill = ctx.createLinearGradient(0, H * 0.2, 0, H);
      fill.addColorStop(0, 'rgba(124,92,255,0.20)');
      fill.addColorStop(1, 'rgba(124,92,255,0)');
      ctx.fillStyle = fill; ctx.fill();

      // the head: a marker that sweeps the finished path, so the panel reads as
      // being watched rather than as being drawn
      const head = path[Math.floor((t / 3) % path.length)];
      const pulse = 4.5 + Math.sin(t / 22) * 1.6;
      ctx.beginPath(); ctx.arc(head.x, head.y, pulse + 7, 0, 6.2832);
      ctx.fillStyle = 'rgba(103,232,249,0.13)'; ctx.fill();
      ctx.beginPath(); ctx.arc(head.x, head.y, pulse, 0, 6.2832);
      ctx.fillStyle = 'rgb(103,232,249)'; ctx.fill();

      t += 1;
      if (!G.RM) requestAnimationFrame(frame);
    }

    build();
    addEventListener('resize', () => { build(); }, { passive: true });
    if (G.RM) { t = 400; frame(); return; }   // reduced motion: one finished paint
    requestAnimationFrame(frame);
  }

  G.signinArt = signinArt;
})(window.G = window.G || {});

/*
 * aetherops-ui-kit.js
 * Small vanilla-JS behaviors backing the recipes in ./aetherops-ui-kit.css.
 * Every helper here replaces a motion/react hook from the cited MagicUI (MIT)
 * source with a plain rAF/DOM equivalent — see the matching numbered comment
 * block in aetherops-ui-kit.css for the source URL + what was dropped/kept.
 * No imports, no globals beyond `window.AetherUIKit`. Safe to concatenate
 * verbatim into the single self-contained cockpit HTML (no CDN, no bundler).
 */
(function (global) {
  "use strict";

  /* ---- #7 uk-number-ticker ------------------------------------------------
   * Source parity: magicui number-ticker.tsx uses useSpring(damping:60,
   * stiffness:100) + an IntersectionObserver-driven `useInView(once:true)`
   * gate, writing Intl.NumberFormat text on every spring tick.
   * Port: a single rAF loop with a cubic ease-out (visually matches a
   * critically-damped spring's settle curve closely enough for a KPI number),
   * gated by the same "animate once when it enters the viewport" rule via
   * IntersectionObserver. */
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  function ukAnimateNumberTicker(el, opts) {
    opts = opts || {};
    var value = opts.value != null ? opts.value : parseFloat(el.textContent) || 0;
    var start = opts.startValue != null ? opts.startValue : 0;
    var decimals = opts.decimalPlaces != null ? opts.decimalPlaces : 0;
    var duration = opts.duration != null ? opts.duration : 1200;
    var prefix = opts.prefix || "";
    var suffix = opts.suffix || "";
    var fmt = new Intl.NumberFormat("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });

    function run() {
      var t0 = null;
      function frame(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min(1, (ts - t0) / duration);
        var eased = easeOutCubic(p);
        var current = start + (value - start) * eased;
        el.textContent = prefix + fmt.format(Number(current.toFixed(decimals))) + suffix;
        if (p < 1) requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }

    if ("IntersectionObserver" in global) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) { run(); io.unobserve(el); }
        });
      }, { threshold: 0 });
      io.observe(el);
    } else {
      run();
    }
  }

  /* ---- #9 uk-spotlight-card ------------------------------------------------
   * Source parity: magicui magic-card.tsx tracks pointer x/y with
   * useMotionValue + useSpring(stiffness:250,damping:30) into a radial-gradient
   * painted at that point, resetting off-card on pointerleave/blur/visibility
   * change (their "reset" callback covers 4 cases: enter/leave/global/init).
   * Port: same 4 reset cases, writing plain --uk-mx/--uk-my custom properties
   * (no spring interpolation — the CSS `transition` on the gradient layers in
   * the stylesheet supplies the same "catches up smoothly" feel). */
  function ukInitSpotlightCards(root) {
    var scope = root || document;
    var cards = scope.querySelectorAll(".uk-spotlight-card");

    function setPos(card, x, y) {
      card.style.setProperty("--uk-mx", x + "px");
      card.style.setProperty("--uk-my", y + "px");
    }

    cards.forEach(function (card) {
      card.addEventListener("pointermove", function (e) {
        var rect = card.getBoundingClientRect();
        setPos(card, e.clientX - rect.left, e.clientY - rect.top);
      });
      card.addEventListener("pointerenter", function (e) {
        var rect = card.getBoundingClientRect();
        setPos(card, e.clientX - rect.left, e.clientY - rect.top);
      });
    });

    function resetAll() {
      cards.forEach(function (card) { setPos(card, "50%", "50%"); });
    }
    global.addEventListener("blur", resetAll);
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible") resetAll();
    });
  }

  /* ---- #10 uk-progress-ring --------------------------------------------
   * Source parity: magicui animated-circular-progress-bar.tsx computes
   * `strokeDasharray = (percent * circumference/100) + " " + circumference`
   * on an r=45 circle (circumference = 2*PI*45) and transitions it on change.
   * Port: identical math, applied to whatever radius the markup uses. */
  function ukSetProgressRing(el, percent) {
    var circle = el.querySelector(".uk-progress-ring__value");
    if (!circle) return;
    var r = circle.r.baseVal.value;
    var circumference = 2 * Math.PI * r;
    var clamped = Math.max(0, Math.min(100, percent));
    circle.style.strokeDasharray =
      (clamped / 100) * circumference + " " + circumference;
    var label = el.querySelector(".uk-progress-ring__label");
    if (label) label.textContent = Math.round(clamped) + "%";
  }

  /* ---- #12 uk-ripple generator -------------------------------------------
   * Source parity: magicui ripple.tsx renders `numCircles` stacked divs,
   * size = mainCircleSize + i*70, opacity = mainCircleOpacity - i*0.03,
   * animation-delay = i*0.06s. Port: same formula, DOM built once in JS. */
  function ukBuildRipple(container, opts) {
    opts = opts || {};
    var mainSize = opts.mainCircleSize != null ? opts.mainCircleSize : 210;
    var mainOpacity = opts.mainCircleOpacity != null ? opts.mainCircleOpacity : 0.24;
    var numCircles = opts.numCircles != null ? opts.numCircles : 6;
    container.classList.add("uk-ripple");
    for (var i = 0; i < numCircles; i++) {
      var ring = document.createElement("div");
      ring.className = "uk-ripple__ring";
      var size = mainSize + i * 70;
      ring.style.width = size + "px";
      ring.style.height = size + "px";
      ring.style.opacity = String(Math.max(0, mainOpacity - i * 0.03));
      ring.style.animationDelay = i * 0.15 + "s";
      container.appendChild(ring);
    }
  }

  /* ---- #13 uk-meteors spawner ---------------------------------------------
   * Source parity: magicui meteors.tsx spawns `number` meteors with
   * left = random(0, window.innerWidth)px, animationDelay =
   * random(minDelay,maxDelay)s, animationDuration = random(minDuration,
   * maxDuration)s, angle via a --angle custom property. Port: identical
   * randomization, plain DOM nodes instead of React state. */
  function ukSpawnMeteors(container, opts) {
    opts = opts || {};
    var count = opts.number != null ? opts.number : 12;
    var minDelay = opts.minDelay != null ? opts.minDelay : 0.2;
    var maxDelay = opts.maxDelay != null ? opts.maxDelay : 1.2;
    var minDuration = opts.minDuration != null ? opts.minDuration : 3;
    var maxDuration = opts.maxDuration != null ? opts.maxDuration : 8;
    var angle = opts.angle != null ? opts.angle : 215;
    container.classList.add("uk-meteors");
    var width = container.getBoundingClientRect().width || 600;
    for (var i = 0; i < count; i++) {
      var m = document.createElement("span");
      m.className = "uk-meteor";
      m.style.setProperty("--uk-angle", -angle + "deg");
      m.style.left = Math.random() * width + "px";
      m.style.animationDelay = (Math.random() * (maxDelay - minDelay) + minDelay) + "s";
      m.style.animationDuration = Math.floor(Math.random() * (maxDuration - minDuration) + minDuration) + "s";
      container.appendChild(m);
    }
  }

  /* ---- #16 uk-flow-ribbon path builder -------------------------------------
   * Source parity: magicui animated-beam.tsx computes
   *   d = "M sx,sy Q (sx+ex)/2,(sy-curvature) ex,ey"
   * from two element rects relative to a container rect, then animates a
   * userSpaceOnUse linearGradient's x1/x2 across it. Port: same quadratic
   * path formula from two DOM rects (for a fixed cockpit layout you can also
   * hardcode the `d` and skip this), gradient motion left to the CSS/SVG
   * <animate> already declared on #uk-flow-gradient in the markup — this
   * helper only positions the path + a moving label chip along it. */
  function ukBuildFlowRibbon(svg, containerEl, fromEl, toEl, opts) {
    opts = opts || {};
    var curvature = opts.curvature != null ? opts.curvature : 60;
    var containerRect = containerEl.getBoundingClientRect();
    var a = fromEl.getBoundingClientRect();
    var b = toEl.getBoundingClientRect();
    var sx = a.left - containerRect.left + a.width / 2;
    var sy = a.top - containerRect.top + a.height / 2;
    var ex = b.left - containerRect.left + b.width / 2;
    var ey = b.top - containerRect.top + b.height / 2;
    var cy = (sy + ey) / 2 - curvature;
    var d = "M " + sx + "," + sy + " Q " + (sx + ex) / 2 + "," + cy + " " + ex + "," + ey;
    var path = svg.querySelector(".uk-flow-ribbon__glow") || (function () {
      var p = document.createElementNS("http://www.w3.org/2000/svg", "path");
      p.setAttribute("class", "uk-flow-ribbon__glow");
      p.setAttribute("stroke-width", opts.width || 18);
      svg.appendChild(p);
      return p;
    })();
    path.setAttribute("d", d);
    return { d: d, midX: (sx + ex) / 2, midY: cy };
  }

  global.AetherUIKit = {
    animateNumberTicker: ukAnimateNumberTicker,
    initSpotlightCards: ukInitSpotlightCards,
    setProgressRing: ukSetProgressRing,
    buildRipple: ukBuildRipple,
    spawnMeteors: ukSpawnMeteors,
    buildFlowRibbon: ukBuildFlowRibbon,
  };
})(window);

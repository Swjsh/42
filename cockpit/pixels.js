/*
 * cockpit/pixels.js — Gamma "office" pixel-art presence layer.
 * ===========================================================================
 * One little pixel worker per LIVE Gamma agent. They WALK AROUND a pixel office
 * (desks + monitors, coffee station, R&D whiteboard, door) doing things — sit
 * and type at a desk, sip at the coffee station, point at the whiteboard. This
 * is the "Gamma is alive" background layer for the cockpit face.
 *
 * Self-contained. Vanilla JS + Canvas. No frameworks, no build step.
 * Sprites are MIT (Pablo De Lucca) — see assets/pixel/LICENSE-pixel-agents.txt.
 *
 * ---------------------------------------------------------------------------
 * INTEGRATION CONTRACT  (the only lines the caller adds to face.html)
 * ---------------------------------------------------------------------------
 * 1) A full-viewport background canvas BEHIND the dashboard content. Add to the
 *    page (the cards/frame must sit at a higher z-index, e.g. .frame{position:
 *    relative; z-index:1}):
 *
 *      <canvas id="gx-office"
 *              style="position:fixed;inset:0;width:100vw;height:100vh;z-index:0;
 *                     pointer-events:none;"></canvas>
 *      <script src="/pixels.js"></script>
 *      <script>
 *        GammaPixels.mount(document.getElementById('gx-office'));
 *        // Feed it the live roster on an interval (see /api/agents-live below):
 *        async function pumpAgents(){
 *          try {
 *            const r = await fetch('/api/agents-live', { cache:'no-store' });
 *            const j = await r.json();
 *            GammaPixels.setAgents(j.agents || []);
 *          } catch (_) { (keep last roster on fetch error - fail open) }
 *        }
 *        pumpAgents(); setInterval(pumpAgents, 2000);
 *      </script>
 *
 * 2) Serve this file + the sprites. NOTE on the existing cockpit/server.js:
 *    its /assets/ handler is FLAT (path.basename) — it cannot serve the nested
 *    /assets/pixel/characters/*.png paths this module requests by default.
 *    Pick ONE of:
 *      (a) add a nested static route for /assets/pixel/** in server.js, OR
 *      (b) flatten the sprites into cockpit/assets/ and call
 *            GammaPixels.mount(el, { assetBase: '/assets', flat: true })
 *          which then requests /assets/char_0.png, /assets/floor_1.png, etc.
 *    Also add a route for GET /pixels.js (mirror the /realtime.js handler).
 *
 * ---------------------------------------------------------------------------
 * EXPECTED /api/agents-live SHAPE
 * ---------------------------------------------------------------------------
 *   { "agents": [
 *       { "id": "conductor-2026-06-27T0955",   // STABLE unique id (required)
 *         "role": "conductor",                 // engine|conductor|kitchen|gym|research|claude
 *         "runner": "Claude Opus",             // who's DRIVING it (LLM / free-agent / Python)
 *         "task": "wiring G6 vix feed",        // short human label (optional)
 *         "status": "working" },               // thinking|working|done   (optional, default working)
 *       ...
 *   ] }
 *
 * - A NEW id → a worker walks IN through the door and goes to work.
 * - An id that VANISHES from the list (or arrives with status:"done") → that
 *   worker finishes up and walks OUT through the door, then despawns. No ghosts:
 *   the live roster is the single source of truth, the seen-set is pruned to it.
 *
 * ---------------------------------------------------------------------------
 * PUBLIC API
 *   GammaPixels.mount(canvasEl, opts?)   // start rAF loop. opts: {assetBase, flat, debugPaths}
 *   GammaPixels.setAgents(list)          // feed the live roster (array, see shape above)
 *   GammaPixels.unmount()                // stop loop, free listeners, clear workers
 *   GammaPixels.setDebugPaths(bool)      // toggle the faint planned-path overlay
 * Test-only globals (set by _pixels-test.html-style harness):
 *   window.__lastPaths                   // { id: [ [c,r], ... ] } last A* path per worker
 *   window.__gxSnapshot()                // read-only worker positions/phases
 * ===========================================================================
 */
(function (global) {
  'use strict';

  // ── Sprite sheet geometry (matches the MIT char sheets: 112x96 = 7x16 frames,
  //    3 direction rows of 32px). Down=row0, Up=row1, Right=row2 (Left = mirror). ──
  var FW = 16, FH = 32, FRAMES = 7;
  var DIR_ROW = { down: 0, up: 1, right: 2, left: 2 };

  // ── Tile world. TILE px is a target; the real grid is recomputed to fill the
  //    canvas so the office always spans the whole viewport. ──
  var TILE = 28;          // logical tile size in CSS px (workers are scaled to it)
  var SPRITE_SCALE = 2;   // 16x32 sprite drawn at 32x64

  // Role → preferred destination station kind + a 1-2 word label.
  var ROLE_META = {
    engine:    { word: 'Engine',    home: 'desk' },
    conductor: { word: 'Conductor', home: 'whiteboard' },
    kitchen:   { word: 'Kitchen',   home: 'coffee' },
    gym:       { word: 'Gym',       home: 'desk' },
    research:  { word: 'Research',  home: 'whiteboard' },
    claude:    { word: 'Claude',    home: 'desk' },
    _default:  { word: 'Agent',     home: 'desk' }
  };
  function roleMeta(role) { return ROLE_META[role] || ROLE_META._default; }

  // Each role gets a stable sprite index (0..5) so the same role looks consistent.
  var ROLE_SPRITE = { engine: 0, conductor: 1, kitchen: 2, gym: 3, research: 4, claude: 5 };
  function spriteFor(role, id) {
    if (ROLE_SPRITE[role] != null) return ROLE_SPRITE[role];
    var h = 0; for (var i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    return h % 6;
  }

  // ───────────────────────────────────────────────────────────────────────────
  //  A* grid pathfinding (4-connected, obstacle-aware). Returns a list of
  //  [col,row] cells from start to goal INCLUSIVE, or null if unreachable.
  //  Walkability is passed as fn(c,r)=>bool so callers can treat a worker's OWN
  //  reserved seat as walkable while every other occupied tile is blocked.
  // ───────────────────────────────────────────────────────────────────────────
  function astar(cols, rows, walkable, start, goal) {
    if (start[0] === goal[0] && start[1] === goal[1]) return [[start[0], start[1]]];
    var key = function (c, r) { return r * cols + c; };
    var open = [];              // tiny binary-ish heap kept as a sorted-on-pop array
    var gScore = {}, fScore = {}, came = {}, inOpen = {};
    var sk = key(start[0], start[1]);
    gScore[sk] = 0; fScore[sk] = heur(start, goal);
    open.push(sk); inOpen[sk] = true;
    var DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    var guard = cols * rows * 4; // hard cap so a pathological map can never spin forever
    while (open.length && guard-- > 0) {
      // pop lowest f (linear scan — grids here are small, < ~1k cells)
      var bi = 0;
      for (var i = 1; i < open.length; i++) if (fScore[open[i]] < fScore[open[bi]]) bi = i;
      var cur = open[bi];
      open.splice(bi, 1); inOpen[cur] = false;
      var cc = cur % cols, cr = (cur - cc) / cols;
      if (cc === goal[0] && cr === goal[1]) return reconstruct(came, cur, cols);
      for (var d = 0; d < 4; d++) {
        var nc = cc + DIRS[d][0], nr = cr + DIRS[d][1];
        if (nc < 0 || nr < 0 || nc >= cols || nr >= rows) continue;
        if (!walkable(nc, nr)) continue;
        var nk = key(nc, nr);
        var tentative = gScore[cur] + 1;
        if (gScore[nk] == null || tentative < gScore[nk]) {
          came[nk] = cur;
          gScore[nk] = tentative;
          fScore[nk] = tentative + heur([nc, nr], goal);
          if (!inOpen[nk]) { open.push(nk); inOpen[nk] = true; }
        }
      }
    }
    return null;
    function heur(a, b) { return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]); } // Manhattan
    function reconstruct(came, cur, cols) {
      var path = [];
      while (cur != null) {
        var c = cur % cols, r = (cur - c) / cols;
        path.push([c, r]);
        cur = came[cur];
      }
      path.reverse();
      return path;
    }
  }

  // ───────────────────────────────────────────────────────────────────────────
  //  The module instance.
  // ───────────────────────────────────────────────────────────────────────────
  var inst = null;

  function Office(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.assetBase = (opts.assetBase || '/assets/pixel').replace(/\/$/, '');
    this.flat = !!opts.flat;            // flat = no subfolders (server can't nest)
    this.debugPaths = !!opts.debugPaths;
    this.dpr = 1; this.W = 0; this.H = 0;
    this.assets = {};
    this.workers = {};                  // id -> worker
    this.roster = {};                   // id -> last roster record (live source of truth)
    this.seen = {};                     // id -> true (so a leaving worker never re-spawns)
    this.grid = null;
    this.stations = null;
    this.raf = 0; this.last = 0; this.running = false;
    this._spawnSeq = 0;
    this._onResize = this._resize.bind(this);
  }

  // ── asset paths (flat or nested) ──
  Office.prototype._url = function (kind, name) {
    if (this.flat) return this.assetBase + '/' + name;
    var sub = kind === 'char' ? 'characters' : kind === 'floor' ? 'floors' : 'furniture';
    return this.assetBase + '/' + sub + '/' + name;
  };
  Office.prototype._loadImg = function (src) {
    return new Promise(function (resolve) {
      var im = new Image();
      im.onload = function () { resolve(im); };
      im.onerror = function () { resolve(null); }; // fail-open → vector fallback
      im.src = src;
    });
  };
  Office.prototype.loadAssets = function () {
    var self = this, jobs = [];
    for (var c = 0; c < 6; c++) (function (c) {
      jobs.push(self._loadImg(self._url('char', 'char_' + c + '.png'))
        .then(function (im) { self.assets['char' + c] = im; }));
    })(c);
    jobs.push(self._loadImg(self._url('floor', 'floor_1.png')).then(function (im) { self.assets.floor = im; }));
    jobs.push(self._loadImg(self._url('furniture', 'DESK_FRONT.png')).then(function (im) { self.assets.desk = im; }));
    jobs.push(self._loadImg(self._url('furniture', 'CACTUS.png')).then(function (im) { self.assets.cactus = im; }));
    return Promise.all(jobs);
  };

  // ── canvas sizing / grid build ──
  Office.prototype._resize = function () {
    var canvas = this.canvas;
    this.dpr = Math.max(1, Math.min(2, global.devicePixelRatio || 1));
    this.W = canvas.clientWidth || canvas.width || 800;
    this.H = canvas.clientHeight || canvas.height || 600;
    canvas.width = Math.round(this.W * this.dpr);
    canvas.height = Math.round(this.H * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._buildGrid();
  };

  // Build the tile grid + station layout. Recomputed whenever the canvas size
  // changes so the office always fills the viewport. Workers re-validate their
  // tile coords against the new grid.
  Office.prototype._buildGrid = function () {
    var cols = Math.max(8, Math.floor(this.W / TILE));
    var rows = Math.max(6, Math.floor(this.H / TILE));
    var cw = this.W / cols, ch = this.H / rows;
    this.grid = { cols: cols, rows: rows, cw: cw, ch: ch };

    // Reserve the center column band (where the dashboard cards sit) as a
    // "no-station" corridor so workers roam the visible MARGINS (sides on a
    // wide screen, top/bottom on a narrow one) rather than hiding behind cards.
    var centerHalf = Math.ceil((220 / cw)); // ~440px column / 2, in tiles
    var midC = Math.floor(cols / 2);
    var cardLo = Math.max(0, midC - centerHalf), cardHi = Math.min(cols - 1, midC + centerHalf);

    var stations = { desks: [], coffee: null, whiteboard: null, door: null, obstacles: {} };
    var occ = function (c, r) { stations.obstacles[r * cols + c] = true; };

    // DOOR — bottom edge, slightly right of center but outside the card band.
    var doorC = Math.min(cols - 2, cardHi + 1);
    if (doorC <= cardHi) doorC = Math.max(1, cardLo - 1);
    stations.door = { c: doorC, r: rows - 1, kind: 'door' };

    // Helper: is a column inside the protected card band?
    var inCard = function (c) { return c >= cardLo && c <= cardHi; };

    // Collect the usable left / right margin columns (outside the card band).
    var leftCols = [], rightCols = [];
    for (var c = 1; c < cols - 1; c++) {
      if (inCard(c)) continue;
      if (c < midC) leftCols.push(c); else rightCols.push(c);
    }

    // KEY PATHING FIX: a column packed with desks every-other-row becomes a
    // near-solid wall (desk/seat/desk/seat…) that blocks vertical travel UP that
    // column. So each desk column MUST have an OPEN circulation lane immediately
    // beside it that the seats open onto. We therefore lay desks on a column and
    // keep the neighbouring (inward) column clear as a lane. Coffee + whiteboard
    // get their OWN columns that never coincide with a desk column.
    var deskRows = [];
    for (var r = 1; r < rows - 2; r += 2) deskRows.push(r);

    // Pick desk columns: the OUTERMOST margin column on each side (+ one more in
    // from it if the margin is wide), always leaving an inward lane free.
    var deskCols = [];
    if (leftCols.length >= 2) {
      deskCols.push(leftCols[0]);                                  // outer-left wall
      if (leftCols.length >= 5) deskCols.push(leftCols[2]);        // a second bank, lane at [1] between
    }
    if (rightCols.length >= 2) {
      deskCols.push(rightCols[rightCols.length - 1]);              // outer-right wall
      if (rightCols.length >= 5) deskCols.push(rightCols[rightCols.length - 3]);
    }

    for (var di = 0; di < deskCols.length; di++) {
      var dc = deskCols[di];
      for (var ri = 0; ri < deskRows.length; ri++) {
        var dr = deskRows[ri];
        if (dr + 1 > rows - 2) continue;
        stations.desks.push({ c: dc, r: dr, seatC: dc, seatR: dr + 1, taken: null });
        occ(dc, dr); // desk top is solid; seat (dr+1) stays walkable, opens to the lane
      }
    }
    var isDeskCol = function (c) { return deskCols.indexOf(c) !== -1; };

    // COFFEE STATION — top-left, on an OPEN (non-desk) margin column so its stand
    // tile below is reachable. Appliance at row 0; stand tile at row 1.
    var coffeeC = null;
    for (var li = 0; li < leftCols.length; li++) {
      if (!isDeskCol(leftCols[li])) { coffeeC = leftCols[li]; break; }
    }
    if (coffeeC == null) coffeeC = leftCols.length ? leftCols[0] : 1;
    stations.coffee = { c: coffeeC, r: 0, standC: coffeeC, standR: 1, kind: 'coffee' };
    occ(coffeeC, 0);

    // WHITEBOARD — top-right, on an OPEN (non-desk) margin column. The "R&D"
    // board at row 0; a worker stands at row 1 to point.
    var wbC = null;
    for (var wi = rightCols.length - 1; wi >= 0; wi--) {
      if (!isDeskCol(rightCols[wi]) && rightCols[wi] !== coffeeC) { wbC = rightCols[wi]; break; }
    }
    if (wbC == null) wbC = rightCols.length ? rightCols[rightCols.length - 1] : cols - 2;
    stations.whiteboard = { c: wbC, r: 0, standC: wbC, standR: 1, kind: 'whiteboard' };
    occ(wbC, 0);

    this.stations = stations;

    // Re-validate workers: clamp their tile coords + re-resolve their desk
    // reservation against the rebuilt grid so a resize never strands anyone.
    var self = this;
    Object.keys(this.workers).forEach(function (id) {
      var w = self.workers[id];
      w.c = Math.max(0, Math.min(cols - 1, w.c));
      w.r = Math.max(0, Math.min(rows - 1, w.r));
      w.px = self._cx(w.c); w.py = self._cy(w.r);
      w.desk = null; w.path = null; w.pathIdx = 0; w.target = null;
      w.dwellUntil = 0; w.state = (w.state === 'leaving') ? 'leaving' : 'idle';
    });
  };

  // tile-center → pixel-center helpers
  Office.prototype._cx = function (c) { return (c + 0.5) * this.grid.cw; };
  Office.prototype._cy = function (r) { return (r + 0.5) * this.grid.ch; };

  // Is tile (c,r) walkable for worker `w`? Obstacles block everyone; another
  // worker's reserved desk-seat blocks; `w`'s OWN seat is walkable.
  Office.prototype._walkableFor = function (w) {
    var self = this, g = this.grid, st = this.stations;
    return function (c, r) {
      if (c < 0 || r < 0 || c >= g.cols || r >= g.rows) return false;
      if (st.obstacles[r * g.cols + c]) return false;
      // another worker's reserved seat tile is "their chair" — don't path through it
      var ids = Object.keys(self.workers);
      for (var i = 0; i < ids.length; i++) {
        var o = self.workers[ids[i]];
        if (o === w || !o.desk) continue;
        if (o.desk.seatC === c && o.desk.seatR === r) return false;
      }
      return true;
    };
  };

  // ── desk reservation ──
  Office.prototype._claimDesk = function (w) {
    if (w.desk) return w.desk;
    var desks = this.stations.desks;
    for (var i = 0; i < desks.length; i++) {
      if (!desks[i].taken) { desks[i].taken = w.id; w.desk = desks[i]; return w.desk; }
    }
    return null; // office full of desks — worker will wander/coffee instead
  };
  Office.prototype._freeDesk = function (w) {
    if (w.desk) { w.desk.taken = null; w.desk = null; }
  };

  // ── spawn / despawn ──
  Office.prototype._spawn = function (rec) {
    if (this.workers[rec.id]) return;
    this.seen[rec.id] = true;
    var st = this.stations, door = st.door;
    var w = {
      id: rec.id, seq: this._spawnSeq++,
      role: rec.role || 'claude', runner: rec.runner || '', task: rec.task || '',
      status: rec.status || 'working',
      sprite: spriteFor(rec.role || 'claude', rec.id),
      // start just BELOW the door tile, walking up into the room
      c: door.c, r: door.r,
      px: this._cx(door.c), py: this.H + TILE, // enter from off-screen-bottom
      dir: 'up', frame: 0, frameT: 0,
      state: 'entering', desk: null, target: null,
      path: null, pathIdx: 0, dwellUntil: 0, dwellKind: null,
      alpha: 0, bob: Math.random() * Math.PI * 2
    };
    this.workers[rec.id] = w;
    // first move: walk to the door tile, then pick a real destination
    w.px = this._cx(door.c); w.py = this.H + TILE;
    this._setPath(w, [door.c, door.r]);
  };

  Office.prototype._beginLeave = function (w) {
    if (w.state === 'leaving') return;
    this._freeDesk(w);
    w.state = 'leaving';
    w.dwellUntil = 0;
    this._setPath(w, [this.stations.door.c, this.stations.door.r]);
  };

  // ── path planning to a goal TILE ──
  Office.prototype._setPath = function (w, goal) {
    var start = [Math.round((w.px / this.grid.cw) - 0.5), Math.round((w.py / this.grid.ch) - 0.5)];
    start[0] = Math.max(0, Math.min(this.grid.cols - 1, start[0]));
    start[1] = Math.max(0, Math.min(this.grid.rows - 1, start[1]));
    var path = astar(this.grid.cols, this.grid.rows, this._walkableFor(w), start, goal);
    if (!path) {
      // unreachable (shouldn't happen on an open floor) — snap a 1-step plan so
      // the worker still nudges toward the goal instead of freezing.
      path = [start, goal];
    }
    w.path = path; w.pathIdx = 0; w.c = start[0]; w.r = start[1];
    // expose for the test harness / debug overlay
    if (global.__lastPaths) global.__lastPaths[w.id] = path.slice();
  };

  // Choose a fresh destination for a working/idle worker and path to it.
  Office.prototype._pickDestination = function (w) {
    var meta = roleMeta(w.role), st = this.stations;
    var roll = Math.random();
    // role "home" is the dominant choice; sometimes wander for life.
    var kind = meta.home;
    if (roll < 0.25) kind = 'coffee';
    else if (roll < 0.40 && st.whiteboard) kind = 'whiteboard';

    if (kind === 'whiteboard' && st.whiteboard) {
      w.target = { kind: 'whiteboard' };
      this._setPath(w, [st.whiteboard.standC, st.whiteboard.standR]);
      return;
    }
    if (kind === 'coffee' && st.coffee) {
      w.target = { kind: 'coffee' };
      this._setPath(w, [st.coffee.standC, st.coffee.standR]);
      return;
    }
    // desk (default): claim one and go to its seat
    var desk = this._claimDesk(w);
    if (desk) {
      w.target = { kind: 'desk', desk: desk };
      this._setPath(w, [desk.seatC, desk.seatR]);
      return;
    }
    // no free desk → idle near coffee
    if (st.coffee) {
      w.target = { kind: 'coffee' };
      this._setPath(w, [st.coffee.standC, st.coffee.standR]);
    } else {
      w.target = { kind: 'wander' };
      this._setPath(w, [Math.max(1, st.door.c - 2), Math.max(1, this.grid.rows - 3)]);
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  Public roster intake. The live list is the SOURCE OF TRUTH: ids present →
  //  ensure spawned; ids absent (or status done) → begin leaving. Pruned so a
  //  worker that finished walking out is gone for good (no ghost-leak).
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype.setAgents = function (list) {
    if (!this.stations) return; // not mounted yet; ignore until grid exists
    list = Array.isArray(list) ? list : [];
    var liveIds = {};
    for (var i = 0; i < list.length; i++) {
      var rec = list[i];
      if (!rec || !rec.id) continue;
      liveIds[rec.id] = true;
      this.roster[rec.id] = rec;
      var w = this.workers[rec.id];
      if (!w) {
        // brand-new agent → only spawn if not already shown-and-left this cycle
        this._spawn(rec);
        w = this.workers[rec.id];
      }
      if (w) {
        w.role = rec.role || w.role;
        w.runner = rec.runner != null ? rec.runner : w.runner;
        w.task = rec.task != null ? rec.task : w.task;
        w.status = rec.status || w.status;
        w.sprite = spriteFor(w.role, w.id);
        if (rec.status === 'done' && w.state !== 'leaving') this._beginLeave(w);
      }
    }
    // any worker whose id is no longer live → walk it out
    var self = this;
    Object.keys(this.workers).forEach(function (id) {
      if (!liveIds[id] && self.workers[id].state !== 'leaving') {
        self._beginLeave(self.workers[id]);
      }
    });
    // prune the seen-set down to live ids so a future re-appearance re-spawns clean
    Object.keys(this.seen).forEach(function (id) {
      if (!liveIds[id] && !self.workers[id]) delete self.seen[id];
    });
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  Per-frame update: move each worker one grid-step interpolation along its
  //  A* path, then dwell / re-path / leave per its state machine.
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype._update = function (dt, ts) {
    var g = this.grid, ids = Object.keys(this.workers);
    var STEP = (TILE * 5) * dt / 1000; // ~5 tiles/sec walking speed (reads as a brisk walk)
    for (var i = 0; i < ids.length; i++) {
      var w = this.workers[ids[i]];
      // fade in on spawn
      if (w.alpha < 1 && w.state !== 'leaving') w.alpha = Math.min(1, w.alpha + dt / 280);

      var moving = false;
      if (w.path && w.pathIdx < w.path.length) {
        var cell = w.path[w.pathIdx];
        var tx = this._cx(cell[0]), ty = this._cy(cell[1]);
        var dx = tx - w.px, dy = ty - w.py, dist = Math.hypot(dx, dy);
        if (dist <= STEP) {
          // arrived at this cell — snap and advance
          w.px = tx; w.py = ty; w.c = cell[0]; w.r = cell[1]; w.pathIdx++;
        } else {
          w.px += (dx / dist) * STEP; w.py += (dy / dist) * STEP;
          // facing follows the dominant axis of travel
          w.dir = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 'left' : 'right') : (dy < 0 ? 'up' : 'down');
          moving = true;
        }
      }

      // walk-frame animation while moving
      if (moving) {
        w.frameT += dt;
        if (w.frameT > 110) { w.frameT = 0; w.frame = (w.frame % (FRAMES - 1)) + 1; }
      } else {
        w.frame = 0;
      }

      var arrived = !w.path || w.pathIdx >= w.path.length;

      // ── state machine on arrival ──
      if (arrived && !moving) {
        if (w.state === 'leaving') {
          // reached the door → fade out and despawn
          w.alpha -= dt / 260;
          w.py += STEP * 0.6; // step down through the door
          if (w.alpha <= 0.02) { this._freeDesk(w); delete this.workers[w.id]; delete this.seen[w.id]; continue; }
        } else if (w.state === 'entering') {
          // crossed the threshold → go pick a real destination
          w.state = 'toStation';
          this._pickDestination(w);
        } else if (w.state === 'toStation') {
          // reached the station → dwell + face the station (up)
          w.state = 'dwell';
          w.dir = 'up';
          w.dwellKind = w.target ? w.target.kind : 'desk';
          var base = w.dwellKind === 'desk' ? 5200 : w.dwellKind === 'whiteboard' ? 4200 : 3200;
          w.dwellUntil = ts + base + Math.random() * 2600;
        } else if (w.state === 'dwell') {
          if (ts >= w.dwellUntil) {
            // done dwelling → release a desk if we were at one (so others can use
            // it while we wander), then pick a new destination.
            if (w.target && w.target.kind === 'desk') this._freeDesk(w);
            w.state = 'toStation';
            this._pickDestination(w);
          }
        } else { // idle (e.g. after a resize reset) → pick something to do
          w.state = 'toStation';
          this._pickDestination(w);
        }
      }
      w.bob += dt / 1000;
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  Rendering.
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype._drawFloor = function () {
    var ctx = this.ctx, W = this.W, H = this.H;
    ctx.imageSmoothingEnabled = false;
    if (this.assets.floor) {
      var ts = FW * 2; // floor tile drawn at 32px
      for (var y = 0; y < H; y += ts) for (var x = 0; x < W; x += ts)
        ctx.drawImage(this.assets.floor, 0, 0, 16, 16, x, y, ts, ts);
    } else {
      ctx.fillStyle = '#10141b'; ctx.fillRect(0, 0, W, H);
    }
    ctx.imageSmoothingEnabled = true;
    // tint toward the dashboard palette (bg #0A0C0F), warm-dark + a center vignette
    ctx.fillStyle = 'rgba(10,12,15,0.62)'; ctx.fillRect(0, 0, W, H);
    var vg = ctx.createRadialGradient(W / 2, H * 0.5, Math.min(W, H) * 0.18, W / 2, H * 0.55, Math.max(W, H) * 0.72);
    vg.addColorStop(0, 'rgba(20,28,44,0)');
    vg.addColorStop(1, 'rgba(6,8,12,0.92)');
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
  };

  Office.prototype._tileRect = function (c, r) {
    return { x: c * this.grid.cw, y: r * this.grid.ch, w: this.grid.cw, h: this.grid.ch };
  };

  Office.prototype._drawDesk = function (c, r) {
    var ctx = this.ctx, t = this._tileRect(c, r);
    // desk body
    ctx.imageSmoothingEnabled = false;
    if (this.assets.desk) {
      // sprite is 48x32; fit to ~1.4 tiles wide, anchored on the tile
      var dw = t.w * 1.5, dh = t.h * 1.2, dx = t.x + (t.w - dw) / 2, dy = t.y + (t.h - dh);
      ctx.drawImage(this.assets.desk, 0, 0, 48, 32, dx, dy, dw, dh);
    } else {
      ctx.fillStyle = '#4a3a2c'; ctx.fillRect(t.x + 1, t.y + t.h * 0.45, t.w - 2, t.h * 0.5);
    }
    // little MONITOR glow on top of the desk (pixel-art rectangle + screen)
    ctx.imageSmoothingEnabled = true;
    var mw = t.w * 0.5, mh = t.h * 0.42, mx = t.x + (t.w - mw) / 2, my = t.y + t.h * 0.06;
    ctx.fillStyle = '#0c0f15'; ctx.fillRect(mx - 1, my - 1, mw + 2, mh + 2);
    ctx.fillStyle = '#17324a'; ctx.fillRect(mx, my, mw, mh);
    // a faint scanline shimmer driven by time so monitors feel "on"
    var t2 = (performance.now() / 600) % 1;
    ctx.fillStyle = 'rgba(120,180,230,' + (0.10 + 0.06 * Math.sin(t2 * Math.PI * 2)) + ')';
    ctx.fillRect(mx, my + mh * (0.2 + 0.6 * t2), mw, 1.5);
  };

  Office.prototype._drawCoffee = function (s) {
    var ctx = this.ctx, t = this._tileRect(s.c, s.r);
    // counter
    ctx.fillStyle = '#2a2f3a'; ctx.fillRect(t.x + 2, t.y + t.h * 0.55, t.w - 4, t.h * 0.42);
    // machine
    ctx.fillStyle = '#3c4250'; ctx.fillRect(t.x + t.w * 0.28, t.y + t.h * 0.18, t.w * 0.44, t.h * 0.42);
    ctx.fillStyle = '#e0a23c'; ctx.fillRect(t.x + t.w * 0.4, t.y + t.h * 0.3, t.w * 0.2, 3); // warm light
    // rising "steam" wisp
    var st = (performance.now() / 700) % 1;
    ctx.strokeStyle = 'rgba(200,210,225,' + (0.28 * (1 - st)) + ')'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    var sx = t.x + t.w * 0.5, sy = t.y + t.h * 0.18 - st * t.h * 0.3;
    ctx.moveTo(sx, sy + 6); ctx.quadraticCurveTo(sx + 4, sy + 2, sx, sy - 3); ctx.stroke();
  };

  Office.prototype._drawWhiteboard = function (s) {
    var ctx = this.ctx, t = this._tileRect(s.c, s.r);
    var bx = t.x + 2, by = t.y + 2, bw = t.w - 4, bh = t.h * 0.7;
    ctx.fillStyle = '#11151c'; ctx.fillRect(bx - 1, by - 1, bw + 2, bh + 2);
    ctx.fillStyle = '#e7eaf2'; ctx.fillRect(bx, by, bw, bh);     // board surface
    // scribbled "R&D" marks (periwinkle accent from the palette)
    ctx.strokeStyle = '#93A8DD'; ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(bx + bw * 0.15, by + bh * 0.3); ctx.lineTo(bx + bw * 0.45, by + bh * 0.3);
    ctx.moveTo(bx + bw * 0.15, by + bh * 0.55); ctx.lineTo(bx + bw * 0.6, by + bh * 0.55);
    ctx.moveTo(bx + bw * 0.55, by + bh * 0.72); ctx.lineTo(bx + bw * 0.85, by + bh * 0.72);
    ctx.stroke();
    ctx.fillStyle = '#43C98E';
    ctx.fillRect(bx + bw * 0.68, by + bh * 0.2, bw * 0.18, 3); // a green sticky
  };

  Office.prototype._drawDoor = function (s) {
    var ctx = this.ctx, t = this._tileRect(s.c, s.r);
    ctx.fillStyle = '#1a1f29'; ctx.fillRect(t.x + t.w * 0.2, t.y + t.h * 0.08, t.w * 0.6, t.h * 0.9);
    ctx.fillStyle = '#0a0c0f'; ctx.fillRect(t.x + t.w * 0.28, t.y + t.h * 0.16, t.w * 0.44, t.h * 0.8);
    ctx.fillStyle = '#93A8DD'; ctx.fillRect(t.x + t.w * 0.6, t.y + t.h * 0.5, 3, 4); // knob
    // "EXIT" hint glow above
    ctx.fillStyle = 'rgba(224,87,78,0.5)';
    ctx.fillRect(t.x + t.w * 0.3, t.y, t.w * 0.4, 2);
  };

  Office.prototype._drawStations = function () {
    var st = this.stations;
    for (var i = 0; i < st.desks.length; i++) this._drawDesk(st.desks[i].c, st.desks[i].r);
    if (st.coffee) this._drawCoffee(st.coffee);
    if (st.whiteboard) this._drawWhiteboard(st.whiteboard);
    if (st.door) this._drawDoor(st.door);
    // a couple of cacti in the bottom corners for life
    if (this.assets.cactus) {
      this.ctx.imageSmoothingEnabled = false;
      var s = 1.6, cw = 16 * s, ch = 32 * s;
      this.ctx.drawImage(this.assets.cactus, 0, 0, 16, 32, 6, this.H - ch - 4, cw, ch);
      this.ctx.drawImage(this.assets.cactus, 0, 0, 16, 32, this.W - cw - 6, this.H - ch - 4, cw, ch);
    }
  };

  // faint planned-path overlay (debug / self-evidence of real A* routing)
  Office.prototype._drawDebugPaths = function () {
    if (!this.debugPaths) return;
    var ctx = this.ctx, ids = Object.keys(this.workers);
    ctx.save();
    ctx.lineWidth = 2;
    for (var i = 0; i < ids.length; i++) {
      var w = this.workers[ids[i]];
      if (!w.path || w.path.length < 2) continue;
      ctx.strokeStyle = 'rgba(147,168,221,0.35)';
      ctx.beginPath();
      for (var p = 0; p < w.path.length; p++) {
        var x = this._cx(w.path[p][0]), y = this._cy(w.path[p][1]);
        if (p === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      // dots at each remaining waypoint
      ctx.fillStyle = 'rgba(205,223,251,0.5)';
      for (var q = w.pathIdx; q < w.path.length; q++) {
        ctx.beginPath();
        ctx.arc(this._cx(w.path[q][0]), this._cy(w.path[q][1]), 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  };

  Office.prototype._drawWorker = function (w) {
    var ctx = this.ctx, sheet = this.assets['char' + w.sprite];
    var sw = FW * SPRITE_SCALE, sh = FH * SPRITE_SCALE;
    var bobY = (w.state === 'dwell') ? Math.sin(w.bob * 2) * 1.2 : 0;
    var dx = Math.round(w.px - sw / 2), dy = Math.round(w.py - sh + 8 + bobY);

    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, w.alpha));
    // soft shadow
    ctx.globalAlpha *= 1;
    ctx.fillStyle = 'rgba(0,0,0,0.34)';
    ctx.beginPath(); ctx.ellipse(w.px, w.py + 2, sw * 0.32, 4, 0, 0, Math.PI * 2); ctx.fill();

    ctx.imageSmoothingEnabled = false;
    var row = DIR_ROW[w.dir], col = w.frame % FRAMES;
    if (sheet) {
      if (w.dir === 'left') {
        ctx.translate(dx + sw, dy); ctx.scale(-1, 1);
        ctx.drawImage(sheet, col * FW, row * FH, FW, FH, 0, 0, sw, sh);
      } else {
        ctx.drawImage(sheet, col * FW, row * FH, FW, FH, dx, dy, sw, sh);
      }
    } else {
      // vector fallback so the office is never empty if a sprite 404s
      ctx.fillStyle = '#93A8DD'; ctx.fillRect(dx + 6, dy + 8, sw - 12, sh - 12);
    }
    ctx.restore();

    // station activity glyph
    this._drawActivity(w, dx, dy, sw, sh);
    // nameplate (runner + role) + status glyph
    this._drawNameplate(w, w.px, dy);
  };

  // typing shimmer at a desk; sip arc at coffee; pointer line at whiteboard
  Office.prototype._drawActivity = function (w, dx, dy, sw, sh) {
    if (w.state !== 'dwell') return;
    var ctx = this.ctx, t = performance.now() / 1000;
    if (w.dwellKind === 'desk') {
      // typing shimmer — flickering caret cluster at the desk monitor
      ctx.fillStyle = 'rgba(147,168,221,' + (0.4 + 0.4 * Math.abs(Math.sin(t * 6))) + ')';
      for (var k = 0; k < 3; k++) {
        if (((Math.floor(t * 8) + k) % 3) === 0)
          ctx.fillRect(w.px - 6 + k * 5, dy - 4, 3, 3);
      }
    } else if (w.dwellKind === 'coffee') {
      // a small sip arc
      ctx.strokeStyle = 'rgba(224,162,60,0.6)'; ctx.lineWidth = 1.4;
      ctx.beginPath(); ctx.arc(w.px + 6, w.py - sh * 0.4, 3, 0, Math.PI); ctx.stroke();
    } else if (w.dwellKind === 'whiteboard') {
      // a pointer line that sweeps
      ctx.strokeStyle = 'rgba(67,201,142,0.7)'; ctx.lineWidth = 1.6;
      var a = Math.sin(t * 2) * 0.4;
      ctx.beginPath();
      ctx.moveTo(w.px, w.py - sh * 0.5);
      ctx.lineTo(w.px + Math.cos(-1 + a) * 10, w.py - sh * 0.5 + Math.sin(-1 + a) * 10);
      ctx.stroke();
    }
  };

  function tidy(s, n) {
    s = (s == null ? '' : String(s)).replace(/\s+/g, ' ').trim();
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
  function roundRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  Office.prototype._drawNameplate = function (w, cx, topY) {
    var ctx = this.ctx, meta = roleMeta(w.role);
    var glyph = w.status === 'thinking' ? '…' : w.status === 'done' ? '✓' : '';
    var runner = tidy(w.runner || '—', 22);
    var roleWord = meta.word;
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, w.alpha));
    ctx.imageSmoothingEnabled = true;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';

    // line 1: runner (who's driving)
    ctx.font = '600 11px "JetBrains Mono", ui-monospace, monospace';
    var w1 = ctx.measureText(runner).width;
    // line 2: role word + glyph
    ctx.font = '600 10px Inter, system-ui, sans-serif';
    var line2 = roleWord + (glyph ? ' ' + glyph : '');
    var w2 = ctx.measureText(line2).width;

    var plateW = Math.max(w1, w2) + 14, plateH = 28;
    var px = Math.round(cx - plateW / 2), py = Math.round(topY - plateH - 4);

    ctx.fillStyle = 'rgba(10,12,15,0.86)';
    ctx.strokeStyle = 'rgba(147,168,221,0.30)';
    ctx.lineWidth = 1;
    roundRectPath(ctx, px, py, plateW, plateH, 6);
    ctx.fill(); ctx.stroke();

    ctx.font = '600 11px "JetBrains Mono", ui-monospace, monospace';
    ctx.fillStyle = '#CDDFFB';
    ctx.fillText(runner, cx, py + 9);

    ctx.font = '600 10px Inter, system-ui, sans-serif';
    ctx.fillStyle = w.status === 'thinking' ? '#A4ABBE' : w.status === 'done' ? '#43C98E' : '#93A8DD';
    ctx.fillText(line2, cx, py + 21);

    // little pointer down to the head
    ctx.fillStyle = 'rgba(10,12,15,0.86)';
    ctx.beginPath();
    ctx.moveTo(cx - 4, py + plateH - 1); ctx.lineTo(cx + 4, py + plateH - 1); ctx.lineTo(cx, py + plateH + 5);
    ctx.closePath(); ctx.fill();
    ctx.restore();
  };

  // ── main loop ──
  Office.prototype._frame = function (ts) {
    if (!this.running) return;
    var dt = this.last ? Math.min(60, ts - this.last) : 16;
    if (dt <= 0) dt = 16;
    this.last = ts;

    // auto-correct a stale canvas size (CSS resize without a window resize event)
    if (this.canvas.clientWidth !== this.W || this.canvas.clientHeight !== this.H) this._resize();

    this._update(dt, ts);

    this._drawFloor();
    this._drawStations();
    this._drawDebugPaths();
    // depth-sort workers by screen-Y so lower ones overlap higher ones
    var ids = Object.keys(this.workers).sort(function (a, b) {
      return this.workers[a].py - this.workers[b].py;
    }.bind(this));
    for (var i = 0; i < ids.length; i++) this._drawWorker(this.workers[ids[i]]);

    this.raf = global.requestAnimationFrame(this._frame.bind(this));
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  Public module surface.
  // ───────────────────────────────────────────────────────────────────────────
  var GammaPixels = {
    mount: function (canvasEl, opts) {
      if (!canvasEl) throw new Error('GammaPixels.mount: canvas element required');
      if (inst) this.unmount();
      if (!global.__lastPaths) global.__lastPaths = {};
      inst = new Office(canvasEl, opts);
      global.addEventListener('resize', inst._onResize);
      var self = inst;
      self._resize();
      self.loadAssets().then(function () {
        self._resize();          // re-measure now fonts/images may have shifted layout
        self.running = true;
        self.last = performance.now();
        self.raf = global.requestAnimationFrame(self._frame.bind(self));
      });
      return this;
    },
    setAgents: function (list) { if (inst) inst.setAgents(list); return this; },
    setDebugPaths: function (on) { if (inst) inst.debugPaths = !!on; return this; },
    unmount: function () {
      if (!inst) return this;
      inst.running = false;
      if (inst.raf) global.cancelAnimationFrame(inst.raf);
      global.removeEventListener('resize', inst._onResize);
      inst.workers = {}; inst.seen = {}; inst.roster = {};
      if (global.__lastPaths) global.__lastPaths = {};
      // clear the canvas so no last frame lingers
      try { inst.ctx.clearRect(0, 0, inst.canvas.width, inst.canvas.height); } catch (_) {}
      inst = null;
      return this;
    }
  };

  // read-only snapshot for the test harness / verification
  global.__gxSnapshot = function () {
    if (!inst) return [];
    return Object.keys(inst.workers).map(function (id) {
      var w = inst.workers[id];
      return {
        id: id, role: w.role, runner: w.runner, status: w.status, state: w.state,
        c: w.c, r: w.r, px: Math.round(w.px), py: Math.round(w.py), dir: w.dir,
        pathLen: w.path ? w.path.length : 0, pathIdx: w.pathIdx,
        desk: w.desk ? [w.desk.c, w.desk.r] : null, alpha: +w.alpha.toFixed(2)
      };
    });
  };
  global.__gxGrid = function () { return inst ? inst.grid : null; };

  global.GammaPixels = GammaPixels;
  if (typeof module !== 'undefined' && module.exports) module.exports = GammaPixels;

})(typeof window !== 'undefined' ? window : this);

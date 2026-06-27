/*
 * cockpit/pixels.js — Gamma "sectioned office" pixel-art presence layer.
 * ===========================================================================
 * A living pixel office split into THEMED SECTORS. One little pixel worker per
 * LIVE Gamma agent walks around — but each worker is CONFINED to its home
 * sector (a kitchen Nemotron cook stays in the Kitchen, a Python validator
 * stays in the Gym, Claude research stays in the Lab, each equity account has
 * a resident in its own Accounts cubicle, the engine lives in Trading). This is
 * the "Gamma is alive" background layer behind the cockpit face.
 *
 * Self-contained. Vanilla JS + Canvas. No frameworks, no build step.
 * Worker sprites are MIT (Pablo De Lucca) — assets/pixel/LICENSE-pixel-agents.txt.
 * All FURNITURE (stoves, weight racks, whiteboards, account terminals, coffee
 * machine) is drawn PROCEDURALLY in pixel art — no external furniture assets.
 *
 * ---------------------------------------------------------------------------
 * INTEGRATION CONTRACT  (the only lines the caller adds to face.html)
 * ---------------------------------------------------------------------------
 * 1) A full-viewport background canvas BEHIND the dashboard content. The cards
 *    sit at a higher z-index (e.g. .frame{position:relative; z-index:1}):
 *
 *      <canvas id="gx-office"
 *              style="position:fixed;inset:0;width:100vw;height:100vh;z-index:0;
 *                     pointer-events:none;"></canvas>
 *      <script src="/pixels.js"></script>
 *      <script>
 *        GammaPixels.mount(document.getElementById('gx-office'));
 *        async function pumpAgents(){
 *          try {
 *            const r = await fetch('/api/agents-live', { cache:'no-store' });
 *            GammaPixels.setAgents((await r.json()).agents || []);
 *          } catch (_) { (keep last roster on fetch error - fail open) }
 *        }
 *        pumpAgents(); setInterval(pumpAgents, 2000);
 *      </script>
 *
 * 2) Serve this file + the worker sprites. The existing cockpit/server.js
 *    /assets/ handler is FLAT (path.basename) — it can't serve the nested
 *    /assets/pixel/characters/*.png paths by default. Pick ONE:
 *      (a) add a nested static route for /assets/pixel/** in server.js, OR
 *      (b) flatten the sprites into cockpit/assets/ and call
 *            GammaPixels.mount(el, { assetBase:'/assets', flat:true })
 *    Also add a route for GET /pixels.js (mirror the /realtime.js handler).
 *
 * ---------------------------------------------------------------------------
 * EXPECTED /api/agents-live SHAPE
 * ---------------------------------------------------------------------------
 *   { "agents": [
 *       { "id": "kitchen-2026...",   // STABLE unique id (required)
 *         "role": "kitchen",         // kitchen|gym|research|conductor|claude|voice|engine|beacon|account
 *         "runner": "Nemotron · free",// who's DRIVING it (LLM / free-agent / Python / account alias)
 *         "task": "seeding cooks",   // short human label (optional)
 *         "status": "working",       // thinking|working|done (optional, default working)
 *         "account": "Gamma-Safe-2"} // ONLY for role=account: the cubicle alias/label (optional)
 *   ] }
 *
 * role → home SECTOR (worker is A*-confined to that sector):
 *   kitchen                              → Kitchen
 *   gym                                  → Gym
 *   research | conductor | claude | voice→ Lab
 *   engine  | beacon                     → Trading
 *   account                              → its own Accounts cubicle (by id order / alias)
 * Unknown roles fall back to the Lab.
 *
 * The 6 equity accounts are great always-on residents: emit them as
 * role:"account" rows (runner = alias) and each gets a labeled cubicle.
 *
 * - A NEW id → a worker appears at its sector door and walks to a workspot.
 * - An id that VANISHES (or status:"done") → it walks back to its sector door
 *   and despawns. No ghosts: live roster is the source of truth; seen-set pruned.
 *
 * ---------------------------------------------------------------------------
 * PUBLIC API
 *   GammaPixels.mount(canvasEl, opts?)   // opts: {assetBase, flat, debugPaths}
 *   GammaPixels.setAgents(list)          // feed the live roster (array)
 *   GammaPixels.unmount()                // stop loop, free listeners, clear
 *   GammaPixels.setDebugPaths(bool)      // planned-path overlay (OFF by default)
 * Test-only read globals:
 *   window.__gxSnapshot()   window.__gxGrid()   window.__gxSectors()
 *   window.__lastPaths      // { id: [[c,r],...] } last A* path per worker
 * ===========================================================================
 */
(function (global) {
  'use strict';

  // ── MIT char sheets: 112x96 = 7x16 frames, 3 dir rows of 32px.
  //    Down=row0, Up=row1, Right=row2 (Left = horizontal mirror of Right). ──
  var FW = 16, FH = 32, FRAMES = 7;
  var DIR_ROW = { down: 0, up: 1, right: 2, left: 2 };

  var TILE = 30;          // target tile size (px); grid recomputed to fill canvas
  var SPRITE_SCALE = 2;   // 16x32 sprite → 32x64

  // ── palette (matches the cockpit face design D) ──
  var COL = {
    bg: '#0A0C0F', floor: '#161b24', floorLit: '#1d2430', wall: '#2b323f',
    wallTop: '#39414f', ink: '#E7EAF2', muted: '#6C7384', accent: '#93A8DD',
    glow: '#CDDFFB', pos: '#43C98E', caution: '#E0A23C', alert: '#E0574E',
    steel: '#9aa6b4', steelDk: '#6b7686', wood: '#5a4636'
  };

  // ── role → sector key + a 1-2 word nameplate role word ──
  var ROLE_SECTOR = {
    kitchen: 'kitchen',
    gym: 'gym',
    research: 'lab', conductor: 'lab', claude: 'lab', voice: 'lab', doc: 'lab',
    engine: 'trading', beacon: 'trading', pilot: 'trading',
    account: 'accounts'
  };
  var ROLE_WORD = {
    kitchen: 'Cook', gym: 'Trainer', research: 'Research', conductor: 'Conductor',
    claude: 'Claude', voice: 'Voice', engine: 'Engine', beacon: 'Beacon',
    pilot: 'Pilot', account: 'Account', doc: 'Docs'
  };
  function sectorForRole(role) { return ROLE_SECTOR[role] || 'lab'; }
  function roleWord(role) { return ROLE_WORD[role] || 'Agent'; }

  // stable sprite index (0..5) per role so a role looks consistent
  var ROLE_SPRITE = { engine: 0, conductor: 1, kitchen: 2, gym: 3, research: 4, claude: 5, account: 1, beacon: 0, voice: 4 };
  function spriteFor(role, id) {
    if (ROLE_SPRITE[role] != null) return ROLE_SPRITE[role];
    var h = 0; for (var i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    return h % 6;
  }

  // ───────────────────────────────────────────────────────────────────────────
  //  A* (4-connected, obstacle-aware). walkable(c,r)=>bool. Returns [[c,r]...]
  //  start→goal inclusive, or null. Used CONFINED: callers pass a walkable fn
  //  that returns false outside the worker's home sector → natural containment.
  // ───────────────────────────────────────────────────────────────────────────
  function astar(cols, rows, walkable, start, goal) {
    if (start[0] === goal[0] && start[1] === goal[1]) return [[start[0], start[1]]];
    if (!walkable(goal[0], goal[1])) return null;
    var key = function (c, r) { return r * cols + c; };
    var open = [], gScore = {}, fScore = {}, came = {}, inOpen = {};
    var sk = key(start[0], start[1]);
    gScore[sk] = 0; fScore[sk] = heur(start, goal);
    open.push(sk); inOpen[sk] = true;
    var DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    var guard = cols * rows * 4;
    while (open.length && guard-- > 0) {
      var bi = 0;
      for (var i = 1; i < open.length; i++) if (fScore[open[i]] < fScore[open[bi]]) bi = i;
      var cur = open[bi]; open.splice(bi, 1); inOpen[cur] = false;
      var cc = cur % cols, cr = (cur - cc) / cols;
      if (cc === goal[0] && cr === goal[1]) return reconstruct(came, cur, cols);
      for (var d = 0; d < 4; d++) {
        var nc = cc + DIRS[d][0], nr = cr + DIRS[d][1];
        if (nc < 0 || nr < 0 || nc >= cols || nr >= rows) continue;
        if (!walkable(nc, nr)) continue;
        var nk = key(nc, nr), tentative = gScore[cur] + 1;
        if (gScore[nk] == null || tentative < gScore[nk]) {
          came[nk] = cur; gScore[nk] = tentative; fScore[nk] = tentative + heur([nc, nr], goal);
          if (!inOpen[nk]) { open.push(nk); inOpen[nk] = true; }
        }
      }
    }
    return null;
    function heur(a, b) { return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]); }
    function reconstruct(came, cur, cols) {
      var path = [];
      while (cur != null) { var c = cur % cols, r = (cur - c) / cols; path.push([c, r]); cur = came[cur]; }
      path.reverse(); return path;
    }
  }

  function tidy(s, n) { s = (s == null ? '' : String(s)).replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function roundRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath(); ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
  }

  // ───────────────────────────────────────────────────────────────────────────
  var inst = null;

  function Office(canvas, opts) {
    opts = opts || {};
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.assetBase = (opts.assetBase || '/assets/pixel').replace(/\/$/, '');
    this.flat = !!opts.flat;
    this.debugPaths = !!opts.debugPaths;     // OFF by default (production)
    this.dpr = 1; this.W = 0; this.H = 0;
    this.assets = {};
    this.workers = {};
    this.roster = {};
    this.seen = {};
    this.grid = null;
    this.sectors = null;       // { key: {label,x,y,w,h, interior:Set, door:[c,r], spots:[...], color} }
    this.obstacles = null;     // global obstacle set (walls + card rect + furniture)
    this.cardRect = null;
    this.raf = 0; this.last = 0; this.running = false;
    this._spawnSeq = 0;
    this._acctSlot = 0;        // round-robin assignment of account cubicles
    this._onResize = this._resize.bind(this);
  }

  // ── asset paths (worker sprites only) ──
  Office.prototype._url = function (kind, name) {
    if (this.flat) return this.assetBase + '/' + name;
    var sub = kind === 'char' ? 'characters' : kind === 'floor' ? 'floors' : 'furniture';
    return this.assetBase + '/' + sub + '/' + name;
  };
  Office.prototype._loadImg = function (src) {
    return new Promise(function (resolve) {
      var im = new Image();
      im.onload = function () { resolve(im); };
      im.onerror = function () { resolve(null); };
      im.src = src;
    });
  };
  Office.prototype.loadAssets = function () {
    var self = this, jobs = [];
    for (var c = 0; c < 6; c++) (function (c) {
      jobs.push(self._loadImg(self._url('char', 'char_' + c + '.png')).then(function (im) { self.assets['char' + c] = im; }));
    })(c);
    return Promise.all(jobs); // furniture is procedural; only worker sprites load
  };

  // ── canvas sizing ──
  Office.prototype._resize = function () {
    var canvas = this.canvas;
    this.dpr = Math.max(1, Math.min(2, global.devicePixelRatio || 1));
    this.W = canvas.clientWidth || canvas.width || 800;
    this.H = canvas.clientHeight || canvas.height || 600;
    canvas.width = Math.round(this.W * this.dpr);
    canvas.height = Math.round(this.H * this.dpr);
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this._buildLayout();
  };

  Office.prototype._cx = function (c) { return (c + 0.5) * this.grid.cw; };
  Office.prototype._cy = function (r) { return (r + 0.5) * this.grid.ch; };
  Office.prototype._tileRect = function (c, r) { return { x: c * this.grid.cw, y: r * this.grid.ch, w: this.grid.cw, h: this.grid.ch }; };

  // ───────────────────────────────────────────────────────────────────────────
  //  LAYOUT — the sectioned office. Reserve the top-center card column, then
  //  carve the open floor (bottom band + side margins) into themed sectors with
  //  visible walls between them. Each sector gets: a wall border (obstacle), a
  //  walkable interior, a door tile, themed furniture spots, and a label.
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype._buildLayout = function () {
    var cols = Math.max(16, Math.floor(this.W / TILE));
    var rows = Math.max(12, Math.floor(this.H / TILE));
    var cw = this.W / cols, ch = this.H / rows;
    this.grid = { cols: cols, rows: rows, cw: cw, ch: ch };

    // reserved card rectangle: ~450px column centered, top → ~55% height
    var halfCard = Math.ceil(228 / cw);
    var midC = Math.floor(cols / 2);
    var cardLo = Math.max(0, midC - halfCard), cardHi = Math.min(cols - 1, midC + halfCard);
    var cardBottom = Math.min(rows - 4, Math.round(rows * 0.55));
    this.cardRect = { lo: cardLo, hi: cardHi, bottom: cardBottom };

    var obstacles = {};                 // global blockers (walls/card/furniture)
    this.obstacles = obstacles;
    var occ = function (c, r) { obstacles[r * cols + c] = true; };
    for (var rr = 0; rr <= cardBottom; rr++) for (var cc = cardLo; cc <= cardHi; cc++) occ(cc, rr);

    // ── DESKTOP-ONLY layout (face.html gates mount at innerWidth>=1000, so we
    //    assume a wide viewport — no narrow/phone fallback). J's drawn layout:
    //
    //      ┌──────────┬──────────────┬──────────┐
    //      │          │  (card col   │          │
    //      │ ACCOUNTS │   reserved   │   LAB    │   ← left & right margins,
    //      │  (left   │   obstacle)  │  (right  │     FULL HEIGHT top→bottom
    //      │  margin, ├──────────────┤  margin, │
    //      │  6 cubes │ KITCH│TRD│GYM│  R&D)    │   ← bottom band (center strip
    //      │  2x3)    │      │   │   │          │     below the card) split into
    //      └──────────┴──────────────┴──────────┘     thirds: Kitchen|Trading|Gym
    //
    //    Left margin  = x 0..cardLo-1, full height          → ACCOUNTS
    //    Right margin = x cardHi+1..cols-1, full height      → LAB / R&D
    //    Bottom band  = x cardLo..cardHi, y cardBottom+1..   → KITCHEN|TRADING|GYM
    var bandTop = cardBottom + 1;
    var bandH = rows - bandTop;          // height of the bottom band
    var sectors = {};
    this.sectors = sectors;

    var self = this;
    // build a sector rectangle [x..x2] x [y..y2] inclusive; carves a 1-tile wall
    // ring (obstacles) and records the interior walkable set + a door on its
    // top or side wall. Furniture spots are added later per theme.
    function makeSector(key, label, color, x, y, x2, y2, doorSide) {
      x = Math.max(0, x); y = Math.max(0, y); x2 = Math.min(cols - 1, x2); y2 = Math.min(rows - 1, y2);
      if (x2 - x < 2 || y2 - y < 2) return null; // too small to be a room
      var interior = {}, interiorList = [];
      // wall ring = the rectangle border tiles (obstacles)
      for (var c = x; c <= x2; c++) { occ(c, y); occ(c, y2); }
      for (var r = y; r <= y2; r++) { occ(x, r); occ(x2, r); }
      // interior = inside the ring
      for (var ic = x + 1; ic <= x2 - 1; ic++) for (var ir = y + 1; ir <= y2 - 1; ir++) {
        interior[ir * cols + ic] = true; interiorList.push([ic, ir]);
      }
      // a DOOR: punch one wall tile open + record it as the entry tile. Default
      // top-center; doorSide can be 'top'|'bottom'|'left'|'right'.
      var door;
      if (doorSide === 'bottom') door = [Math.round((x + x2) / 2), y2];
      else if (doorSide === 'left') door = [x, Math.round((y + y2) / 2)];
      else if (doorSide === 'right') door = [x2, Math.round((y + y2) / 2)];
      else door = [Math.round((x + x2) / 2), y];
      delete obstacles[door[1] * cols + door[0]];           // open the doorway
      interior[door[1] * cols + door[0]] = true;            // door tile is walkable for this sector
      var s = {
        key: key, label: label, color: color, x: x, y: y, x2: x2, y2: y2,
        interior: interior, interiorList: interiorList, door: door,
        spots: [], furniture: []
      };
      sectors[key] = s;
      return s;
    }

    // ── LEFT MARGIN → ACCOUNTS (full height) ──
    // Everything left of the card column, top to bottom. The 6 cubicles are laid
    // out as a 2-col x 3-row grid filling this tall zone (see _furnishSectors).
    makeSector('accounts', 'ACCOUNTS', COL.glow, 0, 0, cardLo - 1, rows - 1, 'right');

    // ── RIGHT MARGIN → LAB / R&D (full height) ──
    // Everything right of the card column, top to bottom. Whiteboards + research
    // / server desks distributed down its height.
    makeSector('lab', 'LAB / R&D', COL.accent, cardHi + 1, 0, cols - 1, rows - 1, 'left');

    // ── BOTTOM BAND (center strip below the card) → KITCHEN | TRADING | GYM ──
    // The card-column width, below the reserved card rect, split into three. GYM
    // gets the largest share (J: "the BIG one").
    var bandX = cardLo, bandX2 = cardHi, by = bandTop, by2 = rows - 1;
    var bandW = bandX2 - bandX + 1;
    // thirds with GYM widest: kitchen 0.30, trading 0.30, gym 0.40
    var kEnd = bandX + Math.floor(bandW * 0.30) - 1;
    var tEnd = bandX + Math.floor(bandW * 0.60) - 1;
    makeSector('kitchen', 'KITCHEN', COL.caution, bandX,     by, kEnd,   by2, 'top');
    makeSector('trading', 'TRADING', COL.alert,   kEnd + 1,  by, tEnd,   by2, 'top');
    makeSector('gym',     'GYM',     COL.pos,     tEnd + 1,  by, bandX2, by2, 'top');

    // Safety: if a sector failed to build (degenerate tiny grid — shouldn't happen
    // on the desktop-only viewport this targets), alias its role to Lab so no
    // worker is ever sector-less. Lab spans the full-height right margin and is the
    // most robust fallback; guarantee it exists.
    if (!sectors.lab) makeSector('lab', 'LAB / R&D', COL.accent, cardHi + 1, 0, cols - 1, rows - 1, 'left');
    if (!sectors.lab) makeSector('lab', 'LAB / R&D', COL.accent, 1, by, Math.min(cols - 2, 1 + 8), by2, 'top');
    this.sectorAlias = {};
    var allKeys = ['kitchen', 'gym', 'lab', 'accounts', 'trading'];
    for (var ak = 0; ak < allKeys.length; ak++) {
      if (!sectors[allKeys[ak]]) this.sectorAlias[allKeys[ak]] = 'lab';
    }

    // ── populate THEMED furniture + dwell spots per sector ──
    this._furnishSectors();

    // re-validate workers against the rebuilt layout
    Object.keys(this.workers).forEach(function (id) {
      var w = self.workers[id];
      var sec = sectors[w.sectorKey] || sectors.lab;
      w.sectorKey = sec ? sec.key : 'lab';
      // clamp into the sector interior; reset pathing
      var spot = self._spotFor(w);
      w.c = spot ? spot.c : (sec ? sec.door[0] : 1);
      w.r = spot ? spot.r : (sec ? sec.door[1] : 1);
      w.px = self._cx(w.c); w.py = self._cy(w.r);
      w.path = null; w.pathIdx = 0; w.target = null; w.dwellUntil = 0;
      w.state = (w.state === 'leaving') ? 'leaving' : 'idle';
    });
  };

  // Walkability for worker `w`: ONLY tiles inside w's home sector interior, minus
  // furniture obstacles, minus other workers' claimed spots (its own spot is OK).
  Office.prototype._walkableFor = function (w) {
    var self = this, g = this.grid, sec = this.sectors[w.sectorKey];
    return function (c, r) {
      if (!sec) return false;
      if (c < 0 || r < 0 || c >= g.cols || r >= g.rows) return false;
      if (!sec.interior[r * g.cols + c]) return false;          // CONTAINMENT
      if (self.obstacles[r * g.cols + c]) return false;          // furniture/wall
      var ids = Object.keys(self.workers);
      for (var i = 0; i < ids.length; i++) {
        var o = self.workers[ids[i]];
        if (o === w || !o.spot) continue;
        if (o.spot.c === c && o.spot.r === r) return false;      // someone's chair
      }
      return true;
    };
  };

  // ── FURNITURE: each sector gets a capped, themed set. A "spot" is a walkable
  //    tile a worker dwells on, facing an adjacent furniture obstacle. ──
  Office.prototype._furnishSectors = function () {
    var g = this.grid, cols = g.cols, self = this;
    var occ = function (c, r) { self.obstacles[r * cols + c] = true; };

    Object.keys(this.sectors).forEach(function (key) {
      var s = self.sectors[key];
      s.spots = []; s.furniture = [];
      var x = s.x + 1, y = s.y + 1, x2 = s.x2 - 1, y2 = s.y2 - 1; // interior bounds
      var iw = x2 - x + 1, ih = y2 - y + 1;

      // helper: add a furniture obstacle tile + a dwell spot in front of it
      // (spot is on the row BELOW the furniture so the worker faces UP at it).
      function addUnit(fc, fr, kind, faceDir) {
        if (fc < x || fc > x2 || fr < y || fr > y2) return false;
        if (self.obstacles[fr * cols + fc]) return false;
        // spot in front
        var sc = fc, sr = fr + 1, sdir = 'up';
        if (faceDir === 'down') { sr = fr - 1; sdir = 'down'; }
        if (sr < y || sr > y2) { sr = fr + 1; sdir = 'up'; if (sr > y2) return false; }
        if (self.obstacles[sr * cols + sc]) return false;
        occ(fc, fr);
        s.furniture.push({ c: fc, r: fr, kind: kind });
        s.spots.push({ c: sc, r: sr, dir: sdir, kind: kind, taken: null });
        return true;
      }

      // place furniture in ROWS spread down the zone height: a furniture row,
      // a seat row, a walking lane — repeated every 3 rows. This fills tall zones
      // (the left/right margins) AND wide ones (the bottom thirds) evenly instead
      // of cramming everything against one wall.
      function fillRows(kinds, colStep, cap) {
        var made = 0;
        for (var fr = y; fr <= y2 - 1 && made < (cap || 999); fr += 3) {
          var ki = 0;
          for (var fc = x; fc <= x2 && made < (cap || 999); fc += colStep) {
            var kind = kinds[(ki++) % kinds.length];
            if (addUnit(fc, fr, kind, 'up')) made++;
          }
        }
        return made;
      }

      if (key === 'accounts') {
        // 6 CUBICLE TERMINALS as a 2-col x 3-row grid filling the TALL left zone.
        // Resident sits BELOW the terminal (faceDir 'up'); rows spaced by 3 so
        // seats never collide; we choose a column step that yields ~2 columns.
        var want = 6, made = 0;
        var aColStep = Math.max(2, Math.floor(iw / 2));        // ~2 cubicle columns
        var rowGap = Math.max(3, Math.floor(ih / 3));          // ~3 cubicle rows down the height
        for (var rr = y; rr <= y2 - 1 && made < want; rr += rowGap) {
          for (var ccx = x; ccx <= x2 && made < want; ccx += aColStep) {
            if (addUnit(ccx, rr, 'terminal', 'up')) made++;
          }
        }
        // top up if the grid under-filled (narrow/short interior): add along any
        // free furniture rows until we reach 6.
        for (var rr2 = y; rr2 <= y2 - 1 && made < want; rr2 += 3) {
          for (var cx2 = x; cx2 <= x2 && made < want; cx2 += 2) {
            if (!self.obstacles[rr2 * cols + cx2]) { if (addUnit(cx2, rr2, 'terminal', 'up')) made++; }
          }
        }
        s.cubicleCount = made;
      } else if (key === 'lab') {
        // R&D right margin (tall): WHITEBOARDS + SERVER/research desks distributed
        // down the full height, alternating, every 3 rows.
        fillRows(['whiteboard', 'serverdesk'], Math.max(3, Math.floor(iw / 2)), 8);
      } else if (key === 'kitchen') {
        // KITCHEN (bottom-left third): stoves, fridge, prep counters spread across.
        fillRows(['stove', 'counter', 'fridge'], 2, 6);
      } else if (key === 'trading') {
        // TRADING (bottom-middle third): engine/beacon terminals + a coffee machine.
        var tmade = fillRows(['engine', 'engine', 'coffee'], 2, 6);
      } else if (key === 'gym') {
        // GYM (bottom-right third, the BIG one): racks, benches, dumbbells, treadmill
        // spread across the wider area.
        fillRows(['rack', 'bench', 'dumbbell', 'treadmill'], 2, 8);
      }

      // guarantee at least ONE spot even if furniture didn't fit, so a worker can
      // still stand somewhere inside its sector.
      if (!s.spots.length) {
        var fallbackC = Math.round((s.x + s.x2) / 2), fallbackR = Math.round((s.y + s.y2) / 2);
        if (!self.obstacles[fallbackR * cols + fallbackC])
          s.spots.push({ c: fallbackC, r: fallbackR, dir: 'down', kind: 'idle', taken: null });
      }
    });
  };

  // ── spot reservation within a sector ──
  Office.prototype._spotFor = function (w) {
    var sec = this.sectors[w.sectorKey]; if (!sec) return null;
    if (w.spot && w.spot.taken === w.id) return w.spot;
    // account residents prefer their assigned cubicle index
    var pool = sec.spots, i;
    if (w.role === 'account' && w.acctSlot != null && pool[w.acctSlot] && !pool[w.acctSlot].taken) {
      pool[w.acctSlot].taken = w.id; w.spot = pool[w.acctSlot]; return w.spot;
    }
    for (i = 0; i < pool.length; i++) if (!pool[i].taken) { pool[i].taken = w.id; w.spot = pool[i]; return w.spot; }
    return null; // sector full → worker will wander between interior tiles
  };
  Office.prototype._freeSpot = function (w) { if (w.spot) { w.spot.taken = null; w.spot = null; } };

  // ── spawn / leave ──
  Office.prototype._spawn = function (rec) {
    if (this.workers[rec.id]) return;
    this.seen[rec.id] = true;
    var role = rec.role || 'claude';
    var secKey = sectorForRole(role);
    var sec = this.sectors[secKey] || this.sectors.lab;
    secKey = sec ? sec.key : 'lab';
    var w = {
      id: rec.id, seq: this._spawnSeq++,
      role: role, runner: rec.runner || '', task: rec.task || '',
      status: rec.status || 'working', account: rec.account || '',
      sprite: spriteFor(role, rec.id),
      sectorKey: secKey, acctSlot: null,
      c: sec ? sec.door[0] : 1, r: sec ? sec.door[1] : 1,
      px: 0, py: 0, dir: 'down', frame: 0, frameT: 0,
      state: 'entering', spot: null, target: null,
      path: null, pathIdx: 0, dwellUntil: 0, dwellKind: null,
      alpha: 0, bob: Math.random() * Math.PI * 2
    };
    if (role === 'account') { w.acctSlot = this._acctSlot % 6; this._acctSlot++; }
    w.px = this._cx(w.c); w.py = this._cy(w.r);
    this.workers[rec.id] = w;
  };

  Office.prototype._beginLeave = function (w) {
    if (w.state === 'leaving') return;
    this._freeSpot(w);
    w.state = 'leaving';
    w.dwellUntil = 0;
    var sec = this.sectors[w.sectorKey];
    if (sec) this._setPath(w, sec.door); else w.path = null;
  };

  // ── path to a goal tile, confined to the worker's sector ──
  Office.prototype._setPath = function (w, goal) {
    var g = this.grid;
    var start = [Math.max(0, Math.min(g.cols - 1, Math.round((w.px / g.cw) - 0.5))),
                 Math.max(0, Math.min(g.rows - 1, Math.round((w.py / g.ch) - 0.5)))];
    var path = astar(g.cols, g.rows, this._walkableFor(w), start, goal);
    if (!path) path = [start]; // stay put if unreachable (never slide across walls)
    w.path = path; w.pathIdx = 0; w.c = start[0]; w.r = start[1];
    if (global.__lastPaths) global.__lastPaths[w.id] = path.slice();
  };

  // pick a destination INSIDE the home sector: usually the worker's own spot;
  // sometimes another spot or a random interior tile (so they roam their room).
  Office.prototype._pickDestination = function (w) {
    var sec = this.sectors[w.sectorKey]; if (!sec) return;
    var roll = Math.random();
    if (roll < 0.62) {
      var spot = this._spotFor(w);
      if (spot) { w.target = { kind: 'spot', spot: spot }; this._setPath(w, [spot.c, spot.r]); return; }
    }
    // wander to a random walkable interior tile of this sector
    var w2 = this._walkableFor(w), tries = 0, list = sec.interiorList;
    while (tries++ < 12 && list.length) {
      var t = list[(Math.random() * list.length) | 0];
      if (w2(t[0], t[1])) { w.target = { kind: 'wander' }; this._setPath(w, [t[0], t[1]]); return; }
    }
    // fallback: go to (or stay at) the door
    w.target = { kind: 'idle' }; this._setPath(w, sec.door);
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  roster intake — live list is source of truth (spawn-in / despawn-out / no
  //  ghosts). Account residents keyed by id; their cubicle slot is stable.
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype.setAgents = function (list) {
    if (!this.sectors) return;
    list = Array.isArray(list) ? list : [];
    var liveIds = {}, self = this;
    for (var i = 0; i < list.length; i++) {
      var rec = list[i]; if (!rec || !rec.id) continue;
      liveIds[rec.id] = true; this.roster[rec.id] = rec;
      var w = this.workers[rec.id];
      if (!w) { this._spawn(rec); w = this.workers[rec.id]; }
      if (w) {
        w.role = rec.role || w.role;
        w.runner = rec.runner != null ? rec.runner : w.runner;
        w.task = rec.task != null ? rec.task : w.task;
        w.account = rec.account != null ? rec.account : w.account;
        w.status = rec.status || w.status;
        w.sprite = spriteFor(w.role, w.id);
        if (rec.status === 'done' && w.state !== 'leaving') this._beginLeave(w);
      }
    }
    Object.keys(this.workers).forEach(function (id) {
      if (!liveIds[id] && self.workers[id].state !== 'leaving') self._beginLeave(self.workers[id]);
    });
    Object.keys(this.seen).forEach(function (id) {
      if (!liveIds[id] && !self.workers[id]) delete self.seen[id];
    });
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  update — grid-step interpolation + per-worker state machine (confined).
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype._update = function (dt, ts) {
    var g = this.grid, ids = Object.keys(this.workers);
    var STEP = (TILE * 4.6) * dt / 1000;
    for (var i = 0; i < ids.length; i++) {
      var w = this.workers[ids[i]];
      if (w.alpha < 1 && w.state !== 'leaving') w.alpha = Math.min(1, w.alpha + dt / 300);

      var moving = false;
      if (w.path && w.pathIdx < w.path.length) {
        var cell = w.path[w.pathIdx];
        var tx = this._cx(cell[0]), ty = this._cy(cell[1]);
        var dx = tx - w.px, dy = ty - w.py, dist = Math.hypot(dx, dy);
        if (dist <= STEP) { w.px = tx; w.py = ty; w.c = cell[0]; w.r = cell[1]; w.pathIdx++; }
        else {
          w.px += (dx / dist) * STEP; w.py += (dy / dist) * STEP;
          w.dir = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 'left' : 'right') : (dy < 0 ? 'up' : 'down');
          moving = true;
        }
      }
      if (moving) { w.frameT += dt; if (w.frameT > 110) { w.frameT = 0; w.frame = (w.frame % (FRAMES - 1)) + 1; } }
      else w.frame = 0;

      var arrived = !w.path || w.pathIdx >= w.path.length;
      if (arrived && !moving) {
        if (w.state === 'leaving') {
          w.alpha -= dt / 260;
          if (w.alpha <= 0.02) { this._freeSpot(w); delete this.workers[w.id]; delete this.seen[w.id]; continue; }
        } else if (w.state === 'entering') {
          w.state = 'toSpot'; this._pickDestination(w);
        } else if (w.state === 'toSpot') {
          w.state = 'dwell';
          // face the furniture this spot belongs to
          w.dir = (w.target && w.target.spot) ? w.target.spot.dir : 'up';
          w.dwellKind = (w.target && w.target.spot) ? w.target.spot.kind : 'idle';
          var base = w.role === 'account' ? 6000 : 3600;
          w.dwellUntil = ts + base + Math.random() * 3000;
        } else if (w.state === 'dwell') {
          if (ts >= w.dwellUntil) {
            // account residents mostly stay at their terminal; others roam more
            if (w.role !== 'account' && w.target && w.target.kind === 'spot' && Math.random() < 0.5) this._freeSpot(w);
            w.state = 'toSpot'; this._pickDestination(w);
          }
        } else { w.state = 'toSpot'; this._pickDestination(w); }
      }
      w.bob += dt / 1000;
    }
  };

  // ───────────────────────────────────────────────────────────────────────────
  //  RENDER
  // ───────────────────────────────────────────────────────────────────────────
  Office.prototype._drawFloor = function () {
    var ctx = this.ctx, W = this.W, H = this.H, g = this.grid;
    // base
    ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
    // checker floor only on sector interiors (so the office reads as rooms, not a
    // full-screen grid). Card region stays near-black.
    if (g && this.sectors) {
      var keys = Object.keys(this.sectors);
      for (var k = 0; k < keys.length; k++) {
        var s = this.sectors[keys[k]];
        for (var c = s.x + 1; c <= s.x2 - 1; c++) for (var r = s.y + 1; r <= s.y2 - 1; r++) {
          var t = this._tileRect(c, r);
          ctx.fillStyle = ((c + r) & 1) ? COL.floor : COL.floorLit;
          ctx.fillRect(t.x, t.y, t.w + 0.6, t.h + 0.6);
        }
      }
    }
    // card rectangle: push to near-black so the dashboard cards read cleanly
    if (g && this.cardRect) {
      var cr = this.cardRect;
      ctx.fillStyle = 'rgba(6,8,11,0.9)';
      ctx.fillRect(cr.lo * g.cw, 0, (cr.hi - cr.lo + 1) * g.cw, (cr.bottom + 1) * g.ch);
    }
    // gentle vignette
    var vg = ctx.createRadialGradient(W / 2, H * 0.66, Math.min(W, H) * 0.25, W / 2, H * 0.6, Math.max(W, H) * 0.82);
    vg.addColorStop(0, 'rgba(20,28,44,0)'); vg.addColorStop(1, 'rgba(5,7,11,0.8)');
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
  };

  Office.prototype._drawSectorWalls = function () {
    var ctx = this.ctx, g = this.grid, keys = Object.keys(this.sectors);
    for (var k = 0; k < keys.length; k++) {
      var s = this.sectors[keys[k]];
      // draw the wall ring as chunky pixel walls
      for (var c = s.x; c <= s.x2; c++) { this._wallTile(c, s.y, s); this._wallTile(c, s.y2, s); }
      for (var r = s.y; r <= s.y2; r++) { this._wallTile(s.x, r, s); this._wallTile(s.x2, r, s); }
      // re-open the doorway visually (draw floor over the door tile)
      var dt = this._tileRect(s.door[0], s.door[1]);
      ctx.fillStyle = COL.floorLit; ctx.fillRect(dt.x, dt.y, dt.w + 0.6, dt.h + 0.6);
      // a thin accent frame on the doorway posts
      ctx.fillStyle = s.color;
      ctx.globalAlpha = 0.5;
      ctx.fillRect(dt.x - 1, dt.y, 2, dt.h); ctx.fillRect(dt.x + dt.w - 1, dt.y, 2, dt.h);
      ctx.globalAlpha = 1;
    }
  };
  Office.prototype._wallTile = function (c, r, s) {
    var ctx = this.ctx, t = this._tileRect(c, r);
    ctx.fillStyle = COL.wall; ctx.fillRect(t.x, t.y, t.w + 0.6, t.h + 0.6);
    ctx.fillStyle = COL.wallTop; ctx.fillRect(t.x, t.y, t.w + 0.6, Math.max(2, t.h * 0.28)); // top bevel
    ctx.fillStyle = 'rgba(0,0,0,0.25)'; ctx.fillRect(t.x, t.y + t.h * 0.82, t.w + 0.6, t.h * 0.18); // base shadow
  };

  Office.prototype._drawSectorLabels = function () {
    var ctx = this.ctx, keys = Object.keys(this.sectors);
    ctx.save(); ctx.imageSmoothingEnabled = true; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    for (var k = 0; k < keys.length; k++) {
      var s = this.sectors[keys[k]];
      var t = this._tileRect(s.x, s.y);
      var lx = t.x + 4, ly = t.y + this.grid.ch * 0.5;
      ctx.font = '700 10px "JetBrains Mono", ui-monospace, monospace';
      var txt = s.label;
      var tw = ctx.measureText(txt).width + 10;
      ctx.fillStyle = 'rgba(10,12,15,0.8)';
      roundRectPath(ctx, lx - 3, ly - 8, tw, 15, 4); ctx.fill();
      ctx.fillStyle = s.color;
      ctx.fillText(txt, lx + 2, ly);
    }
    ctx.restore();
  };

  // ── procedural pixel FURNITURE ──
  Office.prototype._drawFurniture = function () {
    var keys = Object.keys(this.sectors);
    for (var k = 0; k < keys.length; k++) {
      var s = this.sectors[keys[k]];
      for (var f = 0; f < s.furniture.length; f++) {
        var u = s.furniture[f], t = this._tileRect(u.c, u.r);
        this._drawUnit(u.kind, t, s);
      }
      // account cubicle labels (alias) under each terminal
      if (s.key === 'accounts') this._drawCubicleLabels(s);
    }
  };

  Office.prototype._drawUnit = function (kind, t, s) {
    var ctx = this.ctx; ctx.imageSmoothingEnabled = false;
    var x = t.x, y = t.y, w = t.w, h = t.h, T = performance.now() / 1000;
    if (kind === 'stove') {
      // stainless steel stove: body + 4 burners + oven door
      ctx.fillStyle = COL.steel; ctx.fillRect(x + 1, y + h * 0.18, w - 2, h * 0.8);
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + 1, y + h * 0.18, w - 2, 2);
      // burners (two glowing)
      var bx = [x + w * 0.28, x + w * 0.62], by2 = y + h * 0.34;
      for (var b = 0; b < 2; b++) {
        ctx.fillStyle = '#222'; ctx.fillRect(bx[b] - 3, by2 - 3, 6, 6);
        var glow = 0.4 + 0.4 * Math.abs(Math.sin(T * 3 + b));
        ctx.fillStyle = 'rgba(224,87,46,' + glow + ')'; ctx.fillRect(bx[b] - 2, by2 - 2, 4, 4);
      }
      // oven door + handle
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + 2, y + h * 0.56, w - 4, h * 0.38);
      ctx.fillStyle = '#1b1f27'; ctx.fillRect(x + 3, y + h * 0.62, w - 6, h * 0.2);
      ctx.fillStyle = COL.ink; ctx.fillRect(x + 4, y + h * 0.58, w - 8, 2);
    } else if (kind === 'fridge') {
      ctx.fillStyle = '#c8cfd8'; ctx.fillRect(x + w * 0.18, y + 2, w * 0.64, h - 4);
      ctx.fillStyle = '#aab2bd'; ctx.fillRect(x + w * 0.18, y + h * 0.46, w * 0.64, 2); // split
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + w * 0.7, y + h * 0.12, 2, h * 0.28); // handle
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + w * 0.7, y + h * 0.54, 2, h * 0.3);
    } else if (kind === 'counter') {
      ctx.fillStyle = '#7d858f'; ctx.fillRect(x + 1, y + h * 0.4, w - 2, h * 0.55);
      ctx.fillStyle = '#cdd4dc'; ctx.fillRect(x + 1, y + h * 0.4, w - 2, 3); // worktop
      ctx.fillStyle = COL.caution; ctx.fillRect(x + w * 0.3, y + h * 0.28, w * 0.18, h * 0.12); // a pot
    } else if (kind === 'rack') {
      // weight rack: two posts + a barbell with plates
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + w * 0.2, y + 2, 2, h * 0.9); ctx.fillRect(x + w * 0.78, y + 2, 2, h * 0.9);
      ctx.fillStyle = COL.steel; ctx.fillRect(x + w * 0.2, y + h * 0.3, w * 0.6, 2); // bar
      ctx.fillStyle = COL.ink; ctx.fillRect(x + w * 0.22, y + h * 0.22, 3, h * 0.18); ctx.fillRect(x + w * 0.72, y + h * 0.22, 3, h * 0.18); // plates
    } else if (kind === 'bench') {
      ctx.fillStyle = '#3a4150'; ctx.fillRect(x + w * 0.18, y + h * 0.5, w * 0.64, h * 0.14); // pad
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + w * 0.24, y + h * 0.64, 2, h * 0.28); ctx.fillRect(x + w * 0.72, y + h * 0.64, 2, h * 0.28); // legs
      // a barbell over the bench
      ctx.fillStyle = COL.steel; ctx.fillRect(x + w * 0.12, y + h * 0.4, w * 0.76, 2);
      ctx.fillStyle = COL.ink; ctx.fillRect(x + w * 0.12, y + h * 0.34, 3, h * 0.14); ctx.fillRect(x + w * 0.85, y + h * 0.34, 3, h * 0.14);
    } else if (kind === 'treadmill') {
      ctx.fillStyle = '#2c323d'; ctx.fillRect(x + 2, y + h * 0.55, w - 4, h * 0.4); // deck
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + 2, y + h * 0.55, w - 4, 2);
      ctx.fillStyle = '#3a4150'; ctx.fillRect(x + w * 0.7, y + h * 0.2, w * 0.2, h * 0.4); // console
      ctx.fillStyle = COL.pos; ctx.fillRect(x + w * 0.73, y + h * 0.26, w * 0.12, 3);
    } else if (kind === 'dumbbell') {
      ctx.fillStyle = COL.ink; ctx.fillRect(x + w * 0.3, y + h * 0.6, 4, 6); ctx.fillRect(x + w * 0.6, y + h * 0.6, 4, 6);
      ctx.fillStyle = COL.steelDk; ctx.fillRect(x + w * 0.34, y + h * 0.63, w * 0.26, 2);
    } else if (kind === 'whiteboard') {
      ctx.fillStyle = '#11151c'; ctx.fillRect(x + 1, y + 2, w - 2, h * 0.66);
      ctx.fillStyle = '#e7eaf2'; ctx.fillRect(x + 2, y + 3, w - 4, h * 0.6);
      ctx.strokeStyle = COL.accent; ctx.lineWidth = 1.2; ctx.beginPath();
      ctx.moveTo(x + w * 0.16, y + h * 0.18); ctx.lineTo(x + w * 0.5, y + h * 0.18);
      ctx.moveTo(x + w * 0.16, y + h * 0.34); ctx.lineTo(x + w * 0.66, y + h * 0.34);
      ctx.moveTo(x + w * 0.5, y + h * 0.5); ctx.lineTo(x + w * 0.82, y + h * 0.5); ctx.stroke();
      ctx.fillStyle = COL.pos; ctx.fillRect(x + w * 0.68, y + h * 0.12, w * 0.16, 3);
    } else if (kind === 'serverdesk') {
      ctx.fillStyle = COL.wood; ctx.fillRect(x + 1, y + h * 0.5, w - 2, h * 0.45); // desk
      // a server tower with blinking LEDs
      ctx.fillStyle = '#20262f'; ctx.fillRect(x + w * 0.12, y + h * 0.16, w * 0.22, h * 0.4);
      for (var L = 0; L < 3; L++) { ctx.fillStyle = ((Math.floor(T * 4) + L) % 2) ? COL.pos : '#234'; ctx.fillRect(x + w * 0.15, y + h * 0.2 + L * 4, 3, 2); }
      // a monitor
      this._screen(x + w * 0.5, y + h * 0.18, w * 0.4, h * 0.3, COL.accent);
    } else if (kind === 'terminal') {
      // account cubicle: a small desk + a $ screen
      ctx.fillStyle = COL.wood; ctx.fillRect(x + 1, y + h * 0.52, w - 2, h * 0.42);
      this._screen(x + w * 0.22, y + h * 0.14, w * 0.56, h * 0.34, COL.glow, '$');
    } else if (kind === 'engine') {
      // trading engine terminal: a chart screen
      ctx.fillStyle = '#20262f'; ctx.fillRect(x + 1, y + h * 0.5, w - 2, h * 0.45);
      this._screen(x + w * 0.18, y + h * 0.12, w * 0.64, h * 0.36, COL.alert, 'chart');
    } else if (kind === 'coffee') {
      ctx.fillStyle = '#2a2f3a'; ctx.fillRect(x + 2, y + h * 0.55, w - 4, h * 0.4);
      ctx.fillStyle = '#3c4250'; ctx.fillRect(x + w * 0.3, y + h * 0.2, w * 0.4, h * 0.4);
      ctx.fillStyle = COL.caution; ctx.fillRect(x + w * 0.4, y + h * 0.32, w * 0.2, 3);
      var st = (performance.now() / 700) % 1;
      ctx.strokeStyle = 'rgba(200,210,225,' + (0.3 * (1 - st)) + ')'; ctx.lineWidth = 1.4;
      var sx = x + w * 0.5, sy = y + h * 0.2 - st * h * 0.25; ctx.beginPath(); ctx.moveTo(sx, sy + 5); ctx.quadraticCurveTo(sx + 3, sy + 1, sx, sy - 3); ctx.stroke();
    }
  };

  // a little CRT screen with an animated scanline; optional glyph hint
  Office.prototype._screen = function (x, y, w, h, color, glyph) {
    var ctx = this.ctx;
    ctx.fillStyle = '#0c0f15'; ctx.fillRect(x - 1, y - 1, w + 2, h + 2);
    ctx.fillStyle = '#13202e'; ctx.fillRect(x, y, w, h);
    var T = (performance.now() / 600) % 1;
    ctx.fillStyle = 'rgba(' + this._rgb(color) + ',' + (0.16 + 0.1 * Math.sin(T * Math.PI * 2)) + ')';
    ctx.fillRect(x, y + h * (0.15 + 0.7 * T), w, 1.4);
    if (glyph === '$') { ctx.fillStyle = color; ctx.font = 'bold ' + Math.round(h * 0.6) + 'px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('$', x + w / 2, y + h / 2 + 1); }
    else if (glyph === 'chart') {
      ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath();
      ctx.moveTo(x + 2, y + h * 0.7); ctx.lineTo(x + w * 0.35, y + h * 0.4); ctx.lineTo(x + w * 0.6, y + h * 0.55); ctx.lineTo(x + w - 2, y + h * 0.22); ctx.stroke();
    }
  };
  Office.prototype._rgb = function (hex) {
    var h = hex.replace('#', ''); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)].join(',');
  };

  Office.prototype._drawCubicleLabels = function (s) {
    // label each terminal with the resident account alias (if a worker sits there)
    var ctx = this.ctx; ctx.save(); ctx.imageSmoothingEnabled = true; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '600 8px Inter, system-ui, sans-serif';
    for (var i = 0; i < s.spots.length; i++) {
      var sp = s.spots[i]; if (!sp.taken) continue;
      var w = this.workers[sp.taken]; if (!w) continue;
      var alias = tidy(w.account || w.runner || '', 12);
      if (!alias) continue;
      var t = this._tileRect(sp.c, sp.r);
      ctx.fillStyle = 'rgba(10,12,15,0.7)';
      var tw = ctx.measureText(alias).width + 6;
      roundRectPath(ctx, t.x + t.w / 2 - tw / 2, t.y + t.h * 0.7, tw, 11, 3); ctx.fill();
      ctx.fillStyle = COL.glow; ctx.fillText(alias, t.x + t.w / 2, t.y + t.h * 0.7 + 6);
    }
    ctx.restore();
  };

  Office.prototype._drawDebugPaths = function () {
    if (!this.debugPaths) return;
    var ctx = this.ctx, ids = Object.keys(this.workers);
    ctx.save(); ctx.lineWidth = 2;
    for (var i = 0; i < ids.length; i++) {
      var w = this.workers[ids[i]]; if (!w.path || w.path.length < 2) continue;
      ctx.strokeStyle = 'rgba(147,168,221,0.4)'; ctx.beginPath();
      for (var p = 0; p < w.path.length; p++) { var x = this._cx(w.path[p][0]), y = this._cy(w.path[p][1]); if (p === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); }
      ctx.stroke();
      ctx.fillStyle = 'rgba(205,223,251,0.55)';
      for (var q = w.pathIdx; q < w.path.length; q++) { ctx.beginPath(); ctx.arc(this._cx(w.path[q][0]), this._cy(w.path[q][1]), 2.2, 0, Math.PI * 2); ctx.fill(); }
    }
    ctx.restore();
  };

  Office.prototype._drawWorker = function (w) {
    var ctx = this.ctx, sheet = this.assets['char' + w.sprite];
    var sw = FW * SPRITE_SCALE, sh = FH * SPRITE_SCALE;
    var bobY = (w.state === 'dwell') ? Math.sin(w.bob * 2) * 1.1 : 0;
    var dx = Math.round(w.px - sw / 2), dy = Math.round(w.py - sh + 8 + bobY);
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, w.alpha));
    ctx.fillStyle = 'rgba(0,0,0,0.34)'; ctx.beginPath(); ctx.ellipse(w.px, w.py + 2, sw * 0.32, 4, 0, 0, Math.PI * 2); ctx.fill();
    ctx.imageSmoothingEnabled = false;
    var row = DIR_ROW[w.dir], col = w.frame % FRAMES;
    if (sheet) {
      if (w.dir === 'left') { ctx.translate(dx + sw, dy); ctx.scale(-1, 1); ctx.drawImage(sheet, col * FW, row * FH, FW, FH, 0, 0, sw, sh); }
      else ctx.drawImage(sheet, col * FW, row * FH, FW, FH, dx, dy, sw, sh);
    } else { ctx.fillStyle = COL.accent; ctx.fillRect(dx + 6, dy + 8, sw - 12, sh - 12); }
    ctx.restore();
    this._drawActivity(w, dx, dy, sw, sh);
    this._drawNameplate(w, w.px, dy);
  };

  Office.prototype._drawActivity = function (w, dx, dy, sw, sh) {
    if (w.state !== 'dwell') return;
    var ctx = this.ctx, T = performance.now() / 1000, k = w.dwellKind;
    if (k === 'stove' || k === 'counter') {
      ctx.fillStyle = 'rgba(224,162,60,' + (0.4 + 0.4 * Math.abs(Math.sin(T * 5))) + ')';
      ctx.fillRect(w.px - 2, dy - 4, 3, 3); // a little cooking spark
    } else if (k === 'rack' || k === 'bench' || k === 'dumbbell' || k === 'treadmill') {
      // exertion puff
      ctx.fillStyle = 'rgba(67,201,142,' + (0.3 + 0.3 * Math.abs(Math.sin(T * 4))) + ')';
      ctx.fillRect(w.px + 4, dy - 2, 2, 2);
    } else if (k === 'whiteboard') {
      ctx.strokeStyle = 'rgba(67,201,142,0.7)'; ctx.lineWidth = 1.5; var a = Math.sin(T * 2) * 0.4;
      ctx.beginPath(); ctx.moveTo(w.px, w.py - sh * 0.5); ctx.lineTo(w.px + Math.cos(-1 + a) * 9, w.py - sh * 0.5 + Math.sin(-1 + a) * 9); ctx.stroke();
    } else { // terminal / serverdesk / engine / idle → typing shimmer
      ctx.fillStyle = 'rgba(147,168,221,' + (0.4 + 0.4 * Math.abs(Math.sin(T * 6))) + ')';
      for (var i2 = 0; i2 < 3; i2++) if (((Math.floor(T * 8) + i2) % 3) === 0) ctx.fillRect(w.px - 6 + i2 * 5, dy - 4, 3, 3);
    }
  };

  Office.prototype._drawNameplate = function (w, cx, topY) {
    var ctx = this.ctx;
    var glyph = w.status === 'thinking' ? '…' : w.status === 'done' ? '✓' : '';
    var runner = tidy(w.runner || '—', 22);
    var line2 = roleWord(w.role) + (glyph ? ' ' + glyph : '');
    ctx.save(); ctx.globalAlpha = Math.max(0, Math.min(1, w.alpha)); ctx.imageSmoothingEnabled = true;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '600 11px "JetBrains Mono", ui-monospace, monospace'; var w1 = ctx.measureText(runner).width;
    ctx.font = '600 10px Inter, system-ui, sans-serif'; var w2 = ctx.measureText(line2).width;
    var plateW = Math.max(w1, w2) + 14, plateH = 28;
    var px = Math.round(cx - plateW / 2), py = Math.round(topY - plateH - 4);
    ctx.fillStyle = 'rgba(10,12,15,0.86)'; ctx.strokeStyle = 'rgba(147,168,221,0.3)'; ctx.lineWidth = 1;
    roundRectPath(ctx, px, py, plateW, plateH, 6); ctx.fill(); ctx.stroke();
    ctx.font = '600 11px "JetBrains Mono", ui-monospace, monospace'; ctx.fillStyle = COL.glow; ctx.fillText(runner, cx, py + 9);
    ctx.font = '600 10px Inter, system-ui, sans-serif';
    ctx.fillStyle = w.status === 'thinking' ? COL.muted : w.status === 'done' ? COL.pos : COL.accent; ctx.fillText(line2, cx, py + 21);
    ctx.fillStyle = 'rgba(10,12,15,0.86)'; ctx.beginPath();
    ctx.moveTo(cx - 4, py + plateH - 1); ctx.lineTo(cx + 4, py + plateH - 1); ctx.lineTo(cx, py + plateH + 5); ctx.closePath(); ctx.fill();
    ctx.restore();
  };

  Office.prototype._frame = function (ts) {
    if (!this.running) return;
    // The per-frame body is wrapped so a single transient draw/update error can
    // never permanently kill the rAF loop (it would otherwise stop rescheduling
    // and the office would freeze). The first error is surfaced for debugging.
    try {
      var dt = this.last ? Math.min(60, ts - this.last) : 16; if (dt <= 0) dt = 16; this.last = ts;
      if (this.canvas.clientWidth !== this.W || this.canvas.clientHeight !== this.H) this._resize();
      this._update(dt, ts);
      this._drawFloor();
      this._drawSectorWalls();
      this._drawFurniture();
      this._drawSectorLabels();
      this._drawDebugPaths();
      var ids = Object.keys(this.workers).sort(function (a, b) { return this.workers[a].py - this.workers[b].py; }.bind(this));
      for (var i = 0; i < ids.length; i++) this._drawWorker(this.workers[ids[i]]);
    } catch (e) {
      if (!global.__gxFrameError) { global.__gxFrameError = String((e && e.stack) || e); try { console.error('GammaPixels frame error:', e); } catch (_) {} }
    }
    this.raf = global.requestAnimationFrame(this._frame.bind(this));
  };

  // ───────────────────────────────────────────────────────────────────────────
  var GammaPixels = {
    mount: function (canvasEl, opts) {
      if (!canvasEl) throw new Error('GammaPixels.mount: canvas element required');
      if (inst) this.unmount();
      if (!global.__lastPaths) global.__lastPaths = {};
      inst = new Office(canvasEl, opts);
      global.addEventListener('resize', inst._onResize);
      var self = inst; self._resize();
      self.loadAssets().then(function () {
        self._resize(); self.running = true; self.last = performance.now();
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
      try { inst.ctx.clearRect(0, 0, inst.canvas.width, inst.canvas.height); } catch (_) {}
      inst = null; return this;
    }
  };

  // read-only verification globals
  global.__gxSnapshot = function () {
    if (!inst) return [];
    return Object.keys(inst.workers).map(function (id) {
      var w = inst.workers[id];
      return { id: id, role: w.role, runner: w.runner, account: w.account, status: w.status,
        state: w.state, sector: w.sectorKey, c: w.c, r: w.r, px: Math.round(w.px), py: Math.round(w.py),
        dir: w.dir, pathLen: w.path ? w.path.length : 0, pathIdx: w.pathIdx,
        spot: w.spot ? [w.spot.c, w.spot.r] : null, alpha: +w.alpha.toFixed(2) };
    });
  };
  global.__gxGrid = function () { return inst ? inst.grid : null; };
  // Deterministic frame driver — ONLY for verification when a headless test tab is
  // backgrounded (Chromium suspends rAF while document.hidden, so the self-driven
  // loop can't tick). On a real visible window the rAF loop drives itself and this
  // is never needed. Steps `frames` updates+draws of `dtMs` each from a synthetic
  // clock that never lags performance.now() (so dwell timers still fire).
  global.__gxPump = function (frames, dtMs) {
    if (!inst) return null;
    frames = frames || 1; dtMs = dtMs || 16;
    var base = (global.__gxPumpClock == null) ? (inst.last || performance.now()) : global.__gxPumpClock;
    base = Math.max(base, performance.now());
    for (var i = 0; i < frames; i++) { base += dtMs; inst.running = true; inst._frame(base); }
    global.__gxPumpClock = base;
    return global.__gxSnapshot();
  };
  global.__gxSectors = function () {
    if (!inst || !inst.sectors) return null;
    var out = {};
    Object.keys(inst.sectors).forEach(function (k) {
      var s = inst.sectors[k];
      out[k] = { label: s.label, x: s.x, y: s.y, x2: s.x2, y2: s.y2, door: s.door,
        furnitureCount: s.furniture.length, spotCount: s.spots.length,
        furnitureKinds: s.furniture.map(function (f) { return f.kind; }) };
    });
    out.__cardRect = inst.cardRect;
    return out;
  };

  global.GammaPixels = GammaPixels;
  if (typeof module !== 'undefined' && module.exports) module.exports = GammaPixels;

})(typeof window !== 'undefined' ? window : this);

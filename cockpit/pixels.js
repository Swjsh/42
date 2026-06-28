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
 *
 * FURNITURE/FLOORS: if the premium LimeZu Modern Interiors sheets are present
 * (assets/pixel/limezu/interiors16.png + roombuilder16.png — gitignored,
 * local-only), the office draws REAL LimeZu pixel-art furniture + floors/walls.
 * GRACEFUL FALLBACK: when those sheets are absent (a fresh clone), it falls back
 * to the built-in PROCEDURAL furniture/floors — the committed file always works
 * and looks fine with zero LimeZu assets. Gym gear is always procedural (the
 * free LimeZu pack has no gym equipment). Workers stay on the MIT char sheets
 * (the LimeZu character frame grid wasn't cleanly determinable — see report).
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

  // ── LimeZu THEMED furniture tile regions (16px tiles: sheet, col, row, w, h).
  //    Mapped by reading each theme sheet with a coordinate grid (see report).
  //    `sheet` keys into Office.lz.* . Kinds absent here stay procedural (gym
  //    gear uses the pre-built gym room blit, not these). ──
  var LZ_FURN = {
    // KITCHEN (th_kitchen)
    stove:       { sheet: 'kitchen', c: 8,  r: 11, w: 2, h: 2 },  // 4-burner stove+oven
    counter:     { sheet: 'kitchen', c: 0,  r: 11, w: 2, h: 2 },  // wood counter+cabinet
    fridge:      { sheet: 'kitchen', c: 2,  r: 1,  w: 2, h: 3 },  // tall fridge
    sink:        { sheet: 'kitchen', c: 6,  r: 7,  w: 2, h: 2 },  // counter w/ sink
    // LAB / R&D (th_conf + th_generic)
    whiteboard:  { sheet: 'conf',    c: 6,  r: 4,  w: 2, h: 2 },  // wall board/screen
    meeting:     { sheet: 'conf',    c: 5,  r: 7,  w: 4, h: 2 },  // big meeting table
    serverdesk:  { sheet: 'generic', c: 4,  r: 8,  w: 2, h: 2 },  // desk (research)
    server:      { sheet: 'conf',    c: 15, r: 8,  w: 1, h: 2 },  // server tower
    // ACCOUNTS / TRADING terminals (th_generic desk + monitor accent)
    terminal:    { sheet: 'generic', c: 4,  r: 8,  w: 2, h: 2 },  // desk = workstation
    engine:      { sheet: 'generic', c: 0,  r: 8,  w: 2, h: 2 },  // desk variant
    // DISPATCH service counter + register (th_grocery)
    counter_svc: { sheet: 'grocery', c: 1,  r: 8,  w: 2, h: 2 },  // glass display counter
    register:    { sheet: 'grocery', c: 1,  r: 8,  w: 2, h: 2 },  // counter (register drawn on top)
    // shared decor
    plant:       { sheet: 'generic', c: 5,  r: 5,  w: 1, h: 1 }   // small plant
  };
  // roombuilder tiles (rb_floors.png + rb_walls.png) — a distinct floor PER ROOM,
  // and one shared clean wall tile so every room reads as the same building.
  var LZ_WALL  = { c: 1,  r: 4,  w: 1, h: 1 };               // rb_walls grey wall
  var LZ_FLOORS = {                                          // rb_floors per room (verified tiles)
    kitchen:  { c: 1,  r: 9 },   // cream/yellow tile  (231,228,169)
    trading:  { c: 9,  r: 21 },  // slate-purple       (106,101,152)
    lab:      { c: 9,  r: 25 },  // clean teal         (161,210,208)
    accounts: { c: 13, r: 29 },  // light blue         (186,209,220)
    dispatch: { c: 1,  r: 13 },  // warm wood/gold     (184,149,76)
    gym:      { c: 13, r: 5 },   // grey concrete (gym uses pre-built room anyway)
    _default: { c: 13, r: 5 }    // grey concrete for corridors
  };

  // ── PRE-BUILT LimeZu ROOM DESIGNS (6_Home_Designs): one whole, professionally
  //    arranged room blitted per sector — the technique that makes the gym look
  //    great, now applied to EVERY room. {w,h}=native px, layers=lz keys bottom→top.
  //    Thematic mapping: accounts=Shooting-Range booths, lab=Museum gallery,
  //    kitchen=Generic Home, trading=TV Studio consoles, dispatch=Ice-Cream counter.
  var DESIGNS = {
    gym:      { w: 304, h: 240, layers: ['gymBase', 'gymFurn'] },
    accounts: { w: 304, h: 214, layers: ['acctBase', 'acctFurn'] },
    lab:      { w: 320, h: 272, layers: ['labBase', 'labFurn'] },
    kitchen:  { w: 224, h: 214, layers: ['kitBase', 'kitFurn'] },
    trading:  { w: 176, h: 160, layers: ['trdBase', 'trdFurn', 'trdTop'] },
    dispatch: { w: 192, h: 160, layers: ['dispBase', 'dispFurn', 'dispTop'] }
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
    this._cardPx = null;        // real dashboard-card footprint in px (set by face.html)
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
    // OPTIONAL premium LimeZu Modern Interiors sheets (gitignored, local-only).
    // GRACEFUL FALLBACK: if the CORE sheets (walls/floors + the 4 furniture themes)
    // fail to load (fresh clone), _lzReady() stays false and the office draws the
    // built-in PROCEDURAL furniture/floors. The gym room blit is best-effort: if
    // gym_base/gym_furn are missing, the gym falls back to procedural gear too.
    self.lz = { walls: null, floors: null, doors: null, gymBase: null, gymFurn: null,
                kitchen: null, conf: null, generic: null, grocery: null, interiors: null,
                acctBase: null, acctFurn: null, labBase: null, labFurn: null,
                kitBase: null, kitFurn: null, trdBase: null, trdFurn: null, trdTop: null,
                dispBase: null, dispFurn: null, dispTop: null };
    var lzBase = self.assetBase + '/limezu';
    var load = function (file, key) { jobs.push(self._loadImg(lzBase + '/' + file).then(function (im) { self.lz[key] = im; })); };
    load('rb_walls.png', 'walls'); load('rb_floors.png', 'floors'); load('rb_doors.png', 'doors');
    load('gym_base.png', 'gymBase'); load('gym_furn.png', 'gymFurn');
    load('th_kitchen.png', 'kitchen'); load('th_conf.png', 'conf');
    load('th_generic.png', 'generic'); load('th_grocery.png', 'grocery');
    load('interiors16.png', 'interiors');   // legacy decor (plants etc.)
    // PRE-BUILT ROOM DESIGNS (6_Home_Designs) — one whole room blitted per sector,
    // the same technique as the gym. See DESIGNS map for native sizes + layers.
    load('acct_base.png', 'acctBase'); load('acct_furn.png', 'acctFurn');
    load('lab_base.png', 'labBase');   load('lab_furn.png', 'labFurn');
    load('kit_base.png', 'kitBase');   load('kit_furn.png', 'kitFurn');
    load('trd_base.png', 'trdBase');   load('trd_furn.png', 'trdFurn'); load('trd_top.png', 'trdTop');
    load('disp_base.png', 'dispBase'); load('disp_furn.png', 'dispFurn'); load('disp_top.png', 'dispTop');
    return Promise.all(jobs);
  };
  // The premium look needs walls + floors + all 4 furniture themes decoded.
  Office.prototype._lzReady = function () {
    var z = this.lz; if (!z) return false;
    return !!(z.walls && z.walls.width && z.floors && z.floors.width &&
              z.kitchen && z.kitchen.width && z.conf && z.conf.width &&
              z.generic && z.generic.width && z.grocery && z.grocery.width);
  };
  Office.prototype._gymRoomReady = function () {
    return !!(this.lz && this.lz.gymBase && this.lz.gymBase.width && this.lz.gymFurn && this.lz.gymFurn.width);
  };
  // pick the sheet image for a furniture mapping
  Office.prototype._sheetFor = function (name) {
    var z = this.lz; if (!z) return null;
    return z[name] || null;
  };
  // Blit a tile-region of a 16px sheet to a dest rect (crisp, no smoothing).
  Office.prototype._blit = function (sheet, tc, tr, tw, th, dx, dy, dw, dh) {
    var ctx = this.ctx; ctx.imageSmoothingEnabled = false;
    ctx.drawImage(sheet, tc * 16, tr * 16, tw * 16, th * 16, dx, dy, dw, dh);
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

  // Reserve the REAL dashboard-card footprint (px, from face.html). Rebuilds the
  // layout only when the reserved tile span meaningfully changes (avoids thrash).
  Office.prototype.setCardRect = function (rect) {
    if (!rect || !(rect.w > 0)) return;
    var next = { x: rect.x || 0, y: rect.y || 0, w: rect.w, h: rect.h || 0 };
    var prev = this._cardPx;
    this._cardPx = next;
    if (!this.grid) return;                 // first build will pick it up
    if (prev && Math.abs(prev.x - next.x) < this.grid.cw &&
        Math.abs(prev.w - next.w) < this.grid.cw &&
        Math.abs(prev.h - next.h) < this.grid.ch) return;
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

    // reserved card rectangle. Prefer the REAL dashboard-card footprint measured
    // by face.html (setCardRect) so the office never overhangs the card and bleeds
    // through the glass; fall back to a centered ~450px column to ~55% height.
    var cardLo, cardHi, cardBottom;
    if (this._cardPx && this._cardPx.w > 0) {
      var p = this._cardPx;
      cardLo = Math.max(0, Math.floor(p.x / cw) - 1);
      cardHi = Math.min(cols - 1, Math.ceil((p.x + p.w) / cw) + 1);
      // reserve the FULL card height — the office now lives in the side margins,
      // so a tall card no longer starves it, and the vitals can't bleed through.
      cardBottom = Math.max(3, Math.min(rows - 2, Math.ceil((p.y + p.h) / ch)));
    } else {
      var halfCard = Math.ceil(228 / cw);
      var midC = Math.floor(cols / 2);
      cardLo = Math.max(0, midC - halfCard); cardHi = Math.min(cols - 1, midC + halfCard);
      cardBottom = Math.min(rows - 4, Math.round(rows * 0.55));
    }
    this.cardRect = { lo: cardLo, hi: cardHi, bottom: cardBottom };

    var obstacles = {};                 // global blockers (walls/furniture)
    this.obstacles = obstacles;
    var occ = function (c, r) { obstacles[r * cols + c] = true; };
    for (var rr = 0; rr <= cardBottom; rr++) for (var cc = cardLo; cc <= cardHi; cc++) occ(cc, rr);

    // ── ECOSYSTEM layout: WALLED ROOMS separated by a CORRIDOR of open floor.
    //    Rooms are inset by 1 tile from the screen edge / card column so a
    //    continuous corridor ring surrounds them; each room opens to that
    //    corridor through ONE doorway. DISPATCH sits center, just below the card
    //    column, also on the corridor — agents path room → doorway → corridor →
    //    DISPATCH and back. The corridor is ONE connected open-floor region, so a
    //    room→dispatch→room route is guaranteed (asserted in the sim).
    //
    //      ┌─────────┐ corridor ┌─────────┐
    //      │ ACCOUNTS│  (cards) │   LAB   │
    //      │ (left)  │ ┌──────┐ │ (right) │
    //      │         │ │DISPAT│ │         │
    //      │         │ └──────┘ │         │
    //      │  ┌────┬────┬────┐  │         │
    //      └──┤KITCH│TRD│GYM ├──┘  (bottom rooms)
    //         └────┴────┴────┘
    var bandTop = cardBottom + 1;
    var sectors = {};
    this.sectors = sectors;
    // corridor = open-floor tiles between rooms (filled after rooms are carved)
    var corridor = {}; this.corridor = corridor;

    var self = this;
    // Build a WALLED ROOM rect [x..x2]x[y..y2] inclusive: wall ring (obstacles) +
    // walkable interior + ONE doorway punched in the wall facing `doorSide`. The
    // doorway tile AND the corridor tile just outside it are both opened so the
    // room connects to the corridor.
    function makeRoom(key, label, color, x, y, x2, y2, doorSide) {
      x = Math.max(0, x); y = Math.max(0, y); x2 = Math.min(cols - 1, x2); y2 = Math.min(rows - 1, y2);
      if (x2 - x < 2 || y2 - y < 2) return null;
      var interior = {}, interiorList = [];
      for (var c = x; c <= x2; c++) { occ(c, y); occ(c, y2); }
      for (var r = y; r <= y2; r++) { occ(x, r); occ(x2, r); }
      for (var ic = x + 1; ic <= x2 - 1; ic++) for (var ir = y + 1; ir <= y2 - 1; ir++) {
        interior[ir * cols + ic] = true; interiorList.push([ic, ir]);
      }
      var door, outside;
      if (doorSide === 'bottom')      { door = [clampc((x + x2) >> 1), y2]; outside = [door[0], Math.min(rows - 1, y2 + 1)]; }
      else if (doorSide === 'left')   { door = [x, clampr((y + y2) >> 1)]; outside = [Math.max(0, x - 1), door[1]]; }
      else if (doorSide === 'right')  { door = [x2, clampr((y + y2) >> 1)]; outside = [Math.min(cols - 1, x2 + 1), door[1]]; }
      else                            { door = [clampc((x + x2) >> 1), y]; outside = [door[0], Math.max(0, y - 1)]; }
      delete obstacles[door[1] * cols + door[0]];
      interior[door[1] * cols + door[0]] = true;
      // the tile just outside the doorway must be corridor (open) — clear it
      delete obstacles[outside[1] * cols + outside[0]];
      corridor[outside[1] * cols + outside[0]] = true;
      var s = { key: key, label: label, color: color, x: x, y: y, x2: x2, y2: y2,
        interior: interior, interiorList: interiorList, door: door, outside: outside,
        spots: [], furniture: [] };
      sectors[key] = s; return s;
    }
    function clampc(c) { return Math.max(0, Math.min(cols - 1, c)); }
    function clampr(r) { return Math.max(0, Math.min(rows - 1, r)); }

    // ── ROBUST LAYOUT (works at ANY window size) ─────────────────────────────
    //   The Gamma card can be very tall, so the office lives entirely in the two
    //   side MARGINS (full height) — NEVER below the card, so a tall card can't
    //   starve it. Each margin STACKS 3 rooms; a 1-tile hallway flanks the card,
    //   runs between the stacked rooms, and along the bottom — forming ONE
    //   connected corridor that reaches DISPATCH from every room.
    //     LEFT : LAB / ACCOUNTS / DISPATCH       RIGHT: GYM / KITCHEN / TRADING
    //   Each design's REAL door faces that corridor (bottom doors -> the hall
    //   below the room; KITCHEN's left door -> the centre corridor).
    var M = 1, HALL = 1;
    var topY = M;
    var bRoomBot = rows - 1 - M;
    var leftX = M, leftX2 = cardLo - 1 - HALL;          // left-margin room cols
    var rightX = cardHi + 1 + HALL, rightX2 = cols - 1 - M;

    // Fit a room to its DESIGN's aspect, anchored so the art fills the footprint
    // and the chosen door edge faces open corridor. ax 'l'|'r'|'c', ay 't'|'b'|'c'.
    function fitRoom(key, label, color, zx, zy, zx2, zy2, doorSide, ax, ay) {
      zx = Math.max(0, zx); zy = Math.max(0, zy); zx2 = Math.min(cols - 1, zx2); zy2 = Math.min(rows - 1, zy2);
      var zw = zx2 - zx + 1, zh = zy2 - zy + 1;
      if (zw < 3 || zh < 3) return null;
      var rw = zw, rh = zh, d = DESIGNS[key];
      if (d) {
        var a = d.w / d.h;
        if (zw / zh > a) { rh = zh; rw = Math.max(3, Math.round(zh * a)); }
        else { rw = zw; rh = Math.max(3, Math.round(zw / a)); }
        rw = Math.min(rw, zw); rh = Math.min(rh, zh);
      }
      var ox = ax === 'l' ? zx : ax === 'r' ? (zx2 - rw + 1) : zx + Math.floor((zw - rw) / 2);
      var oy = ay === 't' ? zy : ay === 'b' ? (zy2 - rh + 1) : zy + Math.floor((zh - rh) / 2);
      return makeRoom(key, label, color, ox, oy, ox + rw - 1, oy + rh - 1, doorSide);
    }
    // split [y0..y1] vertically into 3 stacked sub-zones with a 1-tile hall between.
    function stack3(y0, y1) {
      var h = y1 - y0 + 1, sub = Math.max(3, Math.floor((h - 2 * HALL) / 3));
      return [[y0, y0 + sub - 1],
              [y0 + sub + HALL, y0 + 2 * sub + HALL - 1],
              [y0 + 2 * sub + 2 * HALL, y1]];
    }
    var lz3 = stack3(topY, bRoomBot), rz3 = stack3(topY, bRoomBot);
    // LEFT margin — rooms hug the card (anchor right); the bottom door opens into
    // the hall below each room, the outer screen edge is the peripheral corridor.
    fitRoom('lab',      'LAB / R&D', COL.accent, leftX, lz3[0][0], leftX2, lz3[0][1], 'bottom', 'r', 'c');
    fitRoom('accounts', 'ACCOUNTS',  COL.glow,   leftX, lz3[1][0], leftX2, lz3[1][1], 'bottom', 'r', 'c');
    fitRoom('dispatch', 'DISPATCH',  COL.glow,   leftX, lz3[2][0], leftX2, lz3[2][1], 'bottom', 'r', 'c');
    // RIGHT margin — rooms hug the card (anchor left); KITCHEN's left door faces
    // the centre corridor.
    fitRoom('gym',     'GYM',      COL.pos,     rightX, rz3[0][0], rightX2, rz3[0][1], 'bottom', 'l', 'c');
    fitRoom('kitchen', 'KITCHEN',  COL.caution, rightX, rz3[1][0], rightX2, rz3[1][1], 'left',   'l', 'c');
    fitRoom('trading', 'TRADING',  COL.alert,   rightX, rz3[2][0], rightX2, rz3[2][1], 'bottom', 'l', 'c');

    // Fallbacks so no role is ever sector-less (degenerate tiny grids).
    if (!sectors.lab) makeRoom('lab', 'LAB / R&D', COL.accent, Math.max(M, rightX), topY, cols - 1 - M, Math.floor(rows / 2), 'left');
    this.sectorAlias = {};
    var allKeys = ['kitchen', 'gym', 'lab', 'accounts', 'trading', 'dispatch'];
    for (var ak = 0; ak < allKeys.length; ak++) {
      if (!sectors[allKeys[ak]]) this.sectorAlias[allKeys[ak]] = sectors.lab ? 'lab' : 'dispatch';
    }

    // ── CORRIDOR: every non-room, non-card, non-wall tile becomes open corridor
    //    floor. This is the connected region the doorways open onto. (Rooms +
    //    card already marked obstacle; furniture added later inside rooms.) ──
    for (var cr = 0; cr < rows; cr++) for (var cc2 = 0; cc2 < cols; cc2++) {
      var key = cr * cols + cc2;
      if (obstacles[key]) continue;                 // wall / card / room-edge
      var inRoom = false;
      for (var si = 0; si < allKeys.length; si++) { var s2 = sectors[allKeys[si]]; if (s2 && s2.interior[key]) { inRoom = true; break; } }
      if (!inRoom) corridor[key] = true;            // open corridor floor
    }

    // ── populate THEMED furniture + dwell spots per room ──
    this._furnishSectors();

    // re-validate workers against the rebuilt layout
    Object.keys(this.workers).forEach(function (id) {
      var w = self.workers[id];
      // re-derive the home sector from the ROLE so a worker that spawned while its
      // room was briefly missing gets moved back to its real room once it exists.
      var want = sectorForRole(w.role);
      var sec = sectors[want] || sectors[w.sectorKey] || sectors.lab;
      w.sectorKey = sec ? sec.key : 'lab';
      // clamp into the sector interior; reset pathing. DROP the stale spot first —
      // it points into the OLD layout, so _spotFor must hand out a fresh desk in
      // the rebuilt room (else the worker teleports to where its desk used to be).
      w.spot = null;
      var spot = self._spotFor(w);
      w.c = spot ? spot.c : (sec ? sec.door[0] : 1);
      w.r = spot ? spot.r : (sec ? sec.door[1] : 1);
      w.px = self._cx(w.c); w.py = self._cy(w.r);
      w.path = null; w.pathIdx = 0; w.target = null; w.dwellUntil = 0;
      w.state = (w.state === 'leaving') ? 'leaving' : 'idle';
    });
  };

  // Walkability for worker `w`.
  //  - DEFAULT (w.roaming false): confined to the home room interior — agents
  //    stay home when working/idle.
  //  - ROAMING (w.roaming true): home interior ∪ the CORRIDOR ∪ the DISPATCH
  //    interior — so on a task pickup the agent can path out its doorway, through
  //    the corridor, into dispatch, and back. Furniture + others' chairs block.
  Office.prototype._walkableFor = function (w) {
    var self = this, g = this.grid, cols = g.cols, sec = this.sectors[w.sectorKey];
    var disp = this.sectors.dispatch;
    return function (c, r) {
      if (c < 0 || r < 0 || c >= cols || r >= g.rows) return false;
      var key = r * cols + c;
      if (self.obstacles[key]) return false;                     // furniture/wall/card
      var ok = sec && sec.interior[key];                         // home room
      if (!ok && w.roaming) {
        ok = self.corridor[key] || (disp && disp.interior[key]); // corridor or dispatch
      }
      if (!ok) return false;
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

      // STATION unit: a furniture obstacle + a dwell SPOT in front of it (a tile a
      // worker stands on, facing the furniture). Used for the things workers use.
      function addUnit(fc, fr, kind, faceDir) {
        if (fc < x || fc > x2 || fr < y || fr > y2) return false;
        if (self.obstacles[fr * cols + fc]) return false;
        var sc = fc, sr = fr + 1, sdir = 'up';
        if (faceDir === 'down') { sr = fr - 1; sdir = 'down'; }
        if (sr < y || sr > y2) { sr = fr + 1; sdir = 'up'; if (sr > y2) return false; }
        if (self.obstacles[sr * cols + sc]) return false;
        occ(fc, fr);
        s.furniture.push({ c: fc, r: fr, kind: kind });
        s.spots.push({ c: sc, r: sr, dir: sdir, kind: kind, taken: null });
        return true;
      }
      // DECOR unit: a furniture obstacle with NO dwell spot — pure visual fill so
      // a room never reads as empty floor. Placed only where it does NOT trap a
      // tile (every decor tile keeps ≥3 open orthogonal neighbours so lanes
      // remain and the room stays fully traversable → containment/routes hold).
      function freeTile(c, r) { return c >= x && c <= x2 && r >= y && r <= y2 && !self.obstacles[r * cols + c]; }
      function openNeighbours(c, r) {
        var n = 0;
        if (freeTile(c - 1, r)) n++; if (freeTile(c + 1, r)) n++;
        if (freeTile(c, r - 1)) n++; if (freeTile(c, r + 1)) n++;
        return n;
      }
      function addDecor(fc, fr, kind) {
        if (!freeTile(fc, fr)) return false;
        if (fc === s.door[0] && fr === s.door[1]) return false;
        // don't sit a decor tile ON a worker's dwell spot
        for (var i = 0; i < s.spots.length; i++) if (s.spots[i].c === fc && s.spots[i].r === fr) return false;
        // keep the tile from becoming a chokepoint: require ≥3 currently-open
        // orthogonal neighbours so removing this tile can't disconnect the room.
        if (openNeighbours(fc, fr) < 3) return false;
        occ(fc, fr);
        s.furniture.push({ c: fc, r: fr, kind: kind, decor: true });
        return true;
      }

      // Fill density scales with ROOM AREA. We (1) place the room's STATION
      // furniture (the things workers use), then (2) DENSE-LINE the perimeter +
      // sprinkle interior clusters with themed DECOR so big rooms read as fully
      // furnished, lived-in spaces — never large empty floors. Decor is placed on
      // a sparse lattice (every other tile, walls first) so walking lanes remain.
      var area = iw * ih;
      function lineWalls(kinds, density) {
        // walk the inner-perimeter ring, dropping decor every `density` tiles.
        var ki = 0, step = density || 2, i = 0;
        // top + bottom rows
        for (var c = x; c <= x2; c++) {
          if (i++ % step === 0) { if (addDecor(c, y, kinds[ki++ % kinds.length])) {} }
          if (ih > 2 && (i++ % step === 0)) { addDecor(c, y2, kinds[ki++ % kinds.length]); }
        }
        // left + right columns
        for (var r = y + 1; r <= y2 - 1; r++) {
          if (i++ % step === 0) { addDecor(x, r, kinds[ki++ % kinds.length]); }
          if (iw > 2 && (i++ % step === 0)) { addDecor(x2, r, kinds[ki++ % kinds.length]); }
        }
      }
      function interiorClusters(kinds, targetCount) {
        // scatter decor through the interior on a coarse lattice (every 2 tiles
        // each axis, offset rows) until we hit the area-scaled target.
        var ki = 0, placed = 0, guard = 0;
        for (var r = y + 1; r <= y2 - 1 && placed < targetCount; r += 2) {
          var off = ((r - y) >> 1) % 2;                  // stagger alternate rows
          for (var c = x + 1 + off; c <= x2 - 1 && placed < targetCount; c += 2) {
            if (guard++ > 4000) return placed;
            if (addDecor(c, r, kinds[ki++ % kinds.length])) placed++;
          }
        }
        return placed;
      }

      if (key === 'dispatch') {
        // DISPATCH HUB (≥3 interior rows): a service COUNTER + register runs the
        // full top wall (the pickup desk, a worker spot below every other tile);
        // the BACK wall gets a row of shelves/servers so the hub reads as a busy
        // task-dispatch station. The middle row stays open so agents reach the
        // counter from the bottom doorway (pickup route).
        for (var dc = x; dc <= x2; dc += 2) addUnit(dc, y, 'counter_svc', 'up');
        if (s.furniture.length) s.furniture[Math.floor(s.furniture.length / 2)].kind = 'register';
        if (s.spots.length < 2) { addUnit(x, y, 'counter_svc', 'up'); addUnit(x2, y, 'counter_svc', 'up'); }
        // back-wall shelves (bottom interior row, beside the doorway) as decor
        var bk = ['server', 'counter', 'plant'], bi = 0;
        for (var bxc = x; bxc <= x2; bxc += 2) {
          if (bxc === s.door[0]) continue;                 // keep the doorway clear
          addDecor(bxc, y2, bk[bi++ % bk.length]);
        }
      } else if (key === 'accounts') {
        // CUBICLE TERMINALS fill the whole accounts room — a workstation every
        // ~3 cols x 3 rows so the room is a dense grid of cubicles, not 6 floating
        // desks. (Account residents claim the first 6; extras read as more desks.)
        var made = 0;
        for (var rr = y; rr <= y2 - 1; rr += 3) {
          for (var ccx = x; ccx <= x2; ccx += 3) {
            if (addUnit(ccx, rr, 'terminal', 'up')) made++;
          }
        }
        s.cubicleCount = made;
        // densely fill the leftover floor: plants/shelves line the walls AND
        // interior clusters so the tall accounts room is never bare floor.
        lineWalls(['plant', 'serverdesk', 'server'], 2);
        interiorClusters(['plant', 'serverdesk'], Math.round(area * 0.12));
      } else if (key === 'lab') {
        // R&D: whiteboards + research/server desks as STATIONS spread on a 3-grid,
        // then dense decor (servers, plants, shelves) lining walls + interior.
        for (var lr = y; lr <= y2 - 1; lr += 3) {
          var lk = 0;
          for (var lc = x; lc <= x2; lc += 3) { addUnit(lc, lr, (lk++ % 2 ? 'serverdesk' : 'whiteboard'), 'up'); }
        }
        lineWalls(['server', 'whiteboard', 'plant'], 2);
        interiorClusters(['server', 'plant'], Math.round(area * 0.10));
      } else if (key === 'kitchen') {
        // KITCHEN: stoves/counters/fridge/sink as STATIONS on a 3-grid, then
        // counters + fridges line the walls densely so it reads as a full kitchen.
        var kk = ['stove', 'counter', 'fridge', 'sink'];
        for (var kr = y; kr <= y2 - 1; kr += 3) {
          var ki2 = 0;
          for (var kc = x; kc <= x2; kc += 3) { addUnit(kc, kr, kk[ki2++ % kk.length], 'up'); }
        }
        lineWalls(['counter', 'stove', 'fridge', 'sink'], 1);  // dense (wide, short room)
        interiorClusters(['counter', 'stove'], Math.round(area * 0.20));
      } else if (key === 'trading') {
        // TRADING: engine/beacon terminals as STATIONS on a 3-grid, then desks +
        // screens + coffee densely fill the room (was the big empty purple room).
        for (var tr = y; tr <= y2 - 1; tr += 3) {
          for (var tc = x; tc <= x2; tc += 3) { addUnit(tc, tr, 'engine', 'up'); }
        }
        lineWalls(['engine', 'serverdesk', 'coffee', 'plant'], 1);  // dense (wide, short room)
        interiorClusters(['engine', 'serverdesk'], Math.round(area * 0.20));
      } else if (key === 'gym') {
        // GYM keeps the pre-built room blit (full of equipment) — no procedural
        // furniture needed. Spots still placed so gym workers have somewhere to
        // stand, but they aren't drawn (the gym room covers them).
        for (var gr = y; gr <= y2 - 1; gr += 3) {
          var gk = ['rack', 'bench', 'dumbbell', 'treadmill'];
          var gi = 0;
          for (var gc = x; gc <= x2; gc += 3) { addUnit(gc, gr, gk[gi++ % gk.length], 'up'); }
        }
      }

      // guarantee at least ONE spot so a worker can always stand somewhere.
      if (!s.spots.length) {
        var fbC = Math.round((s.x + s.x2) / 2), fbR = Math.round((s.y + s.y2) / 2);
        if (!self.obstacles[fbR * cols + fbC]) s.spots.push({ c: fbC, r: fbR, dir: 'down', kind: 'idle', taken: null });
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
      roaming: false, pickupTask: null,   // dispatch-pickup trip state
      alpha: 0, bob: Math.random() * Math.PI * 2
    };
    if (role === 'account') { w.acctSlot = this._acctSlot % 6; this._acctSlot++; }
    w.px = this._cx(w.c); w.py = this._cy(w.r);
    this.workers[rec.id] = w;
  };

  Office.prototype._beginLeave = function (w) {
    if (w.state === 'leaving') return;
    this._freeSpot(w);
    w.roaming = false;
    w.state = 'leaving';
    w.dwellUntil = 0;
    var sec = this.sectors[w.sectorKey];
    if (sec) this._setPath(w, sec.door); else w.path = null;
  };

  // DISPATCH PICKUP: the agent leaves its station, opens roaming so A* may route
  // through the corridor, and heads to the dispatch counter. The counter spot is
  // the dwell target where it picks up the ticket. If dispatch is unreachable
  // (shouldn't happen — corridor is connected) it falls back to staying home.
  Office.prototype._beginPickup = function (w) {
    var disp = this.sectors.dispatch; if (!disp || !disp.spots.length) return;
    this._freeSpot(w);
    w.roaming = true;
    w.pickupTask = w.task;
    w.state = 'goDispatch';
    // pick the dispatch counter spot nearest the worker (don't reserve — it's a
    // shared service point; multiple agents queue/visit it)
    var goal = disp.spots[0];
    this._setPath(w, [goal.c, goal.r]);
    w.target = { kind: 'dispatch', spot: goal };
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
    // Always head to a STATION and work there — no aimless wandering (that read as
    // headless-chicken pacing). If every station is taken, stand quietly by the
    // door rather than pace the room.
    var spot = this._spotFor(w);
    if (spot) { w.target = { kind: 'spot', spot: spot }; this._setPath(w, [spot.c, spot.r]); return; }
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
        var prevTask = w.task;
        w.role = rec.role || w.role;
        w.runner = rec.runner != null ? rec.runner : w.runner;
        var newTask = rec.task != null ? rec.task : w.task;
        w.account = rec.account != null ? rec.account : w.account;
        w.status = rec.status || w.status;
        w.sprite = spriteFor(w.role, w.id);
        if (rec.status === 'done' && w.state !== 'leaving') { this._beginLeave(w); w.task = newTask; }
        // DISPATCH PICKUP: a NEW task (task string changed) on a settled agent →
        // it leaves its room, walks to the dispatch counter to pick up the
        // ticket, dwells, then returns to its station. Skip while entering/
        // leaving/already on a pickup, and skip the account residents (they hold
        // their cubicles) unless dispatch is the only place to go.
        var settled = (w.state !== 'entering' && w.state !== 'leaving' && w.state !== 'goDispatch' && w.state !== 'atDispatch' && w.state !== 'returnHome');
        if (settled && newTask && newTask !== prevTask && this.sectors.dispatch && w.role !== 'account') {
          w.task = newTask; this._beginPickup(w);
        } else {
          w.task = newTask;
        }
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
        } else if (w.state === 'goDispatch') {
          // reached the dispatch counter → dwell to "pick up" the ticket
          w.state = 'atDispatch'; w.dir = 'up'; w.dwellKind = 'dispatch';
          w.dwellUntil = ts + 1800 + Math.random() * 1200;
        } else if (w.state === 'atDispatch') {
          if (ts >= w.dwellUntil) {
            // ticket in hand → walk back home (still roaming so the route through
            // the corridor + own doorway is valid), then re-confine on arrival.
            w.state = 'returnHome';
            var home = this.sectors[w.sectorKey];
            this._setPath(w, home ? home.door : [w.c, w.r]);
          }
        } else if (w.state === 'returnHome') {
          // back at the home doorway → re-confine + go to a station to work
          w.roaming = false; w.pickupTask = null;
          w.state = 'toSpot'; this._pickDestination(w);
        } else if (w.state === 'toSpot') {
          w.state = 'dwell';
          w.dir = (w.target && w.target.spot) ? w.target.spot.dir : 'up';
          w.dwellKind = (w.target && w.target.spot) ? w.target.spot.kind : 'idle';
          var base = w.role === 'account' ? 16000 : 10000;
          w.dwellUntil = ts + base + Math.random() * 9000;
        } else if (w.state === 'dwell') {
          if (ts >= w.dwellUntil) {
            // mostly stay seated; occasionally get up + walk to a different station.
            if (w.target && w.target.kind === 'spot' && Math.random() < 0.18) this._freeSpot(w);
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
    ctx.fillStyle = COL.bg; ctx.fillRect(0, 0, W, H);
    var lz = this._lzReady();

    // 1) CORRIDOR floor — a subtle dark tile under the connecting walkways so the
    //    rooms read as connected by halls, not floating boxes.
    if (g && this.corridor) {
      var ck = Object.keys(this.corridor);
      for (var ci = 0; ci < ck.length; ci++) {
        var idx = +ck[ci], cc = idx % g.cols, rrr = (idx - cc) / g.cols;
        var ct = this._tileRect(cc, rrr);
        // a real LimeZu HALLWAY floor, so the whole office reads as one connected
        // building floor with rooms set on it — not rooms floating in a void.
        if (lz) this._blit(this.lz.floors, 13, 29, 1, 1, ct.x, ct.y, ct.w + 0.6, ct.h + 0.6);
        else { ctx.fillStyle = '#222a38'; ctx.fillRect(ct.x, ct.y, ct.w + 0.6, ct.h + 0.6); }
        ctx.fillStyle = 'rgba(9,12,18,0.22)'; ctx.fillRect(ct.x, ct.y, ct.w + 0.6, ct.h + 0.6);
      }
    }

    // 2) ROOM floors — a DISTINCT rb_floors tile per room (procedural checker
    //    fallback). The GYM is a pre-built room blit (handled in _drawGymRoom).
    if (g && this.sectors) {
      var keys = Object.keys(this.sectors);
      for (var k = 0; k < keys.length; k++) {
        var s = this.sectors[keys[k]];
        if (this._designReady(s.key)) continue; // pre-built design supplies its own floor
        var fl = LZ_FLOORS[s.key] || LZ_FLOORS._default;
        for (var c = s.x + 1; c <= s.x2 - 1; c++) for (var r = s.y + 1; r <= s.y2 - 1; r++) {
          var t = this._tileRect(c, r);
          if (lz) this._blit(this.lz.floors, fl.c, fl.r, 1, 1, t.x, t.y, t.w + 0.6, t.h + 0.6);
          else { ctx.fillStyle = ((c + r) & 1) ? COL.floor : COL.floorLit; ctx.fillRect(t.x, t.y, t.w + 0.6, t.h + 0.6); }
        }
      }
    }

    // 3) PRE-BUILT DESIGNS — blit each sector's whole LimeZu room (gym-quality).
    this._drawDesignRooms();

    // card rectangle: push to near-black so the dashboard cards read cleanly
    if (g && this.cardRect) {
      var cr = this.cardRect;
      ctx.fillStyle = 'rgba(6,8,11,0.92)';
      ctx.fillRect(cr.lo * g.cw, 0, (cr.hi - cr.lo + 1) * g.cw, (cr.bottom + 1) * g.ch);
    }
    // gentle vignette
    var vg = ctx.createRadialGradient(W / 2, H * 0.66, Math.min(W, H) * 0.25, W / 2, H * 0.6, Math.max(W, H) * 0.82);
    vg.addColorStop(0, 'rgba(20,28,44,0)'); vg.addColorStop(1, 'rgba(5,7,11,0.8)');
    ctx.fillStyle = vg; ctx.fillRect(0, 0, W, H);
  };

  // Blit the LimeZu PRE-BUILT GYM room (gym_base = walls+floor, gym_furn =
  // equipment) into the gym sector rect — FIT-PRESERVE-ASPECT (letterbox), never
  // stretched. The pre-built gym is 19x15 tiles; we scale it UNIFORMLY to fit
  // within the room and CENTER it, then fill the leftover with the gym floor tile
  // so the equipment always reads at its native proportions (no squish).
  Office.prototype._drawGymRoom = function () {
    if (!this._gymRoomReady()) return;
    var s = this.sectors.gym; if (!s) return;
    var ctx = this.ctx; ctx.imageSmoothingEnabled = false;
    var t0 = this._tileRect(s.x, s.y);
    var roomW = (s.x2 - s.x + 1) * this.grid.cw, roomH = (s.y2 - s.y + 1) * this.grid.ch;
    var gw = this.lz.gymBase.width, gh = this.lz.gymBase.height;     // 304 x 240

    // fill the WHOLE room with the gym floor tile first (so letterbox margins
    // read as gym floor, not the room's default floor / dark bg).
    if (this._lzReady() && this.lz.floors && this.lz.floors.width) {
      var fl = LZ_FLOORS.gym;
      for (var c = s.x; c <= s.x2; c++) for (var r = s.y; r <= s.y2; r++) {
        var ft = this._tileRect(c, r);
        this._blit(this.lz.floors, fl.c, fl.r, 1, 1, ft.x, ft.y, ft.w + 0.6, ft.h + 0.6);
      }
    }

    // uniform scale to fit inside the room, centered (letterbox).
    var scale = Math.min(roomW / gw, roomH / gh);
    var dw = Math.round(gw * scale), dh = Math.round(gh * scale);
    var dx = Math.round(t0.x + (roomW - dw) / 2), dy = Math.round(t0.y + (roomH - dh) / 2);
    ctx.drawImage(this.lz.gymBase, 0, 0, gw, gh, dx, dy, dw, dh);
    ctx.drawImage(this.lz.gymFurn, 0, 0, gw, gh, dx, dy, dw, dh);
  };

  // True once every layer of this sector's pre-built DESIGN is decoded. false →
  // the room falls back to procedural floor/walls/furniture (fresh-clone safe).
  Office.prototype._designReady = function (key) {
    var d = DESIGNS[key]; if (!d || !this.lz) return false;
    for (var i = 0; i < d.layers.length; i++) { var im = this.lz[d.layers[i]]; if (!im || !im.width) return false; }
    return true;
  };
  // Blit one sector's pre-built LimeZu room — uniform scale, centered, letterboxed
  // onto a dark matte (so margins read as a clean frame, never a void). All layers
  // bottom→top (walls/floor → furniture → ceiling overlay).
  Office.prototype._drawDesignRoom = function (key) {
    if (!this._designReady(key)) return false;
    var d = DESIGNS[key], s = this.sectors[key]; if (!s) return false;
    var ctx = this.ctx; ctx.imageSmoothingEnabled = false;
    var t0 = this._tileRect(s.x, s.y);
    var roomW = (s.x2 - s.x + 1) * this.grid.cw, roomH = (s.y2 - s.y + 1) * this.grid.ch;
    ctx.fillStyle = '#0e1118'; ctx.fillRect(t0.x, t0.y, roomW + 0.6, roomH + 0.6);
    var scale = Math.min(roomW / d.w, roomH / d.h);
    var dw = Math.round(d.w * scale), dh = Math.round(d.h * scale);
    var dx = Math.round(t0.x + (roomW - dw) / 2), dy = Math.round(t0.y + (roomH - dh) / 2);
    for (var i = 0; i < d.layers.length; i++) { var im = this.lz[d.layers[i]]; if (im && im.width) ctx.drawImage(im, 0, 0, d.w, d.h, dx, dy, dw, dh); }
    return true;
  };
  Office.prototype._drawDesignRooms = function () {
    if (!this.sectors) return;
    var keys = Object.keys(this.sectors);
    for (var k = 0; k < keys.length; k++) this._drawDesignRoom(keys[k]);
  };

  Office.prototype._drawSectorWalls = function () {
    var ctx = this.ctx, g = this.grid, keys = Object.keys(this.sectors);
    for (var k = 0; k < keys.length; k++) {
      var s = this.sectors[keys[k]];
      if (this._designReady(s.key)) {
        // pre-built design supplies its own walls — just punch the logical
        // doorway so the worker path + entrance read through it.
        this._openDoorway(s); continue;
      }
      for (var c = s.x; c <= s.x2; c++) { this._wallTile(c, s.y, s); this._wallTile(c, s.y2, s); }
      for (var r = s.y; r <= s.y2; r++) { this._wallTile(s.x, r, s); this._wallTile(s.x2, r, s); }
      this._openDoorway(s);
    }
  };
  Office.prototype._openDoorway = function (s) {
    var ctx = this.ctx, dt = this._tileRect(s.door[0], s.door[1]);
    // floor under the doorway (so it reads as an opening, not a wall)
    var fl = LZ_FLOORS[s.key] || LZ_FLOORS._default;
    if (this._lzReady()) this._blit(this.lz.floors, fl.c, fl.r, 1, 1, dt.x, dt.y, dt.w + 0.6, dt.h + 0.6);
    else { ctx.fillStyle = COL.floorLit; ctx.fillRect(dt.x, dt.y, dt.w + 0.6, dt.h + 0.6); }
    // EVERY door reads at a glance: a lit threshold mat + jambs in the room's
    // colour set into the wall opening, with the rb_doors arch on top if present.
    ctx.save();
    var pad = Math.min(dt.w, dt.h) * 0.16;
    ctx.fillStyle = 'rgba(205,223,251,0.15)';
    ctx.fillRect(dt.x + pad, dt.y + pad, dt.w - 2 * pad, dt.h - 2 * pad);
    var horiz = (s.door[1] === s.y || s.door[1] === s.y2);   // door in a top/bottom wall
    ctx.fillStyle = s.color; ctx.globalAlpha = 0.85;
    if (horiz) { ctx.fillRect(dt.x, dt.y + 1, 2, dt.h - 2); ctx.fillRect(dt.x + dt.w - 2, dt.y + 1, 2, dt.h - 2); }
    else { ctx.fillRect(dt.x + 1, dt.y, dt.w - 2, 2); ctx.fillRect(dt.x + 1, dt.y + dt.h - 2, dt.w - 2, 2); }
    ctx.restore();
    if (this._lzReady() && this.lz.doors && this.lz.doors.width) {
      this._blit(this.lz.doors, 0, 5, 2, 2, dt.x - dt.w * 0.5, dt.y - dt.h * 0.4, dt.w * 2, dt.h * 1.4);
    }
  };
  Office.prototype._wallTile = function (c, r, s) {
    var ctx = this.ctx, t = this._tileRect(c, r);
    if (this._lzReady()) {
      // LimeZu rb_walls grey wall tile + a slight accent tint along the top edge
      this._blit(this.lz.walls, LZ_WALL.c, LZ_WALL.r, 1, 1, t.x, t.y, t.w + 0.6, t.h + 0.6);
      ctx.fillStyle = 'rgba(10,12,15,0.18)'; ctx.fillRect(t.x, t.y, t.w + 0.6, t.h + 0.6);
      return;
    }
    ctx.fillStyle = COL.wall; ctx.fillRect(t.x, t.y, t.w + 0.6, t.h + 0.6);
    ctx.fillStyle = COL.wallTop; ctx.fillRect(t.x, t.y, t.w + 0.6, Math.max(2, t.h * 0.28));
    ctx.fillStyle = 'rgba(0,0,0,0.25)'; ctx.fillRect(t.x, t.y + t.h * 0.82, t.w + 0.6, t.h * 0.18);
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
      // design rooms are blitted whole (furniture is in the design) — only draw
      // procedural furniture for a sector WITHOUT a ready pre-built design.
      if (!this._designReady(s.key)) {
        for (var f = 0; f < s.furniture.length; f++) {
          var u = s.furniture[f], t = this._tileRect(u.c, u.r);
          this._drawUnit(u.kind, t, s);
        }
      }
      if (s.key === 'accounts') this._drawCubicleLabels(s);
      if (s.key === 'dispatch') this._drawDispatchSign(s);
    }
  };

  Office.prototype._drawUnit = function (kind, t, s) {
    var ctx = this.ctx; ctx.imageSmoothingEnabled = false;
    var x = t.x, y = t.y, w = t.w, h = t.h, T = performance.now() / 1000;

    // PREMIUM PATH: if the LimeZu sheets are loaded AND this kind maps to a themed
    // sheet, blit the real multi-tile sprite — bottom-anchored + centered, scaled
    // by the grid cell. Gym gear isn't here (pre-built room). Unmapped kinds fall
    // through to the procedural drawing.
    if (this._lzReady() && LZ_FURN[kind]) {
      var m = LZ_FURN[kind];
      var sheet = this._sheetFor(m.sheet);
      if (sheet && sheet.width) {
        var cw = this.grid.cw, ch = this.grid.ch;
        var dw = m.w * cw, dh = m.h * ch;
        var dx = x + w / 2 - dw / 2;          // center on the furniture tile
        var dy = y + h - dh;                  // bottom-anchored (stands on the tile)
        this._blit(sheet, m.c, m.r, m.w, m.h, Math.round(dx), Math.round(dy), Math.round(dw), Math.round(dh));
        // a register accent on the dispatch counter
        if (kind === 'register') { ctx.fillStyle = '#1b1f27'; ctx.fillRect(x + w * 0.35, y + h * 0.15, w * 0.3, h * 0.22); ctx.fillStyle = COL.pos; ctx.fillRect(x + w * 0.4, y + h * 0.2, w * 0.2, 3); }
        return;
      }
    }

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
    } else if (kind === 'counter_svc' || kind === 'register') {
      // DISPATCH service counter (procedural fallback) — a desk-height counter
      // with a register box + green readout.
      ctx.fillStyle = '#3a3f4b'; ctx.fillRect(x + 1, y + h * 0.42, w - 2, h * 0.54);
      ctx.fillStyle = '#cdd4dc'; ctx.fillRect(x + 1, y + h * 0.42, w - 2, 3);     // counter top
      ctx.fillStyle = '#1b1f27'; ctx.fillRect(x + w * 0.36, y + h * 0.16, w * 0.3, h * 0.24); // register
      ctx.fillStyle = COL.pos; ctx.fillRect(x + w * 0.42, y + h * 0.22, w * 0.18, 3);
    } else if (kind === 'meeting') {
      // big meeting table
      ctx.fillStyle = COL.wood; ctx.fillRect(x + 2, y + h * 0.3, w - 4, h * 0.5);
      ctx.fillStyle = '#6b543f'; ctx.fillRect(x + 2, y + h * 0.3, w - 4, 3);
    } else if (kind === 'server') {
      ctx.fillStyle = '#20262f'; ctx.fillRect(x + w * 0.3, y + 2, w * 0.4, h - 4);
      for (var Sl = 0; Sl < 4; Sl++) { ctx.fillStyle = ((Math.floor(T * 4) + Sl) % 2) ? COL.pos : '#234'; ctx.fillRect(x + w * 0.36, y + 4 + Sl * 5, w * 0.28, 2); }
    }
  };

  // a small "DISPATCH" sign / glow over the hub so it reads as the task desk.
  Office.prototype._drawDispatchSign = function (s) {
    var ctx = this.ctx, t = this._tileRect(s.door[0], s.door[1]);
    ctx.save(); ctx.imageSmoothingEnabled = true; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    var cx = (this._cx(s.x) + this._cx(s.x2)) / 2, cy = this._cy(s.y) - 2;
    ctx.font = '700 9px "JetBrains Mono", ui-monospace, monospace';
    ctx.fillStyle = 'rgba(205,223,251,0.18)'; // faint hub glow handled by label already
    ctx.restore();
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
    setCardRect: function (rect) { if (inst) inst.setCardRect(rect); return this; },
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
        dir: w.dir, pathLen: w.path ? w.path.length : 0, pathIdx: w.pathIdx, roaming: !!w.roaming,
        task: w.task, spot: w.spot ? [w.spot.c, w.spot.r] : null, alpha: +w.alpha.toFixed(2) };
    });
  };
  global.__gxGrid = function () { return inst ? inst.grid : null; };
  // LimeZu asset state (for verification): true once both premium sheets are
  // loaded + decoded. false → the office is drawing procedural furniture/floors.
  global.__gxLzReady = function () { return inst ? inst._lzReady() : false; };
  global.__gxLzState = function () {
    if (!inst || !inst.lz) return null;
    var o = {}; Object.keys(inst.lz).forEach(function (k) { var im = inst.lz[k]; o[k] = im ? (im.width + 'x' + im.height) : 'null'; });
    o.__designReady = {}; ['gym','accounts','lab','kitchen','trading','dispatch'].forEach(function (k) { o.__designReady[k] = inst._designReady(k); });
    return o;
  };
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
      out[k] = { label: s.label, x: s.x, y: s.y, x2: s.x2, y2: s.y2, door: s.door, outside: s.outside,
        furnitureCount: s.furniture.length, spotCount: s.spots.length,
        furnitureKinds: s.furniture.map(function (f) { return f.kind; }) };
    });
    out.__cardRect = inst.cardRect;
    return out;
  };
  // Corridor + a BFS reachability check the sim uses to PROVE a room→dispatch
  // route exists for every sector (over corridor + dispatch + each room interior).
  global.__gxCorridor = function () { return inst ? Object.keys(inst.corridor || {}).map(Number) : []; };
  // Is tile (c,r) part of the connected travel network (corridor ∪ any room
  // interior ∪ dispatch)? Used by the sim's room→dispatch BFS.
  global.__gxNetWalkable = function (c, r) {
    if (!inst || !inst.grid) return false;
    var g = inst.grid, key = r * g.cols + c;
    if (c < 0 || r < 0 || c >= g.cols || r >= g.rows) return false;
    if (inst.obstacles[key]) return false;
    if (inst.corridor[key]) return true;
    var ks = Object.keys(inst.sectors);
    for (var i = 0; i < ks.length; i++) if (inst.sectors[ks[i]].interior[key]) return true;
    return false;
  };

  global.GammaPixels = GammaPixels;
  if (typeof module !== 'undefined' && module.exports) module.exports = GammaPixels;

})(typeof window !== 'undefined' ? window : this);

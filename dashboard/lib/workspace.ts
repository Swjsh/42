import path from "node:path";

export const WORKSPACE_ROOT =
  process.env.GAMMA_WORKSPACE ?? "C:\\Users\\jackw\\Desktop\\42";

const st = (...parts: string[]) =>
  path.join(WORKSPACE_ROOT, "automation", "state", ...parts);

export const paths = {
  loopState: st("loop-state.json"),
  loopStateBold: st("aggressive", "loop-state.json"),
  todayBias: st("today-bias.json"),
  keyLevels: st("key-levels.json"),
  positionSafe: st("current-position-safe.json"),
  positionBold: st("current-position-bold.json"),
  circuitBreaker: st("circuit-breaker.json"),
  circuitBreakerBold: st("aggressive", "circuit-breaker.json"),
  decisionsJsonl: st("decisions.jsonl"),
  decisionsJsonlBold: st("aggressive", "decisions.jsonl"),
  kitchenStatus: st("kitchen-status.json"),
  liveWatch: st("live-watch.json"),
  trendlineWatch: st("trendline-watch.json"),
  dialogue: st("dashboard-dialogue.json"),
  journal: (dateYYYYMMDD: string) =>
    path.join(WORKSPACE_ROOT, "journal", `${dateYYYYMMDD}.md`),
  trades: path.join(WORKSPACE_ROOT, "journal", "trades.csv"),

  // --- Gamma App (/gamma) additions, 2026-08-08 ---
  discordOutbox: st("discord-outbox.jsonl"),
  futuresMirrorLedger: st("futures", "mirror-would-be.jsonl"),
  ssrShadowLedger: st("futures", "ssr-shadow-would-be.jsonl"),
  catastropheLedger: path.join(WORKSPACE_ROOT, "analysis", "recommendations", "catastrophe-cap-shadow-ledger.jsonl"),
  gammaWants: st("gamma-wants.json"),
  overnightQueue: path.join(WORKSPACE_ROOT, "automation", "overnight", "queue.md"),
  gammaHqScript: path.join(WORKSPACE_ROOT, "setup", "scripts", "gamma_hq.py"),
  pythonExe: path.join(WORKSPACE_ROOT, "backtest", ".venv", "Scripts", "python.exe"),

  // --- Vitals tile (unattended-unit traffic lights), 2026-08-09 ---
  unattendedHealth: st("unattended-health.json"),
  unattendedEvents: st("unattended-events.jsonl"),

  // --- Station "/station" face (GOAL-GAMMA-STATION-2026-09-13 item 5 pivot,
  // 2026-09-13): all under automation/state/station/. The Python side
  // (setup/scripts/station_loop.py + station_board.py) is the only writer of
  // ideasBoard/stationBrief/stationLedger/stationConfig/stationMode/
  // stationPendingNotes/plannerBench; the dashboard writes ONLY stationInbox
  // (via /api/station/action), chatLedger (via /api/station/ask) and tvCapability
  // (via GET /api/station/tv-probe -- the TV reporting its own WebGL/fps). Never the
  // reverse -- a page read must never become a Python write target. ---
  stationDir: st("station"),
  ideasBoard: st("station", "ideas-board.json"),
  stationBrief: st("station", "station-brief.md"),
  stationConfig: st("station", "config.json"),
  stationMode: st("station", "mode.json"),
  stationLedger: st("station", "loop-ledger.jsonl"),
  stationInbox: st("station", "station-inbox.jsonl"),
  stationPendingNotes: st("station", "station-pending-notes.json"),
  chatLedger: st("station", "chat-ledger.jsonl"),
  stationPresence: st("station", "presence.json"),
  // TV browser self-report (GET /api/station/tv-probe, 2026-09-13): WebGL1/2 + fps + UA,
  // overwritten once per LAN kiosk page load. Decides 3D-vs-2D for the TV face.
  tvCapability: st("station", "tv-capability.json"),
  // Which path the TV should be showing ({"tv_path": "/station" | "/hq"}); the LAN kiosk
  // page follows it, so the face flips without anyone typing on the TV remote.
  stationFace: st("station", "face.json"),
  // The bundle id this server process was started on (dashboard/.next/BUILD_ID); the
  // kiosk page reloads itself when it changes, so a rebuild lands on the TV unattended.
  dashboardBuildId: path.join(WORKSPACE_ROOT, "dashboard", ".next", "BUILD_ID"),
  plannerBench: st("station", "planner-bench.json"),
  brainQuiz: st("station", "brain-quiz.json"),
  stationPromptMd: path.join(WORKSPACE_ROOT, "automation", "prompts", "station.md"),

  // --- Gamma HQ "/hq" three.js face (2026-09-13): sectors.rows shells the
  // Python reader below (fixed argv, no user input); the other three are
  // plain-file reads. All four are read-only from this app's side -- nothing
  // under automation/state/ is ever written by /api/hq. ---
  sectorRowsScript: path.join(WORKSPACE_ROOT, "setup", "scripts", "sector_rows.py"),
  futuresHealth: st("futures", "health.json"),
  cryptoTwinDecisions: st("crypto-twin", "decisions.jsonl"),
  // HQ v2 (2026-09-13): unified TV render-perf history, one line per report
  // from either kiosk face's own self-probe (gitignored, capped at 200 lines
  // by dashboard/lib/hq.ts's appendTvPerfRow -- see that module). Lives next
  // to tv-capability.json under station/, not directly under state/.
  tvPerf: st("station", "tv-perf.jsonl"),
  // HQ v3 Company Mode (2026-09-13): the "NEEDS J" card's third read-only
  // source (discordOutbox and overnightQueue above already exist).
  conductorProposals: st("conductor-proposals.jsonl"),
  // "Talk to Gamma" chat persona (amendment 5a, 2026-09-13) -- deliberately NOT
  // stationPromptMd above: station.md is the 30-min loop's JSON-only output-schema
  // prompt, and using it for chat would make Gamma answer J in raw JSON. Fable
  // owns both station.md and this identity file; this app only ever reads them.
  stationIdentityMd: path.join(WORKSPACE_ROOT, "automation", "prompts", "station-identity.md"),
  stationFactsScript: path.join(WORKSPACE_ROOT, "setup", "scripts", "station_facts.py"),
  // "NEEDS J" hotfix (2026-09-13): the goal-autopilot's ordered queue --
  // its `[~]` line marks the SINGLE currently-active goal (no active-
  // goal.json exists on disk; LADDER.md's own marker is authoritative).
  goalLadder: st("goals", "LADDER.md"),

  // --- LIVE-1 item 5 (2026-09-14, coordinator-directed): HQ trading status
  // strip -- "are we ready to trade today?" All read-only. ---
  premarketReadiness: st("premarket-readiness.json"),
  preopenReadiness: st("preopen-readiness.json"),
  openBellPinged: st("open-bell-pinged.json"),
  // 121MB+ and growing (2026-09-14) -- read via a byte-seek TAIL in
  // lib/hq.ts#readCoreDecisionsLatest, never a full fs.readFile.
  coreDecisions: st("core-decisions.jsonl"),

  // --- UX-1 U0 (2026-09-14): "is it working?" build instrument. Advisory
  // lock a builder writes/deletes around `npm run build` (never read by
  // anything but this route); dashboardBuildId's own MTIME (not its
  // content, already covered by readBuildId) is the "deployed at" signal.
  // Both under dashboard/, not automation/state/ -- build-local, not
  // trading state. ---
  dashboardBuildLock: path.join(WORKSPACE_ROOT, "dashboard", ".build.lock"),
  // Real screen captures every builder writes proof to -- "last capture"
  // reads whichever PNG in here has the newest mtime.
  stationCaptures: st("station", "captures"),
};

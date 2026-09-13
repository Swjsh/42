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
  // (via /api/station/action) and chatLedger (via /api/station/ask). Never the
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
  plannerBench: st("station", "planner-bench.json"),
  brainQuiz: st("station", "brain-quiz.json"),
  stationPromptMd: path.join(WORKSPACE_ROOT, "automation", "prompts", "station.md"),
  // "Talk to Gamma" chat persona (amendment 5a, 2026-09-13) -- deliberately NOT
  // stationPromptMd above: station.md is the 30-min loop's JSON-only output-schema
  // prompt, and using it for chat would make Gamma answer J in raw JSON. Fable
  // owns both station.md and this identity file; this app only ever reads them.
  stationIdentityMd: path.join(WORKSPACE_ROOT, "automation", "prompts", "station-identity.md"),
  stationFactsScript: path.join(WORKSPACE_ROOT, "setup", "scripts", "station_facts.py"),
};

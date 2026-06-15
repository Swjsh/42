import path from "node:path";

export const WORKSPACE_ROOT =
  process.env.GAMMA_WORKSPACE ?? "C:\\Users\\jackw\\Desktop\\42";

export const paths = {
  loopState: path.join(WORKSPACE_ROOT, "automation", "loop-state.json"),
  todayBias: path.join(WORKSPACE_ROOT, "automation", "state", "today-bias.json"),
  keyLevels: path.join(WORKSPACE_ROOT, "automation", "state", "key-levels.json"),
  currentPosition: path.join(
    WORKSPACE_ROOT,
    "automation",
    "state",
    "current-position.json",
  ),
  circuitBreaker: path.join(
    WORKSPACE_ROOT,
    "automation",
    "state",
    "circuit-breaker.json",
  ),
  mode: path.join(WORKSPACE_ROOT, "automation", "state", "mode.json"),
  dialogue: path.join(
    WORKSPACE_ROOT,
    "automation",
    "state",
    "dashboard-dialogue.json",
  ),
  journal: (dateYYYYMMDD: string) =>
    path.join(WORKSPACE_ROOT, "journal", `${dateYYYYMMDD}.md`),
  trades: path.join(WORKSPACE_ROOT, "journal", "trades.csv"),
};

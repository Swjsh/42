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
  dialogue: st("dashboard-dialogue.json"),
  journal: (dateYYYYMMDD: string) =>
    path.join(WORKSPACE_ROOT, "journal", `${dateYYYYMMDD}.md`),
  trades: path.join(WORKSPACE_ROOT, "journal", "trades.csv"),
};

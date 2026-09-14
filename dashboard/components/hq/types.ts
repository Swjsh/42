import type { StationIdeaCard, StationPresence, StationFace, HqBuildStatus } from "@/lib/station";
import type { SectorRow, TvPerfRow, BlockedItem, TradingStatus, CoreDecisionRow, CrewEvent, SectorsSnapshot } from "@/lib/hq";
import type { PersonaState, Handoff } from "@/lib/personas";
// INTERACT-2 (I1, 2026-09-14): per-desk real-work content -- type-only, see
// lib/desk-content.ts's own module header for why this file must never take
// a VALUE import from that module (it touches node:fs).
import type { DeskPersonaName, DeskContent } from "@/lib/desk-content";

export type { SectorRow, BlockedItem, PersonaState, Handoff, TradingStatus, CoreDecisionRow, CrewEvent, DeskPersonaName, DeskContent, HqBuildStatus, SectorsSnapshot };

export interface HqBrainVitals {
  model: string | null;
  mode?: string;
  gpu: {
    ok: boolean;
    util_pct: number | null;
    mem_used_mib: number | null;
    mem_total_mib: number | null;
    temp_c: number | null;
    power_w: number | null;
    say: string;
  };
  models: Array<{ name: string; id: string; size: string; processor: string; context: string; until: string }>;
  modelsOk: boolean;
  plannerSpeed: unknown;
  lastRow: { ts_et: string; status: string; reason: string } | null;
  fireTimeline: unknown[];
}

/** One PASS/WARN/FAIL check inside a persona's audit row. */
export interface AuditCheck {
  verdict: "PASS" | "WARN" | "FAIL" | string;
  evidence: string;
}

/** One persona's row from the company audit (commit 58d0b9c6, 2026-09-13) --
 * matched to a PersonaState by `name` (identical strings: "Scout", "Pilot",
 * "Gamma (Manager)", etc). `verdict` is the roll-up of the 4 `checks`; each
 * check's own `evidence` string is real (a scheduler state + deliverable
 * mtime comparison), never a guess -- this is what "the roster must show
 * ghosts as ghosts" (J, this session) means: a PASS-status persona with a
 * FAIL audit is a ghost (looks alive, isn't), and this is the field that
 * catches it. */
export interface PersonaAudit {
  name: string;
  role_file: string;
  objective: string;
  kpi: string;
  cadence: string;
  tasks: string[];
  deliverable: string;
  goal_ref: string;
  verdict: "PASS" | "WARN" | "FAIL" | string;
  checks: {
    works: AuditCheck;
    has_goal: AuditCheck;
    is_smart: AuditCheck;
    autonomous: AuditCheck;
  };
  quiz: { asked: boolean; verdict: string; note: string };
}

export interface HqAudit {
  ts_et: string;
  last_trading_day: string;
  personas: PersonaAudit[];
  summary: { pass: number; warn: number; fail: number; total: number };
}

export interface HqExtras {
  futures_verdict: string | null;
  crypto: { last_action: string | null; last_ts: string | null };
  kitchen: {
    daemon_alive: boolean | null;
    idle: boolean | null;
    current_task_id: string | null;
    failed_permanent: number | null;
  };
}

export interface HqApiResponse {
  fetched_at: string;
  mode: string;
  presence: StationPresence | null;
  brainVitals: HqBrainVitals;
  ideas: { cards: StationIdeaCard[]; count: number };
  brief: { text: string; mtime_ms: number | null };
  sectors: { rows: SectorRow[]; say: string };
  extras: HqExtras;
  face: StationFace | null;
  build_id: string | null;
  perf: TvPerfRow | null;
  perfOther: TvPerfRow | null;
  company: { personas: PersonaState[]; handoffs: Handoff[] };
  blocked: BlockedItem[];
  /** Company audit (commit 58d0b9c6, 2026-09-13) -- null on an /api/hq
   * response older than that commit or if the audit script itself failed
   * (fail-open per this route's own convention: a missing audit degrades
   * to "no badge," never a fake PASS). */
  audit: HqAudit | null;
  /** LIVE-1 item 5 (2026-09-14, coordinator-directed): trading status
   * strip source data -- see lib/hq.ts#readTradingStatus for the fail-open
   * contract per underlying file. */
  trading: TradingStatus;
  // CREW-2 (roster) -- additive field, see lib/hq.ts#readCrewEvents. May be
  // [] before CREW-RIG's crew-events.jsonl producer lands -- never fabricated.
  crewEvents: CrewEvent[];
  // INTERACT-2 (I1) -- additive field, see lib/desk-content.ts#readDesksSnapshot.
  // Pilot is deliberately absent (Scene.tsx keeps reading data.trading.core
  // for Pilot's own desk screen -- see that file's own comment). A Partial
  // string-keyed record (not the stricter Record<DeskPersonaName, ...>) is
  // the honest wire type here: callers look this up by an arbitrary
  // PersonaState.name (a plain string), and only 6 of those names actually
  // resolve to a real entry.
  desks: Partial<Record<string, DeskContent>>;
  // INTERACT-2 (I3) -- explicit alias for brief.mtime_ms as a readable ISO
  // string; same real mtime, no new read. Null exactly when brief.mtime_ms is.
  briefWrittenAt: string | null;
  // UX-1 U0 (2026-09-14) -- additive, see lib/station.ts#readHqBuildStatus.
  // "is it working?" instrument: deployed-at/building-now/last-capture, all
  // server-side facts (fs reads only, this route never shells out).
  build: HqBuildStatus;
  // Coordinator-directed (2026-09-14) -- additive, see
  // lib/hq.ts#readSectorsSnapshot. NOT the same source as `sectors` above
  // (that one is sector_rows.py's live shell; this is CREW-RIG's
  // sectors.json file snapshot) -- named differently on purpose so the two
  // never collide. Null until that producer has fired at least once.
  sectorsSnapshot: SectorsSnapshot | null;
}

/** One module's derived (not server-sent) presentation state -- computed
 * client-side once per poll from a SectorRow + the global mode, never
 * per-frame. "parked" covers every row shape the brief's mapping table calls
 * dark: state killed/dormant/dead, or health frozen/zombie (STATE_VALUES has
 * no literal "parked"/"frozen" entry -- health carries "frozen"). */
export interface ModuleDerived {
  row: SectorRow;
  parked: boolean;
  freshnessMinutes: number | null;
  agentBehavior: "working" | "idle" | "alert" | "frozen";
}

/** LAYOUT builder pass (2026-09-14, campus-cross rebuild): the contract
 * Agent.tsx's own walk consumer will read once MOTION-2 wires it up there
 * (this pass does not edit Agent.tsx/KitAgent.tsx -- see layout.ts's own
 * "Walk graph" section header). `waypoints` is a real path through the walk
 * graph (layout.ts#findWalkPath) -- hub-center, doorways, T-junctions, bay/
 * persona desks -- never a single point, so a walker never has to be
 * trusted to cut a straight line through a wall to reach it. `purpose` is
 * the same one-line reason text this scene already surfaces in a speech
 * bubble (see Scene.tsx's own purposeful-walk/eventWalk bubble text);
 * `dwellS`/`dwellAnim` describe what the walker does once it arrives
 * (how long, and which of Agent.tsx's existing animation states to hold). */
export interface WalkPlan {
  waypoints: [number, number, number][];
  purpose: string;
  dwellS: number;
  dwellAnim: "interact" | "point" | "idle";
  // MOTION-2 (2026-09-14) -- additive, per that task's own file-ownership
  // note ("types.ts (additive faceYaw only)"). Optional: when omitted,
  // Agent.tsx's walk consumer faces the direction implied by the final leg
  // of `waypoints` (the heading the walker arrives WITH) instead. Lets a
  // producer request a specific dwell facing (e.g. "face the wall screen",
  // not just "face whichever way the last corridor leg happened to run").
  faceYaw?: number;
}

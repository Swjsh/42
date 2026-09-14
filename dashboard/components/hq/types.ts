import type { StationIdeaCard, StationPresence, StationFace } from "@/lib/station";
import type { SectorRow, TvPerfRow } from "@/lib/hq";

export type { SectorRow };

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

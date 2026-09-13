import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { paths } from "./workspace";

const execFileAsync = promisify(execFile);

// ─── Types (mirror the Python producers byte-for-byte -- see
//     setup/scripts/station_board.py / station_loop.py / station_facts.py) ────

export interface StationIdeaCard {
  id: string;
  ts_et: string;
  prompted_by?: string;
  status: "proposed" | "testing" | "killed" | "shipped" | "supported" | "refuted" | string;
  model?: string;
  title: string;
  mechanism: string;
  evidence: string[];
  proposed_shadow_test: string;
  cost_line: string;
  confidence: "low" | "med" | "high" | string;
  // Amendment 5b (2026-09-13): a separate builder writes these once a card's
  // shadow test has actually run -- this app only ever RENDERS them, never
  // computes a verdict itself. All three are optional since most cards never
  // reach a verdict.
  verdict?: string;
  verdict_n_pre?: number;
  verdict_n_post?: number;
}

export interface StationLedgerRow {
  ts_et: string;
  model: string;
  status: "ok" | "yielded" | "error" | string;
  reason: string;
  duration_s: number | null;
  prompt_tokens: number | null;
  gen_tokens: number | null;
  cards_added: number;
  board_size: number;
}

export interface StationConfig {
  model?: string;
  ollama_base_url?: string;
  tv_host?: string;
  tv_mac?: string;
  station_url?: string;
  pc_lan_ips?: string[];
  station_serve_port?: number;
  [key: string]: unknown;
}

export interface StationPresence {
  present: boolean;
  idle_s: number;
  ts_et: string;
  transitions_today: number;
}

export interface PlannerBenchRun {
  num_ctx?: number;
  prompt_tok_per_s?: number;
  gen_tok_per_s?: number;
  processor_split?: string;
  wall_s?: number;
  answer_correct?: boolean;
}

export interface PlannerBenchRecord {
  ts_et: string;
  model: string;
  gpu?: string;
  runs: PlannerBenchRun[];
}

export interface BrainQuizQuestion {
  id?: string;
  label?: string;
  expected?: string;
  answer?: string;
  correct?: boolean;
  gen_tokens?: number;
  gen_tok_per_s?: number;
  prompt_tokens?: number;
  prompt_tok_per_s?: number;
  load_s?: number;
  wall_s?: number;
}

// Verified against the real automation/state/station/brain-quiz.json J wrote
// 2026-09-13 15:08 ET -- gen_tok_per_s/processor_split live at the TOP level
// (the model's own overall run, not a per-question average), each question
// carries `label` (human-readable) rather than a bare `q`, and an optional
// `others` array holds other models' quiz runs for comparison. This module
// only ever reads its own model's block; `others` is preserved on the type
// so a future panel can use it without another schema round-trip.
export interface BrainQuiz {
  ts_et: string;
  model: string;
  score: string;
  gen_tok_per_s?: number;
  processor_split?: string;
  questions: BrainQuizQuestion[];
  others?: Array<{ model: string; score: string; gen_tok_per_s?: number; ts_et: string }>;
}

export interface GpuVitals {
  ok: boolean;
  util_pct: number | null;
  mem_used_mib: number | null;
  mem_total_mib: number | null;
  temp_c: number | null;
  power_w: number | null;
  say: string;
}

export interface OllamaPsRow {
  name: string;
  id: string;
  size: string;
  processor: string;
  context: string;
  until: string;
}

// ─── Plain-file readers -- fail-open, never throw, never fabricate ───────────

async function readJsonFile<T>(p: string): Promise<T | null> {
  try {
    const text = await fs.readFile(p, "utf-8");
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

async function readJsonlTail<T>(p: string, n: number): Promise<T[]> {
  try {
    const text = await fs.readFile(p, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const rows: T[] = [];
    for (const line of lines.slice(-n)) {
      try {
        rows.push(JSON.parse(line) as T);
      } catch {
        // one malformed line never drops the rest of the tail
      }
    }
    return rows;
  } catch {
    return [];
  }
}

export async function readIdeasBoard(): Promise<StationIdeaCard[]> {
  const board = await readJsonFile<StationIdeaCard[]>(paths.ideasBoard);
  return Array.isArray(board) ? board : [];
}

export async function readStationBrief(): Promise<{ text: string; mtimeMs: number | null }> {
  try {
    const [text, stat] = await Promise.all([
      fs.readFile(paths.stationBrief, "utf-8"),
      fs.stat(paths.stationBrief),
    ]);
    return { text: text.trim(), mtimeMs: stat.mtimeMs };
  } catch {
    return { text: "", mtimeMs: null };
  }
}

export async function readStationConfig(): Promise<StationConfig> {
  const cfg = await readJsonFile<StationConfig>(paths.stationConfig);
  return cfg ?? {};
}

export async function readStationMode(): Promise<string> {
  const data = await readJsonFile<{ mode?: string }>(paths.stationMode);
  return data?.mode ?? "work";
}

export async function readLedgerTail(n = 10): Promise<StationLedgerRow[]> {
  return readJsonlTail<StationLedgerRow>(paths.stationLedger, n);
}

export async function readPresence(): Promise<StationPresence | null> {
  return readJsonFile<StationPresence>(paths.stationPresence);
}

/** The LAST run of the LAST bench record -- planner-bench.json is a growing
 * list of {ts_et, model, gpu, ollama, runs:[...]}; "current planner speed" is
 * the most recent run of the most recent record, never an average across the
 * whole history (that would blend old/new hardware or model configs). */
export async function readPlannerSpeed(): Promise<{
  ts_et: string;
  model: string;
  run: PlannerBenchRun;
} | null> {
  const records = await readJsonFile<PlannerBenchRecord[]>(paths.plannerBench);
  if (!Array.isArray(records) || records.length === 0) return null;
  const last = records[records.length - 1];
  if (!last || !Array.isArray(last.runs) || last.runs.length === 0) return null;
  return { ts_et: last.ts_et, model: last.model, run: last.runs[last.runs.length - 1] };
}

export async function readBrainQuiz(): Promise<BrainQuiz | null> {
  return readJsonFile<BrainQuiz>(paths.brainQuiz);
}

// ─── System probes (amendment 4, 2026-09-13): fixed-argv execFile only, never
//     a shell string, never user input -- these are read-only local system
//     utilities (nvidia-smi / ollama ps), not arbitrary command execution. ────

let gpuCache: { data: GpuVitals; at: number } | null = null;
const GPU_CACHE_MS = 5000;

/** `nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,
 * temperature.gpu,power.draw --format=csv,noheader` -- one CSV line, e.g.
 * "2 %, 1376 MiB, 16303 MiB, 45, 40.55 W". Cached 5s so the page's 10s poll
 * (or multiple simultaneous viewers) never spawns nvidia-smi more than twice
 * a second. Missing/erroring nvidia-smi (no GPU, not on PATH) fails open. */
export async function readGpuVitals(): Promise<GpuVitals> {
  if (gpuCache && Date.now() - gpuCache.at < GPU_CACHE_MS) return gpuCache.data;
  const notFound: GpuVitals = {
    ok: false, util_pct: null, mem_used_mib: null, mem_total_mib: null,
    temp_c: null, power_w: null, say: "NO DATA, nvidia-smi unavailable",
  };
  try {
    const { stdout } = await execFileAsync(
      "nvidia-smi",
      ["--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw", "--format=csv,noheader"],
      { timeout: 3000, windowsHide: true },
    );
    const parts = stdout.trim().split(",").map((s) => s.trim());
    const num = (s: string | undefined) => (s ? parseFloat(s) : null);
    const data: GpuVitals = {
      ok: true,
      util_pct: num(parts[0]),
      mem_used_mib: num(parts[1]),
      mem_total_mib: num(parts[2]),
      temp_c: num(parts[3]),
      power_w: num(parts[4]),
      say: "nvidia-smi live",
    };
    gpuCache = { data, at: Date.now() };
    return data;
  } catch {
    gpuCache = { data: notFound, at: Date.now() };
    return notFound;
  }
}

/** `ollama ps` -- a tabwriter-aligned table (NAME ID SIZE PROCESSOR CONTEXT
 * UNTIL, columns separated by 2+ spaces, the same convention `ollama list`
 * uses). No CSV/JSON mode exists for this command. Empty (no models loaded)
 * is a normal, valid state, not an error. */
export async function readOllamaPs(): Promise<{ ok: boolean; models: OllamaPsRow[]; say: string }> {
  try {
    const { stdout } = await execFileAsync("ollama", ["ps"], { timeout: 3000, windowsHide: true });
    const lines = stdout.split("\n").map((l) => l.trimEnd()).filter(Boolean);
    if (lines.length === 0) return { ok: true, models: [], say: "no models loaded" };
    const dataLines = lines.slice(1); // drop the header row
    const models: OllamaPsRow[] = dataLines.map((line) => {
      const cols = line.split(/\s{2,}/).map((c) => c.trim()).filter(Boolean);
      return {
        name: cols[0] ?? "", id: cols[1] ?? "", size: cols[2] ?? "",
        processor: cols[3] ?? "", context: cols[4] ?? "", until: cols[5] ?? "",
      };
    });
    return { ok: true, models, say: `${models.length} model(s) loaded` };
  } catch {
    return { ok: false, models: [], say: "NO DATA, ollama ps failed (is Ollama running?)" };
  }
}

/** Shell out to `python station_facts.py --json` (the "simpler" of the two
 * options the ask-route spec offered -- station_facts.py already owns the
 * gather/render logic, so on-demand-per-chat-message is one process spawn
 * per user turn, not a duplicated implementation in TypeScript). Fixed argv,
 * no shell, no user input reaches the command line. */
export async function readStationFactsText(): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync(
      paths.pythonExe,
      [paths.stationFactsScript, "--json"],
      { timeout: 20000, windowsHide: true, cwd: paths.stationDir },
    );
    const parsed = JSON.parse(stdout) as { facts_text?: string };
    return typeof parsed.facts_text === "string" ? parsed.facts_text : null;
  } catch {
    return null;
  }
}

// Amendment 5a (2026-09-13): "Talk to Gamma" must NOT load station.md as its
// system prompt -- station.md is the 30-minute loop's format contract and
// carries "Output valid JSON only" + the card rules, so a chat face using it
// verbatim would answer J in raw JSON instead of prose. Fable owns both
// station.md and the new automation/prompts/station-identity.md (an identity-
// only capsule, no output schema); this module only ever reads them.
const CHAT_CONTRACT = [
  "",
  "## Chat contract (Talk to Gamma -- the dashboard chat box, NOT the 30-minute loop)",
  "Reply in plain prose for J: lead with the answer, <=4 short bullets or <=2 sentences, bold the",
  'load-bearing words, no menus of options, no permission questions ("want me to...?"), never',
  'invent a number -- say "not in my facts" instead.',
].join("\n");

export async function readStationPersona(): Promise<string> {
  try {
    const identity = (await fs.readFile(paths.stationIdentityMd, "utf-8")).trim();
    if (identity) return identity + "\n" + CHAT_CONTRACT;
  } catch {
    // fall through to the station.md-derived fallback below
  }
  console.warn(
    "[station] automation/prompts/station-identity.md missing/unreadable -- " +
    "falling back to a trimmed station.md for Talk-to-Gamma's persona (JSON-only " +
    "output rules stripped so the chat face still answers in prose)",
  );
  try {
    const raw = await fs.readFile(paths.stationPromptMd, "utf-8");
    const trimmed = raw
      .split("\n")
      .slice(0, 40)
      .filter((line) => !/output valid json only|no markdown code fences|no commentary before or after/i.test(line))
      .join("\n")
      .trim();
    if (trimmed) return trimmed + "\n" + CHAT_CONTRACT;
  } catch {
    // both sources gone -- final generic fallback below
  }
  return "You are Gamma's Station. Cite only the facts you are given. Never invent a number." + "\n" + CHAT_CONTRACT;
}

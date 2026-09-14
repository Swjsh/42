// I1 (INTERACT-2, 2026-09-14): "the desks show real work" -- one small,
// self-contained reader per non-Pilot persona, each pointed at the exact
// evidence file that persona's own real output lives in. Every reader is
// fail-open (never throws -- a missing/garbled source degrades to an honest
// "no data yet" DeskContent, never a fabricated one) so one bad file can
// never 500 /api/hq. Pilot is deliberately NOT covered here -- Scene.tsx
// already reads data.trading.core.{safe,bold} for Pilot's desk screen
// (commit 81147547); duplicating that wiring through a second reader would
// give the live trading strip two sources of truth for the same screen.
//
// Kept fs-only and Node-only on purpose (no import from anything under
// components/hq/*): this module is consumed exclusively by
// app/api/hq/route.ts (a server route). A "use client" file must only ever
// take TYPE-only imports from here (see lib/dialogue.ts's own getLatestSpeech
// vs LatestSpeech split for the established, verified-safe precedent) --
// importing a VALUE from this file into a client component would pull
// node:fs into the browser bundle.

import { promises as fs } from "node:fs";
import path from "node:path";
import { WORKSPACE_ROOT, paths } from "./workspace";

export type DeskPersonaName = "Scout" | "Coach" | "Analyst" | "Chef" | "Treasurer" | "Gamma (Manager)";

export interface DeskContent {
  /** The real evidence line, e.g. a top catalyst, a card title, a P&L line. */
  headline: string;
  /** A shorter secondary line -- a figure, a count, a status. */
  sub: string;
  /** Minutes since the source evidence's OWN timestamp (mtime or ts_et) --
   * null when unknown (no source file yet), never guessed at 0. */
  ageMin: number | null;
  /** True when ageMin exceeds this role's own real cadence (DESK_CADENCE_MIN
   * below) -- DeskScreen.tsx's caller (Scene.tsx) tints the age line amber
   * when this is true. Always computed server-side (readDesksSnapshot's own
   * withStale wrapper), never left for a client to recompute. */
  stale: boolean;
  /** Repo-relative path to the real source file, for traceability. */
  path: string;
}

// ─── local, self-contained helpers (deliberately NOT imported from
//     components/hq/palette.ts -- every existing lib/*.ts reader in this
//     codebase already keeps its own private copy of these exact idioms
//     rather than sharing one; see personas.ts#etLikeToIso/todayET,
//     useMotionEvents.ts#toComparableEtMs, palette.ts#parseEtLikeMinutes/
//     nowEtMinutes -- this file follows that same established convention). ──

function truncate(text: string | null | undefined, max: number): string {
  if (!text) return "";
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

function fmtSigned(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "n/a";
  const rounded = Math.round(Math.abs(n));
  return `${n >= 0 ? "+" : "-"}$${rounded.toLocaleString("en-US")}`;
}

/** "YYYY-MM-DD HH:MM:SS ET" / "...T..." (no offset) -> minutes elapsed,
 * computed the same "Date.UTC of the raw digits, compared against an
 * Intl-derived 'now' expressed the identical way" trick every other ET-
 * string reader in this codebase uses. Returns null on anything unparsable. */
function ageMinFromEtString(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(raw);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number) as unknown as number[];
  const thenMs = Date.UTC(y, mo - 1, d, h, mi, s);
  const nowParts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const get = (t: string) => Number(nowParts.find((p) => p.type === t)?.value ?? "0");
  const nowMs = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second"));
  return Math.max(0, (nowMs - thenMs) / 60000);
}

function ageMinFromMtimeMs(mtimeMs: number | null): number | null {
  if (mtimeMs === null) return null;
  return Math.max(0, (Date.now() - mtimeMs) / 60000);
}

function emptyDesk(headline: string, srcPath: string): DeskContent {
  return { headline, sub: "", ageMin: null, stale: false, path: srcPath };
}

// ─── Scout: automation/scout/state/scout_output.json -- top catalyst line ────

interface ScoutOutputShape {
  catalysts_in_session?: Array<{ type?: string; name?: string; time_et?: string }>;
  macro_calendar_today?: Array<{ event?: string; severity?: string; time_et?: string }>;
  scout_one_line_summary?: string;
}

async function readScoutDesk(): Promise<DeskContent> {
  const srcPath = "automation/scout/state/scout_output.json";
  const p = path.join(WORKSPACE_ROOT, "automation", "scout", "state", "scout_output.json");
  try {
    const [text, stat] = await Promise.all([fs.readFile(p, "utf-8"), fs.stat(p)]);
    const data = JSON.parse(text) as ScoutOutputShape;
    const topCatalyst = data.catalysts_in_session?.[0];
    const highCal = data.macro_calendar_today?.find((c) => c.severity === "HIGH");
    const headline = topCatalyst?.name
      ? truncate(`${topCatalyst.time_et ?? "?"} ${topCatalyst.name}`, 90)
      : highCal?.event
        ? truncate(`${highCal.time_et ?? "?"} ${highCal.event}`, 90)
        : truncate(data.scout_one_line_summary, 90) || "no catalyst flagged today";
    const sub = truncate(data.scout_one_line_summary, 90) || "(no summary)";
    return { headline, sub, ageMin: ageMinFromMtimeMs(stat.mtimeMs), stale: false, path: srcPath };
  } catch {
    return emptyDesk("no scout report yet", srcPath);
  }
}

// ─── Chef: analysis/recommendations/station-verdicts.jsonl joined with
//     automation/state/station/ideas-board.json (card_id -> title) ──────────

interface StationVerdictRow {
  ts_et?: string;
  card_id?: string;
  result?: { n_pre?: number; n_post?: number; effect_pre?: number; detail?: string };
}

async function readIdeaCardTitle(cardId: string): Promise<string | null> {
  try {
    const text = await fs.readFile(paths.ideasBoard, "utf-8");
    const board = JSON.parse(text) as Array<{ id?: string; title?: string }>;
    return board.find((c) => c.id === cardId)?.title ?? null;
  } catch {
    return null;
  }
}

async function readChefDesk(): Promise<DeskContent> {
  const srcPath = "analysis/recommendations/station-verdicts.jsonl";
  const verdictsPath = path.join(WORKSPACE_ROOT, "analysis", "recommendations", "station-verdicts.jsonl");
  try {
    const text = await fs.readFile(verdictsPath, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean).slice(-300);
    const latestByCard = new Map<string, StationVerdictRow>();
    for (const line of lines) {
      let row: StationVerdictRow;
      try {
        row = JSON.parse(line) as StationVerdictRow;
      } catch {
        continue;
      }
      if (!row.card_id || !row.ts_et) continue;
      const prev = latestByCard.get(row.card_id);
      if (!prev || row.ts_et > (prev.ts_et ?? "")) latestByCard.set(row.card_id, row);
    }
    if (latestByCard.size === 0) return emptyDesk("no verdicts scored yet", srcPath);
    // "top testing card" = whichever card was scored most recently.
    let top: StationVerdictRow | null = null;
    for (const row of latestByCard.values()) {
      if (!top || (row.ts_et ?? "") > (top.ts_et ?? "")) top = row;
    }
    const cardId = top?.card_id ?? "";
    const title = cardId ? await readIdeaCardTitle(cardId) : null;
    const nPost = top?.result?.n_post ?? null;
    const effectPre = top?.result?.effect_pre ?? null;
    const minN = /min_n=(\d+)/.exec(top?.result?.detail ?? "")?.[1] ?? "10";
    const sub = `n_post ${nPost ?? "?"}/${minN} · pre ${fmtSigned(effectPre)}`;
    return {
      headline: truncate(title ?? `card ${cardId}`, 90) || `card ${cardId}`,
      sub,
      ageMin: ageMinFromEtString(top?.ts_et),
      stale: false,
      path: srcPath,
    };
  } catch {
    return emptyDesk("no verdicts file yet", srcPath);
  }
}

// ─── Coach: automation/state/station/sectors.json (NEW, CREW-RIG builder --
//     does not exist on disk as of this build; fully fail-open). Shape per
//     the INTERACT-2 spec: {ts_et, rows[], summary_line, task_health}. ───────

interface SectorsSnapshotShape {
  ts_et?: string;
  rows?: Array<Record<string, unknown>>;
  summary_line?: string;
  task_health?: { disabled?: string[]; failed_last_run?: string[] };
}

// ASSUMPTION: sectors.json's per-row shape wasn't finalized as of this build
// (the file doesn't exist on disk yet -- see the module header). Rank order
// mirrors components/hq/palette.ts#HEALTH_COLOR's own meaning (red worst,
// then amber/zombie, then frozen, green best) applied to whichever of
// lane/name/task + health/status/verdict fields a row actually carries.
// Never fabricates a lane name -- returns null (caller falls through to an
// honest summary-only line) if no row exposes a recognizable field.
const HEALTH_RANK: Record<string, number> = { red: 3, amber: 2, zombie: 2, frozen: 1, green: 0 };

function findWorstRow(rows: Array<Record<string, unknown>>): string | null {
  let worst: { name: string; health: string; rank: number } | null = null;
  for (const row of rows) {
    const name = (row.lane ?? row.name ?? row.task) as string | undefined;
    const health = (row.health ?? row.status ?? row.verdict) as string | undefined;
    if (!name || !health) continue;
    const rank = HEALTH_RANK[String(health).toLowerCase()] ?? 0;
    if (!worst || rank > worst.rank) worst = { name: String(name), health: String(health), rank };
  }
  return worst ? `${worst.name}: ${worst.health}` : null;
}

async function readCoachDesk(): Promise<DeskContent> {
  const srcPath = "automation/state/station/sectors.json";
  const p = path.join(WORKSPACE_ROOT, "automation", "state", "station", "sectors.json");
  try {
    const text = await fs.readFile(p, "utf-8");
    const data = JSON.parse(text) as SectorsSnapshotShape;
    const headline = truncate(data.summary_line, 90) || "no summary line";
    const failed = data.task_health?.failed_last_run ?? [];
    const disabled = data.task_health?.disabled ?? [];
    let sub: string;
    if (failed.length > 0) {
      sub = `failed: ${failed[0]}${failed.length > 1 ? ` (+${failed.length - 1} more)` : ""}`;
    } else {
      const worst = findWorstRow(data.rows ?? []);
      if (worst) sub = worst;
      else if (disabled.length > 0) sub = `${disabled.length} task(s) disabled`;
      else sub = (data.rows?.length ?? 0) > 0 ? "all lanes green" : "no lane rows yet";
    }
    return { headline, sub, ageMin: ageMinFromEtString(data.ts_et), stale: false, path: srcPath };
  } catch {
    return emptyDesk("no sectors report yet (CREW-RIG pending)", srcPath);
  }
}

// ─── Analyst: analysis/eod/<newest>.md -- first heading + P&L line ──────────

async function readAnalystDesk(): Promise<DeskContent> {
  const srcPath = "analysis/eod/";
  const dir = path.join(WORKSPACE_ROOT, "analysis", "eod");
  try {
    const files = await fs.readdir(dir);
    const mdFiles = files.filter((f) => /^\d{4}-\d{2}-\d{2}\.md$/.test(f));
    if (mdFiles.length === 0) return emptyDesk("no EOD digest yet", srcPath);
    mdFiles.sort(); // YYYY-MM-DD filenames sort chronologically as plain strings
    const newest = mdFiles[mdFiles.length - 1];
    const fp = path.join(dir, newest);
    const [text, stat] = await Promise.all([fs.readFile(fp, "utf-8"), fs.stat(fp)]);
    const headingMatch = /^#{1,6}\s+(.+)$/m.exec(text);
    const headline = truncate(headingMatch?.[1], 90) || "(no heading found)";
    const pnlMatch = /Total recorded P&L:\s*(-?[\d,.]+)/i.exec(text) ?? /P&L[^\n]{0,60}/i.exec(text);
    const sub = pnlMatch ? truncate(pnlMatch[0], 90) : "(no P&L line found)";
    return { headline, sub, ageMin: ageMinFromMtimeMs(stat.mtimeMs), stale: false, path: `analysis/eod/${newest}` };
  } catch {
    return emptyDesk("no EOD digest yet", srcPath);
  }
}

// ─── Treasurer: newest analysis/treasury/*.md (dated reports AND
//     draft-params-changes.md both qualify -- either is a real "new treasury
//     file") -- headline + a figure ──────────────────────────────────────────

async function readTreasurerDesk(): Promise<DeskContent> {
  const srcPath = "analysis/treasury/";
  const dir = path.join(WORKSPACE_ROOT, "analysis", "treasury");
  try {
    const files = await fs.readdir(dir);
    const mdFiles = files.filter((f) => f.endsWith(".md"));
    if (mdFiles.length === 0) return emptyDesk("no treasury report yet", srcPath);
    const withStats = await Promise.all(
      mdFiles.map(async (f) => ({ f, stat: await fs.stat(path.join(dir, f)) })),
    );
    withStats.sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs);
    const newest = withStats[0];
    const text = await fs.readFile(path.join(dir, newest.f), "utf-8");
    const headingMatch = /^#\s+(.+)$/m.exec(text);
    const headline = truncate(headingMatch?.[1], 90) || newest.f;
    const figureLine = /^.*equity.*\$[\d,.]+.*$/im.exec(text) ?? /-?\$[\d,]+(?:\.\d+)?/.exec(text);
    const sub = figureLine ? truncate(figureLine[0].replace(/\|/g, " "), 90) : "(no figure found)";
    return { headline, sub, ageMin: ageMinFromMtimeMs(newest.stat.mtimeMs), stale: false, path: `analysis/treasury/${newest.f}` };
  } catch {
    return emptyDesk("no treasury report yet", srcPath);
  }
}

// ─── Gamma (Manager): automation/state/station/station-brief.md -- the
//     brief's own first line (the header) + the first real prose line ───────

async function readGammaDesk(): Promise<DeskContent> {
  const srcPath = "automation/state/station/station-brief.md";
  try {
    const [text, stat] = await Promise.all([fs.readFile(paths.stationBrief, "utf-8"), fs.stat(paths.stationBrief)]);
    const lines = text.split(/\r?\n/);
    const headline = truncate(lines[0], 90) || "(empty brief)";
    const bodyFirstLine = lines.slice(1).find((l) => l.trim().length > 0);
    const sub = truncate(bodyFirstLine, 90) || "(no body yet)";
    return { headline, sub, ageMin: ageMinFromMtimeMs(stat.mtimeMs), stale: false, path: srcPath };
  } catch {
    return emptyDesk("no brief written yet", srcPath);
  }
}

// ─── cadence + combinator ────────────────────────────────────────────────────

// Per-role real cadence, in minutes -- drawn from each persona's OWN
// documented schedule (lib/personas.ts's collectors carry the same schedule
// strings) rather than invented. ageMin > this => DeskScreen renders an
// amber "stale" tint on the age line (Scene.tsx reads `.stale` directly,
// see this file's own DeskContent doc comment -- computed here once, never
// recomputed client-side, so no client file needs this table at all).
const DESK_CADENCE_MIN: Record<DeskPersonaName, number> = {
  Scout: 24 * 60, // fires daily 05:30 ET
  Coach: 45, // sectors.json rides the ~30min Station-loop cadence + slack
  Analyst: 24 * 60, // fires weekdays 16:45 ET -- genuinely stale over a weekend, which is true
  Chef: 45, // station-verdicts.jsonl scores on the same ~30min Station-loop cadence (verified live: 09:51/10:21/10:51/11:21)
  Treasurer: 7 * 24 * 60, // fires Sundays 16:00 ET
  "Gamma (Manager)": 7 * 60, // 30min loop cadence, but correctly YIELDS (writes nothing) the whole 09:30-15:55 ET RTH window -- 7h covers that yield without a false stale flag
};

function isDeskStale(name: DeskPersonaName, ageMin: number | null): boolean {
  if (ageMin === null) return false; // unknown age is not the same as confirmed-stale -- never guess
  return ageMin > DESK_CADENCE_MIN[name];
}

export type DesksSnapshot = Record<DeskPersonaName, DeskContent>;

/** Combines all six desk readers -- each independently fail-open, so one bad
 * source degrades only that persona's card, never the whole /api/hq payload
 * (same Promise.all discipline as lib/hq.ts#readBlocked/readTradingStatus). */
export async function readDesksSnapshot(): Promise<DesksSnapshot> {
  const [scout, coach, analyst, chef, treasurer, gamma] = await Promise.all([
    readScoutDesk(),
    readCoachDesk(),
    readAnalystDesk(),
    readChefDesk(),
    readTreasurerDesk(),
    readGammaDesk(),
  ]);
  const withStale = (name: DeskPersonaName, d: DeskContent): DeskContent => ({ ...d, stale: isDeskStale(name, d.ageMin) });
  return {
    Scout: withStale("Scout", scout),
    Coach: withStale("Coach", coach),
    Analyst: withStale("Analyst", analyst),
    Chef: withStale("Chef", chef),
    Treasurer: withStale("Treasurer", treasurer),
    "Gamma (Manager)": withStale("Gamma (Manager)", gamma),
  };
}

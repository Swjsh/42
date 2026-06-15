import { promises as fs } from "node:fs";
import { paths } from "./workspace";
import type { HeartbeatLine } from "./scores";

export type { HeartbeatLine } from "./scores";

export interface JournalParse {
  count: number;
  latest: HeartbeatLine | null;
  recent: HeartbeatLine[];
}

const HB_LINE =
  /HB#(\d+)\s+(\d{2}:\d{2})\s+(\S+)\s*\|\s*(.+?)\s*\|\s*(.+?)$/;

function extractNumber(re: RegExp, body: string): number | null {
  const m = body.match(re);
  return m ? Number(m[1]) : null;
}

function extractString(re: RegExp, body: string): string | null {
  const m = body.match(re);
  return m ? m[1] : null;
}

export function parseHeartbeatLine(raw: string): HeartbeatLine | null {
  const m = raw.match(HB_LINE);
  if (!m) return null;
  const [, tick, time_et, action, body, reason] = m;
  return {
    tick: Number(tick),
    time_et,
    action,
    spy: extractNumber(/spy=([\d.]+)/, body),
    ribbon_spread_cents: extractNumber(/ribbon=([\d.]+)c/, body),
    ribbon_stack: extractString(/ribbon=[\d.]+c\((\w+)\)/, body),
    vix: extractNumber(/vix=([\d.]+)/, body),
    vix_dir: extractString(/vix=[\d.]+\((\w+)\)/, body),
    bear_score: extractNumber(/bear=(\d+)\/10/, body),
    bull_score: extractNumber(/bull=(\d+)\/11/, body),
    reason: reason.trim(),
    raw: raw.trim(),
  };
}

export async function parseJournalToday(
  dateYYYYMMDD: string,
): Promise<JournalParse> {
  try {
    const text = await fs.readFile(paths.journal(dateYYYYMMDD), "utf-8");
    const lines = text.split(/\r?\n/);
    const ticks: HeartbeatLine[] = [];
    for (const line of lines) {
      const parsed = parseHeartbeatLine(line);
      if (parsed) ticks.push(parsed);
    }
    return {
      count: ticks.length,
      latest: ticks.length > 0 ? ticks[ticks.length - 1] : null,
      recent: ticks.slice(-8),
    };
  } catch {
    return { count: 0, latest: null, recent: [] };
  }
}

export async function countTradesToday(
  dateYYYYMMDD: string,
): Promise<number> {
  try {
    const text = await fs.readFile(paths.trades, "utf-8");
    const lines = text.split(/\r?\n/).slice(1); // skip header
    return lines.filter((l) => l.startsWith(dateYYYYMMDD)).length;
  } catch {
    return 0;
  }
}

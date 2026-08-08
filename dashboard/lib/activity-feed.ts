// LIVE ACTIVITY STREAM data layer for the Gamma App -- a reverse-chron feed of
// REAL events only, zero fabrication, merged from four sources:
//   1. git commits (repo history -- "what I shipped")
//   2. discord-outbox.jsonl, ALLOWLISTED sources only (standups/narrative/
//      prospector -- "what I told J"), banned-substring filtered so a raw
//      DEGRADED infra-ops dump never reaches the page (same discipline
//      gamma_hq.py's _BANNED_SUBSTRINGS already enforces for the terminal)
//   3. journal/trades.csv (REAL fills -- "what I traded"). NOTE: the engine's
//      per-tick decisions.jsonl / aggressive/decisions.jsonl are STALE
//      (last written 2026-06-25, verified live before wiring this) and would
//      silently misrepresent "recent" activity if used -- trades.csv is both
//      the doctrinally-correct source (C1: real-fills is the only authority)
//      and the one that's actually current.
//   4. the shadow-strategy ledgers (futures mirror-shadow + SSR shadow --
//      "what my paper strategies did"), always labeled as shadow/no-real-money
//      so this can never be mistaken for a real fill.

import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { WORKSPACE_ROOT, paths } from "./workspace";
import { parseBareTimestampInZone } from "./time";
import { sanitizeText, isLogSpew, stripLeadingBracketTag, fmtSignedMoney, humanizeIdentifier } from "./text";
import type { ActivityEvent } from "./gamma-app-types";

const execFileAsync = promisify(execFile);

// --- 1. git commits ---------------------------------------------------------

async function readGitCommits(n: number): Promise<ActivityEvent[]> {
  try {
    const { stdout } = await execFileAsync(
      "git",
      ["log", `--pretty=format:%h%x1f%ct%x1f%s`, `-${n}`],
      { cwd: WORKSPACE_ROOT, timeout: 10_000, windowsHide: true },
    );
    return stdout
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line): ActivityEvent | null => {
        const [hash, epochSec, subject] = line.split("\x1f");
        const epoch = Number(epochSec);
        if (!hash || !Number.isFinite(epoch)) return null;
        return {
          type: "commit",
          atIso: new Date(epoch * 1000).toISOString(),
          title: sanitizeText(subject, 140, "(no subject)"),
          subtitle: hash,
        };
      })
      .filter((e): e is ActivityEvent => e !== null);
  } catch {
    return [];
  }
}

// --- 2. discord-outbox.jsonl (narrative sources, log-spew filtered) --------

// Producers whose messages are first-person narrative/status content worth
// showing on the page. Deliberately excludes "self_check" -- live inspection
// (2026-08-08) showed 100% of recent self_check rows are raw "DEGRADED: ..."
// infra-ops dumps (PDT-blocked counters, masked-exit-code audits) with zero
// narrative value; every other allowlisted source is genuinely first-person.
const NARRATIVE_SOURCES = new Set([
  "gamma_standup_morning",
  "gamma_standup_eod",
  "daily_brief_morning",
  "daily_brief_eod",
  "prospector",
  "firm_brief",
  "trade_autopsy",
  "conductor",
  "pipeline_promoter",
  "open_bell_status",
]);

interface OutboxRow {
  ts?: string;
  queued_at?: string;
  source?: string;
  content?: string;
  message?: string;
}

async function readOutboxNarrative(n: number, scanLines = 400): Promise<ActivityEvent[]> {
  try {
    const text = await fs.readFile(paths.discordOutbox, "utf-8");
    const lines = text.split(/\r?\n/).filter(Boolean);
    const tail = lines.slice(-scanLines);
    const events: ActivityEvent[] = [];
    for (const line of tail) {
      let row: OutboxRow;
      try {
        row = JSON.parse(line) as OutboxRow;
      } catch {
        continue;
      }
      if (!row.source || !NARRATIVE_SOURCES.has(row.source)) continue;
      const rawText = String(row.content ?? row.message ?? "");
      if (!rawText.trim() || isLogSpew(rawText)) continue; // skip raw DEGRADED/traceback dumps outright
      // Order matters: content is "<@ID> [TAG] rest..." -- the Discord mention
      // sits BEFORE the bracket tag, so the tag-strip must run after the
      // mention-strip or it never matches (both are leading-anchor regexes).
      const withoutMention = rawText.replace(/^<@!?\d+>\s*/, "");
      const clean = sanitizeText(stripLeadingBracketTag(withoutMention.trim()), 180, "");
      if (!clean) continue;
      const at = parseBareTimestampInZone(row.queued_at ?? row.ts);
      if (!at) continue;
      events.push({
        type: "narrative",
        atIso: at.toISOString(),
        title: clean,
        subtitle: humanizeIdentifier(row.source),
      });
    }
    return events.slice(-n);
  } catch {
    return [];
  }
}

// --- 3. journal/trades.csv (real fills) -------------------------------------

function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        cur += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ",") {
      out.push(cur);
      cur = "";
    } else {
      cur += c;
    }
  }
  out.push(cur);
  return out;
}

async function readRealTrades(n: number): Promise<ActivityEvent[]> {
  try {
    const text = await fs.readFile(paths.trades, "utf-8");
    const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
    if (lines.length < 2) return [];
    const header = parseCsvLine(lines[0]).map((h) => h.replace(/^﻿/, "").trim());
    const col = (name: string): number => header.indexOf(name); // NAME-based, never positional (BXM header-drift class of bug)

    const iDate = col("date");
    const iTimeExit = col("time_exit");
    const iSetup = col("setup");
    const iContract = col("contract");
    const iPnl = col("dollar_pnl");
    const iQty = col("qty");
    if ([iDate, iTimeExit, iSetup, iContract, iPnl].some((i) => i === -1)) return [];

    const events: ActivityEvent[] = [];
    for (const line of lines.slice(1)) {
      const cells = parseCsvLine(line);
      const date = cells[iDate]?.trim();
      const timeExit = cells[iTimeExit]?.trim();
      const pnl = Number(cells[iPnl]);
      if (!date || !timeExit || !Number.isFinite(pnl)) continue;
      const at = parseBareTimestampInZone(`${date} ${timeExit}`);
      if (!at) continue;
      const setup = humanizeIdentifier(cells[iSetup]);
      const contract = (cells[iContract] ?? "").trim();
      const qty = cells[iQty]?.trim();
      events.push({
        type: "trade",
        atIso: at.toISOString(),
        title: `Closed ${setup || "trade"} ${contract} — ${fmtSignedMoney(pnl)}`,
        subtitle: qty ? `qty ${qty}` : undefined,
        tone: pnl > 0 ? "up" : pnl < 0 ? "down" : undefined,
      });
    }
    return events.slice(-n);
  } catch {
    return [];
  }
}

// --- 4. shadow-strategy ledgers (paper only, always labeled) --------------

interface MirrorRow {
  ts_et?: string;
  event?: string;
  pnl_usd_mes?: number;
  setup_name?: string;
  direction?: string;
}

async function readJsonlTailRows(filePath: string, n: number): Promise<Record<string, unknown>[]> {
  try {
    const text = await fs.readFile(filePath, "utf-8");
    const lines = text.split(/\r?\n/).filter(Boolean);
    const rows: Record<string, unknown>[] = [];
    for (const line of lines.slice(-n * 3)) {
      // over-fetch: some producers write a leading "_doc" line with no event
      try {
        const obj = JSON.parse(line) as Record<string, unknown>;
        if (obj && typeof obj === "object" && !("_doc" in obj)) rows.push(obj);
      } catch {
        continue;
      }
    }
    return rows.slice(-n);
  } catch {
    return [];
  }
}

async function readShadowFills(n: number): Promise<ActivityEvent[]> {
  const [mirrorRows] = await Promise.all([readJsonlTailRows(paths.futuresMirrorLedger, n)]);
  const events: ActivityEvent[] = [];
  for (const raw of mirrorRows) {
    const row = raw as MirrorRow;
    if (!row.event || typeof row.pnl_usd_mes !== "number") continue;
    const at = parseBareTimestampInZone(row.ts_et);
    if (!at) continue;
    const setup = humanizeIdentifier(row.setup_name);
    events.push({
      type: "shadow_fill",
      atIso: at.toISOString(),
      title: `Shadow ${setup || "mirror"} ${humanizeIdentifier(row.event)} — ${fmtSignedMoney(row.pnl_usd_mes)}`,
      subtitle: "MES futures mirror-shadow — no real money",
      tone: row.pnl_usd_mes > 0 ? "up" : row.pnl_usd_mes < 0 ? "down" : undefined,
    });
  }
  // ssr-shadow-would-be.jsonl currently holds zero closed round trips
  // (n_round_trips=0 per its own progress file) -- readJsonlTailRows already
  // fails open to [] there (the file's only line is a "_doc" header), so no
  // separate handling needed; wired here for when it starts producing rows.
  return events;
}

// --- merge ------------------------------------------------------------------

export async function gatherActivityFeed(limit = 20): Promise<ActivityEvent[]> {
  const [commits, narrative, trades, shadow] = await Promise.all([
    readGitCommits(limit),
    readOutboxNarrative(limit),
    readRealTrades(limit),
    readShadowFills(limit),
  ]);
  const merged = [...commits, ...narrative, ...trades, ...shadow].sort(
    (a, b) => new Date(b.atIso).getTime() - new Date(a.atIso).getTime(),
  );

  // Dedupe adjacent rows with identical type+title (observed live: a producer
  // occasionally queues the exact same outbox message twice in a row -- this
  // never invents or merges DIFFERENT content, only collapses a literal repeat).
  const deduped: ActivityEvent[] = [];
  for (const event of merged) {
    const prev = deduped[deduped.length - 1];
    if (prev && prev.type === event.type && prev.title === event.title) continue;
    deduped.push(event);
  }

  return deduped.slice(0, limit);
}

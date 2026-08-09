// Data layer for the Gamma App's live market chart (/api/gamma-chart) --
// REAL data only, zero fabrication, three independent sources:
//   1. backtest/data/spy_5m_*.csv (real SPY 5-minute bars, RTH session only)
//   2. automation/state/sight-beacon.json (a live ~1min-fresh single-tick
//      snapshot, refreshed by a real scheduled task -- extends the chart with
//      the freshest known price as a "live" point, distinct from closed bars)
//   3. journal/trades.csv (real fills -- TODAY's entries/exits, ET-dated)
//
// Each source is independently fail-open (bars: [], live: null, trades: [])
// so one bad/missing file degrades only its own piece of the chart -- same
// discipline as lib/activity-feed.ts's gatherActivityFeed.

import { promises as fs } from "node:fs";
import path from "node:path";
import { WORKSPACE_ROOT, paths } from "./workspace";
import { todayET, parseBareTimestampInZone } from "./time";
import { humanizeIdentifier, sanitizeText } from "./text";

export interface ChartBar {
  /** UTCTimestamp (seconds) -- see the note on etDigitsToChartTime below:
   * this encodes the literal ET wall-clock digits SPY printed, not a true
   * UTC instant. Use only for chart plotting. */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartLivePoint {
  price: number;
  /** True UTC instant, ISO string. */
  atIso: string;
  ageSeconds: number;
}

export interface ChartTradeMarker {
  /** True UTC instant, ISO string. */
  atIso: string;
  side: "entry" | "exit";
  direction: "call" | "put";
  /** The real option premium recorded in the journal (entry_px/exit_px) --
   * NOT a SPY price. Used for narration/tooltip text, never as a chart
   * y-coordinate (SPY bars and option premiums are on wildly different
   * scales). */
  price: number;
  setup: string;
  note: string | null;
  /** Only ever populated on the "exit" side -- an entry hasn't resolved yet. */
  pnl: number | null;
}

export interface ChartData {
  bars: ChartBar[];
  live: ChartLivePoint | null;
  trades: ChartTradeMarker[];
}

// --- quote-aware CSV line parser ---------------------------------------
// Ported verbatim from lib/activity-feed.ts's parseCsvLine (not exported
// there, and that file is outside this module's edit scope) -- a
// character-by-character, quote-aware splitter. journal/trades.csv has
// legacy rows with unescaped commas inside free-text notes fields; a naive
// String.split(",") silently misaligns every column after the first
// offender. Keep in sync with activity-feed.ts's copy if that one changes.
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

// --- wall-clock digit helpers -------------------------------------------

interface WallClockDigits {
  y: number;
  mo: number;
  d: number;
  hh: number;
  mm: number;
  ss: number;
}

const BARE_TS_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/;

/** Parse a "YYYY-MM-DD[T ]HH:MM:SS" prefix, ignoring any zone/offset suffix
 * -- backtest/data/spy_5m_*.csv's `timestamp_et` column already carries the
 * literal ET wall-clock digits (the "-04:00" suffix is informational, not
 * something we need to convert through). Never throws; returns null on
 * anything that doesn't match. */
function parseWallClockDigits(raw: string): WallClockDigits | null {
  const m = BARE_TS_RE.exec(raw.trim());
  if (!m) return null;
  const [, y, mo, d, hh, mm, ss] = m.map(Number);
  return { y, mo, d, hh, mm, ss };
}

/**
 * Lightweight Charts always displays time in UTC by design -- it does not
 * support a timezone option (confirmed against its own type declarations /
 * docs). SPY bars in this repo are already labeled in ET wall-clock digits.
 * Converting those digits to a true UTC instant would only have the chart
 * (or a viewer in a different OS timezone) reformat them right back to some
 * OTHER local time, defeating the point. Instead we encode the literal ET
 * digits AS a UTCTimestamp -- the chart shows exactly the digits SPY
 * actually printed, independent of the viewer's timezone. This is a
 * *display* timestamp, not a real UTC instant; never use it for elapsed-time
 * math -- use the `atIso` fields for that (see wallClockInZoneToUtc /
 * parseBareTimestampInZone in lib/time.ts for real-instant conversions).
 */
function etDigitsToChartTime(w: WallClockDigits): number {
  return Math.floor(Date.UTC(w.y, w.mo - 1, w.d, w.hh, w.mm, w.ss) / 1000);
}

function minutesOfDay(w: WallClockDigits): number {
  return w.hh * 60 + w.mm;
}

// --- 1. backtest/data/spy_5m_*.csv (real bars, RTH only) -----------------

const SPY_BARS_RE = /^spy_5m_\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})\.csv$/;
const RTH_OPEN_MIN = 9 * 60 + 30; // 09:30 ET
const RTH_CLOSE_MIN = 16 * 60; // 16:00 ET (exclusive -- last RTH bar is 15:55)

/** Newest spy_5m_START_END.csv by the END date encoded in the filename --
 * never hardcode a date that will go stale. Deliberately excludes
 * non-standard names like spy_5m_2026-07-23_supplement.csv (no parseable
 * end-date, so it can never win the newest-file comparison). */
async function findNewestBarsFile(): Promise<string | null> {
  const dir = path.join(WORKSPACE_ROOT, "backtest", "data");
  let entries: string[];
  try {
    entries = await fs.readdir(dir);
  } catch {
    return null;
  }
  let newest: { file: string; endDate: string } | null = null;
  for (const name of entries) {
    const m = SPY_BARS_RE.exec(name);
    if (!m) continue;
    const endDate = m[1];
    if (!newest || endDate > newest.endDate) newest = { file: name, endDate };
  }
  return newest ? path.join(dir, newest.file) : null;
}

async function loadRecentBars(): Promise<ChartBar[]> {
  try {
    const filePath = await findNewestBarsFile();
    if (!filePath) return [];
    const text = await fs.readFile(filePath, "utf-8");
    const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
    if (lines.length < 2) return [];
    const header = parseCsvLine(lines[0]).map((h) => h.replace(/^﻿/, "").trim());
    const col = (name: string): number => header.indexOf(name); // NAME-based, never positional

    const iTs = col("timestamp_et");
    const iOpen = col("open");
    const iHigh = col("high");
    const iLow = col("low");
    const iClose = col("close");
    if ([iTs, iOpen, iHigh, iLow, iClose].some((i) => i === -1)) return [];

    const rows: Array<ChartBar & { etDate: string }> = [];
    for (const line of lines.slice(1)) {
      const cells = parseCsvLine(line);
      const w = parseWallClockDigits(cells[iTs] ?? "");
      if (!w) continue;
      const minutes = minutesOfDay(w);
      if (minutes < RTH_OPEN_MIN || minutes >= RTH_CLOSE_MIN) continue; // extended-hours rows excluded

      const open = Number(cells[iOpen]);
      const high = Number(cells[iHigh]);
      const low = Number(cells[iLow]);
      const close = Number(cells[iClose]);
      if (![open, high, low, close].every(Number.isFinite)) continue;

      const etDate = `${String(w.y).padStart(4, "0")}-${String(w.mo).padStart(2, "0")}-${String(w.d).padStart(2, "0")}`;
      rows.push({ time: etDigitsToChartTime(w), open, high, low, close, etDate });
    }
    if (rows.length === 0) return [];

    // Most recent ~1-2 trading days present in the file. The file is
    // chronologically ascending, so walking forward and recording each new
    // date as it's first seen gives distinct dates in order.
    const distinctDates: string[] = [];
    for (const r of rows) {
      if (distinctDates[distinctDates.length - 1] !== r.etDate) distinctDates.push(r.etDate);
    }
    const keepDates = new Set(distinctDates.slice(-2));

    return rows.filter((r) => keepDates.has(r.etDate)).map(({ time, open, high, low, close }) => ({ time, open, high, low, close }));
  } catch {
    return [];
  }
}

// --- 2. automation/state/sight-beacon.json (live ~1min tick) -------------

interface SightBeaconFile {
  ok?: boolean;
  ts_utc?: string;
  ts_et?: string;
  spy?: number;
}

async function loadLivePoint(): Promise<ChartLivePoint | null> {
  try {
    const filePath = path.join(WORKSPACE_ROOT, "automation", "state", "sight-beacon.json");
    const text = await fs.readFile(filePath, "utf-8");
    const beacon = JSON.parse(text) as SightBeaconFile;
    if (beacon.ok !== true || typeof beacon.spy !== "number" || !Number.isFinite(beacon.spy)) return null;

    // Both ts_utc ("...+00:00") and ts_et ("...-04:00") carry an explicit
    // offset suffix, so a plain Date parse is unambiguous here -- no
    // wall-clock-in-zone conversion needed (unlike the bare, zone-less
    // timestamps journal/trades.csv writes).
    const rawTs = beacon.ts_utc ?? beacon.ts_et;
    if (!rawTs) return null;
    const atMs = Date.parse(rawTs);
    if (!Number.isFinite(atMs)) return null;

    const ageSeconds = Math.max(0, Math.round((Date.now() - atMs) / 1000));
    return { price: beacon.spy, atIso: new Date(atMs).toISOString(), ageSeconds };
  } catch {
    return null;
  }
}

// --- 3. journal/trades.csv (today's real fills) ---------------------------

async function loadTodaysTrades(): Promise<ChartTradeMarker[]> {
  try {
    const text = await fs.readFile(paths.trades, "utf-8");
    const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
    if (lines.length < 2) return [];
    const header = parseCsvLine(lines[0]).map((h) => h.replace(/^﻿/, "").trim());
    const col = (name: string): number => header.indexOf(name);

    const iDate = col("date");
    const iTimeEntry = col("time_entry");
    const iTimeExit = col("time_exit");
    const iSetup = col("setup");
    const iCorP = col("c_or_p");
    const iEntryPx = col("entry_px");
    const iExitPx = col("exit_px");
    const iPnl = col("dollar_pnl");
    const iNotes = col("notes_short");
    if ([iDate, iTimeEntry, iTimeExit, iSetup, iCorP, iEntryPx, iExitPx, iPnl].some((i) => i === -1)) return [];

    const today = todayET(); // real ET-aware "today" -- this box runs Mountain time
    const markers: ChartTradeMarker[] = [];

    for (const line of lines.slice(1)) {
      const cells = parseCsvLine(line);
      const date = cells[iDate]?.trim();
      if (date !== today) continue;

      const cpRaw = cells[iCorP]?.trim().toUpperCase();
      const direction: "call" | "put" | null = cpRaw === "C" ? "call" : cpRaw === "P" ? "put" : null;
      if (!direction) continue; // never guess a direction the row didn't state

      const setup = humanizeIdentifier(cells[iSetup]) || "a setup";
      const note = iNotes >= 0 ? sanitizeText(cells[iNotes], 240, "") || null : null;

      const timeEntry = cells[iTimeEntry]?.trim();
      const entryPx = Number(cells[iEntryPx]);
      if (timeEntry && Number.isFinite(entryPx)) {
        const entryAt = parseBareTimestampInZone(`${date} ${timeEntry}`);
        if (entryAt) {
          markers.push({ atIso: entryAt.toISOString(), side: "entry", direction, price: entryPx, setup, note, pnl: null });
        }
      }

      const timeExit = cells[iTimeExit]?.trim();
      const exitPx = Number(cells[iExitPx]);
      if (timeExit && Number.isFinite(exitPx)) {
        const exitAt = parseBareTimestampInZone(`${date} ${timeExit}`);
        if (exitAt) {
          const pnl = Number(cells[iPnl]);
          markers.push({
            atIso: exitAt.toISOString(),
            side: "exit",
            direction,
            price: exitPx,
            setup,
            note,
            pnl: Number.isFinite(pnl) ? pnl : null,
          });
        }
      }
    }
    return markers;
  } catch {
    return [];
  }
}

// --- assemble ---------------------------------------------------------------

export async function getChartData(): Promise<ChartData> {
  const [bars, live, trades] = await Promise.all([loadRecentBars(), loadLivePoint(), loadTodaysTrades()]);
  return { bars, live, trades };
}

import { promises as fs } from "node:fs";
import path from "node:path";
import { WORKSPACE_ROOT } from "./workspace";

// Mirrors setup/scripts/sight_beacon.py's STALE_AFTER_S constant ("consumers
// must treat a beacon older than this as untrustworthy"). Kept in sync by
// hand -- if that script's constant changes, update this too.
const STALE_AFTER_S = 180;

const SIGHT_BEACON_PATH = path.join(WORKSPACE_ROOT, "automation", "state", "sight-beacon.json");
const PRIOR_CLOSE_PATH = path.join(WORKSPACE_ROOT, "automation", "state", "prior-rth-close.json");

// Real on-disk schema of automation/state/sight-beacon.json as written by
// setup/scripts/sight_beacon.py (verified by reading the live file, not
// assumed). All fields optional -- a malformed/partial write must degrade,
// never throw.
interface SightBeaconFile {
  ok?: boolean;
  ts_utc?: string;
  ts_et?: string;
  time_et?: string;
  age_s?: number;
  spy?: number;
  ribbon_stack?: string;
  ema_fast?: number;
  ema_pivot?: number;
  ema_slow?: number;
  sma_50?: number;
  spread_cents?: number;
  data_source?: string;
  fetch_note?: string;
}

// Real on-disk schema of automation/state/prior-rth-close.json (a structured
// file, distinct from the free-text prior-close mention buried in
// today-bias.json's bias_note prose -- this is the derivable one).
interface PriorRthCloseFile {
  date?: string;
  prior_rth_close?: number;
  spot?: number;
  gap_pts?: number;
  gap_direction?: string;
}

export type Staleness = "live" | "stale" | "unavailable";

export interface Quote {
  price: number | null;
  /** Wall-clock HH:MM:SS pulled from the beacon's own ts_et (already ET-offset,
   * so no client-side timezone math is needed). Null if the beacon lacks a
   * parseable timestamp. */
  asOfEt: string | null;
  /** Real elapsed seconds computed fresh against `ts_utc` at request time --
   * NOT the file's own `age_s` field, which is only accurate at the instant
   * sight_beacon.py wrote it and goes stale itself between ~1min writes. */
  ageSeconds: number | null;
  staleness: Staleness;
  ribbonStack: string | null;
  change: number | null;
  changePct: number | null;
  priorClose: number | null;
  dataSource: string | null;
}

async function readJson<T>(p: string): Promise<T | null> {
  try {
    const raw = await fs.readFile(p, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function extractTimeOfDay(tsEt: string | undefined): string | null {
  if (!tsEt) return null;
  const m = /T(\d{2}:\d{2}:\d{2})/.exec(tsEt);
  return m ? m[1] : null;
}

const UNAVAILABLE_QUOTE: Quote = {
  price: null,
  asOfEt: null,
  ageSeconds: null,
  staleness: "unavailable",
  ribbonStack: null,
  change: null,
  changePct: null,
  priorClose: null,
  dataSource: null,
};

/**
 * Real ~1min-fresh SPY snapshot from the NEVER-BLIND sight beacon
 * (automation/state/sight-beacon.json, written by setup/scripts/sight_beacon.py
 * every ~1min during RTH via a real broker/yfinance REST fetch -- no MCP, no
 * simulation). This is honestly ~1min-fresh data, never tick-by-tick
 * real-time -- staleness is computed here, fresh, every call, and must be
 * surfaced to the user rather than hidden.
 *
 * Change-vs-prior-close is derived from automation/state/prior-rth-close.json
 * (a structured file consumed by the live setup_dispatch gap-fill logic) when
 * present; null when not derivable -- never fabricated.
 */
export async function getQuote(): Promise<Quote> {
  const beacon = await readJson<SightBeaconFile>(SIGHT_BEACON_PATH);
  if (!beacon || typeof beacon.spy !== "number" || !Number.isFinite(beacon.spy)) {
    return UNAVAILABLE_QUOTE;
  }

  const writtenAtMs = beacon.ts_utc ? Date.parse(beacon.ts_utc) : NaN;
  const ageSeconds = Number.isFinite(writtenAtMs)
    ? Math.max(0, Math.round((Date.now() - writtenAtMs) / 1000))
    : null;
  const staleness: Staleness = ageSeconds === null ? "unavailable" : ageSeconds > STALE_AFTER_S ? "stale" : "live";

  const priorCloseFile = await readJson<PriorRthCloseFile>(PRIOR_CLOSE_PATH);
  const priorClose =
    typeof priorCloseFile?.prior_rth_close === "number" && Number.isFinite(priorCloseFile.prior_rth_close)
      ? priorCloseFile.prior_rth_close
      : null;
  const change = priorClose !== null ? beacon.spy - priorClose : null;
  const changePct = priorClose !== null && priorClose !== 0 && change !== null ? (change / priorClose) * 100 : null;

  return {
    price: beacon.spy,
    asOfEt: extractTimeOfDay(beacon.ts_et) ?? beacon.time_et ?? null,
    ageSeconds,
    staleness,
    ribbonStack: beacon.ribbon_stack ?? null,
    change,
    changePct,
    priorClose,
    dataSource: beacon.data_source ?? null,
  };
}

// Real per-arm P&L for the Money tile's progress bars -- parses
// journal/trades.csv (the ONLY authority per doctrine C1: "real-fills is the
// only WR authority") and rolls dollar_pnl up per fleet arm: today (real ET
// trading day), the last 7 real trading days present in the data, and
// all-time. Fails open -- an arm with zero trades today (a real, valid,
// expected state, especially on a non-trading day) still returns a real row
// with todayPnl:0, never omitted or fabricated.
//
// journal/trades.csv predates the 2026-06-25 fleet grid rebuild and still
// uses SHORT account_id labels that don't 1:1 match
// automation/state/fleet/accounts.json's arm ids. Mapping confirmed
// 2026-08-09 by cross-checking row counts + date ranges against
// accounts.json's own frozen_at/retired_at fields:
//   "safe"    (55 rows, 2026-04-29..2026-08-07, the longest-running/oldest
//              label) -> safe-2 / CORE-SAFE  (accounts.json frozen_at
//              2026-06-20, the mcp_heartbeat-executed CONTROL arm -- the
//              only arm old enough to own the pre-fleet-grid "safe" rows)
//   "bold"    (11 rows, 2026-07-17..2026-08-04) -> bold-2 / CORE-BOLD (same
//              control-arm reasoning, aggressive side; accounts.json
//              frozen_at 2026-06-20)
//   "safe-3"  (53 rows) -> safe-3  / FLEET-TIGHT-S    (id matches verbatim)
//   "risky-1" (58 rows) -> risky-1 / FLEET-FULLSEND-R (id matches verbatim)
//   "risky-3" (82 rows) -> risky-3 / FLEET-LOOSE-R    (id matches verbatim)
// "safe-1" (31 rows, ends 2026-07-09) is accounts.json's RETIRED arm
// (retired_at 2026-07-11, its broker account was reassigned to safe-2) --
// correctly excluded from the 5 active arms this tile shows. A small number
// of legacy rows (~20, blank account_id, dated 2026-06-15..2026-07-06,
// predating the quote-aware CSV parser) plus a handful of comma-corrupted
// rows whose account_id cell parses as free-text notes are excluded the same
// way: any label that doesn't match one of the 5 known arms is skipped, never
// guessed at.

import { promises as fs } from "node:fs";
import { paths } from "./workspace";
import { todayET } from "./time";
import { parseCsvLine } from "./activity-feed";
import type { FleetArmPnl } from "./gamma-app-types";

const JOURNAL_LABEL_TO_ARM: Record<string, { armId: string; displayName: string }> = {
  safe: { armId: "safe-2", displayName: "CORE-SAFE (46VG)" },
  bold: { armId: "bold-2", displayName: "CORE-BOLD (U67N)" },
  "safe-3": { armId: "safe-3", displayName: "FLEET-TIGHT-S (T20H)" },
  "risky-1": { armId: "risky-1", displayName: "FLEET-FULLSEND-R (V0A4)" },
  "risky-3": { armId: "risky-3", displayName: "FLEET-LOOSE-R (5H6Z)" },
};

// Fixed display order -- the two production control arms (safe/bold pair)
// first, then the three fleet gate-variant arms in the same
// tight->fullsend->loose order accounts.json's grid uses.
const ARM_ORDER = ["safe-2", "bold-2", "safe-3", "risky-1", "risky-3"];

// J's per-account daily target band (CLAUDE.md 2026-08-07 correction: PER
// ACCOUNT, not book-wide) -- one clean +30% level trade at $2K.
const TARGET_LOW = 100;
const TARGET_HIGH = 200;

interface ArmTotals {
  today: number;
  todayTrades: number;
  week: number;
  allTime: number;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

export async function getFleetPnl(): Promise<FleetArmPnl[]> {
  const totals = new Map<string, ArmTotals>();
  for (const armId of ARM_ORDER) totals.set(armId, { today: 0, todayTrades: 0, week: 0, allTime: 0 });

  try {
    const text = await fs.readFile(paths.trades, "utf-8");
    const lines = text.split(/\r?\n/).filter((l) => l.length > 0);
    if (lines.length >= 2) {
      const header = parseCsvLine(lines[0]).map((h) => h.replace(/^﻿/, "").trim());
      const col = (name: string): number => header.indexOf(name); // NAME-based, never positional
      const iDate = col("date");
      const iPnl = col("dollar_pnl");
      const iAccount = col("account_id");

      if (iDate !== -1 && iPnl !== -1 && iAccount !== -1) {
        const rows: { date: string; pnl: number; armId: string }[] = [];
        const allDates = new Set<string>();

        for (const line of lines.slice(1)) {
          const cells = parseCsvLine(line);
          const date = cells[iDate]?.trim();
          const pnl = Number(cells[iPnl]);
          const label = cells[iAccount]?.trim();
          if (!date || !Number.isFinite(pnl) || !label) continue;
          const mapped = JOURNAL_LABEL_TO_ARM[label];
          if (!mapped) continue; // safe-1 (retired) + blank/comma-corrupted legacy rows -- never guessed at
          allDates.add(date);
          rows.push({ date, pnl, armId: mapped.armId });
        }

        // "Last 7 real trading days present in the data" -- not a naive
        // 7-calendar-day window (weekends/holidays would silently shrink it).
        const last7 = new Set([...allDates].sort().slice(-7));
        const today = todayET(); // ET trading day, never naive local time (this box runs Mountain)

        for (const row of rows) {
          const bucket = totals.get(row.armId);
          if (!bucket) continue;
          bucket.allTime += row.pnl;
          if (last7.has(row.date)) bucket.week += row.pnl;
          if (row.date === today) {
            bucket.today += row.pnl;
            bucket.todayTrades += 1;
          }
        }
      }
    }
  } catch {
    // fail-open -- every arm below still returns a real, valid zeroed row
    // rather than the whole tile going blank.
  }

  return ARM_ORDER.map((armId) => {
    const meta = Object.values(JOURNAL_LABEL_TO_ARM).find((m) => m.armId === armId)!;
    const t = totals.get(armId)!;
    return {
      armId,
      displayName: meta.displayName,
      todayPnl: round2(t.today),
      todayTrades: t.todayTrades,
      targetLow: TARGET_LOW,
      targetHigh: TARGET_HIGH,
      weekPnl: round2(t.week),
      allTimePnl: round2(t.allTime),
    };
  });
}

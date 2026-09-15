// HQ-TRADE-MOMENTS (2026-09-15): per-arm TODAY P&L panel, built strictly
// from fills-ledger.jsonl FIFO math (lib/hq-positions-pure.ts#
// computeClosedToday), NOT journal/trades.csv (lib/fleet-pnl.ts's existing
// Money-tile source). Deliberately a SEPARATE reader from fleet-pnl.ts: the
// task this module was filed against explicitly requires "values must equal
// fills-ledger FIFO math", i.e. the SAME source lib/hq-positions.ts already
// reads for the open-position truth, so a viewer never sees two different
// numbers for "today's P&L" that both claim to be live truth depending on
// which panel they're looking at within the position/trade-moment surface.
// journal/trades.csv stays the Money tile's own authority (doctrine C1) --
// this module doesn't touch or replace it.

import type { AccountPositions } from "./hq-positions-pure";

export interface ArmPnlRow {
  armId: string;
  displayName: string | null;
  trades: number;
  wins: number;
  losses: number;
  realizedUsd: number;
  openQty: number;
  error: string | null;
}

export interface FleetPnlLive {
  arms: ArmPnlRow[];
  bookRealizedUsd: number;
}

/** Rolls a Record<armId, AccountPositions> (already keyed by every active
 * arm -- see lib/hq-fleet-arms-pure.ts) into the per-arm P&L panel, in the
 * caller-supplied display order (so the panel's row order matches
 * accounts.json's own grid order, not object-key iteration order). An arm
 * with a read error contributes 0 to bookRealizedUsd (never a silent
 * fabricated number) but still renders its own row with `error` set, so the
 * panel can show "safe-3: unavailable" instead of quietly omitting it. */
export function buildFleetPnlLive(
  positionsByArm: Readonly<Record<string, AccountPositions>>,
  armOrder: readonly { id: string; displayName: string | null }[],
): FleetPnlLive {
  const arms: ArmPnlRow[] = armOrder.map(({ id, displayName }) => {
    const pos = positionsByArm[id];
    if (!pos) {
      return { armId: id, displayName, trades: 0, wins: 0, losses: 0, realizedUsd: 0, openQty: 0, error: "no position data" };
    }
    const wins = pos.closedToday.filter((c) => c.realizedUsd > 0).length;
    const losses = pos.closedToday.filter((c) => c.realizedUsd < 0).length;
    const openQty = pos.open.reduce((sum, leg) => sum + leg.qty, 0);
    return {
      armId: id,
      displayName,
      trades: pos.closedToday.length,
      wins,
      losses,
      realizedUsd: Math.round(pos.realizedTodayUsd * 100) / 100,
      openQty,
      error: pos.error,
    };
  });
  const bookRealizedUsd = Math.round(arms.reduce((sum, a) => sum + (a.error ? 0 : a.realizedUsd), 0) * 100) / 100;
  return { arms, bookRealizedUsd };
}

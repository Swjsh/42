// HQ-TRADE-MOMENTS (2026-09-15): pure filter over automation/state/fleet/
// accounts.json's ALREADY-PARSED JSON, deriving "which arms does HQ show
// live trade moments + per-arm P&L for today" -- the fleet grid registry is
// the ONE place that knows which arms are live (an arm's status flips
// active/retired/pending_build on a real schedule, e.g. safe-1's 2026-07-11
// retirement, weekly-1's still-pending build), so this reads accounts.json
// fresh every poll instead of a hardcoded arm list going stale the next
// time the grid changes. Zero fs imports -- same pure/adapter split every
// other hq-*-pure.ts module in this directory documents.

/** One active SPY 0DTE arm, as accounts.json itself describes it. */
export interface FleetArmMeta {
  id: string;
  displayName: string | null;
}

/** `status === "active"` AND `instrument === "SPY_0DTE_OPTION"` -- as of
 * 2026-09-15 that's exactly {safe-3, safe-2, risky-1, bold-2, risky-3} (5
 * arms), verified against the live file this session. The instrument gate
 * is deliberate, not redundant: it keeps a FUTURE active futures/weekly arm
 * (mes-linear-sim, weekly-1 -- both `pending_build` today) from silently
 * appearing in the SPY 0DTE trade-moment/P&L surfaces this module feeds,
 * should one of them flip to active before this reader is updated for a
 * genuinely multi-instrument HQ. Never throws -- a malformed/missing arm
 * entry is skipped, not fatal to the rest of the roster (same per-item
 * fail-open convention every other reader in this codebase follows). */
export function activeSpyArms(accountsJson: unknown): FleetArmMeta[] {
  if (!accountsJson || typeof accountsJson !== "object") return [];
  const arms = (accountsJson as Record<string, unknown>).arms;
  if (!Array.isArray(arms)) return [];
  const out: FleetArmMeta[] = [];
  for (const raw of arms) {
    if (!raw || typeof raw !== "object") continue;
    const rec = raw as Record<string, unknown>;
    if (rec.status !== "active") continue;
    if (rec.instrument !== "SPY_0DTE_OPTION") continue;
    if (typeof rec.id !== "string") continue;
    out.push({
      id: rec.id,
      displayName: typeof rec.display_name === "string" ? rec.display_name : null,
    });
  }
  return out;
}

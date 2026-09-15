// HQ-TRADE-MOMENTS (2026-09-15): thin fs adapter around
// lib/hq-fleet-arms-pure.ts -- reads automation/state/fleet/accounts.json
// and hands its already-parsed JSON to the pure filter. Same pure/adapter
// split every other hq-*-pure.ts module in this directory documents.

import fs from "node:fs/promises";
import { paths } from "./workspace";
import { activeSpyArms, type FleetArmMeta } from "./hq-fleet-arms-pure";

// The two production control arms this dashboard has always known about --
// used ONLY as a fail-open floor if accounts.json itself can't be read, so
// a corrupt/missing registry file degrades HQ back to its pre-existing
// safe-2/bold-2 behavior rather than blanking the position/trade-moment
// surfaces entirely. Never used when the real read succeeds.
const FAIL_OPEN_FLOOR: FleetArmMeta[] = [
  { id: "safe-2", displayName: "CORE-SAFE (46VG)" },
  { id: "bold-2", displayName: "CORE-BOLD (U67N)" },
];

/** Every arm accounts.json currently marks `status:"active"` +
 * `instrument:"SPY_0DTE_OPTION"` -- read fresh (no caching) so a grid
 * change (an arm retired/added) shows up on the next poll without a
 * restart. Fails open to FAIL_OPEN_FLOOR + an explicit error string on any
 * read/parse failure, never an empty roster (which would silently drop
 * every arm's position/P&L data from HQ). */
export async function readActiveFleetArms(): Promise<{ arms: FleetArmMeta[]; error: string | null }> {
  let text: string;
  try {
    text = await fs.readFile(paths.fleetAccounts, "utf-8");
  } catch (e: unknown) {
    const code = (e as NodeJS.ErrnoException)?.code;
    return {
      arms: FAIL_OPEN_FLOOR,
      error: code === "ENOENT" ? `fleet accounts.json not found: ${paths.fleetAccounts}` : `fleet accounts.json read failed: ${String(e)}`,
    };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e: unknown) {
    return { arms: FAIL_OPEN_FLOOR, error: `fleet accounts.json parse failed: ${String(e)}` };
  }
  const arms = activeSpyArms(parsed);
  if (arms.length === 0) return { arms: FAIL_OPEN_FLOOR, error: "fleet accounts.json parsed but yielded zero active SPY_0DTE_OPTION arms" };
  return { arms, error: null };
}

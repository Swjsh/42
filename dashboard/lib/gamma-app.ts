// Top-level aggregator for the Gamma App: gathers the presence header (via the
// gamma_hq.py --json bridge), the live activity feed, the wants cards, and the
// this-week plan card, all in parallel. Every piece is independently
// fail-open (see each module) so one bad source degrades only its own
// section -- consumed by app/api/gamma/route.ts.

import { fetchPresenceView } from "./gamma-hq-bridge";
import { gatherActivityFeed } from "./activity-feed";
import { readWants } from "./wants";
import { readThisWeek } from "./this-week";
import { getFleetPnl } from "./fleet-pnl";
import type { GammaAppView } from "./gamma-app-types";

export async function buildGammaAppView(): Promise<GammaAppView> {
  const [presence, activity, wants, thisWeek, fleetPnl] = await Promise.all([
    fetchPresenceView(),
    gatherActivityFeed(10),
    readWants(4),
    readThisWeek(3),
    getFleetPnl(),
  ]);

  return {
    fetchedAt: new Date().toISOString(),
    presence,
    activity,
    wants,
    thisWeek,
    fleetPnl,
  };
}

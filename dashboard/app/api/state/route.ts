import { NextResponse } from "next/server";
import { paths } from "@/lib/workspace";
import {
  readJson,
  readJsonlTail,
  type LoopState,
  type KeyLevelsFile,
  type TodayBias,
  type CircuitBreaker,
  type DialogueFile,
  type KitchenStatus,
  type DecisionTick,
} from "@/lib/state";
import { todayET } from "@/lib/time";
import { countTradesToday } from "@/lib/journal";
import { readHqPositions } from "@/lib/hq-positions";
import { toLegacyCurrentPosition } from "@/lib/hq-positions-pure";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const today = todayET();

  const [
    loopState,
    loopStateBold,
    todayBias,
    keyLevels,
    positions,
    circuitBreaker,
    circuitBreakerBold,
    kitchenStatus,
    dialogue,
    ticksSafe,
    ticksBold,
    tradesToday,
  ] = await Promise.all([
    readJson<LoopState>(paths.loopState),
    readJson<LoopState>(paths.loopStateBold),
    readJson<TodayBias>(paths.todayBias),
    readJson<KeyLevelsFile>(paths.keyLevels),
    // HQ-POSITION-TRUTH (2026-09-15): repointed off the dead
    // current-position-{safe,bold}.json pair (nothing writes them -- see
    // lib/hq-positions.ts's header) onto the LIVE exit-state.json truth,
    // adapted to this route's existing CurrentPosition shape so this
    // floor's "/" dashboard stops lying FLAT during a real open position
    // too, not just /hq.
    readHqPositions(),
    readJson<CircuitBreaker>(paths.circuitBreaker),
    readJson<CircuitBreaker>(paths.circuitBreakerBold),
    readJson<KitchenStatus>(paths.kitchenStatus),
    readJson<DialogueFile>(paths.dialogue),
    readJsonlTail(paths.decisionsJsonl, 20),
    readJsonlTail(paths.decisionsJsonlBold, 20),
    countTradesToday(today),
  ]);
  const positionSafe = toLegacyCurrentPosition(positions["safe-2"]);
  const positionBold = toLegacyCurrentPosition(positions["bold-2"]);

  // Merge ticks from both accounts, filter to today, sort by time, keep last 12
  const allTicks: DecisionTick[] = [
    ...ticksSafe.map((t) => ({ ...t, account_id: "safe" as const })),
    ...ticksBold.map((t) => ({ ...t, account_id: "bold" as const })),
  ]
    .filter((t) => t.date === today)
    .sort((a, b) => a.time_et.localeCompare(b.time_et))
    .slice(-12);

  return NextResponse.json(
    {
      fetched_at: new Date().toISOString(),
      today,
      loopState,
      loopStateBold,
      todayBias,
      keyLevels,
      positionSafe,
      positionBold,
      circuitBreaker,
      circuitBreakerBold,
      kitchenStatus,
      dialogue,
      recentTicks: allTicks,
      tradesToday,
    },
    {
      headers: { "Cache-Control": "no-store, max-age=0" },
    },
  );
}

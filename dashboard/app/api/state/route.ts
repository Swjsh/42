import { NextResponse } from "next/server";
import { paths } from "@/lib/workspace";
import {
  readJson,
  readJsonlTail,
  type LoopState,
  type KeyLevelsFile,
  type TodayBias,
  type CurrentPosition,
  type CircuitBreaker,
  type DialogueFile,
  type KitchenStatus,
  type DecisionTick,
} from "@/lib/state";
import { todayET } from "@/lib/time";
import { countTradesToday } from "@/lib/journal";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const today = todayET();

  const [
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
    ticksSafe,
    ticksBold,
    tradesToday,
  ] = await Promise.all([
    readJson<LoopState>(paths.loopState),
    readJson<LoopState>(paths.loopStateBold),
    readJson<TodayBias>(paths.todayBias),
    readJson<KeyLevelsFile>(paths.keyLevels),
    readJson<CurrentPosition>(paths.positionSafe),
    readJson<CurrentPosition>(paths.positionBold),
    readJson<CircuitBreaker>(paths.circuitBreaker),
    readJson<CircuitBreaker>(paths.circuitBreakerBold),
    readJson<KitchenStatus>(paths.kitchenStatus),
    readJson<DialogueFile>(paths.dialogue),
    readJsonlTail(paths.decisionsJsonl, 20),
    readJsonlTail(paths.decisionsJsonlBold, 20),
    countTradesToday(today),
  ]);

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

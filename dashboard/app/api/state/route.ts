import { NextResponse } from "next/server";
import { paths } from "@/lib/workspace";
import {
  readJson,
  type LoopState,
  type KeyLevelsFile,
  type TodayBias,
  type CurrentPosition,
  type CircuitBreaker,
  type ModeFile,
  type DialogueFile,
} from "@/lib/state";
import { todayET } from "@/lib/time";
import { parseJournalToday, countTradesToday } from "@/lib/journal";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export async function GET() {
  const today = todayET();
  const [
    loopState,
    todayBias,
    keyLevels,
    currentPosition,
    circuitBreaker,
    mode,
    dialogue,
    journal,
    tradesToday,
  ] = await Promise.all([
    readJson<LoopState>(paths.loopState),
    readJson<TodayBias>(paths.todayBias),
    readJson<KeyLevelsFile>(paths.keyLevels),
    readJson<CurrentPosition>(paths.currentPosition),
    readJson<CircuitBreaker>(paths.circuitBreaker),
    readJson<ModeFile>(paths.mode),
    readJson<DialogueFile>(paths.dialogue),
    parseJournalToday(today),
    countTradesToday(today),
  ]);

  return NextResponse.json(
    {
      fetched_at: new Date().toISOString(),
      today,
      loopState,
      todayBias,
      keyLevels,
      currentPosition,
      circuitBreaker,
      mode,
      dialogue,
      journal,
      tradesToday,
    },
    {
      headers: { "Cache-Control": "no-store, max-age=0" },
    },
  );
}

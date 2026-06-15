export interface HeartbeatLine {
  tick: number;
  time_et: string;
  action: string;
  spy: number | null;
  ribbon_spread_cents: number | null;
  ribbon_stack: string | null;
  vix: number | null;
  vix_dir: string | null;
  bear_score: number | null;
  bull_score: number | null;
  reason: string;
  raw: string;
}

export function parseScoresFromSpeech(
  speech: string | null | undefined,
): { bull: number | null; bear: number | null } {
  if (!speech) return { bull: null, bear: null };
  const bull = speech.match(/bull\s+(\d+)\/11/i);
  const bear = speech.match(/bear\s+(\d+)\/10/i);
  return {
    bull: bull ? Number(bull[1]) : null,
    bear: bear ? Number(bear[1]) : null,
  };
}

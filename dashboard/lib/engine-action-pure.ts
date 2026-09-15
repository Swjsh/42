// MARKET-TRUTH (2026-09-15): pure mapping of setup/scripts/heartbeat_core.py's
// per-tick `action` ledger code (core-decisions.jsonl's "action" field, set
// throughout the post-verdict ladder in that module's run_account(), roughly
// L1857-1965) to a short human sentence HQ can render next to the engine's
// bar price. Codes below are read off that file's own logged strings, not
// guessed -- see each comment for the exact source line at the time this was
// written.
//
// Zero fs/path/workspace imports (same "no extensionless import chain" split
// lib/hq-chart-pure.ts documents) so this is directly `node --test`-able
// without a bundler. lib/hq.ts imports this for the real /api/hq payload;
// dashboard/tests/engine-action.test.ts imports it directly for unit tests.

/** Every `action` string heartbeat_core.py's ledger has logged as of
 * 2026-09-15 (grepped verbatim out of setup/scripts/heartbeat_core.py) --
 * codes NOT in this table (a future addition, or a raw verdict passthrough
 * like "ENTER_BEAR"/"HOLD" the `else: rec["action"] = v` branch, L1964-1965,
 * emits verbatim) fall through describeEngineAction's default branch below
 * rather than throwing or guessing. */
const ACTION_REASONS: Record<string, string> = {
  // L1857-1858: the trigger bar is a carried-over PRIOR-SESSION bar (today's
  // first fresh 5m bar hasn't closed yet, or the feed is behind) -- always
  // wins over any other branch, so this is what an early-morning tick shows.
  SKIP_STALE_TRIGGER: "waiting for a fresh trigger bar (today's bar hasn't closed yet)",
  // L1897-1906: no key levels loaded AND the entry has no price anchor --
  // the engine is refusing a trendline-only entry because it cannot see.
  SKIP_NO_LEVELS: "blind: no key levels loaded, entry had no price anchor -- refused",
  // L1917: past the entry-ceiling wall-clock time (too late in the day).
  SKIP_LATE_ENTRY: "past today's entry-ceiling time -- too late to enter",
  // L1921-1922: before the entry-floor wall-clock time (09:35 ET default).
  SKIP_EARLY_ENTRY: "before the entry-floor time (09:35 ET) -- too early to enter",
  // L1934: the trigger bar's close diverges too far from a fresh live quote.
  SKIP_STALE_SIGHT: "trigger bar has drifted too far from the live tape -- stale sight",
  // L1944: both free-model lanes voted no-go on an otherwise-valid entry.
  VETOED_BY_MODELS: "entry vetoed by the free-model sanity check",
  // L1950: perception-only mode -- verdict logged, the fleet executor (not
  // this account's own core tick) owns placement.
  PERCEPTION_ONLY: "verdict logged -- fleet executor places orders, not this tick",
  // L1965 (else branch): no ENTER_* verdict fired this tick -- routine hold.
  HOLD: "no entry trigger fired -- holding",
};

/** Order-side verdicts (raw verdict passthrough, L1964-1965) get their own
 * phrasing rather than falling into the generic default. */
const VERDICT_PREFIXES: Array<[RegExp, string]> = [
  [/^ENTER_BEAR$/, "bear trigger fired -- entry in progress"],
  [/^ENTER_BULL$/, "bull trigger fired -- entry in progress"],
];

/** Human-readable one-line reason for a core-decisions.jsonl `action` code.
 * Never throws; an unmapped/null code degrades to a short honest fallback
 * that still shows the raw code (never fabricates a meaning for a code this
 * table hasn't verified against the source file). */
export function describeEngineAction(action: string | null | undefined): string {
  if (!action) return "no action logged yet";
  const known = ACTION_REASONS[action];
  if (known) return known;
  for (const [re, phrase] of VERDICT_PREFIXES) {
    if (re.test(action)) return phrase;
  }
  // An exec status (e.g. a fill/reject status string from _execute, L1954)
  // or any other unmapped code -- shown verbatim rather than guessed.
  return `engine action: ${action}`;
}

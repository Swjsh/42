// @ts-nocheck -- same reason as tests/hq-runtime.test.ts's own header: this
// file uses explicit ".ts" extensions on its relative imports (required for
// plain `node --test` to resolve them; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`, which
// would otherwise fail `next build`'s project-wide type-check over this one
// file). Purely a syntax-erasure pragma -- has no effect on what actually
// runs.
//
// PANEL-3 (2026-09-14): unit tests for lib/hq-learn.ts's PURE functions --
// the fs readers (readHqLearn) are exercised live instead, via a real
// `curl /api/hq` proof against the running dashboard (see this task's own
// build-proof step), matching this codebase's established convention (see
// tests/hq-runtime.test.ts's own header for the precedent this follows).
//
// Run: cd dashboard && node --test tests/hq-learn.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  todayEtDateStr,
  hhmmFromTsEt,
  hhmmEtFromEpoch,
  isTodayEt,
  truncateOneLine,
  stripWhoPrefix,
  latestVerdictsForDay,
  verdictChangedText,
  hqReviewChangedText,
  buildAutopsyRow,
  tallyVerdictsToday,
  buildHqLearn,
  type StationVerdictRow,
  type AutopsyRow,
  type IdeasBoardCardMinimal,
} from "../lib/hq-learn.ts";

// 2026-09-14T22:21:00.000Z == 18:21 ET (EDT, UTC-4) -- same fixed instant
// tests/hq-runtime.test.ts's own NOW constant uses, reused here for the same
// reason (a real, verifiable EDT conversion, not an arbitrary pick).
const NOW = Date.parse("2026-09-14T22:21:00.000Z");

// ─── todayEtDateStr / hhmmFromTsEt / hhmmEtFromEpoch / isTodayEt ───────────

test("todayEtDateStr converts a UTC instant to its ET calendar date", () => {
  assert.equal(todayEtDateStr(NOW), "2026-09-14");
});

test("todayEtDateStr crosses midnight correctly near the UTC/ET boundary", () => {
  // 2026-09-15T02:30:00Z == 2026-09-14 22:30 EDT -- still the 14th in ET,
  // even though the UTC calendar date has already rolled to the 15th.
  const lateNight = Date.parse("2026-09-15T02:30:00.000Z");
  assert.equal(todayEtDateStr(lateNight), "2026-09-14");
});

test("hhmmFromTsEt extracts HH:MM from the real 'YYYY-MM-DD HH:MM:SS ET' shape", () => {
  assert.equal(hhmmFromTsEt("2026-09-14 19:21:01 ET"), "19:21");
});

test("hhmmFromTsEt returns null for an unparseable string, never a guess", () => {
  assert.equal(hhmmFromTsEt("not a timestamp"), null);
  assert.equal(hhmmFromTsEt(""), null);
});

test("hhmmEtFromEpoch matches the known EDT offset for this fixed instant", () => {
  assert.equal(hhmmEtFromEpoch(NOW), "18:21");
});

test("isTodayEt matches only rows whose ts_et starts with the given ET day", () => {
  assert.equal(isTodayEt("2026-09-14 19:21:01 ET", "2026-09-14"), true);
  assert.equal(isTodayEt("2026-09-13 19:21:01 ET", "2026-09-14"), false);
  assert.equal(isTodayEt(null, "2026-09-14"), false);
  assert.equal(isTodayEt(undefined, "2026-09-14"), false);
});

// ─── truncateOneLine / stripWhoPrefix ──────────────────────────────────────

test("truncateOneLine leaves short strings untouched", () => {
  assert.equal(truncateOneLine("short", 70), "short");
});

test("truncateOneLine truncates with an ellipsis at the given length", () => {
  const s = "a".repeat(100);
  const out = truncateOneLine(s, 10);
  assert.equal(out.length, 10);
  assert.ok(out.endsWith("…"));
});

test("stripWhoPrefix removes a leading 'Who: ' prefix", () => {
  assert.equal(stripWhoPrefix("Coach: risky-1 last 5 sessions", "Coach"), "risky-1 last 5 sessions");
});

test("stripWhoPrefix leaves text with no matching prefix untouched", () => {
  assert.equal(stripWhoPrefix("no prefix here", "Coach"), "no prefix here");
});

// ─── latestVerdictsForDay ───────────────────────────────────────────────────

function verdictRow(overrides: Partial<StationVerdictRow> = {}): StationVerdictRow {
  return {
    ts_et: "2026-09-14 17:51:01 ET",
    card_id: "f5deabe978",
    spec: { type: "size_cap", params: { cap: 3 } },
    result: { n_pre: 148, n_post: 3, effect_pre: 1236.6, effect_post: -4.0, verdict: "pending", detail: "n_post=3 < min_n=10" },
    ...overrides,
  };
}

test("latestVerdictsForDay collapses repeated same-day scoring passes into one row, counting them", () => {
  const rows = [
    verdictRow({ ts_et: "2026-09-14 17:51:01 ET" }),
    verdictRow({ ts_et: "2026-09-14 18:21:01 ET" }),
    verdictRow({ ts_et: "2026-09-14 18:51:01 ET", result: { n_pre: 148, n_post: 4, effect_pre: 1236.6, effect_post: -3.0, verdict: "pending", detail: "n_post=4 < min_n=10" } }),
  ];
  const out = latestVerdictsForDay(rows, "2026-09-14");
  assert.equal(out.length, 1);
  assert.equal(out[0].scoresToday, 3);
  assert.equal(out[0].row.result.n_post, 4); // the LATEST pass, not the first
});

test("latestVerdictsForDay excludes rows from a different ET day", () => {
  const rows = [verdictRow({ ts_et: "2026-09-13 17:51:01 ET" })];
  assert.deepEqual(latestVerdictsForDay(rows, "2026-09-14"), []);
});

test("latestVerdictsForDay tracks multiple distinct cards independently", () => {
  const rows = [
    verdictRow({ card_id: "aaa" }),
    verdictRow({ card_id: "bbb", ts_et: "2026-09-14 18:00:00 ET" }),
  ];
  const out = latestVerdictsForDay(rows, "2026-09-14");
  assert.equal(out.length, 2);
  assert.deepEqual(new Set(out.map((o) => o.row.card_id)), new Set(["aaa", "bbb"]));
});

// ─── verdictChangedText (freeze-aware) ─────────────────────────────────────

test("verdictChangedText: pending reads as an honest non-event", () => {
  assert.equal(verdictChangedText("pending"), "nothing acted on this yet -- still pending");
});

test("verdictChangedText: supported names the freeze, never implies it shipped", () => {
  const text = verdictChangedText("supported");
  assert.match(text, /freeze/i);
  assert.match(text, /2026-10-30/);
});

test("verdictChangedText: refuted matches the task's own literal example shape", () => {
  assert.equal(verdictChangedText("refuted"), "card refuted, parked");
});

test("verdictChangedText: spec_error is called out distinctly, not folded into pending", () => {
  assert.match(verdictChangedText("spec_error"), /spec error/i);
});

// ─── hqReviewChangedText ────────────────────────────────────────────────────

test("hqReviewChangedText: all-empty stale/ghosts/desks_stale reads healthy", () => {
  const text = hqReviewChangedText({ score_0_100: 100, stale: [], ghosts: [], desks_stale: [] });
  assert.match(text, /no action needed/);
  assert.match(text, /100\/100/);
});

test("hqReviewChangedText: any stale/ghost entries flip to a flagged verdict with real counts", () => {
  const text = hqReviewChangedText({ score_0_100, stale: [{ name: "Gamma (Manager)" }], ghosts: [{ name: "Analyst" }], desks_stale: [] } as any);
  assert.match(text, /1 stale/);
  assert.match(text, /1 ghost/);
});

// (helper for the test above -- score_0_100 constant, avoids a magic number typo)
const score_0_100 = 71;

// ─── buildAutopsyRow ────────────────────────────────────────────────────────

function autopsyRow(overrides: Partial<AutopsyRow> = {}): AutopsyRow {
  return {
    date: "2026-09-14", arm: "safe-3", strategy: "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    symbol: "SPY260914C00763000", entry_ts_utc: "2026-09-14T18:01:06.578665Z",
    actual_pnl: 3.0, stop_cost_vs_best: -61.5, best_counterfactual: "wide_stop_-50",
    ...overrides,
  };
}

test("buildAutopsyRow returns null when there is nothing to report -- an honest empty, not a fabricated row", () => {
  assert.equal(buildAutopsyRow([], "2026-09-14"), null);
});

test("buildAutopsyRow combines multiple mirrored fills into ONE row with a real dollar range", () => {
  const rows = [
    autopsyRow({ arm: "safe-3", stop_cost_vs_best: -61.5 }),
    autopsyRow({ arm: "risky-1", stop_cost_vs_best: -102.5, entry_ts_utc: "2026-09-14T18:01:08.758988Z" }),
    autopsyRow({ arm: "risky-3", stop_cost_vs_best: -102.5, entry_ts_utc: "2026-09-14T18:01:10.906186Z" }),
  ];
  const row = buildAutopsyRow(rows, "2026-09-14");
  assert.ok(row);
  assert.equal(row!.who, "Autopsy");
  assert.match(row!.what, /3 fills/);
  assert.match(row!.what, /safe-3, risky-1, risky-3/);
  assert.match(row!.what, /\$61\.50-\$102\.50/);
  assert.match(row!.changed, /frozen to 2026-10-30/);
  assert.equal(row!.evidence, "analysis/autopsies/2026-09-14.jsonl (n=3)");
  // "when" is the LATEST real fill time (18:01:10Z == 14:01 EDT), not "now".
  assert.equal(row!.when, "14:01");
});

test("buildAutopsyRow uses a single dollar figure (no dash range) when every fill costs the same", () => {
  const rows = [autopsyRow({ stop_cost_vs_best: -50 })];
  const row = buildAutopsyRow(rows, "2026-09-14");
  assert.match(row!.what, /\$50\.00/);
  assert.ok(!row!.what.includes("-$50.00-$50.00"));
});

// ─── tallyVerdictsToday ─────────────────────────────────────────────────────

test("tallyVerdictsToday counts only the three tracked buckets, ignoring proposed/killed/shipped", () => {
  const cards: IdeasBoardCardMinimal[] = [
    { id: "1", status: "proposed", title: "a" },
    { id: "2", status: "testing", title: "b" },
    { id: "3", status: "supported", title: "c" },
    { id: "4", status: "refuted", title: "d" },
    { id: "5", status: "refuted", title: "e" },
    { id: "6", status: "killed", title: "f" },
  ];
  assert.deepEqual(tallyVerdictsToday(cards), { supported: 1, refuted: 2, testing: 1 });
});

test("tallyVerdictsToday returns real zeros on an empty board, never fabricated counts", () => {
  assert.deepEqual(tallyVerdictsToday([]), { supported: 0, refuted: 0, testing: 0 });
});

// ─── buildHqLearn (the full pure combiner) ─────────────────────────────────

test("buildHqLearn on all-empty inputs is an honest empty tab", () => {
  const out = buildHqLearn({
    dayEt: "2026-09-14", verdictRows: [], ideasCards: [], coachNotes: null,
    hqReview: null, autopsyRows: [], settled: [],
  });
  assert.deepEqual(out.learned, []);
  assert.equal(out.lastLearnedAtEt, null);
  assert.equal(out.settledMechanisms, 0);
  assert.deepEqual(out.verdictsToday, { supported: 0, refuted: 0, testing: 0 });
});

test("buildHqLearn sorts rows newest-first across all sources and sets lastLearnedAtEt to the newest", () => {
  const out = buildHqLearn({
    dayEt: "2026-09-14",
    verdictRows: [verdictRow({ ts_et: "2026-09-14 09:00:00 ET" })],
    ideasCards: [{ id: "f5deabe978", status: "testing", title: "Cap entry size" }],
    coachNotes: { ts_et: "2026-09-14 17:12:52 ET", notes: [{ lane: "risky-1", stat: "counterfactual", line: "Coach: risky-1 net -$460.00", delta: 415.0 }] },
    hqReview: { ts_et: "2026-09-14 20:00:00 ET", score_0_100: 100, stale: [], ghosts: [], desks_stale: [], lines: ["7/7 crew live"] },
    autopsyRows: [],
    settled: [],
  });
  assert.equal(out.learned.length, 3);
  assert.equal(out.learned[0].who, "Coach"); // hq-review, 20:00, newest
  assert.equal(out.learned[0].what, "HQ self-review -- 7/7 crew live");
  assert.equal(out.learned[1].what, "risky-1 net -$460.00"); // "Coach: " prefix stripped
  assert.match(out.learned[1].changed, /ranked #1/);
  assert.match(out.learned[1].changed, /\$415/);
  assert.equal(out.learned[2].who, "Chef"); // verdict, 09:00, oldest
  assert.equal(out.lastLearnedAtEt, "20:00");
});

test("buildHqLearn attaches a real card title from the ideas board, falling back to the card_id when unmatched", () => {
  const withTitle = buildHqLearn({
    dayEt: "2026-09-14", verdictRows: [verdictRow()],
    ideasCards: [{ id: "f5deabe978", status: "testing", title: "Cap entry size at 3 shares" }],
    coachNotes: null, hqReview: null, autopsyRows: [], settled: [],
  });
  assert.match(withTitle.learned[0].what, /Cap entry size at 3 shares/);

  const withoutTitle = buildHqLearn({
    dayEt: "2026-09-14", verdictRows: [verdictRow()], ideasCards: [],
    coachNotes: null, hqReview: null, autopsyRows: [], settled: [],
  });
  assert.match(withoutTitle.learned[0].what, /f5deabe978/);
});

test("buildHqLearn ignores a coaching/hq-review doc that is stale (not from today)", () => {
  const out = buildHqLearn({
    dayEt: "2026-09-14", verdictRows: [], ideasCards: [],
    coachNotes: { ts_et: "2026-09-10 17:12:52 ET", notes: [{ lane: "x", stat: "y", line: "old note", delta: 1 }] },
    hqReview: { ts_et: "2026-09-11 20:00:00 ET", score_0_100: 50, stale: [], ghosts: [], desks_stale: [], lines: [] },
    autopsyRows: [], settled: [],
  });
  assert.deepEqual(out.learned, []);
});

test("buildHqLearn emits a settled-mechanism row only when settled_on matches today, and always reports the real total", () => {
  const out = buildHqLearn({
    dayEt: "2026-09-14", verdictRows: [], ideasCards: [], coachNotes: null, hqReview: null, autopsyRows: [],
    settled: [
      { mechanism: "stop_inside_noise_floor", settled_on: "2026-08-06", verdict: "REGIME_CONDITIONAL_NOT_SHIPPABLE" },
      { mechanism: "todays_mechanism", settled_on: "2026-09-14", verdict: "REFUTED" },
    ],
  });
  assert.equal(out.settledMechanisms, 2); // total, regardless of when each settled
  assert.equal(out.learned.length, 1); // only the row settled TODAY gets a timeline entry
  assert.equal(out.learned[0].who, "Gamma");
  assert.match(out.learned[0].what, /todays_mechanism/);
});

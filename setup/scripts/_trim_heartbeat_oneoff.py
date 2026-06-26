"""One-off: trim reference prose out of automation/prompts/heartbeat.md.

Each region is sliced by UNIQUE ASCII start/end markers and replaced with a lean
pointer to markdown/0dte/heartbeat-provenance.md. Every replacement asserts its
markers exist exactly as expected; ANY mismatch aborts with NO write (the live
prompt is never left half-edited). Executable rubric (filters, gates, exit
hierarchy, decisions/state-write schema, output format) is preserved verbatim;
only history / evidence / scorecard-citation / validation-blockquote prose moves.
"""
import sys

PATH = "automation/prompts/heartbeat.md"
src = open(PATH, encoding="utf-8").read()
orig_len = len(src)

# (name, start_marker, end_marker, replacement). The slice [start_of(start) :
# start_of(end)) is replaced. end_marker is the next line to KEEP.
REGIONS = [
    # --- v15 / v15.1 ratification history -> provenance pointer ---------------
    ("v15_history",
     "# v15 ratification (LIVE 2026-05-13 evening)",
     "# Shadow-mode (Karpathy method, NEW 2026-05-09)",
     "# Rule provenance (read the NUMBERS from params.json)\n\n"
     "This prompt states the decision LOGIC; **every rule VALUE — stops, TP1, VIX "
     "thresholds, sizing tiers, every gate param — is read from "
     "`automation/state/params.json` at tick time.** Full ratification history "
     "(v15 strike-per-tier + 09:35 entry gate + trailing-chandelier profit-lock + "
     "per-tier max-premium gate; v15.1 continuous 09:35-15:00 entry window + R1 "
     "closed-bar fix; v15.3 ribbon-conviction gate + chart-stop-primary), per-change "
     "A/B evidence, and revert paths: **`markdown/0dte/heartbeat-provenance.md`** + "
     "`CHANGELOG.md`. v14 backup: `automation/prompts/heartbeat-v14-prod-backup.md`.\n\n"),

    # --- shadow-mode -> condensed (operational steps preserved) ---------------
    ("shadow_mode",
     "# Shadow-mode (Karpathy method, NEW 2026-05-09)",
     "# Step 0 — pre-flight (harness contract)",
     "# Shadow-mode (Karpathy method)\n\n"
     "Read `automation/state/shadow-version.json` once/tick. Missing OR "
     "`enabled:false` → no shadow logging. If `enabled:true` (file carries a "
     "candidate param overlay): compute bear/bull scores TWICE — production params "
     "(drives the real action) and the candidate overlay (read-only). Production "
     "action is NEVER affected. Append the shadow row(s) to "
     "`automation/state/decisions.jsonl` with a `version` field "
     "(`\"v14\"` / `\"<shadow_version>\"`), the shadow row using "
     "`would_have_action` instead of `action`; if the tick is identical between "
     "production and shadow, emit ONE row with `version:\"both\"`. EOD-summary 8c "
     "diffs the version logs. Cost ~$0.05/day.\n\n"),

    # --- numeric alert -> condensed (behavior + banned list preserved) --------
    ("numeric_alert",
     "## Step 0a — Numeric alert context (v15.2, RATIFIED 2026-05-18 evening)",
     "## Step 0b — Safe MCP self-test (SAFE account only)",
     "## Step 0a — Numeric alert context (v15.2)\n\n"
     "Read `automation/state/numeric-alert.jsonl`; filter to rows whose "
     "`fire_at_utc` is within the last 60 s. If any present, the most recent is "
     "this tick's NUMERIC ALERT CONTEXT (the L2 `numeric_pulse` pipeline's "
     "ground-truth corroboration — see `markdown/0dte/heartbeat-provenance.md`).\n"
     "- **On alert:** note pattern+bias+key_price as ATTENTION; STILL apply ALL 11 "
     "filters (alert is corroboration, NOT a trigger override); append "
     "` numeric_alert={pattern}/{bias}` to the one-line output; set "
     "`numeric_alert_consumed: true` in the decisions.jsonl row.\n"
     "- **No alert:** standard tick, no change.\n"
     "- **Banned:** skipping filter evaluation because an alert fired; entering a "
     "trade you would not have entered without it; modifying `numeric-alert.jsonl` "
     "(append-only by numeric_pulse).\n\n"),

    # --- BTC cross-signal -> condensed (hard constraints preserved) -----------
    ("btc_cross",
     "## Step 0c — BTC cross-signal (SOFT-ADOPT 2026-06-16, FORENSIC ONLY — zero gate authority)",
     "# Output — ONE LINE ONLY",
     "## Step 0c — BTC cross-signal (FORENSIC ONLY — zero gate authority)\n\n"
     "Read the last line of `automation/state/crypto/ribbon-log.jsonl`. Missing/"
     "empty OR `now_utc - row.time > 20 min` (stale) → `btc_ribbon = null`; else "
     "`btc_ribbon = row.ribbon` (`\"BULL\"`|`\"BEAR\"`). **Hard constraints (no "
     "exceptions):** NEVER block an entry, NEVER boost scores, NEVER change the "
     "action, NEVER appear in the gate sequence. Append `btc={btc_ribbon}` to the "
     "one-line output; add `\"btc_ribbon\": ...` to the decisions.jsonl row. "
     "Promotion criteria: `markdown/0dte/heartbeat-provenance.md`.\n\n"),

    # --- flag-gated setup validation blockquotes -> 1-line pointers -----------
    ("gap_and_go_bq",
     "> Once-per-day opening-gap continuation.",
     "Read `params.json#gap_and_go_enabled`",
     "> Default-OFF / inert. Validation, detector, wiring: `markdown/0dte/heartbeat-provenance.md`.\n\n"),
    ("vwap_cont_bq",
     "> J's near-daily VWAP-aligned MORNING CONTINUATION edge",
     "Read `params.json#j_vwap_cont_enabled`",
     "> Default-OFF / inert. Validation, detector, wiring: `markdown/0dte/heartbeat-provenance.md`.\n\n"),
    ("vwap_reclaim_bq",
     "> The SUBTRACTIVE/STRUCTURAL sibling of VWAP_CONTINUATION",
     "Read `params.json#j_vwap_reclaim_fb_enabled`",
     "> Default-OFF / inert. Validation, detector, wiring: `markdown/0dte/heartbeat-provenance.md`.\n\n"),
    ("vix_dayside_bq",
     "> The VIX-regime-conditional DAY+SIDE directional system",
     "Read `params.json#j_vix_dayside_enabled`",
     "> Default-OFF / inert. Validation, detector, wiring: `markdown/0dte/heartbeat-provenance.md`.\n\n"),

    # --- ribbon conviction gate evidence blockquote -> pointer ---------------
    ("ribbon_gate_evidence",
     "> Evidence: 16-month real-fills IS/OOS",
     "After ALL BEARISH (filters 1-10) or BULLISH (filters 1-11) pass",
     "> Evidence + scorecard: `markdown/0dte/heartbeat-provenance.md` (v15.3 ribbon "
     "gate). Params: `min_ribbon_momentum_cents`, `max_ribbon_duration_bars`, "
     "`midday_trendline_gate`.\n\n"),

    # --- watcher-layer explanatory blockquote -> pointer ----------------------
    ("watcher_intro_bq",
     "> **Status 2026-06-18: replaces the per-watcher ORB + FBW branches.**",
     "**Only run when:** THIS account's position is flat",
     "> **WATCH-ONLY — NEVER places an order** (OP-21 live gate stands; activating "
     "execution is a Rule-9 change). Generalises the ORB+FBW pattern across the whole "
     "`Gamma_WatcherLive` fleet (registry `backtest/lib/watchers/runner.py#WATCHERS` "
     "is the single source of truth) and logs `WATCH_ONLY` rows so the ledger sees "
     "every watcher. Cost ~0. Design notes + revert: `markdown/0dte/heartbeat-provenance.md`.\n\n"),
]


def slice_replace(text: str, name: str, start_m: str, end_m: str, repl: str) -> str:
    sc = text.count(start_m)
    ec = text.count(end_m)
    if sc != 1:
        sys.exit(f"ABORT [{name}]: start marker count={sc} (expected 1): {start_m!r}")
    if ec < 1:
        sys.exit(f"ABORT [{name}]: end marker not found: {end_m!r}")
    si = text.index(start_m)
    ei = text.index(end_m, si + len(start_m))
    if ei <= si:
        sys.exit(f"ABORT [{name}]: end marker precedes start")
    return text[:si] + repl + text[ei:]


for name, start_m, end_m, repl in REGIONS:
    before = len(src)
    src = slice_replace(src, name, start_m, end_m, repl)
    print(f"  {name:22s} -{before - len(src):>6d} bytes")

with open(PATH, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(src)

print(f"\nheartbeat.md: {orig_len} -> {len(src)} bytes "
      f"(-{orig_len - len(src)}, {100*(orig_len-len(src))/orig_len:.1f}%)")

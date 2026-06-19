# GEX → Premarket Wiring (propose-only)

> **Status: PROPOSE-ONLY (Rule 9). NOT applied to the live `premarket.md`.** This doc is the exact, copy-pasteable edit that connects the now-live daily GEX capture to an actual decision input. Apply only after the apply-gate below is met (a few days of the tag banking + a sanity check), by J or the conductor.
>
> Authored 2026-06-19 (weekend loop). Closes a partial-visibility gap: `automation/scripts/gex_capture.py` writes `automation/state/gex-regime.json` every morning, but **nothing consumes it** — a producer with no consumer. This wires the consumer (premarket → today-bias → heartbeat/regime_book).

---

## 1. What this wires, and why it's safe

| Piece | State | Role |
|---|---|---|
| `gex_capture.py` (`Gamma_GexCapture`) | **LIVE, banking daily** | Producer: writes `gex-regime.json` (regime label, walls, net-GEX sign, zero-gamma flip) |
| `lib/engine/gex_regime.py` | built, tested | Pure GEX math (reused by the capture job) |
| `lib/engine/regime_book.py#classify_regime` | built, **WATCH_ONLY** | Consumer interface: **already accepts an optional `gex_hint`** (reinforce-only corroborator) |
| **premarket.md** | **NOT wired (this doc)** | The missing link: read the tag, carry it into `today-bias.json` |

The consumer interface already exists and is conservative by design: `_apply_gex_corroboration` only nudges a **NEUTRAL** base read and can **never flip** a directional one. GEX is strictly *additive regime context*, never a trigger and never an override of the chart/VIX read. That is why this is low-risk to wire.

## 2. The GEX → trading-context mapping (the rationale)

Dealer gamma positioning is the one peer-reviewed regime signal the weekend research flagged as worth wiring (CONTEXT-112). The sign tells you how dealer hedging interacts with price:

| `gex-regime.json` regime | Dealer behavior | Trading context | Effect in `classify_regime` |
|---|---|---|---|
| `short_gamma_trend` (net GEX < 0) | Hedging **amplifies** moves (sell lower / buy higher) | **Trend / continuation-friendly** — Gamma's confirmed BEARISH_REJECTION + pullback/continuation edge regime | `+` high VIX → reinforces `high_vol` |
| `long_gamma_pin` (net GEX > 0) | Hedging **dampens** moves (buy lower / sell higher) → pins toward walls | **Mean-revert / pin** — directional 0DTE continuation should **size down / abstain**; respect the call/put walls as magnets | `+` low VIX → nudges NEUTRAL → `range_pin` |
| `flat` / `null` / stale | indeterminate | no GEX adjustment | base read untouched |

The **walls** (`call_wall.strike`, `put_wall.strike`) are the strikes with the most dealer gamma — in a `long_gamma_pin` regime they act as intraday magnets/barriers; surface them as context levels alongside the chart levels.

## 3. The exact `premarket.md` edits (propose-only — do NOT apply yet)

### Edit 1 — add the tag to the Reads block (line ~13)

Change the header `# Reads (5 files only)` → `# Reads (6 files only)` and append:

```
6. `automation/state/gex-regime.json` — this morning's dealer-GEX regime tag (advisory; written by Gamma_GexCapture ~09:26 ET). Fail-open: missing/stale/`status != "ok"` ⇒ skip, never block.
```

### Edit 2 — new advisory intake step (insert after Step 3, mirroring the Step 1c swarm pattern)

```markdown
## Step 3c — GEX regime intake (NEW, advisory dealer-gamma context)

**Why this exists:** `Gamma_GexCapture` writes `automation/state/gex-regime.json` each morning from the live SPY option chain. The dealer-gamma sign is a regime corroborator (short-gamma ⇒ trend/continuation-friendly; long-gamma ⇒ pin/fade toward walls). Advisory only — it never overrides the chart/VIX read.

**Steps:**

1. Check `automation/state/gex-regime.json` exists AND `status == "ok"` AND `session_date == today` (else it is yesterday's stale tag). If not: log `GEX_CONTEXT_UNAVAILABLE` to the journal header and skip this step. Do NOT block — it is purely advisory (same posture as Step 1c).
2. Read and extract: `regime` (`short_gamma_trend`/`long_gamma_pin`/`flat`), `net_gex_sign`, `call_wall.strike`, `put_wall.strike`, `zero_gamma_flip`, `spot`.
3. Map to a one-line context note for the journal header:
   - `short_gamma_trend` → `GEX: short-gamma — trend/continuation regime; directional setups favored.`
   - `long_gamma_pin` → `GEX: long-gamma — pin/mean-revert regime; size down directional continuation, respect walls {put_wall}–{call_wall} as magnets.`
   - `flat`/missing → no note.
4. Carry the `gex_context` object (schema in Step 4) into `today-bias.json`. The heartbeat passes `gex_context.regime` to `regime_book.classify_regime(gex_hint=...)` as a reinforce-only corroborator.

**Cost:** ~$0 (pure file read; the chain pull is charged to Gamma_GexCapture).
```

### Edit 3 — add `gex_context` to the Step 4 today-bias.json field list (line ~231)

```
- `gex_context`: **populated from Step 3c** — `{ regime, net_gex_sign, call_wall, put_wall, zero_gamma_flip, spot, session_date, stale }`. Advisory dealer-gamma regime tag. `stale: true` (and `regime: null`) when Step 3c skipped (missing/stale/status!=ok). The heartbeat reads `gex_context.regime` as the `gex_hint` corroborator into `classify_regime`; a stale/null tag is simply ignored (the classifier never requires it).
```

## 4. The `today-bias.json#gex_context` schema

```json
{
  "regime": "short_gamma_trend",
  "net_gex_sign": "short",
  "call_wall": 750.0,
  "put_wall": 750.0,
  "zero_gamma_flip": null,
  "spot": 748.46,
  "session_date": "2026-06-19",
  "stale": false
}
```

When Step 3c is skipped, write `{ "regime": null, "stale": true }` (the heartbeat / `classify_regime` treats a null hint as "no corroboration").

## 5. Downstream consumption (already built — verified)

The heartbeat already constructs `RegimeSignals` for the regime read; this adds `gex_hint=today_bias.gex_context.regime`. The Python path (`signals_from_bar_context(ctx, gex_hint=...)`) and the engine_cli shadow read the same tag.

**Verified end-to-end on the live tag (2026-06-19), `classify_regime`:**
- Live `gex-regime.json` regime = `short_gamma_trend`, `status: ok` — **in the accepted vocab** ✓
- low-VIX MIXED base: no-hint → `neutral`; `+long_gamma_pin` → `range_pin` ✓ (the pin/fade regime fires)
- high-VIX MIXED base: `+short_gamma_trend` → `high_vol` ✓
- **reinforce-only invariant:** strong-BULL base `+long_gamma_pin` hint → stays `bull_trend` ✓ (a hint can never flip a directional read)

**Today this is additive context only** — `regime_book.select_setups()` returns `()` for every regime (the whole book is `WATCH_ONLY`), so wiring the hint changes *no trade*. It (a) gives J/the heartbeat live dealer-gamma situational awareness now, and (b) is ready the moment any setup is promoted to `REGIME_ACTIVE`.

## 6. Caveats + the apply-gate

- **Context, not a trigger.** Never sizes or fires a trade on its own; it nudges the regime read, which (once the book is live) routes *which* setups are eligible.
- **Cannot be backtested** — no historical full-chain OI/gamma archive (the daily capture is now accruing that; `assess_backtest_feasibility` tracks when a GEX backtest becomes possible).
- **Reinforce-only / fail-open** — never overrides the chart/VIX read; missing/stale tag is silently ignored. Matches the conservative design of the existing corroborator.
- **Apply-gate (before pasting these edits into the live prompt):** (1) ≥ ~5 trading days of `gex-regime.json` banked with `status: ok`; (2) eyeball that the regime labels line up with realized intraday character (short-gamma days trended, long-gamma days chopped/pinned) on those days; (3) apply after-hours, never mid-session (Rule 9). This is a CONTEXT add (not a validated edge change), so it stays propose-only until that sanity check passes — J or the conductor applies.

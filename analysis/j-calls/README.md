# J-Calls — anchor capture (G5, 2026-07-08)

J's live trade **calls** ("if we reject 750 enter puts", "certified scalp move") are the
source of truth (OP-16) — but until now they evaporated in chat/Discord instead of being
captured as structured anchors like the 7 immutable source-of-truth trades in CLAUDE.md.

`anchors.jsonl` is the standing capture corpus. Each J call is appended as one row via
`setup/scripts/j_call_capture.py::capture(call)` (validated; a malformed call raises rather
than silently corrupting the corpus). Entry thesis is captured at call time; `outcome`/`pnl`
are filled in after the trade resolves.

## Row schema

| field | type | notes |
|---|---|---|
| `call_id` | str | auto (`jc_<sha1[:10]>`) if omitted |
| `ts_et` | str | **required** — when J made the call (ET) |
| `source` | str | **required** — `discord` \| `chat` \| `manual` |
| `symbol` | str | **required** — e.g. `SPY` |
| `side` | str | **required** — `call` \| `put` \| `long` \| `short` |
| `thesis` | str | **required** — J's stated reasoning |
| `level` | float\|null | the price level J referenced |
| `strike` | float\|null | if an options call |
| `expiry` | str\|null | `0DTE` / ISO date |
| `outcome` | str\|null | `win` \| `loss` \| `flat` \| `open` — filled after resolve |
| `pnl` | float\|null | realized — filled after resolve |
| `tags` | list[str] | e.g. `["level_reject","midday","aligned"]` |
| `captured_at` | str | auto — UTC ISO |

## How it feeds the flywheel

DETECT (`level_memory.emit_reject_alert` pings J on a high-memory-level rejection) →
J makes a call → **CAPTURE** here → the anchor corpus grows → edge-capture scoring +
future validation run against real J calls, not just the 7 frozen anchors. When the corpus
reaches n≈30 the burned-OOS-window concern (audit R1) reopens on fresh J-labelled data.

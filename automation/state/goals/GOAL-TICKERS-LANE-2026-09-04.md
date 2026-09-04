# GOAL: TICKERS-LANE-2026-09-04

> J verbatim (2026-09-04 00:4x ET): *"wire this 4 new alpaca account for all non spy options trading
> ... Tickers-1 / Tickers-2 / Tickers-3 ... i want these 3 accounts trading non SPY options tomorrow
> just like how we trade spy 0dte, wire up the new engine to these, test it and lets trade tomorrow
> with these 3."* Then (00:5x ET): *"i dont care thats what paper accounts are for is to get them out
> there testing things. we have a goldmine of data, wire it all up so they trade. your /goal is they
> trade tomorrow and do our best to make money and its all wired up and documented properly. im going
> to bed so dont prompt me or stop if you hit blockers proceed and work around them. test everything
> thoroughly"*

## WHY THIS IS THE EXPERIMENT NOBODY RAN, NOT A REVIVAL
Every non-SPY test this shop has run scored a COPY of the engine (`multi/lib/filters.py`, 1,211
lines vs production's 2,342): weekly lane 684 real fills, multi lane 7,489 signals, catalysts 7,019
signals -- all ~49%. The production scorer (`backtest/lib/filters.py`) has never been run on any
name but SPY. This lane runs it unmodified, on the multi lane's audited plumbing, on three DEDICATED
paper accounts. Prereg frozen first: `analysis/recommendations/prereg-tickers-lane-production-scorer-2026-09-04.json`
(commit `5062ea52`, before the executor existed). multi-1's own kill rule ("a NEW signal and a NEW
pre-registration") is satisfied: different code, this prereg.

## DONE-WHEN
Falsifiable, each checked by a command or ledger row quoted in the PROGRESS LOG:
- (a) **Three accounts authenticate as paper and are pinned.** `python multi/tickers_verify.py`
  prints account_number / equity / options level for tickers-1/2/3 with 0 failures, and
  `automation/state/tickers/<arm>/account.json` exists for each.
- (b) **The lane ticks unattended.** `Gamma_TickersLane` State=Ready, fires 09:35 ET every 2 min
  to ~14:55 ET (LOCAL 07:35 -- this box is Mountain; `Gamma_MultiCore` was registered at local
  09:35 = 11:35 ET for its whole life, the 2h scar), and `Gamma_TickersEodFlatten` at 14:52 ET.
  Ledger rows appear under `automation/state/tickers/<arm>/ledger.jsonl` on the first session.
- (c) **It trades.** At least one paper FILL on at least one arm, recorded in
  `journal/trades-tickers-<arm>.csv` with the broker order id, and the FIRST-FILL line on
  `STATUS.md ## Known broken` (the REVOKE surface).
- (d) **Every clamp held.** No fill with qty != 3; never more than 1 open contract per arm; no
  entry after 14:30 ET; no SPY symbol anywhere in a ledger; every exit decision acted on within
  one tick; flat by 14:55 ET (verified from broker positions, not from state).
- (e) **Scorer is production, provably.** `test_tickers_scorer_2026_09_04.py` vary-and-assert
  green; every ledger row carries `scorer: "production"`.
- (f) **Tested thoroughly.** `test_tickers_execute_2026_09_04.py` + `test_tickers_scorer_2026_09_04.py`
  + `test_multi_core.py` (AST no-order guard) green; a full `--shadow` end-to-end tick against a
  real account produced WOULD_PLACE/BLOCKED rows through every gate with 0 exceptions.
- (g) **Documented properly.** `markdown/planning/TICKERS-LANE.md` (lane doc), rows in
  `automation/state/SCHEDULED-TASKS.md`, `markdown/specs/ARCHITECTURE.md` s3.2 append, STATUS
  OPEN line, this goal file's PROGRESS LOG, and a morning note for J with the one human step.

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: `backtest/lib/filters.py` is IMPORTED, never edited.
  No SPY params, no `accounts.json`, no `heartbeat_core.py`. `git diff --stat` on all ten frozen
  paths is empty before every commit.
- **Paper only, permanently.** `multi/lib/creds.py` refuses any base_url without "paper";
  `live:false` in params is not a knob. OP-0 #1 is J's alone.
- **Separation.** Three dedicated accounts; per-arm state under `automation/state/tickers/<arm>/`;
  never a file shared with the SPY fleet, multi-1, or the crypto twin. SPY is never in a universe.
- **Day-one clamps are frozen by the prereg**: qty exactly 3, 1 concurrent per arm, 1% daily kill,
  entries 09:35-14:30, time stop 14:45/14:50, flatten 14:52. Raising any is a risk EXPANSION.
- **Secrets**: J pastes into gitignored `automation/state/tickers/secrets.json` (template
  `secrets.json.example`). The rig's write-time credential guard blocks a session from writing a
  key literal and Claude does not defeat it. The executor self-heals: `NO_CREDS` is logged and
  retried every tick, so the lane starts within one tick of the file appearing.
- Every fire calls `python setup/scripts/conductor_outcome.py record ...`. STATUS line at OPEN and
  at first fill. Never `/loop`.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [x] T0 -- prereg frozen + lane foundation (creds allowlist, gitignore verified, params derived
  from multi, secrets template). Commit `5062ea52`.
- [~] T1 -- PRODUCTION SCORER ADAPTER `multi/lib/scorer_production.py` + kwargs threaded through
  `multi/core.py::tick` (state_path, level_state_dir, realized_pnl_today, kill_switch_tripped) +
  scorer dispatch; tests incl. vary-and-assert; live read-only smoke on NVDA/AAPL/QQQ vs the fork.
- [~] T2 -- ARMED EXECUTOR `multi/execute.py` (invariants, creds self-heal, account pin, per-arm
  paths, exits-first, qty clamp, kill switch, entry window, first-fill STATUS line) +
  `multi/tickers_verify.py` + `multi/tickers_flatten.py` + two installers + tests.
- [ ] T3 -- INTEGRATE + REVIEW: Fable reads both builds; full `--shadow` end-to-end tick against a
  real account; adversarial reviewer pass; fix; all tests green.
- [ ] T4 -- REGISTER `Gamma_TickersLane` (07:35 LOCAL = 09:35 ET, PT2M) + `Gamma_TickersEodFlatten`
  (12:52 LOCAL = 14:52 ET); SCHEDULED-TASKS rows; verify State=Ready + next-run time in ET.
- [ ] T5 -- DOCUMENT: `markdown/planning/TICKERS-LANE.md`, ARCHITECTURE s3.2 append, STATUS OPEN
  line, morning note for J (the one paste + `python multi/tickers_verify.py`).
- [ ] T6 -- FIRST SESSION (2026-09-04): confirm ledger rows at 09:37 ET; on secrets present,
  confirm verify + first fill; quote the first-fill STATUS line; EOD: flat check from broker.
- [ ] T7 -- Day-one autopsy: per-arm fills, every clamp audited from the broker, scorer parity
  (production rows vs the fork on the same bars, descriptive), written to the goal file.

## J-DECISIONS
- None required to trade paper. Revoke = set `shadow_only: true` in
  `automation/state/tickers/params.json` (new entries stop within one tick; exits + flatten still
  run) or `git revert <sha>` per commit.

## PROGRESS LOG
- 2026-09-04 01:05 ET -- Opened by Fable (session 76844c47) from J's directive. Prereg + foundation
  committed `5062ea52`. Two Sonnet builders launched on disjoint files (T1 scorer adapter, T2
  executor). Found while reading the installer to clone: `install-multi-core.ps1` registers at
  LOCAL 09:35 = 11:35 ET -- `Gamma_MultiCore` fired two hours late for its whole life.
  `install-multi-evaluate.ps1` has the correct convention (07:00 local = 09:00 ET) and a warning
  comment; the tickers installers follow it.

## HONEST STATE
Building. Nothing registered, nothing trading yet. Secrets file absent (J-only paste).

# GOAL: SEPT-MIDWINDOW-READ-2026-09-15

> Queued by Fable 2026-09-05 08:14 ET. The September scoring window (2026-08-31 -> ~09-29) decides whether one
> account arms live in October (go-live gate: PF CI-lower > 1.0 on as-traded, ex-best-day and cost-
> adjusted over >= 20 scored days, plus operational / reconciliation / behavioural / prod-shadow).
> On 09-03 it read RED on the statistical criterion (safe-3 0.44, safe-2 0.29, risky-1 0.43, bold-2
> 0.38) and INSUFFICIENT_DAYS on prod-shadow. A mid-window read on 09-15 tells J whether October is
> reachable or whether the window is already answering NO -- without touching anything.

## DONE-WHEN
On or after 2026-09-15 16:30 ET: `python setup/scripts/go_live_gate.py` run fresh, its five criteria
quoted per arm with n_days; the right-tail capture 20-session rate per arm; the intervention counter
(Sept target ZERO; rescues separate); the checkpoint packet's verdict counts; zero-enter day count
in the window; a one-paragraph honest read appended to markdown/planning/ROADMAP.md's September
section (append, never rewrite) stating, per arm, whether the CI-lower is trending toward 1.0 and
what n remains; NO recommendation to arm (that is J's on 09-29/10-30 with the packet).

## OPERATING RULES
- **CONFIG FREEZE 2026-08-31 -> 2026-10-30**: verification and reads only; no trading-path edits.
- Every fire calls `python setup/scripts/conductor_outcome.py record --task-id <id> --drained <n> --added <n> --lessons <n> --tests-delta <n> --regressions <n> --note "<note>"`.
- Every `Agent` fan-out passes `model:"sonnet"` explicitly.
- `STATUS.md` gets a line at OPEN and CLOSE only, never per-fire.
- Never `/loop /gamma-goal`; `Gamma_Conductor` + the Stop hook's bounded continuation only.
- Every stamp is read from `python setup/scripts/et_clock.py` in the same call, never typed.
- Not before its date: items are gated on real fires having happened; an early fire records "not yet" and stops.

## QUEUE
[ ] todo   [~] wip   [x] done   [B] blocked   [B-J] blocked on J
- [ ] M1 -- (on/after 09-15 16:30 ET) run the gate + the four reads above; quote everything.
- [ ] M2 -- ROADMAP.md September section append (per-arm read, n remaining, no arming recommendation).
- [ ] M3 -- STATUS CLOSE line; if any arm's operational/reconciliation criterion is RED, file the node
  to Known broken.

## J-DECISIONS
- None until the checkpoint packets.

## PROGRESS LOG
- {now} ET -- queued by Fable (EOD-audit session).
## HONEST STATE
Queued. Not before 2026-09-15 16:30 ET.

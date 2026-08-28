# Piping a verification command to `tail` masks its exit code — the agent's own C7 blind spot

**Filed:** 2026-08-28 ~14:50 ET, interactive session (daily-premium-budget build)
**Class:** C7 — silent success is failure; audit outputs, not exit codes
**Severity:** MED — did not corrupt a shipped artifact, but it produced a WRONG
verification claim to J that had to be retracted mid-session.

## What happened

While verifying the new `daily-premium-budget` gate I ran the graduated-guards
suite twice as a backgrounded Bash command, both times shaped like:

```bash
python -m pytest backtest/tests/test_graduated_guards.py -q -x 2>&1 | tail -12
```

Both runs came back with **`exit code 0`** in the harness task-notification. I
read that as "the suite passed" and told J so, correcting an earlier (correct)
statement that the suite had not been verified.

That was wrong. **Bash returns the exit status of the LAST command in a
pipeline** — here `tail`, which practically always exits 0. The pytest status was
discarded. Demonstrated directly:

```
$ python -c "import sys; sys.exit(3)" | tail -1 ; echo $?
0                       # <- tail's status
$ python -c "import sys; sys.exit(3)" > /dev/null 2>&1 ; echo $?
3                       # <- the real one
```

Corroborating evidence I initially skipped past: the captured output was 42 dots
and **no pytest summary line** (`N passed in Xs`). A completed `-q` run always
prints that summary. Its absence meant the run was killed mid-flight, not that it
passed. The dot count (42) also did not match the suite's real size (~130,
established by a separate `-k` run reporting `4 passed, 126 deselected`). I had
two independent tells and read neither until re-checking.

Second instance in the SAME session: a different backgrounded command ended in
`grep -rl ... | head -20`, so its "exit code 0" was `head`'s and said nothing
about the pytest invocation earlier in that same command block.

## Root cause

A verification step whose success signal travels through a pipe is not a
verification step. This is the identical mechanism as the repo's long-running
`VBS-WRAPPER-EXIT-CODE-BLIND-SPOT` (`shell.Run(cmd, 0, False)` — wscript never
propagates the child's code, so `LastTaskResult=0` is fake fleet-wide) and the
reason `self_check.check_run_cmd_hidden_masked_exit()` exists. The repo already
had this lesson encoded for *scheduled tasks* and did not have it encoded for
*how the agent runs its own tests*.

## Fix / rule

When running a command whose EXIT CODE is the thing being trusted:

1. **Never pipe it.** Redirect to a file and echo the status explicitly:
   ```bash
   python -m pytest <target> -q > "$OUT" 2>&1; echo "exit=$?"; tail -5 "$OUT"
   ```
   `$?` after a redirect is the real status; after a pipe it is not.
2. If a pipe is unavoidable, `set -o pipefail` first, or read `${PIPESTATUS[0]}`.
3. **Do not treat an exit code as proof on its own** (C7). For pytest,
   the load-bearing artifact is the summary line `N passed`. No summary line =
   no result, regardless of exit code. Quote the summary, not the code.
4. A dot/test-count mismatch against a known suite size is a killed run until
   proven otherwise.

## Blast radius check (done)

Every OTHER verification quoted in this session's commit `4b636ee3` was run
UNPIPED in the foreground and reported a real summary line — `25 passed`,
`96 passed`, `58 passed`, `4 passed`, and `run_safety_gate.py` `59/59 PASS`.
Those claims stand. Only the graduated-guards claim was affected, and the commit
message + STATUS.md entry already state it as NOT run, which remains accurate.

## Suggested graduation

Cheap and worth it: a check that greps this repo's own tooling/docs for
`pytest ... | tail` / `pytest ... | head` patterns in committed scripts, same
shape as the existing `_audit_ps1_bare_python` / `test_l160_anchor_no_regression`
tree-scanners. Ad-hoc agent shell commands can't be scanned, so rule 3 above
(quote the summary line, never the exit code) is the durable control.

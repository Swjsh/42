# Gap: global `block-no-verify` PreToolUse hook false-positives on plain `git commit -F`/`--file`

**Observed:** 2026-08-30T05:xx ET conductor fire. `git commit -F /tmp/commit_msg2.txt` and
`git commit --file=/tmp/commit_msg2.txt` (no `--no-verify` anywhere in the command, no shell
metacharacters, no history injection) were both refused by the global PreToolUse hook with:

```
PreToolUse:Bash hook error: [... hidden_hook.py --npx-pkg block-no-verify --npx-spec block-no-verify@1.1.2]:
BLOCKED: --no-verify flag is not allowed with git commit. Git hooks must not be bypassed.
```

The EARLIER commit in the same fire (`git commit -F /tmp/commit_msg.txt`, byte-identical
shape) succeeded. Only difference found: the second attempt's message file lived under
git-bash's `/tmp/` (which Windows-native Python resolved to a *different*, nonexistent path
under `AppData\Local\Temp` — a known git-bash-vs-Windows-path mismatch), so the retry that
actually worked used `setup/scripts/commit_msgfile.py` with a message file inside the repo
tree (`automation/state/.tmp-commit-msg-status.txt`) instead of `/tmp/`.

**Root cause: NOT diagnosed to a single mechanism this fire** (per the debugging discipline —
flagging honestly rather than guessing). Two candidate mechanisms, either or both:
1. The `block-no-verify` npm package may be doing broad heuristic string matching on the full
   hook payload (which can include recent session/command context, not just the literal
   command being invoked) and is over-triggering on unrelated `-F`/`--file` usage.
2. The failed `git commit -F /tmp/...` invocations may never have reached git at all (the
   file didn't exist under the Windows-resolved path), and the hook's block message is a
   RED HERRING for what was actually a `[Errno 2] No such file or directory` — needs a
   controlled repro (same command, message file confirmed to exist under both path
   interpretations) to separate "hook falsely blocks" from "hook's error message is
   misleading when the underlying git invocation would have failed anyway."

**Workaround that reliably works:** always route commit messages through
`setup/scripts/commit_msgfile.py <msgfile-inside-repo-tree> <path...>` (never `/tmp/`,
never a bare `git commit -F`/`-m` with a long message) — this is already standing doctrine
(`_lesson-inbox/2026-08-29-shell-quoting-and-stale-process.md`) and it happened to also route
around whatever tripped the hook here.

**Suggested next step (not done this fire — investigation-only budget):** reproduce with a
message file confirmed to exist at the exact path passed, isolate whether `block-no-verify`
or the git-bash/Windows path mismatch is the true cause, and if the hook itself is at fault,
either patch/pin the npm package version or replace it with a Python-native check (the
project already has the pattern via `hidden_hook.py`'s own docstring about npx shim overhead).

---
date: 2026-08-29
source: cockpit chat build session
kind: lesson
---

# Two foot-guns that cost most of one build session

## 1. Backticks and heredocs in shell strings are CODE, not text

Hit four times in one day, in four different disguises:

1. A commit message quoting `TZ=America/New_York date` while documenting the guard that blocks
   it — **the guard blocked its own commit.**
2. A shell `for` loop carrying commands inside quotes as data — the same guard blocked its own
   verification command.
3. An apostrophe inside a double-quoted commit message (`the guard's`) broke a regex that
   scanned for quoted spans, then an escaped inner quote broke the scanner that replaced it.
4. Backticks around `` `resume` `` and `` `node server.js` `` inside a commit message passed to
   a shell: **the shell ran them as command substitution.** `resume: command not found`, and
   node tried to execute a file that does not exist. Both words were silently deleted from the
   committed message.

**The rule:** anything that scans command text must separate code from data, and the
discriminator has to be exact or it trades a security hole for a lockout. When *writing* a
shell command, treat backticks and `$(...)` in any quoted payload as executable until proven
otherwise — prefer a file (`-F file`, `--data-binary @file`) or a Python heredoc over inlining
prose that contains punctuation.

## 2. A background process started from a tool call is not the process you are testing

Symptom: a fix is applied, the server is "restarted", the test still fails, so the fix looks
wrong. Six restarts were burned on this.

Mechanism, in one sentence: `node server.js` spawned from inside a tool call dies when that
call ends, and the 5-minute `Gamma_CompanionKeepalive` then starts a fresh one from whatever
the file happened to be at **its** tick — so the process under test is routinely older than
the edit under test.

**The check that settles it, before believing any companion result:**

```powershell
(Get-Process -Id <listener pid>).StartTime     # must be LATER than
```
```bash
ls -la --time-style=+%H:%M:%S gamma-companion/server.js
```

If process start < file mtime, the test is measuring the previous build. This belongs in the
same family as the existing "silent death = external kill" scar: the environment is acting on
the process, and reasoning about the code without checking that is wasted.

## Still open

`POST /api/orchestrator-chat` receives an empty body from `readBody()` while the adjacent
`/api/approve`, at the same brace depth in the same handler with the same helper and the same
curl shape, reads its body fine on the same process. Ruled out by test: route shadowing (there
was a real one, since fixed), handler nesting, position, stale process, and `authed()`
consuming the stream. Not root-caused.

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

---

## RE-VIOLATED 2026-08-30 — twice more, and the second one HUNG the commit

Same file, same day, two more incidents. That makes this a missing guardrail, not a
memory failure, so it now has code behind it.

**Incident 3.** A commit message explained a bug using the field names in backticks:
`...because `input` is not on the wire -- only the server-humanised `label` is.`
Inside a double-quoted bash argument those are COMMAND SUBSTITUTION. `input` printed
"command not found"; `label` invoked the Windows volume-label prompt, which then sat
waiting on stdin a non-interactive shell never provides. The commit hung until it was
killed 2 minutes later, and the working tree sat uncommitted the whole time.

**Why "escape it next time" is the wrong fix.** Backticks around an identifier are
*correct prose* in a commit message about code. A rule that says "write worse commit
messages" will be broken the moment a message needs to name a field. The real defect
is that a long piece of prose was being handed to a shell parser at all.

**The guardrail (shipped):** `setup/scripts/commit_msgfile.py`. It reads the message
as bytes from a file the shell never sees and execs `commit_scoped.py` with a real
argv list (`shell=False`), so no character in the message can be interpreted.

```
python setup/scripts/commit_msgfile.py <msgfile> <path> [<path>...]
```

Write the message with the Write tool (which does no shell parsing), then pass the
path. Use this for ANY commit message longer than one line.

**Generalised rule:** never interpolate prose into a shell command. If a payload is
authored text -- a commit message, a card body, a journal entry, a prompt -- it goes
through a file or a real argv list, never through quoting. The three characters that
break it (backtick, `$`, `\`) are all ordinary punctuation in technical writing.

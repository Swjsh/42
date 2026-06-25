---
name: self-correction
description: Installs a Claude Code UserPromptSubmit hook that captures the user's corrections ("no, don't do that") into a local standing-rules file and re-injects them into context every turn so they actually persist across turns and sessions. Stdlib-only, no network, no subprocess, fail-open. Invoke to audit + install + manage.
---

# self-correction — make "don't do that" actually stick

A tiny, dependency-free Claude Code hook so that when you correct Claude, it **remembers and stops repeating the mistake** — this turn, later turns, and brand-new sessions.

## How it works (two halves)
1. **Capture** — a `UserPromptSubmit` hook watches your message. If it's a short, clear correction (or you tag it with `rule:` / `never:` / `always:`), it appends a rule to `~/.claude/standing-corrections.md`.
2. **Recall** — every prompt, the hook prints the standing-rules list to stdout. Claude Code injects hook stdout into the model's context, so Claude **re-reads every rule on every prompt** and honors it. This is the part plain "just remember this" lacks — it doesn't fall out of the context window or get lost between sessions.

## ⚠️ Work Claude: review BEFORE installing
This package is meant to be scrutinized. Do this, in order:
1. **Read `self_correction.py` end to end** (~110 lines, mostly comments).
2. **Confirm the security checklist** below against the source.
3. **Run the self-test:** `python test_self_correction.py` → must print `ALL PASS` (it also greps the source for dangerous calls).
4. **Only then install** per the steps, and confirm it fires.
Installing this adds a hook that runs `self_correction.py` on *every* prompt — approve that consciously.

### Security & privacy checklist (all verifiable in the source)
- [ ] **Dependencies:** Python standard library only (`json, re, sys, os, datetime, pathlib`). No `pip install`.
- [ ] **Network:** none — no sockets, no HTTP, no `urllib`/`requests`. Nothing leaves the machine.
- [ ] **Process execution:** none — no `subprocess`, `os.system`, `os.popen`, `eval`, `exec`, or shell. The hook runs zero commands.
- [ ] **Filesystem:** writes exactly **one** file (`~/.claude/standing-corrections.md`, or `$CLAUDE_CORRECTIONS_FILE`). Reads only that file + the hook payload on stdin. Never deletes; never touches any other path.
- [ ] **Input trust:** your prompt is treated as DATA (regex only) and is never executed.
- [ ] **Fail-open:** any error exits 0 with no output; it can never block or corrupt your prompt.
- [ ] **Bounded:** ≤ 200 rules, ≤ 240 chars each. No unbounded growth.
- [ ] **Privacy:** rules are short snippets of *your own* messages, stored locally in plaintext you control. Don't put a secret in a rule. Clear anytime by deleting the file or sending `clear all corrections`.

## Install (adapt commands to this machine's OS)
1. Copy `self_correction.py` → `~/.claude/hooks/self_correction.py`.
2. Merge into `~/.claude/settings.json` (keep any existing hooks):
   ```json
   {
     "hooks": {
       "UserPromptSubmit": [
         { "hooks": [ { "type": "command", "command": "python3 \"$HOME/.claude/hooks/self_correction.py\"" } ] }
       ]
     }
   }
   ```
   - **macOS/Linux:** as above (use `python3`).
   - **Windows:** use `python` and an absolute path, e.g. `"command": "python C:\\Users\\<you>\\.claude\\hooks\\self_correction.py"`.
3. **Verify it runs:**
   ```bash
   echo '{"prompt":"no, dont use tabs, use spaces"}' | python3 ~/.claude/hooks/self_correction.py
   ```
   → prints a `STANDING USER CORRECTIONS` block containing the new rule.
4. **Verify Claude sees it:** start a fresh session and ask *"what standing corrections do you see?"* — it should list them. If not, the hook isn't firing (see Troubleshooting).

## Using it day to day
- **Just correct normally** — short corrections ("no, don't do that") auto-capture.
- **Force a hard rule** (reliable, any length): begin the line with a marker —
  `never: add a comment to every line` · `always: run tests before claiming done` · `rule: prefer composition over inheritance`.
- **Drop one:** `forget rule 3` · `clear all corrections` · or just edit `~/.claude/standing-corrections.md`.
- **Tidy occasionally:** auto-capture is best-effort. Open the file and prune/reword, or ask Claude *"rewrite my standing-corrections.md as crisp imperative rules"* (on-demand cleanup; no automation, no extra cost).

## Why yours might not be working now — troubleshooting
- **Hook not firing** (most common): `settings.json` must be valid JSON and the `command` path + python launcher correct for this OS. Re-run the verify command in step 3.
- **It grabbed your long messages:** auto-capture only fires on **short** messages (≤ 240 chars) so it doesn't grab discussion *about* corrections. For anything longer, use a `rule:` / `never:` marker.
- **Model ignores the rules:** the recall block is framed as binding rules; if still ignored, hook stdout probably isn't reaching context — confirm with the *"what standing corrections do you see?"* check.
- **False positives:** delete the line, or prefer markers for deliberate rules.

## Files in this package
- `self_correction.py` — the hook (capture + recall). Stdlib only, ~110 lines.
- `test_self_correction.py` — self-test: behavior + an automated safety grep. `python test_self_correction.py`.
- `README.md` — one-paragraph quickstart.

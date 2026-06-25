# self-correction — make "don't do that" actually stick

A tiny, dependency-free **Claude Code** hook: when you correct Claude ("no, don't do that"), it
records the correction to a local file and **re-injects it into context on every prompt**, so Claude
stops repeating the mistake — across turns and across new sessions.

- **Safe by design** for work environments: Python standard library only, **no network, no subprocess,
  no eval/exec**, writes exactly one local file, fail-open. Full audit + checklist in **[SKILL.md](SKILL.md)**.
- **Verify before installing:** `python test_self_correction.py` → `ALL PASS` (also greps the source for dangerous calls).

## Quickstart
1. Have your Claude read **[SKILL.md](SKILL.md)**, confirm the security checklist, and run the self-test.
2. Install: copy `self_correction.py` → `~/.claude/hooks/`, wire it as a `UserPromptSubmit` hook in
   `~/.claude/settings.json` (snippet in SKILL.md).
3. Use it: just correct normally; for a guaranteed hard rule start a line with `never:` / `always:` / `rule:`;
   drop one with `forget rule N` or by editing `~/.claude/standing-corrections.md`.

## Files
| File | What |
|---|---|
| [`SKILL.md`](SKILL.md) | Install guide + security/privacy audit + troubleshooting (the entry point) |
| [`self_correction.py`](self_correction.py) | The hook — capture + recall, stdlib only (~110 lines) |
| [`test_self_correction.py`](test_self_correction.py) | Self-test: behavior + automated safety grep |

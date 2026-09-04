# Lesson inbox -- gitignore protects credential FILES, not credential VALUES

**Filed:** 2026-09-03 evening (Fable, money-leak session)  **Theme:** C7 silent success / security
**Severity:** the highest-consequence repeat in this repo's history -- FOUR occurrences over three months

## Symptom
Six Alpaca paper credentials (three of them key+SECRET pairs, i.e. full API access) were readable in
the PUBLIC repo's git history. Found only because a pre-push audit was run BY HAND on 2026-09-03;
a parallel session pushed 20 minutes later, carrying the newest one to the public remote.

## Root cause, one sentence
`.gitignore` protects the credential FILES (`.mcp.json`, `automation/state/fleet/secrets.json` --
both correctly ignored, never tracked, never leaked), but nothing stopped a session from READING a
value out of one and writing the LITERAL into ordinary tracked source.

## Every occurrence had the same shape
| Commit date | Vector |
|---|---|
| 2026-06-15 | hardcoded env fallback default: `os.environ.get("ALPACA_API_KEY", "PK33...")` in 4 files |
| 2026-06-19 | same fallback pattern in the GEX capture job |
| 2026-06-24 | pasted as a "redaction example" in the github-audit skill's OWN docs |
| 2026-09-03 | an `ACCOUNT_KEYS` dict + a debug script, atticed by an auto-commit at 02:27 ET |

The temptation is always the same: a fallback default makes a script "just work" without the loader.

## Why it survived three months
The only three defences all operated AFTER the literal was already on disk, and the outermost one
was broken: `github_audit.py --history` crashed before scanning (cp1252 decode + a None dereference),
so the one tool that could have found an existing leak had NEVER run to completion. It also had no
pattern for Alpaca LIVE keys at all -- a live credential would have scanned GREEN.

## The fix that actually closes it (shipped 2026-09-03)
1. **WRITE-TIME (the layer that never existed):** `setup/hooks/doctrine.py#credential_write_hit` +
   `gamma_doctrine.py` PreToolUse refusal on Edit/Write/NotebookEdit/MultiEdit (added content) and
   Bash/PowerShell (raw command, so heredocs count), importing `github_audit.SECRET_PATTERNS` by
   identity. It blocked its own author's command within the hour.
2. **COMMIT-TIME:** `github_audit.py --staged` wired into `setup/git-hooks/pre-commit`.
3. **PUSH-TIME:** the history scan repaired + live-key/secret/OpenRouter/Discord/PEM patterns added.

## Rules for every future session
- NEVER write a credential literal into tracked source, not even as a fallback default, not even in
  a docs example, not even in an attic/debug script. Load at runtime (`_load_account_keys()` in
  `setup/scripts/fast_path_executor.py`).
- A test fixture that needs a key-shaped string builds it by CONCATENATION (`"PK" + "A"*24`).
- "It's gitignored" is never the answer to "is this credential safe?" -- ask instead: does the VALUE
  appear in a tracked file?
- A security scanner that is permanently RED on an un-silenceable false positive is a scanner people
  learn to ignore (the noqa marker was `#`-only, so no JS file could ever be allowlisted -- fixed).

## Cross-refs
STATUS 2026-09-03 `SECRETS-ON-PUBLIC-REMOTE`; commits `ef7e4aed` (staged scan), `c43832e2` (history
repair), `b35067c0` (write-time guard); queue `SECRET-WRITE-TIME-GUARD`, `GITHUB-AUDIT-NO-LIVE-KEY-PATTERN`.

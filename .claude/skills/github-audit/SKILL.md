---
name: github-audit
description: Secrets + privacy audit before any push to Swjsh/42 (public repo). Scans every tracked file for hardcoded API keys, tokens, and credentials; verifies gitignore coverage; emits GREEN (safe to push) or RED (stop, fix first) verdict with itemized file:line findings. Run before every `git push` and whenever a new script is added that touches credentials. Also catches history leaks already in the local commit log. NEVER edits files or commits — audit only.
allowed-tools: Bash Read Grep Glob
---

# Skill: github-audit — secrets & privacy audit before every push

> **Target:** `https://github.com/Swjsh/42` is a **PUBLIC repo**. Every committed line is visible to the world. Run this skill before `git push` and anytime a new script is added that references credentials.

This skill is **audit-only** — it never edits files, never commits, never reverts. It produces a **GREEN / RED verdict** with exact file:line citations. Fix findings, then re-run until GREEN before pushing.

---

## 0 — WHEN TO RUN

| Trigger | Action |
|---|---|
| Before any `git push origin` | Run full audit — hard gate |
| After adding any new `.py`, `.js`, `.ps1`, `.json`, `.md` file | Run audit — new files are the most common leak vector |
| After a `git merge` or `git pull --rebase` | Run audit — merges can reintroduce scrubbed content |
| After key rotation (new keys exist, old ones must be removed) | Run audit — verifies old values are gone everywhere |
| Anytime STATUS.md logs a secret-related incident | Run audit + history scan |

---

## 1 — RUNNING THE AUDIT

**Primary (automated, full scan):**

```powershell
& "C:\Users\jackw\Desktop\42\setup\scripts\venv_python.ps1" `
    "C:\Users\jackw\Desktop\42\setup\scripts\github_audit.py"
```

Or with Python directly:

```powershell
python "C:\Users\jackw\Desktop\42\setup\scripts\github_audit.py"
```

No external deps — stdlib only. Takes ~3s on the full repo.

**Quick scan (Bash, no script):**

```bash
# Alpaca API key pattern (PK + 24 uppercase alphanumeric)
git ls-files | xargs grep -Pn '\bPK[A-Z0-9]{24}\b' 2>/dev/null

# Secret/key assignment patterns in code
git ls-files | xargs grep -in '_KEY\s*=\s*["'"'"'][A-Za-z0-9+/=_-]\{20,\}["'"'"']' 2>/dev/null

# Long bare strings that look like secrets (40+ char alphanumeric)
git ls-files --include="*.py" --include="*.js" | \
  xargs grep -Pn '["'"'"'][A-Za-z0-9]{40,}["'"'"']' 2>/dev/null | \
  grep -v "# noqa:secret-ok"
```

---

## 2 — WHAT THE SCRIPT CHECKS

### 2a. Secret pattern scan (tracked files)

Scanned via `git ls-files` so only committed + staged content is inspected — untracked files are irrelevant (they can't be pushed until staged).

| Pattern | What it catches | Risk |
|---|---|---|
| `PK[A-Z0-9]{24}` | Alpaca API key (paper or live) | HIGH |
| `ALPACA_SECRET_KEY\s*[:=]\s*["'][A-Za-z0-9]{30,}` | Alpaca secret key in assignment | HIGH |
| `APCA-API-SECRET-KEY.*[A-Za-z0-9]{30,}` | Alpaca secret in HTTP header dicts | HIGH |
| `sk-or-v1-[a-zA-Z0-9]{40,}` | OpenRouter API key | HIGH |
| Long string (40+ char) near `secret`/`token`/`password`/`credential` keyword | Generic credential-like assignment | MEDIUM |
| `C:\\Users\\jackw\\` or `C:/Users/jackw/` in `.py`/`.js` files | Personal path hardcoded in portable script | LOW |

**Allowlist:** lines ending with `# noqa:secret-ok` are intentionally ignored. Use sparingly and only for non-sensitive lookalikes (e.g. a SHA256 hash that triggers the 40-char rule).

### 2b. Gitignore coverage check

Verifies the following patterns exist in `.gitignore`:

```
.mcp.json
**/.mcp.json
**/.discord-config.json
**/.discord-token
**/.alpaca-keys
**/.openrouter.key
**/.heartbeat-api-key
**/.heartbeat-api-key-bold
automation/state/fleet/secrets.json
**/fleet-secrets.json
*.pem
*.key (under setup/)
```

A missing gitignore entry = RED even if no file currently exists — the pattern gate must be in place before the file is created.

### 2c. Tracked file allowability check

Checks that no currently-tracked file matches a sensitive pattern that should have been gitignored:

```
*.mcp.json  (should be gitignored — contains live API keys)
*secrets*.json  (unless explicitly benign)
*-keys.json
*.pem
*.key
```

### 2d. Git history scan (HIGH value, SLOW — run before first push to a new remote)

If `--history` flag is passed, the script scans the **full local commit log** for secrets using `git log -p`. This is important because:
- Git history is permanent. Even if a secret was "removed" in a later commit, `git push` exposes every prior commit.
- If a secret is found in history, the fix is `git filter-repo` (not just a new commit removing the file).

```powershell
python "C:\Users\jackw\Desktop\42\setup\scripts\github_audit.py" --history
```

> **History scan takes 30-90s** on this repo. Run it once before the first push to a new remote, and after any suspected leak-then-remove cycle.

---

## 3 — READING THE OUTPUT

```
══════════════════════════════════════════════════════
GITHUB SECRETS & PRIVACY AUDIT — 2026-06-24 23:15 ET
══════════════════════════════════════════════════════

[SCAN] 847 tracked files checked in 2.1s

SECRET PATTERNS
  ✓  No Alpaca API key pattern found
  ✓  No secret-key assignment found
  ✗  setup/some-script.py:42  long-string near 'secret_key' → "ELWu7Q..."
       → FIX: load from .mcp.json at runtime (see _load_account_keys pattern)

GITIGNORE COVERAGE
  ✓  .mcp.json excluded
  ✓  automation/state/fleet/secrets.json excluded
  ✗  *.heartbeat-api-key-bold missing from .gitignore
       → FIX: add line "**/.heartbeat-api-key-bold" to .gitignore

TRACKED FILE ALLOWABILITY
  ✓  No blocked file types tracked

══════════════════════════════════════════════════════
VERDICT: RED — 2 findings (fix before git push)
══════════════════════════════════════════════════════
```

**GREEN** = safe to push. **RED** = stop; fix every finding before pushing.

---

## 4 — FIXING FINDINGS

### Finding: hardcoded Alpaca key in a Python script

**Canonical fix** — load from `.mcp.json` at runtime (already gitignored):

```python
import json
from pathlib import Path

def _load_alpaca_key(account: str = "safe") -> tuple[str, str]:
    """Load key/secret from .mcp.json (gitignored). Never hardcode here."""
    _SERVER = {"safe": "alpaca", "bold": "alpaca_aggressive"}
    mcp = json.loads((Path(__file__).resolve().parents[2] / ".mcp.json").read_text())
    env = mcp["mcpServers"][_SERVER[account]]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]

KEY, SECRET = _load_alpaca_key()
```

Reference implementations: [`setup/scripts/fast_path_executor.py`](../../../setup/scripts/fast_path_executor.py) (`_load_account_keys`) and [`automation/scripts/gex_capture.py`](../../../automation/scripts/gex_capture.py) (`_load_alpaca_key`).

### Finding: hardcoded key in a JavaScript/Node script

```javascript
// Load from .mcp.json (gitignored) — never hardcode
const mcp = JSON.parse(require('fs').readFileSync(
  require('path').join(__dirname, '../../.mcp.json'), 'utf8'
));
const { ALPACA_API_KEY, ALPACA_SECRET_KEY } = mcp.mcpServers.alpaca.env;
```

### Finding: secret in a changelog / doc entry

Replace the value with a placeholder or abbreviated form:
- Full key `PKEXAMPLE1234FAKEKEY5678` → `PKEXAMPL…` or `<redacted>`
- Never put even the first 8 chars if they uniquely identify an account

### Finding: key in git history (the hard case)

If `--history` finds a secret in a prior commit:
1. **Do NOT push** — the exposed commit is already in local history and would be uploaded
2. Run `git filter-repo --path <file> --invert-paths` to rewrite history (or use BFG Repo Cleaner)
3. Rotate the leaked key immediately (even if paper — treat as compromised)
4. Force-push after filter-repo: `git push origin main --force` (alert J before doing this)
5. Re-run the full audit (including `--history`) to confirm clean

### Finding: missing gitignore pattern

Add the required line to `.gitignore` under the `# Secrets` block. Then verify with:
```bash
git check-ignore -v <path-that-should-be-excluded>
```

---

## 5 — SECRET LOCATIONS IN THIS REPO (canonical map)

| Secret type | Where it lives | Gitignored? |
|---|---|---|
| Alpaca API keys (Safe-2 + Risky-2) | `.mcp.json` (project root) | ✓ `.mcp.json` |
| Fleet per-account keys | `automation/state/fleet/secrets.json` | ✓ `automation/state/fleet/secrets.json` |
| Alpaca keys in scripts | **NEVER** — load from `.mcp.json` | N/A |
| Discord token | `.discord-token` in project root | ✓ `**/.discord-token` |
| Discord config | `.discord-config.json` | ✓ `**/.discord-config.json` |
| OpenRouter key | `.openrouter.key` | ✓ `**/.openrouter.key` |
| Heartbeat API key (Safe) | `.heartbeat-api-key` | ✓ `**/.heartbeat-api-key` |
| Heartbeat API key (Bold) | `.heartbeat-api-key-bold` | ✓ `**/.heartbeat-api-key-bold` |
| TastyTrade credentials | `.env.tastytrade` | ✓ `.env.tastytrade` |

---

## 6 — WHAT THIS SKILL NEVER DOES

- Edit any file (audit only — fixes are J's or Gamma's responsibility once cited)
- Commit or push anything
- Rotate keys (key rotation is a J action — the audit only detects and reports)
- Block J's interactive Claude session (fail-open like all guards)
- Run during market hours unless explicitly invoked by J (audit is always safe to run, but not scheduled during RTH)

---

## Cross-references

- **Secret loader pattern:** [`setup/scripts/fast_path_executor.py`](../../../setup/scripts/fast_path_executor.py) (`_load_account_keys`) — canonical reference implementation
- **Gitignore:** [`.gitignore`](../../../.gitignore) — `# Secrets` block at top
- **CLAUDE.md GitHub section:** `## GitHub` — secrets rule + push discipline
- **Tech stack row:** `Source control` row in `## Tech stack`
- **L21/L60 lesson (anchor paths):** anchor to `__file__` not cwd — applies to the audit script itself
- **C10 (rate-limit pool / key hygiene):** [`markdown/doctrine/LESSONS-LEARNED.md`](../../../markdown/doctrine/LESSONS-LEARNED.md) L54/L62/L68/L69

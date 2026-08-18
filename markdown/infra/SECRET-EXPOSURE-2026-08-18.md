# Secret exposure review — 2026-08-18

> Found during J's alignment review while auditing account-identity drift. **No secret value
> appears in this document.** Credentials are referred to by their first six characters only,
> which is enough to identify them in a broker console without re-publishing them.
>
> Scope of the check: every git-tracked file scanned by pattern (Alpaca `PK…` keys, 40-char
> literals adjacent to a SECRET/PASSWORD/TOKEN assignment, OpenRouter `sk-or-v1-…`, Discord
> bot tokens, generic `sk-…`), plus a `git log --all -S<value>` history search for each
> credential actually found, plus a push-status check (`git merge-base --is-ancestor … origin/main`)
> on every commit containing one.

---

## ✅ The reassuring finding first

**All four credentials Gamma uses TODAY have never been committed.** Verified by searching the
entire reachable history for each value read live from `.mcp.json`:

| server | field | first 6 | commits in history |
|---|---|---|---:|
| `alpaca` | API key | `PKWEWC…` | **0** |
| `alpaca` | secret | `GcX4rV…` | **0** |
| `alpaca_aggressive` | API key | `PKEZ6O…` | **0** |
| `alpaca_aggressive` | secret | `BWesrV…` | **0** |

The `.mcp.json`-only credential rule has held for the live path.

## 🚨 What IS exposed on the public repo

`https://github.com/Swjsh/42` is public, so anything in pushed history must be assumed read.

| credential | what it is | pushed commits | since | status |
|---|---|---:|---|---|
| `43092f…` | **Tastytrade OAuth client_secret** | **1** | — | ⚠️ **ROTATE — highest priority** |
| `PKQMQD…` | Alpaca API key (old bold arm) | **3** | 2026-06-15 | likely dead — verify/revoke |
| `ELWu7Q…` | Alpaca **secret** matching the above | **3** | 2026-06-15 | likely dead — verify/revoke |

The three Alpaca-bearing commits are `d0c8ac06` (2026-06-15), `4394d4c6` (2026-06-24) and
`667217a1` (2026-06-26). **`4394d4c6` is titled "fix(security): scrub hardcoded Alpaca keys"** —
it cleaned the working tree but the values remained reachable in history, which is the classic
half-fix. That pair belongs to an account deleted in the 2026-08-03 fleet rebuild, so the
credential is very likely already dead; "very likely" is not "verified," so it should still be
revoked in the Alpaca console.

**The Tastytrade secret is the one that matters.** It is a real brokerage OAuth app credential,
it was published, and unlike the Alpaca pair there is no reason to think it has been rotated.

## What I did, and what I deliberately did not

**Did** — removed credentials from three scripts, all now loading from `.mcp.json` at runtime
per the documented `fast_path_executor.py` pattern:

- `setup/scripts/tastytrade_oauth.py` (tracked) — the secret was the `os.getenv` default **and**
  a copy-pasteable line in the module docstring. Now absent; the no-secret path exits 2 loudly
  instead of attempting auth with an empty string.
- `setup/scripts/alpaca_api_audit.py` (was untracked) — four plaintext credentials.
- `setup/scripts/mcp_audit_runner.py` (was untracked) — four plaintext credentials.

**Did not** — and these are deliberately J's:

- **Rotating anything.** Rotating or exposing a secret is one of the few actions that always
  needs J.
- **Rewriting history.** That means a force-push: an irreversible external action. Also worth
  saying plainly — **rotation matters more than rewriting.** Once a value is published, assume
  it was scraped; scrubbing history closes the door after the fact but does not un-publish.

## ⚠️ A mistake I made during this review, recorded honestly

While cleaning up, I committed `mcp_audit_runner.py` — a file that was **untracked and carried
four hardcoded credentials**. My earlier scan had only covered git-*tracked* files, so it never
saw them, and I committed without re-scanning a file I was newly adding.

Caught immediately afterwards by scanning the committed blob. The commit was **local only**
(the repo was 211 commits ahead of `origin/main`), so nothing reached GitHub. I removed the
credentials and amended that same unpushed commit, then verified `PKZFN5G3…` now appears in
**0** commits anywhere in history.

**The lesson, which is the reason this section exists:** *scanning tracked files is not enough
before a commit that ADDS files.* An untracked file has never been scanned by any tracked-file
sweep, and `git add` is exactly the moment it stops being private. Any future secret sweep must
scan the working tree, not just the index.

## Standing recommendations

1. **Rotate the Tastytrade client_secret** at `my.tastytrade.com` → Settings → API Access →
   OAuth Applications. Then set `TT_SECRET` in the environment; the script now requires it.
2. **Revoke the old Alpaca key `PKQMQD…`** in the Alpaca console if it still exists.
3. Decide separately whether history rewriting is worth it. It is a force-push on a public repo
   and does not undo publication.
4. Consider a pre-commit secret scan that reads the **working tree** for staged additions. The
   existing `commit_scoped.py` already scopes what gets committed; a scan hook would catch what
   is *in* those paths.

"""claude_auth_canary.py -- cheap deterministic detector for a lost Claude CLI login.

WHY THIS EXISTS (incident 2026-09-15 ~08:45 ET): the standalone `claude` CLI lost its
saved claude.ai login overnight. `claude auth status` returned
{"loggedIn": false, "authMethod": "none", "apiProvider": "firstParty"} -- the refresh
token had expired 2026-09-14 10:25 local, and the tokens on disk were blank from 13:55
local the prior day. NOTHING flagged this until Gamma_Premarket failed at 08:30 ET with
"Not logged in - Please run /login" and silently fell back to a degraded deterministic
bias. Gamma_Premarket, the 15:55 secondary flatten net, the conductor, EOD summary,
analyst and scout personas all depend on the same CLI session.

WHAT THIS DOES (one-shot, <20s, $0 -- pure stdlib, no LLM call):
  1. Runs `claude auth status` (the SAME claude.exe path Invoke-Claude resolves in
     setup/scripts/_shared.ps1 -- $Global:ClaudeExe) and parses its JSON.
  2. Separately checks ~/.claude/.credentials.json -- WITHOUT ever reading
     accessToken/refreshToken (the actual secret values) -- for
     claudeAiOauth.refreshTokenExpiresAt, a plain numeric epoch-ms timestamp. Only that
     timestamp is read, converted, and printed; never the token strings themselves.
  3. Writes automation/state/claude-auth-canary.json with a verdict:
       OK          - logged in, refresh token has > 72h left (or no expiry info to worry about)
       EXPIRING    - logged in, but refresh token expires within 72h
       LOGGED_OUT  - `claude auth status` says loggedIn=false, OR the refresh token has
                     already expired
       UNKNOWN     - the CLI binary is missing or `auth status` produced no parseable
                     JSON (fail-open: this script must never crash or fabricate a verdict)

Fail-open per OP-25: any unexpected exception is caught, logged to stderr, and reported
as verdict=UNKNOWN with the error text -- this canary never raises into its caller and
never fabricates a plausible-looking OK when it actually doesn't know.

CLI:
    python setup/scripts/claude_auth_canary.py
    python setup/scripts/claude_auth_canary.py --claude-exe <path> --credentials <path>

Surfacing: setup/scripts/claude_auth_canary_surface.py (separate module) upserts a
'CLAUDE_AUTH:' marker into STATUS.md's '## Known broken' section via the existing
status_known_broken.py writer whenever verdict != OK, and clears it on a return to OK.

Guard: setup/scripts/test_claude_auth_canary.py.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # pragma: no cover - trivial import shim, mirrors scheduled_task_staleness.py's pattern
    from et_clock import et_now
except Exception:  # pragma: no cover - fail-open even if et_clock itself is broken
    et_now = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / "automation" / "state" / "claude-auth-canary.json"

# Same resolved path as $Global:ClaudeExe in setup/scripts/_shared.ps1's Invoke-Claude --
# kept as a literal here (not shelled out to PowerShell) so this stays pure-Python/$0.
DEFAULT_CLAUDE_EXE = (
    r"C:\Users\jackw\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe"
)
DEFAULT_CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"

EXPIRING_THRESHOLD_HOURS = 72.0
FIX_HINT = "run `claude` then /login in a terminal (J credential step)"


def _fmt_local(epoch_ms: Optional[float]) -> Optional[str]:
    """epoch-ms -> 'YYYY-MM-DD HH:MM:SS ET' string, or None. Uses et_clock's DST-aware
    UTC->ET conversion (never a naive local-time guess -- this box runs Mountain time)."""
    if epoch_ms is None or et_now is None:
        return None
    try:
        import datetime as _dt
        utc_dt = _dt.datetime.fromtimestamp(epoch_ms / 1000.0, tz=_dt.timezone.utc)
        et_dt = et_now(now_utc=utc_dt)
        return et_dt.strftime("%Y-%m-%d %H:%M:%S") + " ET"
    except Exception:
        return None


def _run_auth_status(claude_exe: str) -> "tuple[Optional[bool], Optional[str], Optional[str]]":
    """Returns (loggedIn, authMethod, error). error is None on a clean parse."""
    exe_path = Path(claude_exe)
    if not exe_path.exists():
        return None, None, f"claude CLI not found at {claude_exe}"
    try:
        # `claude auth status` exits 1 when logged out (confirmed live 2026-09-15) but
        # still prints valid JSON to stdout -- never gate on returncode, only on
        # whether stdout parses.
        proc = subprocess.run(
            [claude_exe, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open, any subprocess failure -> UNKNOWN
        return None, None, f"subprocess failed: {type(exc).__name__}: {exc}"

    stdout = (proc.stdout or "").strip()
    try:
        data = json.loads(stdout)
    except Exception:
        stderr_tail = (proc.stderr or "").strip()[:300]
        return None, None, f"non-JSON output (exit={proc.returncode}): {stdout[:200]!r} {stderr_tail!r}"

    logged_in = data.get("loggedIn")
    auth_method = data.get("authMethod")
    if not isinstance(logged_in, bool):
        return None, auth_method, f"unexpected auth-status shape: {data!r}"
    return logged_in, auth_method, None


def _read_refresh_expiry(credentials_path: Path) -> "tuple[Optional[float], Optional[str]]":
    """Returns (refreshTokenExpiresAt epoch-ms, error). NEVER reads accessToken or
    refreshToken -- only the numeric expiry field, per the task's explicit constraint."""
    if not credentials_path.exists():
        return None, f"credentials file not found at {credentials_path}"
    try:
        raw = credentials_path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return None, f"could not parse credentials file: {type(exc).__name__}: {exc}"

    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None, "credentials file has no claudeAiOauth block"
    expiry = oauth.get("refreshTokenExpiresAt")
    if not isinstance(expiry, (int, float)):
        return None, "refreshTokenExpiresAt missing or non-numeric"
    return float(expiry), None


def _verdict(
    logged_in: Optional[bool],
    auth_error: Optional[str],
    hours_left: Optional[float],
) -> str:
    if logged_in is None:
        return "UNKNOWN"
    if not logged_in:
        return "LOGGED_OUT"
    if hours_left is not None and hours_left <= 0:
        return "LOGGED_OUT"
    if hours_left is not None and hours_left <= EXPIRING_THRESHOLD_HOURS:
        return "EXPIRING"
    return "OK"


def run_canary(
    claude_exe: str = DEFAULT_CLAUDE_EXE,
    credentials_path: Path = DEFAULT_CREDENTIALS_PATH,
) -> dict:
    """Runs the full canary check and returns the state dict (also written to
    STATE_PATH by main()). Never raises -- any internal failure degrades to
    verdict=UNKNOWN with the error text preserved in the returned dict."""
    try:
        logged_in, auth_method, auth_error = _run_auth_status(claude_exe)
        expiry_ms, expiry_error = _read_refresh_expiry(credentials_path)

        hours_left: Optional[float] = None
        if expiry_ms is not None and et_now is not None:
            try:
                import datetime as _dt
                now_ms = _dt.datetime.now(_dt.timezone.utc).timestamp() * 1000.0
                hours_left = (expiry_ms - now_ms) / (1000.0 * 3600.0)
            except Exception:
                hours_left = None

        verdict = _verdict(logged_in, auth_error, hours_left)
        ts_et = et_now().strftime("%Y-%m-%d %H:%M:%S ET") if et_now is not None else None

        errors = [e for e in (auth_error, expiry_error) if e]

        return {
            "ts_et": ts_et,
            "loggedIn": logged_in,
            "authMethod": auth_method,
            "refresh_expires_at_local": _fmt_local(expiry_ms),
            "hours_left": round(hours_left, 2) if hours_left is not None else None,
            "verdict": verdict,
            "fix_hint": FIX_HINT,
            "errors": errors or None,
        }
    except Exception as exc:  # noqa: BLE001 - fail-open (OP-25): never raise, never fabricate
        return {
            "ts_et": et_now().strftime("%Y-%m-%d %H:%M:%S ET") if et_now is not None else None,
            "loggedIn": None,
            "authMethod": None,
            "refresh_expires_at_local": None,
            "hours_left": None,
            "verdict": "UNKNOWN",
            "fix_hint": FIX_HINT,
            "errors": [f"canary internal failure: {type(exc).__name__}: {exc}"],
        }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claude-exe", default=DEFAULT_CLAUDE_EXE)
    ap.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS_PATH))
    ap.add_argument("--state-path", default=str(STATE_PATH))
    args = ap.parse_args(argv)

    state = run_canary(claude_exe=args.claude_exe, credentials_path=Path(args.credentials))

    state_path = Path(args.state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - fail-open on the write too
        print(f"claude_auth_canary: FAILED to write state file: {exc}", file=sys.stderr)

    print(json.dumps(state, indent=2))

    # Surface to STATUS.md's Known broken section (best-effort, never blocks/crashes this script).
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import claude_auth_canary_surface as surface  # noqa: PLC0415
        surface.surface(state)
    except Exception as exc:  # noqa: BLE001
        print(f"claude_auth_canary: surfacing failed (fail-open, state file still written): {exc}",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

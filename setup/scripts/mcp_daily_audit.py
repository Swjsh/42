"""mcp_daily_audit.py -- deterministic, $0 replacement for the LLM-driven
`Gamma_McpDailyAudit` fire (was `automation/prompts/mcp-weekly-audit.md` via
`run-mcp-daily-audit.ps1`'s `Invoke-Claude`).

WHY THIS EXISTS (2026-09-03): the free-model prompt wrote TWO false BLOCKERs into
STATUS.md `## Known broken` in one night -- `MCP_AUDIT_RED: Alpaca Safe and Bold
both 401 Unauthorized ... BLOCKER` at 00:03 ET, then `MCP_AUDIT_YELLOW ... 404
(credential/account mismatch)` at 07:48 ET. Both were false: a direct REST
`GET https://paper-api.alpaca.markets/v2/account` using the SAME `.mcp.json` keys
returned 200 for both accounts (PA3POKNV46VG $5,653.87 ACTIVE, PA3WEBXJU67N
$5,593.52 ACTIVE) at 01:20 ET, and the live engine trades via direct REST with
those same keys all day -- it never saw an outage. This is a pure network
round-trip probe; per CLAUDE.md's "deterministic > LLM on hot paths" doctrine, a
free-model fire that can hallucinate a BLOCKER on a $0-verifiable REST call is
strictly worse than the deterministic version, which cannot hallucinate a status
code. `automation/prompts/mcp-weekly-audit.md` is retired (see its own header) and
`run-mcp-daily-audit.ps1` now calls this script directly.

Two prior UNWIRED attempts at exactly this (`mcp_audit_direct.py`,
`automation/scripts/mcp_audit_probe.py`) already exist in this repo and are the
source of the registry-driven expected-accounts pattern (`expected_accounts()`,
lifted near-verbatim from `mcp_audit_direct.py` -- see that file's own docstring
for the 2026-08-18 hardcoded-phantom-account incident this avoids) and the WMI
process-liveness pattern (`bg_status.py::_detached_workers`). This module is the
canonical merge; the two prior scripts are left in place (unreferenced) rather
than deleted, per smallest-diff scope.

CHECKS
  (a) Alpaca REST /v2/account for BOTH `.mcp.json` servers (`alpaca`,
      `alpaca_aggressive`) -- status code, account_number matches
      `automation/state/fleet/accounts.json`'s safe-2/bold-2 account_number,
      status == "ACTIVE". A DEFINITIVE mismatch (200 but wrong account/status) is
      RED immediately -- it is a config fact, not a network blip, so it needs no
      retry. An UNREACHABLE read (non-200 / network error / timeout) is only a
      CANDIDATE failure: it is re-probed once, 30s later, and only counts as RED
      if it fails BOTH times. A single transient miss that recovers is YELLOW.
  (b) Alpaca /v2/clock reachability, per account (folded into the same probe;
      account already confirmed healthy but clock unreachable = YELLOW, not RED).
  (c) TradingView CDP port 9222 (`/json/version`) -- REPORT-ONLY, never RED.
  (d) The two `uvx alpaca-mcp-server` processes (WMI command-line match) --
      REPORT-ONLY, never RED. The live engine trades via direct REST, not through
      these processes (see doctrine block above), so their absence only matters
      to an interactive Claude session's own MCP tools, not to trading safety.

OUTPUT
  `automation/state/mcp-daily-audit.json` -- as_of (ET), verdict, per-check
  detail, reason. No secrets (API keys/secrets are read for the request headers
  and never placed in any returned dict).
  STATUS.md `## Known broken`, ONLY via the shared de-duplicating writer
  `status_known_broken.upsert("MCP_AUDIT_", line_or_None)` -- GREEN clears the
  marker, non-GREEN writes exactly one line, never a stack of stale readings.
  No Discord: this is a transition-only signal at most (STATUS.md), and wiring a
  ping is out of scope for this fire (recurring-Discord-cost gate, CLAUDE.md #5).

CLI:
    python setup/scripts/mcp_daily_audit.py
Exit 0 on GREEN, 1 otherwise (mirrors the retired LLM fire's contract).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import et_now  # noqa: E402
import status_known_broken as skb  # noqa: E402

MCP_JSON_PATH = REPO_ROOT / ".mcp.json"
ACCOUNTS_PATH = REPO_ROOT / "automation" / "state" / "fleet" / "accounts.json"
OUTPUT_PATH = REPO_ROOT / "automation" / "state" / "mcp-daily-audit.json"
STATUS_PATH = REPO_ROOT / "automation" / "overnight" / "STATUS.md"
MARKER = "MCP_AUDIT_"

# OP-27 L41 / C8: headless Windows spawns must never flash a console window.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

RETRY_WAIT_SECONDS = 30.0


def _et_ts() -> str:
    return et_now().strftime("%Y-%m-%dT%H:%M:%S ET")


def load_mcp_creds() -> dict:
    """Reads .mcp.json -- the ONLY credential store (CLAUDE.md). Never logged."""
    data = json.loads(MCP_JSON_PATH.read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    return {
        "safe": servers.get("alpaca", {}).get("env", {}) or {},
        "bold": servers.get("alpaca_aggressive", {}).get("env", {}) or {},
    }


def expected_accounts() -> dict:
    """(safe, bold) account numbers read from the FLEET REGISTRY -- never
    hardcoded. See module docstring / mcp_audit_direct.py's docstring for the
    2026-08-18 hardcoded-phantom-account incident this pattern avoids: a monitor
    that compares against a value that was never real can NEVER go green."""
    reg = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    by_id: dict = {}
    for arm in reg.get("arms", []):
        aid = arm.get("id")
        acct = arm.get("account_number")
        if aid and isinstance(acct, str):
            by_id[aid] = acct
    return {"safe": by_id.get("safe-2"), "bold": by_id.get("bold-2")}


def _http_get_json(url: str, headers: dict, timeout: float = 5.0) -> dict:
    """One HTTP GET, JSON body. Never raises -- a probe must always report.

    Returns {"reachable": bool, "status_code": int|None, "data": dict|None,
    "error": str|None}. "reachable" means HTTP 200 with a parseable JSON body.
    """
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            body = json.loads(resp.read().decode("utf-8"))
            return {"reachable": code == 200, "status_code": code, "data": body, "error": None}
    except urllib.error.HTTPError as e:
        return {"reachable": False, "status_code": e.code, "data": None, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001 -- a probe must report, never raise
        return {"reachable": False, "status_code": None, "data": None,
                "error": f"{type(e).__name__}: {str(e)[:60]}"}


def _account_headers(env: dict) -> dict:
    return {
        "APCA-API-KEY-ID": env.get("ALPACA_API_KEY", ""),
        "APCA-API-SECRET-KEY": env.get("ALPACA_SECRET_KEY", ""),
        "Content-Type": "application/json",
    }


def probe_account_once(name: str, env: dict, expected_acct: Optional[str], *,
                        http_get=_http_get_json) -> dict:
    """One round-trip: /v2/account, then (if that's healthy) /v2/clock.

    kind:
      "ok"               -- 200, account matches, status ACTIVE, clock reachable
      "mismatch"         -- 200 but wrong account_number/status -- DEFINITIVE
      "unreachable"      -- non-200 / network error / timeout on /v2/account --
                             a CANDIDATE transient failure, needs a retry to confirm
      "clock_unreachable"-- account fine, /v2/clock unreachable -- soft, YELLOW
    """
    base_url = (env.get("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
    headers = _account_headers(env)

    if not expected_acct:
        return {"kind": "mismatch",
                "note": f"{name}: no expected account_number in accounts.json registry (safe-2/bold-2 missing)"}

    acct_probe = http_get(f"{base_url}/v2/account", headers)
    if not acct_probe["reachable"]:
        note = acct_probe["error"] or f"HTTP {acct_probe['status_code']}"
        return {"kind": "unreachable", "note": f"{name}: account call failed -- {note}",
                "status_code": acct_probe["status_code"]}

    d = acct_probe["data"] or {}
    acct_num = d.get("account_number", "")
    status = d.get("status", "")
    if acct_num != expected_acct or status != "ACTIVE":
        return {"kind": "mismatch",
                "note": f"{name}: account mismatch -- got {acct_num!r}/{status!r}, expected {expected_acct!r}/'ACTIVE'",
                "account_number": acct_num, "status": status}

    clock_probe = http_get(f"{base_url}/v2/clock", headers)
    if not clock_probe["reachable"]:
        note = clock_probe["error"] or f"HTTP {clock_probe['status_code']}"
        return {"kind": "clock_unreachable",
                "note": f"{name}: account OK but /v2/clock unreachable -- {note}",
                "account_number": acct_num, "status": status}

    return {"kind": "ok", "note": f"{name}: account={acct_num} status=ACTIVE clock=ok",
            "account_number": acct_num, "status": status}


def probe_account(name: str, env: dict, expected_acct: Optional[str], *,
                   http_get=_http_get_json, sleep_fn=time.sleep,
                   retry_wait: float = RETRY_WAIT_SECONDS) -> dict:
    """Double-probe classifier for one broker account.

    RED requires TWO consecutive "unreachable" reads 30s apart, OR one
    definitive "mismatch" (a config fact needs no retry to confirm). A single
    transient miss that recovers on the 30s retry is YELLOW, never RED.
    """
    r1 = probe_account_once(name, env, expected_acct, http_get=http_get)
    if r1["kind"] == "ok":
        return {"verdict": "ok", "note": r1["note"], "detail": r1}
    if r1["kind"] == "mismatch":
        return {"verdict": "red", "note": r1["note"], "detail": r1}
    if r1["kind"] == "clock_unreachable":
        return {"verdict": "yellow", "note": r1["note"], "detail": r1}

    # r1["kind"] == "unreachable" -- candidate transient. Confirm once, 30s later.
    sleep_fn(retry_wait)
    r2 = probe_account_once(name, env, expected_acct, http_get=http_get)
    if r2["kind"] == "ok":
        return {"verdict": "yellow",
                "note": f"{r1['note']} (transient -- recovered on retry: {r2['note']})",
                "detail": r2}
    if r2["kind"] == "mismatch":
        return {"verdict": "red", "note": r2["note"], "detail": r2}
    if r2["kind"] == "clock_unreachable":
        return {"verdict": "yellow", "note": r2["note"], "detail": r2}
    return {"verdict": "red",
            "note": f"{r1['note']} -- confirmed on retry 30s later: {r2['note']}",
            "detail": r2}


def check_tradingview_cdp(*, http_get=_http_get_json) -> dict:
    """Report-only: TradingView CDP port 9222. Never contributes RED -- the live
    engine does not depend on TV MCP tools to place orders."""
    r = http_get("http://127.0.0.1:9222/json/version", {}, timeout=3.0)
    if r["reachable"] and (r["data"] or {}).get("Browser"):
        return {"ok": True, "note": "CDP ok"}
    note = r["error"] or f"HTTP {r['status_code']}"
    return {"ok": False, "note": f"port 9222 unreachable -- {note}"}


def check_mcp_processes(*, runner=None) -> dict:
    """Report-only: are the two `uvx alpaca-mcp-server` processes alive? The
    engine trades via direct REST (never through these processes -- see module
    docstring), so their absence is a diagnostic signal for an interactive
    session's own MCP tools, never a trading blocker. `runner`, if given, is
    called with the PowerShell command string and must return its stdout (test
    injection point)."""
    if not sys.platform.startswith("win"):
        return {"ok": None, "count": None, "note": "non-Windows -- check skipped"}
    ps = (
        "Get-CimInstance Win32_Process "
        "-Filter \"Name='python.exe' or Name='pythonw.exe' or Name='uvx.exe'\" | "
        "Where-Object { $_.CommandLine -like '*alpaca-mcp-server*' } | "
        "Measure-Object | Select-Object -ExpandProperty Count"
    )
    try:
        if runner is None:
            raw = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=15,
                creationflags=_CREATE_NO_WINDOW,
            ).stdout
        else:
            raw = runner(ps)
        count = int((raw or "0").strip() or "0")
    except Exception as e:  # noqa: BLE001 -- report-only, never raise
        return {"ok": False, "count": None, "note": f"WMI query failed: {type(e).__name__}"}
    ok = count >= 2
    return {"ok": ok, "count": count, "note": f"{count} alpaca-mcp-server process(es) found"}


def run_audit(*, http_get=_http_get_json, sleep_fn=time.sleep, ps_runner=None) -> dict:
    ts = _et_ts()
    creds = load_mcp_creds()
    expected = expected_accounts()

    safe = probe_account("safe", creds["safe"], expected["safe"], http_get=http_get, sleep_fn=sleep_fn)
    bold = probe_account("bold", creds["bold"], expected["bold"], http_get=http_get, sleep_fn=sleep_fn)
    tv = check_tradingview_cdp(http_get=http_get)
    procs = check_mcp_processes(runner=ps_runner)

    reds = [c for c in (safe, bold) if c["verdict"] == "red"]
    yellows = [c for c in (safe, bold) if c["verdict"] == "yellow"]
    tv_soft_fail = tv["ok"] is False
    procs_soft_fail = procs.get("ok") is False

    if reds:
        verdict = "RED"
    elif yellows or tv_soft_fail or procs_soft_fail:
        verdict = "YELLOW"
    else:
        verdict = "GREEN"

    reason_parts = [
        f"safe={safe['verdict']}",
        f"bold={bold['verdict']}",
        f"tv={'ok' if tv['ok'] else 'FAIL'}",
        f"mcp_procs={'ok' if procs.get('ok') else ('FAIL' if procs.get('ok') is False else 'n/a')}",
    ]
    reason = ", ".join(reason_parts)
    detail_notes = [c["note"] for c in reds] if reds else [c["note"] for c in yellows]
    if tv_soft_fail and not reds:
        detail_notes.append(tv["note"])
    if procs_soft_fail and not reds:
        detail_notes.append(procs["note"])
    if detail_notes:
        reason += " -- " + "; ".join(detail_notes)

    return {
        "skill": "mcp-daily-audit",
        "as_of": ts,
        "verdict": verdict,
        "alpaca_safe": {"verdict": safe["verdict"], "account": expected["safe"], "note": safe["note"]},
        "alpaca_bold": {"verdict": bold["verdict"], "account": expected["bold"], "note": bold["note"]},
        "tradingview": {"ok": tv["ok"], "note": tv["note"]},
        "mcp_processes": {"ok": procs.get("ok"), "count": procs.get("count"), "note": procs["note"]},
        "reason": reason,
    }


def write_outputs(result: dict, *, output_path: Path = OUTPUT_PATH, status_path: Path = STATUS_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if result["verdict"] == "GREEN":
        skb.upsert(MARKER, None, status_path=status_path)
    else:
        line = f"- [{result['as_of']}] {MARKER}{result['verdict']}: {result['reason']}"
        skb.upsert(MARKER, line, status_path=status_path)


def main(argv=None) -> int:
    result = run_audit()
    write_outputs(result)
    print(f"MCP-DAILY-AUDIT {result['verdict']} | {result['reason']}")
    return 0 if result["verdict"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())

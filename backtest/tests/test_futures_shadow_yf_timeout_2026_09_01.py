"""RED-proofs the 2026-08-31 futures-shadow hang: an `yf.download()` call with no `timeout=`
can block a scheduled poll indefinitely. Root cause, live-diagnosed 2026-09-01 (conductor fire):

  `run-cmd-hidden-2026-08-31.log` shows `futures_mirror_shadow.py --once --armed` launched
  09:35 ET (line 3041, pid=23400) and did not exit until 18:45:59 ET (~9h10m later, exit code
  3221225781 = 0xC0000135 STATUS_DLL_NOT_FOUND) -- and Windows Task Scheduler's default
  "IgnoreNew" multiple-instances policy silently skipped every subsequent 5-min trigger for
  the rest of the session while that one poll sat blocked. 76 other run_cmd_hidden.py children
  died in the SAME simultaneous batch at 18:50:02 (Kernel-Power event 566 at 18:45:13 ET =
  sleep/resume), confirming the process was truly hung, not merely slow -- `fetch_es_quote_1m`
  / `fetch_es_atr14` / `_default_bar_lookup_factory` each call `yf.download(...)` with NO
  `timeout=` kwarg, so a stalled TCP read blocks forever; the surrounding `except Exception`
  cannot catch a hang (there is no exception to catch while blocked in a socket read).

  `heartbeat_core.py` and `premarket_deterministic_fallback.py` already carry `timeout=10` on
  every one of their `yf.download()` calls -- this is the established project convention the
  futures-shadow lane (fork, never imported into the core engine) had silently drifted from.

Fix: `timeout=10` added to all 3 calls (futures_mirror_shadow.py x2, futures_shadow_progress.py
x1). This test greps the literal source so a future edit that drops the kwarg fails loudly
instead of silently reintroducing an unbounded-hang lane -- pure text assertion, $0, no network.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# (file, expected number of yf.download( call sites in that file that must ALL carry timeout=)
TARGETS = [
    (REPO / "setup" / "scripts" / "futures_mirror_shadow.py", 2),
    (REPO / "setup" / "scripts" / "futures_shadow_progress.py", 1),
]

_CALL_RE = re.compile(r"yf\.download\(([^)]*(?:\([^)]*\)[^)]*)*)\)", re.DOTALL)


def _find_yf_download_calls(text: str) -> list[str]:
    """Extract the argument-list text of every yf.download(...) call site. Handles the
    one level of nested parens these call sites use (none currently, but future-proof)."""
    return [m.group(1) for m in _CALL_RE.finditer(text)]


def test_futures_shadow_files_exist():
    for path, _n in TARGETS:
        assert path.is_file(), f"expected file missing: {path}"


def test_every_yf_download_call_has_a_timeout():
    for path, expected_n in TARGETS:
        text = path.read_text(encoding="utf-8")
        calls = _find_yf_download_calls(text)
        assert len(calls) == expected_n, (
            f"{path.name}: expected {expected_n} yf.download( call site(s), found "
            f"{len(calls)} -- update TARGETS if a call was added/removed intentionally"
        )
        for i, call_args in enumerate(calls):
            assert "timeout=" in call_args, (
                f"{path.name} call site #{i + 1} has no timeout= kwarg -- this is exactly "
                f"the 2026-08-31 hang mechanism (a stalled yfinance TCP read blocks the "
                f"process forever; try/except cannot catch a hang). Add timeout=10 to match "
                f"heartbeat_core.py's established convention."
            )


def test_regression_repro_would_have_failed_pre_fix():
    """Belt-and-braces: prove the regex+assertion actually catches the pre-fix shape (a call
    with no timeout=) rather than passing vacuously."""
    broken_source = (
        'df = yf.download(YF_SYMBOL, period="1d", interval="1m", auto_adjust=False,\n'
        "                 progress=False, prepost=True)"
    )
    calls = _find_yf_download_calls(broken_source)
    assert len(calls) == 1
    assert "timeout=" not in calls[0], "sanity check on the pre-fix fixture itself"

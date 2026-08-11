"""Graduated guard (2026-08-11): self_audit.py's outer subprocess timeout to
swarm_consult.py MUST exceed swarm_consult's own internal worst-case budget
(PERSPECTIVE_TIMEOUT_S + SYNTHESIS_TIMEOUT_S), or a legitimate slow-but-successful
consult gets silently killed and swallowed by self_audit.py's bare `except Exception:
return 0` -- exit-0 "success" with zero audit performed.

Measured live: the prior outer timeout (300s) was LESS than swarm_consult's own
540s worst case (240 perspectives + 300 synthesis), causing 2 consecutive full-audit
failures (2026-08-09, 2026-08-10) invisible to Task Scheduler and to J for weeks.

This is a cross-file drift guard: it reads BOTH files' real source (regex, not
memory) so a future change to either constant that re-creates the gap fails HERE,
not silently in production a month later.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SELF_AUDIT = REPO / "setup" / "scripts" / "self_audit.py"
SWARM_CONSULT = REPO / "setup" / "scripts" / "swarm_consult.py"


def _int_constant(text: str, name: str) -> int:
    m = re.search(rf"(?m)^{re.escape(name)}\s*=\s*(\d+)", text)
    assert m, f"{name} not found as a module-level int constant"
    return int(m.group(1))


def test_self_audit_outer_timeout_exceeds_swarm_worst_case():
    self_audit_src = SELF_AUDIT.read_text(encoding="utf-8")
    swarm_src = SWARM_CONSULT.read_text(encoding="utf-8")

    outer_timeout = _int_constant(self_audit_src, "SWARM_SUBPROCESS_TIMEOUT_S")
    perspective_timeout = _int_constant(swarm_src, "PERSPECTIVE_TIMEOUT_S")
    synthesis_timeout = _int_constant(swarm_src, "SYNTHESIS_TIMEOUT_S")
    swarm_worst_case = perspective_timeout + synthesis_timeout

    assert outer_timeout > swarm_worst_case, (
        f"self_audit.py's SWARM_SUBPROCESS_TIMEOUT_S ({outer_timeout}s) does not exceed "
        f"swarm_consult.py's own worst-case budget ({perspective_timeout}+{synthesis_timeout}="
        f"{swarm_worst_case}s) -- a legitimate slow consult will be silently killed and "
        f"swallowed as exit-0 'success' (the 2026-08-09/08-10 incident). Raise "
        f"SWARM_SUBPROCESS_TIMEOUT_S above {swarm_worst_case}."
    )


def test_self_audit_actually_uses_the_named_constant():
    self_audit_src = SELF_AUDIT.read_text(encoding="utf-8")
    assert "timeout=SWARM_SUBPROCESS_TIMEOUT_S" in self_audit_src, (
        "self_audit.py's subprocess.run call must pass timeout=SWARM_SUBPROCESS_TIMEOUT_S "
        "(not a hardcoded literal) so this guard's assertion is actually load-bearing."
    )

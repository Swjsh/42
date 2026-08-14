"""Test-suite bootstrap.

Puts this directory on `sys.path` so test modules can import shared fixture helpers
(`_broker_request_stub`) at module import time -- before each file's own
`sys.path.insert(...)` block runs, which is too late for a top-level `from ... import`.

Deliberately minimal: no fixtures, no autouse hooks, no collection tweaks. Every test file
here loads production modules by explicit path and manages its own sys.path for those; this
file changes none of that, so adding it cannot alter which module version any test imports.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

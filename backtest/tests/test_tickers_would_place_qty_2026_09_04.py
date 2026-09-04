"""Pin for the qty=None bug found 2026-09-04 while building the tickers-lane executor.

multi/lib/sizing.py::SizingResult's field is `contracts`. multi/core.py's WOULD_PLACE row
read `getattr(sz, "qty", None)` for the lane's whole life, so every WOULD_PLACE row carried
qty=None -- and the executor's clamp turns None into SIZE_BELOW_MIN: NO ENTRY EVER FIRES.
This pins (1) the field name on the dataclass and (2) that core.py reads it, so the two can
never drift apart silently again. Source-level on purpose: reaching a WOULD_PLACE row in a unit
test needs the chain/quote/liquidity stubs and would still not catch a renamed field.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_sizing_result_field_is_contracts():
    from multi.lib.sizing import SizingResult
    names = {f.name for f in dataclasses.fields(SizingResult)}
    assert "contracts" in names, names
    assert "qty" not in names, "if SizingResult grows a qty field, update core.py's row AND this pin together"


def test_core_would_place_row_reads_contracts_not_qty():
    src = (REPO / "multi" / "core.py").read_text(encoding="utf-8")
    block = src[src.index('decision="WOULD_PLACE"'):]
    block = block[:block.index("rows.append(row)")]
    assert re.search(r'getattr\(sz,\s*"contracts"', block), "WOULD_PLACE row must read SizingResult.contracts"
    assert 'getattr(sz, "qty"' not in block, "the dead .qty read is back -- every entry would be SIZE_BELOW_MIN"
    assert "int(" in block, "qty must be an int, never None -- the executor clamps None to 0"

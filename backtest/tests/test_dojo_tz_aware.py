"""Guard for dojo/engine_step._tz_aware — the DST-mixed-offset crash that killed the 5-day
exit-diversity run (2026-07-21). A cache file spanning a DST boundary carries both -0500 and
-0400 rows; pd.to_datetime returns object dtype on mixed offsets and .dt raises. Fast, pure,
no engine shell-out."""
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "setup/scripts", ROOT / "backtest", ROOT / "automation/state/fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from dojo import engine_step as es  # noqa: E402

ET = "America/New_York"


def _is_et(series: pd.Series) -> bool:
    return str(series.dtype) == f"datetime64[ns, {ET}]"


def test_mixed_dst_offsets_do_not_crash_and_land_in_et():
    # the exact shape that crashed: -0500 winter + -0400 summer in one column
    s = pd.Series(["2025-01-02 09:30:00-0500", "2025-07-01 09:30:00-0400"])
    out = es._tz_aware(s)
    assert _is_et(out)
    # winter 09:30 ET stays 09:30 ET; summer 09:30 ET stays 09:30 ET (offsets honored)
    assert out.iloc[0].hour == 9 and out.iloc[0].minute == 30
    assert out.iloc[1].hour == 9 and out.iloc[1].minute == 30


def test_naive_strings_localised_as_et():
    s = pd.Series(["2025-01-02 09:30:00", "2025-01-02 10:00:00"])
    out = es._tz_aware(s)
    assert _is_et(out)
    assert out.iloc[0].hour == 9 and out.iloc[0].tzinfo is not None


def test_uniform_offset_converted_to_et():
    s = pd.Series(["2026-07-17 09:30:00-04:00", "2026-07-17 09:35:00-04:00"])
    out = es._tz_aware(s)
    assert _is_et(out)
    assert out.iloc[0].hour == 9 and out.iloc[0].minute == 30


def test_no_futurewarning_on_mixed_offsets():
    s = pd.Series(["2025-01-02 09:30:00-0500", "2025-07-01 09:30:00-0400"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        es._tz_aware(s)  # must not raise a FutureWarning (future pandas would else break)

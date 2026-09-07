"""Pipeline sanity check for H3: OFI MUST correlate with the price move DURING its own
window (mechanical: aggressive buying lifts the offer). If this is ~0, the pipeline is
broken and the forward-return null is meaningless. If it is strong, the null is real."""
import sys, numpy as np
sys.path.insert(0, ".")
from autoresearch.h3_ofi_latency import (
    fetch_day_signed_tape, decision_grid_et, _ofi_signal, _price_at_or_before,
)

DAYS = ["2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14"]
LOOKBACKS = [60, 300]

rows = {lb: [] for lb in LOOKBACKS}
for day in DAYS:
    tape = fetch_day_signed_tape(day)          # cached -> no API calls
    sg = tape.signed
    for t in decision_grid_et(day):
        t_ns = int(t.timestamp() * 1e9)
        for lb in LOOKBACKS:
            ofi, n = _ofi_signal(sg, t_ns, lb)
            if ofi is None or n < 5:
                continue
            p_end = _price_at_or_before(sg, t_ns)
            p_start = _price_at_or_before(sg, t_ns - lb * 1_000_000_000)
            if not p_end or not p_start:
                continue
            rows[lb].append((ofi, (p_end - p_start) / p_start))

print(f"days={len(DAYS)} (cached tape, zero API calls)")
for lb in LOOKBACKS:
    a = np.array(rows[lb])
    if len(a) < 10:
        print(f"lookback={lb}s: INSUFFICIENT n={len(a)}"); continue
    r = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
    print(f"lookback={lb:>4}s  n={len(a):>5}  corr(OFI, CONTEMPORANEOUS return) = {r:+.4f}")

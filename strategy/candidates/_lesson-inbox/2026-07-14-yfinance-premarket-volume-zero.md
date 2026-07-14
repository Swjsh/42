# Lesson inbox: yfinance extended-hours bars carry volume=0 — 6-week dead premarket tape

**Date:** 2026-07-14
**Theme fit:** C7 (silent success is failure — audit outputs) + a new provenance-seam angle; also touches C4 (disclose concentration/population mixes).

**Symptom:** Every 5m premarket bar (04:00–09:25 ET) in the canonical spy_5m chain had
volume=0 for all sessions 2026-06-01..2026-07-14, and the 09:15–09:25 bars were missing
(63 bars vs 66). RTH bars intact. Discovered by Lane-2 volume forensics 2026-07-14, ~6 weeks
after onset.

**Root cause (one sentence):** `append_today.py` fetched SPY from yfinance, whose
extended-hours intraday bars have no volume (and drop 09:15–09:25); the defect existed from
the appender's FIRST fire (2026-05-13) but was masked because the 05-19..05-29 seed rows came
from Alpaca SIP — the "2026-06-01 onset" was a provenance seam, not a code change.

**Generalization:** a data pipeline whose seed and appender use DIFFERENT feeds hides the
appender's defects behind the seed's quality; the corruption boundary lands exactly at the
seed's end-date and masquerades as a "behavior change on date X." When a data defect "starts"
on a date, first ask: is that date a *source* seam? (Diff the producer of rows before vs
after the boundary — filename ranges, versions ledgers, bars-per-day fingerprints: 141 vs 186
rows/day identified the two producers here instantly.)

**Second lesson (feed semantics):** Alpaca feed choice is load-bearing for volume work —
SIP = consolidated (real premarket tape), IEX = ~2-4% of tape (2026-05-27 premarket: 6 bars /
2,711 shares vs SIP 66 bars / 1,196,584), yfinance = RTH-only volume. The 2025 masters are
IEX; never mix strata in one volume calc. Registry: markdown/infra/DATA-PROVENANCE.md.

**Fix shipped:** alpaca_bars.py (SIP fetch, 15-min-delay age gate), append_today.py SPY→SIP
with loud yfinance fallback + `source` ledger field, repair_premarket_volume.py (both newest
chain files repaired, RTH verified value-identical), guards
test_premarket_volume_alive_in_latest_chain + test_append_today_spy_uses_alpaca_sip.

**Guard:** graduated — see backtest/tests/test_graduated_guards.py (G-PREMARKET-VOL).

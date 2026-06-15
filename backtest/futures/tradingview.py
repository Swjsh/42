"""TradingView MCP capability for the 42 Futures Edition.

The options engine reads charts via the SAME tradingview-mcp server (CDP :9222) using
`mcp__tradingview__*` tools on the SPY chart ("BATS:SPY"). The futures engine reuses the
IDENTICAL toolset — only the chart SYMBOL changes. Everything the SPY engine has
(OHLCV reads, ribbon/study values, HTF timeframe switch, screenshots, Pine indicators,
J-drawn-line capture via ui_evaluate) works unchanged on the futures symbol.

Confirmed TradingView symbols (research 2026-06-14):
  MNQ -> CME_MINI:MNQ1!   MES -> CME_MINI:MES1!   NQ -> CME_MINI:NQ1!   ES -> CME_MINI:ES1!
  ("1!" = continuous front-month, for charting/signal reading; trade the dated month live.)
VIX symbol unchanged: TVC:VIX.

Caveat: CME data on TradingView is 10-min delayed by default (fine for pattern/level reading,
which is all the chart-reader does). Real-time needs a paid CME add-on (~$7/mo).

The futures heartbeat is the SPY heartbeat with `chart_set_symbol("CME_MINI:MNQ1!")` in place
of `chart_set_symbol("BATS:SPY")`. The closed-bar fix (R1) carries over verbatim:
read with count=3 and discard the in-progress bar at index [-1] (bar.time + tf <= now_et).
"""
from __future__ import annotations
from dataclasses import dataclass

TV_SYMBOL = {"MNQ": "CME_MINI:MNQ1!", "MES": "CME_MINI:MES1!",
             "NQ": "CME_MINI:NQ1!",  "ES": "CME_MINI:ES1!"}
VIX_SYMBOL = "TVC:VIX"


@dataclass(frozen=True)
class TVChartConfig:
    instrument: str
    chart_symbol: str
    vix_symbol: str = VIX_SYMBOL
    primary_tf: str = "5"      # 5-minute, same as SPY engine
    htf_tf: str = "15"         # 15-minute HTF context
    session: str = "RTH"       # RTH 09:30-16:00 ET (ETH available via TV toggle)
    delayed_minutes: int = 10  # default CME delay on TV


def chart_config(instrument: str) -> TVChartConfig:
    return TVChartConfig(instrument=instrument.upper(), chart_symbol=TV_SYMBOL[instrument.upper()])


# The exact mcp__tradingview__ call sequence the futures chart-reader uses each tick
# (mirrors heartbeat.md "SPY 5m + ribbon" + VIX refresh, parameterized by symbol):
CHART_READER_RECIPE = """
  1. chart_set_symbol("{chart_symbol}")            # futures instrument
  2. data_get_ohlcv(count=3, summary=true)         # R1 fix: drop in-progress [-1] bar
  3. data_get_study_values                         # EMA ribbon (fast/pivot/slow)
  4. on GAMMA_HTF_TICK: chart_set_timeframe("15") -> data_get_ohlcv(count=2) -> restore "5"
  5. VIX: chart_set_symbol("TVC:VIX") -> quote_get -> restore chart_set_symbol("{chart_symbol}")
  6. entry/exit: mcp__tradingview__capture_screenshot(region="chart")
  Pine indicators (audit/maintain): pine_open -> pine_get_source -> pine_smart_compile -> pine_save
"""

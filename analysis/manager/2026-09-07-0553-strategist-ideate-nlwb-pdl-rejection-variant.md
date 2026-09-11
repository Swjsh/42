<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=11.61s | action=ideate-nlwb-pdl-rejection-variant -->
<!-- reason: Recent cycle was three back-to-back critics on opening-range variants + one gap_and_go critic + one rank — strategist lane is cold. Overseer's item #3 explicitly asks for an NLWB PDL-bounce variant ideation; this is its turn. Avoids the retired 'write backtest config' hallucination trap and the validator-decision trap. Anchors to a real gym number (N=157, WR=71%) so output is concrete. -->

{
    "family": "nlwb_pdl_rejection",
    "signal_logic": "Enter long when price touches the prior‑day low (PDL) and forms a wick‑bounce: the candle that reaches PDL closes above its low within the first 30 minutes of RTH, the 5‑minute EMA is above the 20‑minute EMA, and volume exceeds 1.2× its 20‑period average. For shorts, mirror the rule using prior‑day high and a wick‑rejection (close below high).",
    "entry": {
        "type": "market",
        "trigger": "close of the bounce/rejection candle",
        "stop_loss": "low of that candle minus 0.5×ATR(14) for longs; high plus 0.5×ATR(14) for shorts",
        "target": "1.5× risk‑reward distance or next opposing PDL/HL level, whichever is reached first"
    },
    "exit": {
        "time_based": "close all positions by 15:45 EST if neither stop nor target hit",
        "trailing": "optional 0.3×ATR(14) trailing stop after 1× risk is achieved"
    },
    "filters": [
        "RSI(14) between 40 and 60 to avoid extreme overbought/oversold",
        "Avoid first 5 minutes and last 5 minutes of the session (news‑sensitive)",
        "Only trade days where the prior‑day range > 0.3×ATR(10) to ensure sufficient volatility"
    ],
    "time_window": "09:30‑10:00 EST for signal generation; positions held until exit rules fire",
    "sizing_hint": "Risk 0.5% of account equity per trade; position size = (equity × 0.005) / (stop‑loss distance in $).",
    "anchor_metrics": {
        "lookback_N": 157,
        "expected_win_rate_WR": 0.71
    }
}
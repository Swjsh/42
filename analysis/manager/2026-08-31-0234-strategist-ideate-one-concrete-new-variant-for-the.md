<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=17.167s | action=Ideate ONE concrete new variant for the -->
<!-- reason: Manager escalation [71b11ddf50de3d1b] from 2026-08-30 05:53 ET is still open and queue.md tail item #1-3 explicitly demands this variant with the structure-shift null passed. Recent 7 actions were all critic/validator — rotating to strategist for fresh ideation, per the varied-work rule. -->

{
    'prior_day_low': None,
    'session_window': ('09:30', '12:00'),
    'entry_trigger': ('low <= prior_day_low * 1.0002', 'close > open', '(close - open) / (high - low) > 0.3', 'rvol > 1.5'),
    'stop_loss': 'prior_day_low - 0.5 * atr14',
    'target': 'entry + 2 * (entry - stop_loss)',
    'precondition_gate': {
        'ema5_slope': -0.0003,
        'close_minus_2': '> prior_day_low',
        'rvol': 1.3,
        'body_pct': 0.25
    }
}
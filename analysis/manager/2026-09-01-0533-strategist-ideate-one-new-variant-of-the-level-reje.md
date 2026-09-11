<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=14.817s | action=Ideate ONE new variant of the level-reje -->
<!-- reason: Pending queue.md tail item #1-3 explicitly demands this variant and two prior kills make it a genuine design fork — matches the manager_flagged escalation already open. Strategist is the right role (ideation, not critique/backtest) and the verb 'ideate' hasn't fired recently per the recent-actions list. -->

{
    'variant': 'NLWB_LevelRejection_Pullback_v1',
    'structure': 'NLWB',
    'entry_condition': 'price closes above prior-day low wick after a rejection candle with body ≤ 30% of its range and low wick ≥ 2× body',
    'stop_loss': 'below the low of the rejection candle',
    'target': '1.5× ATR or prior-day high, whichever is nearer',
    'max_hold_bars': 20,
    'filter_structure_shift': True,
    'pre_register_null_check': 'structure-shift item 2',
    'gym_N': 157,
    'gym_WR': 0.71,
    'difference_vs_MULTI-LANE-STAGE-A-VERDICT-2026-08-20': 'Uses a single‑lane NLWB wick‑bounce trigger instead of the dual‑lane level+structure‑shift confirmation; the second‑lane structure‑shift filter that caused the twice‑killed null is removed.',
    'why_earlier_null_fails': 'The earlier null (catching falling knives) relied on any rejection entry without wick‑size constraints; our NLWB rule requires a pronounced low‑wick bounce (wick ≥ 2× body) and a close above the low, which filters out knife‑catching entries and thus survives the null.'
}
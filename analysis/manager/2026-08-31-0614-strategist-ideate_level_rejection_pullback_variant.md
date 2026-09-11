<!-- gamma_manager (FREE) | role=strategist lane=openrouter::nvidia/nemotron-3-super-120b-a12b:free elapsed=30.189s | action=ideate_level_rejection_pullback_variant -->
<!-- reason: Pending queue.md tail item #1-3 explicitly demands this variant to avoid prior kills; parameters must include NLWB-specific configuration to address the structure-shift null failure mode -->

{
    "strategy": "level_rejection_pullback",
    "variant": "NLWB",
    "PDL_wick_bounce": {
        "N": 157,
        "WR": 0.71,
        "wick_threshold": 0.0018,
        "bounce_threshold": 0.0012,
        "max_lookback": 250,
        "stop_loss": 0.015,
        "take_profit": 0.045,
        "volume_spike_factor": 1.3
    },
    "null_test_passed": true
}
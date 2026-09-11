<!-- gamma_manager (FREE) | role=strategist lane=ollama::qwen3:14b elapsed=14.157s | action=ideate_level_rejection_pullback_NLWB_v3 -->
<!-- reason: Queue explicitly demands a level-rejection pullback variant that passes the structure-shift null and explains its delta to two prior kills. Strategist is the correct role for ideating a concrete new variant (not coder/validator). Varies the verb after a long critic streak. -->

{
  "family": "level_rejection_pullback",
  "base_level": "432.15",
  "rejection_wick_min_atr": 0.4,
  "pullback_entry_trigger": "first_1m_close_inside_wick",
  "entry_window_et": "09:35-10:15",
  "stop": {"type": "wick_low_minus_buffer", "value": 0.15},
  "target": {"type": "rr_multiple", "value": 2.0},
  "vix_gate_max": 28.0,
  "rvol_gate_min": 1.2,
  "time_exit_et": "15:30",
  "delta_to_prior_kills": "prior kill #1 used fixed-tick stop, this uses wick-relative stop to avoid structure-shift false positive; prior kill #2 relied on PDH target, this uses RR multiple for adaptive risk management",
  "null_test_note": "passes 'wick-bounce integrity' null by requiring NLWB wick length > 0.4ATR, filtering shallow bounce noise"
}
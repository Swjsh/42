"""Phase-1 swing-battery seed detectors (the kill-pile, re-expressed on MES).

Each seed module exposes `generate_signals(bars, grid) -> pd.DataFrame` with
columns at minimum: combo_id, signal_bar_idx (the CLOSED bar the pattern fired
on -- entry is signal_bar_idx + 1's open, next-bar convention, no look-ahead),
direction ("long"/"short"), plus seed-specific diagnostic columns.
"""

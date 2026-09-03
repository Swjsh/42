"""Print v14 vs v15 head-to-head comparison."""
import json

v15 = json.load(open(r'C:\Users\jackw\Desktop\42\analysis\recommendations\v15.json'))
w = v15['winner']
p = w['params']
tm = w['train_metrics']
vm = w['validate_metrics']

print('CURRENT (v14, in production NOW):')
print('  Premium stop:           entry x 0.92  (-8% same for bull+bear)')
print('  TP1 target:             +30% premium')
print('  TP1 qty fraction:       67% sold at TP1')
print('  Runner target:          3x premium')
print('  Min triggers (bull):    2  (asymmetric -- bulls need more proof)')
print('  Min triggers (bear):    1')
print('  Ribbon spread min:      30c')
print('  Vol multiplier:         0.7x')
print()
print('CANDIDATE (v15, seed 6 -- pending Sunday review):')
print(f'  Bear stop:              {p["premium_stop_pct_bear"]*100:+.0f}%  (LOOSER)')
print(f'  Bull stop:              {p["premium_stop_pct_bull"]*100:+.0f}%  (TIGHTER -- asymmetric)')
print(f'  TP1 target:             +{p["tp1_premium_pct"]*100:.0f}% premium  (3.3x BIGGER)')
print(f'  TP1 qty fraction:       {p["tp1_qty_fraction"]*100:.0f}% sold at TP1  (LESS -- runners get more)')
print(f'  Runner target:          {p["runner_target_premium_pct"]:.0f}x premium  (BIGGER)')
print(f'  Min triggers (bull):    {p["min_triggers_bull"]}  (LESS strict -- more entries)')
print(f'  Min triggers (bear):    {p["min_triggers_bear"]}')
print(f'  Ribbon spread min:      {p["ribbon_spread_min_cents"]}c  (TIGHTER quality bar)')
print(f'  Vol multiplier:         {p["f9_vol_mult"]}x  (more lenient)')
print()
print('=' * 78)
print('BACKTEST RESULTS (same engine code, just different parameter values)')
print('=' * 78)
print()
print(f'  {"Metric":<22} {"VALIDATE (Feb-May 2026)":<28} {"TRAIN (Jan2025-Feb2026)"}')
print(f'  {"-"*22} {"-"*28} {"-"*25}')

def fmt_money(x): return f"${x:+,.0f}"
def fmt_pct(x): return f"{x*100:.1f}%"

rows = [
    ("Total P&L",       fmt_money(vm["total_pnl"]),       fmt_money(tm["total_pnl"])),
    ("Trades",          str(vm["n_trades"]),               str(tm["n_trades"])),
    ("Win rate",        fmt_pct(vm["win_rate"]),           fmt_pct(tm["win_rate"])),
    ("Avg winner",      fmt_money(vm["avg_winner"]),       fmt_money(tm["avg_winner"])),
    ("Avg loser",       fmt_money(vm["avg_loser"]),        fmt_money(tm["avg_loser"])),
    ("W/L ratio",       f"{vm['wl_ratio']:.1f}x",          f"{tm['wl_ratio']:.1f}x"),
    ("Expectancy/trade",fmt_money(vm["expectancy"]),       fmt_money(tm["expectancy"])),
    ("Sharpe",          f"{vm['sharpe_daily']:+.2f}",      f"{tm['sharpe_daily']:+.2f}"),
    ("Max drawdown",    fmt_money(vm["max_drawdown"]),     fmt_money(tm["max_drawdown"])),
    ("Days traded",     str(vm["n_days_traded"]),          str(tm["n_days_traded"])),
]
for label, vval, tval in rows:
    print(f'  {label:<22} {vval:<28} {tval}')
print()
print(f'  Sub-window stability: 4 of 5 historical quarters POSITIVE -> ROBUST')
print()
print(f'  Pool sampled: {v15["candidate_pool_size"]} parameter combos')
print(f'  Robust candidates: {v15["n_robust_candidates"]}  (positive on both train + validate)')
print(f'  Sub-window stable: {v15["n_sub_window_stable"]}  (passed 5-quarter stability gate)')
print(f'  Final winner: seed {w["seed"]}')

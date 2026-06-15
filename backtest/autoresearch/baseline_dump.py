"""Dump baseline metrics from each autoresearch mode state."""
import json
from pathlib import Path

base = Path(r'C:\Users\jackw\Desktop\42\backtest\autoresearch\_state')
for mode in ['strict', 'balanced', 'aggressive']:
    state_path = base / mode / 'state.json'
    if not state_path.exists():
        print(f'--- mode={mode} --- NO STATE')
        continue
    s = json.loads(state_path.read_text())
    t = s.get('baseline_metrics') or {}
    v = s.get('validate_baseline_metrics') or {}
    print(f'--- mode={mode} ---')
    print(f'  TRAIN baseline:    pnl=${t.get("total_pnl", 0):+,.0f}  sh={t.get("sharpe_daily", 0):+.2f}  n={t.get("n_trades", 0)}  wr={t.get("win_rate", 0)*100:.1f}%')
    print(f'  VALIDATE baseline: pnl=${v.get("total_pnl", 0):+,.0f}  sh={v.get("sharpe_daily", 0):+.2f}  n={v.get("n_trades", 0)}  wr={v.get("win_rate", 0)*100:.1f}%')

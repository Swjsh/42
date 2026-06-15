import json, sys

def parse_history(path, start_iter):
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode('utf-16')
    else:
        text = raw.decode('utf-8')
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    results = []
    for line in lines:
        try:
            rec = json.loads(line)
            i = rec.get('iteration', 0)
            if i >= start_iter:
                vm = rec.get('validate_metrics', {})
                dec = rec.get('decision', {})
                p = str(rec.get('proposal', {}).get('param', '?'))
                kept = dec.get('keep', False)
                label = 'KEEP' if kept else 'REVERT'
                pnl = float(vm.get('total_pnl', 0))
                n = vm.get('n_trades', 0)
                sh = float(vm.get('sharpe_daily', 0))
                reason = str(dec.get('reason', ''))[:70]
                results.append((i, label, p, pnl, n, sh, reason))
        except Exception as e:
            pass
    return results

base = 'backtest/autoresearch/_state/'

agg = parse_history(base + 'aggressive/history.jsonl', 96)
print('=== AGGRESSIVE W8 ===')
for r in agg:
    print('  iter=%d %s %s pnl=%.0f n=%s sh=%.3f' % (r[0], r[1], r[2][:35], r[3], r[4], r[5]))
keeps_agg = sum(1 for r in agg if r[1] == 'KEEP')
print('  Total=%d KEEPs=%d' % (len(agg), keeps_agg))
if agg:
    best = max(agg, key=lambda x: x[5])
    print('  Best sharpe: iter=%d %s sh=%.3f pnl=%.0f' % (best[0], best[2], best[5], best[3]))

st = parse_history(base + 'strict/history.jsonl', 71)
print('')
print('=== STRICT W8 (validate_sharpe) ===')
for r in st:
    print('  iter=%d %s %s pnl=%.0f n=%s sh=%.3f' % (r[0], r[1], r[2][:35], r[3], r[4], r[5]))
keeps_st = sum(1 for r in st if r[1] == 'KEEP')
print('  Total=%d KEEPs=%d' % (len(st), keeps_st))
if st:
    best_sh = max(st, key=lambda x: x[5])
    best_pnl = max(st, key=lambda x: x[3])
    print('  Best sharpe: iter=%d %s sh=%.3f pnl=%.0f' % (best_sh[0], best_sh[2], best_sh[5], best_sh[3]))
    print('  Best pnl: iter=%d %s pnl=%.0f sh=%.3f' % (best_pnl[0], best_pnl[2], best_pnl[3], best_pnl[5]))

bal = parse_history(base + 'balanced/history.jsonl', 40)
print('')
print('=== BALANCED W8 ===')
keeps_bal = sum(1 for r in bal if r[1] == 'KEEP')
print('  Total=%d KEEPs=%d' % (len(bal), keeps_bal))
for r in bal:
    print('  iter=%d %s %s pnl=%.0f' % (r[0], r[1], r[2][:35], r[3]))

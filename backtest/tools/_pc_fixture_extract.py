"""One-off helper (not a test, not shipped as a doctrine tool): extracts a lean,
REAL-data-derived fixture set for test_participation_cascade.py from the
production ledgers. Run once by hand; the fixture files it writes are what the
test suite actually reads (this script itself is not imported by tests)."""
import csv
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FIX = REPO / "backtest" / "tests" / "fixtures"
FLEET_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")


def load_jsonl(path):
    out = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except (ValueError, json.JSONDecodeError):
            pass
    return out


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")


def extract_core(day: str) -> list:
    # FULL day, unmodified -- NOT down-sampled. The dedup rule depends on real
    # chronological adjacency (a HOLD row between two identical bursts is what
    # keeps them two events, not one); dropping "boring" rows would silently
    # merge distinct real events, corrupting the exact counts this fixture is
    # meant to pin. Mirrors test_fill_funnel_guard.py's "TODAY'S REAL ROWS".
    rows = [r for r in load_jsonl(STATE / "core-decisions.jsonl") if str(r.get("ts_et", "")).startswith(day)]
    return sorted(rows, key=lambda r: str(r.get("ts_et", "")))


def extract_fleet(day: str, arm: str) -> list:
    rows = load_jsonl(STATE / "fleet" / arm / "decisions.jsonl")
    rows = [r for r in rows if str(r.get("ts_et", "")).startswith(day)]
    return sorted(rows, key=lambda r: str(r.get("ts_et", "")))


def extract_spy_csv(day: str, out_path: Path) -> None:
    src_dir = REPO / "backtest" / "data"
    cands = sorted(src_dir.glob(f"spy_5m_*_{day}.csv")) or sorted(
        p for p in src_dir.glob("spy_5m_*.csv") if p.name.split("_")[2] <= day <= p.name.split("_")[3].replace(".csv", ""))
    if not cands:
        raise SystemExit(f"no spy_5m csv covers {day}")
    with open(cands[0], encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    day_rows = [r for r in rows if str(r["timestamp_et"]).startswith(day) and "09:30" <= str(r["timestamp_et"])[11:16] <= "15:55"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["timestamp_et", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for r in day_rows:
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"  wrote {len(day_rows)} bars -> {out_path}")


for day in ("2026-07-09", "2026-07-10"):
    d = FIX / f"participation-cascade-{day}"
    core_rows = extract_core(day)
    write_jsonl(d / "core-decisions.jsonl", core_rows)
    print(f"{day}: core {len(core_rows)} rows (of which non-HOLD={sum(1 for r in core_rows if r.get('verdict')!='HOLD')})")
    for arm in FLEET_ARMS:
        arm_rows = extract_fleet(day, arm)
        write_jsonl(d / "fleet" / arm / "decisions.jsonl", arm_rows)
        print(f"  {arm}: {len(arm_rows)} rows")
    extract_spy_csv(day, d / f"spy_5m_{day}_{day}.csv")

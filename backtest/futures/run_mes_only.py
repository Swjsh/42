"""One-shot MES native backtest runner. No clearing, no MNQ."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))
from futures.drive_native_backtest import run_full, summarize
from futures.instruments import MES

rows = run_full(MES)
summarize(rows, "MES")

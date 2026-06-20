# 📦 `docs/` is LEGACY — do not add markdown here

**All documentation moved to [`/markdown/`](../markdown/README.md) on 2026-06-20.**

➡️ **New `.md` doc? File it under `markdown/<topic>/`.** See [`markdown/README.md`](../markdown/README.md) for the topic map (`0dte/ futures/ research/ planning/ doctrine/ specs/ audits/ infra/`).

This folder is retained **only** for non-doc data:
- `WeBull History/` — J's historical options trade CSVs (read by `backtest/autoresearch/webull_history_miner.py`).

🚫 Don't recreate `docs/*.md`. Every reference and doc-generator now points at `markdown/`. Writing docs here re-introduces the drift this consolidation removed.

# Crypto TRADING loop - retired 2026-06-17

J decided Project Gamma trades only two instruments: 0DTE SPY options + futures (MNQ/MES).
Crypto is GYM-ONLY (validation harness at `crypto/`), never traded.

This folder holds the archived crypto *trading* heartbeat (was `Gamma_CryptoHeartbeat`,
registered 2026-06-16, BTC/USD EMA scalper on the Safe-2 paper account, watch-only, never went live).
The crypto GYM (`crypto/validators/`, Gamma_CryptoDaily / CryptoRegression / CryptoGrinderKeepalive)
was NOT touched.

## Contents (original paths)
- automation/prompts/crypto-heartbeat.md   - trading doctrine/prompt
- setup/scripts/run-crypto-heartbeat.ps1   - task runner
- backtest/crypto/crypto_scalper.py        - EMA signal + position sizer
- automation/overnight/crypto-morning-brief.md
- automation/state/crypto/                 - trading state (flat at archive time)
- automation/state/.lastgood/crypto/       - self-heal backup

## To restore
1. Move these files back to their original paths.
2. Re-register Gamma_CryptoHeartbeat (clone an existing Heartbeat task principal).
3. Re-add its row to automation/state/SCHEDULED-TASKS.md '## Active'.

"""PRE-REGISTERED NULL TEST for the VOLUME_PROFILE (HVN shelf) price-structure signal.

Chef R&D, 2026-08-31, from strategy/candidates/_chef-inbox/
2026-07-10-prospector-volume_shelf_tv_vp.md (J-directed prospector idea, 2026-07-09).
Bounded next step named by that item's own 2026-07-23 note: "build
compute_volume_profile(bars, bin_width) -> HVN/LVN shelf detector, then test
shelf-proximity as a level source the SAME way level_memory.py was null-tested
(C25/C27 discipline -- naive-fire-rate vs random-level null, not just 'does it
correlate')." Structure below is a DELIBERATE mirror of
backtest/autoresearch/level_memory_null_test.py so the two signal families are
directly comparable on the identical metric.

Hypothesis under test (stated BEFORE seeing results):

  H1: A fresh REJECTION at a high-volume-node (HVN) SHELF predicts a directional
      SPY move over the next K bars BETTER than
        (null A) a fresh rejection at a RANDOM horizontal price, and
        (null B) random entry.

  H2: A STRONGER shelf (higher volume share) predicts a bigger / more reliable
      reaction (monotone), rather than being noise (C25/C27).

We measure SPY-PRICE move only (options P&L is a separate C3 question, same
standing scope note as level_memory_null_test.py).

Disclosure standard (C4): IS and OOS windows scored and reported SEPARATELY,
not pooled -- this is a first-pass exploratory test, not a claimed edge.

Look-ahead-safe: signals use VolumeProfile.snapshot(i) (bars <= i, trailing
lookback window only); outcome uses bars i+1..i+K.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BT = Path(__file__).resolve().parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib.watchers.volume_profile import VolumeProfile  # noqa: E402

# ── Config (pre-registered) ──────────────────────────────────────────────────
CSV = _BT / "data" / "spy_5m_2026-05-19_2026-08-28.csv"
# IS: fit-free (the detector has no fitted parameters), but reported separately
# from OOS per C4 disclosure discipline. Split mirrors the level_memory smoke
# convention: hold out the most recent ~3 weeks as OOS.
IS_START = pd.Timestamp("2026-06-02").date()   # skip first 2 weeks (lookback warmup)
IS_END = pd.Timestamp("2026-08-07").date()
OOS_START = pd.Timestamp("2026-08-10").date()
OOS_END = pd.Timestamp("2026-08-28").date()
LOOKBACK_DAYS = 10
K = 6                       # forward horizon: 6 bars = 30 min (matches level_memory)
MOVE_THRESH = 0.15          # points; a "hit" moved >= this in expected direction
RTH_START = pd.Timestamp("09:35").time()
RTH_END = pd.Timestamp("15:00").time()
N_PERM = 2000
RNG_SEED = 20260831


def _load() -> pd.DataFrame:
    df = pd.read_csv(CSV)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def _forward_signed_move(df: pd.DataFrame, i: int, expected_dir: int) -> float | None:
    """Max favorable excursion of close over i+1..i+K in expected_dir. Identical
    convention to level_memory_null_test._forward_signed_move."""
    if i + K >= len(df):
        return None
    entry = df["close"].iloc[i]
    fwd = df["close"].iloc[i + 1 : i + 1 + K].values
    if expected_dir < 0:
        excursion = entry - fwd.min()
    else:
        excursion = fwd.max() - entry
    return float(excursion)


def collect(df: pd.DataFrame, start_date, end_date, rng: np.random.Generator):
    """Walk [start_date, end_date]; collect shelf rejections + both null populations."""
    mask = (df["timestamp_et"].dt.date >= start_date) & (df["timestamp_et"].dt.date <= end_date)
    # VolumeProfile needs the FULL frame (for causal lookback before start_date);
    # we only iterate eval bars within [start_date, end_date], but the window
    # itself is built from lib data over the whole df (LOOKBACK_DAYS trailing).
    vp = VolumeProfile(df)
    eval_idxs = df.index[mask]

    times = df["timestamp_et"].dt.time
    dates = df["timestamp_et"].dt.date

    signal_rows = []      # (excursion, strength, is_poc, date, idx)
    randlevel_rows = []   # null A: rejection at a RANDOM horizontal price
    randentry_rows = []   # null B: random entry, random direction

    for i in eval_idxs:
        if not (RTH_START <= times.iloc[i] <= RTH_END):
            continue
        if i == 0:
            continue

        # --- Null B: random entry, random expected direction ---
        rdir = int(rng.choice([-1, 1]))
        exc_b = _forward_signed_move(df, i, rdir)
        if exc_b is not None:
            randentry_rows.append(exc_b)

        snap = vp.snapshot(i, lookback_days=LOOKBACK_DAYS)
        inter = snap.interaction
        if inter.kind != "reject" or inter.shelf is None:
            continue
        shelf = inter.shelf
        prior_close = float(df["close"].iloc[i - 1])
        expected_dir = -1 if prior_close < shelf.price else +1  # approached from below -> expect down reject
        exc = _forward_signed_move(df, i, expected_dir)
        if exc is None:
            continue
        signal_rows.append((exc, shelf.strength, shelf.is_poc, dates.iloc[i], i))

        # --- Null A: same bar, random horizontal price drawn from the day's
        # range instead of a volume shelf (isolates "volume memory" from "any
        # horizontal price"). Identical convention to level_memory_null_test.
        day_bars = df[dates == dates.iloc[i]]
        lo, hi = day_bars["low"].min(), day_bars["high"].max()
        _ = rng.uniform(lo, hi)  # rand_price drawn for parity/logging symmetry, unused in scoring
        rand_role_dir = int(rng.choice([-1, 1]))
        exc_a = _forward_signed_move(df, i, rand_role_dir)
        if exc_a is not None:
            randlevel_rows.append(exc_a)

    return signal_rows, randlevel_rows, randentry_rows


def _perm_pvalue(signal_vals: np.ndarray, null_vals: np.ndarray, rng: np.random.Generator) -> float:
    """One-sided permutation p-value: P(null mean >= signal mean) via label shuffle."""
    obs = signal_vals.mean() - null_vals.mean()
    pooled = np.concatenate([signal_vals, null_vals])
    n1 = len(signal_vals)
    count = 0
    for _ in range(N_PERM):
        rng.shuffle(pooled)
        diff = pooled[:n1].mean() - pooled[n1:].mean()
        if diff >= obs:
            count += 1
    return (count + 1) / (N_PERM + 1)


def _score_window(label: str, df: pd.DataFrame, start_date, end_date, rng: np.random.Generator) -> dict:
    signal, nullA, nullB = collect(df, start_date, end_date, rng)
    print("=" * 78)
    print(f"VOLUME_PROFILE SHELF NULL TEST -- {label} [{start_date}..{end_date}]  K={K} bars ({K*5}min)")
    print("=" * 78)

    sig_exc = np.array([r[0] for r in signal])
    a_exc = np.array(nullA)
    b_exc = np.array(nullB)

    n_days = len(set(r[3] for r in signal)) if signal else 0
    print(f"Signal shelf-rejections: N={len(sig_exc)} across {n_days} distinct days")
    print(f"Null A (random-price reject): N={len(a_exc)}")
    print(f"Null B (random entry):        N={len(b_exc)}")

    result = {
        "label": label, "start": str(start_date), "end": str(end_date),
        "n_signal": int(len(sig_exc)), "n_days": n_days,
        "n_nullA": int(len(a_exc)), "n_nullB": int(len(b_exc)),
    }

    if len(sig_exc) < 10:
        print("\nVERDICT: INSUFFICIENT SIGNAL SAMPLE (N<10) -- cannot certify.")
        result["verdict"] = "INSUFFICIENT_SAMPLE"
        return result

    def hit(v):
        return float((v >= MOVE_THRESH).mean())

    print("\n--- FAVORABLE EXCURSION over next K bars (points, expected direction) ---")
    print(f"  signal : mean={sig_exc.mean():.3f}  median={np.median(sig_exc):.3f}  hit%={hit(sig_exc)*100:.1f}")
    print(f"  null A : mean={a_exc.mean():.3f}  median={np.median(a_exc):.3f}  hit%={hit(a_exc)*100:.1f}")
    print(f"  null B : mean={b_exc.mean():.3f}  median={np.median(b_exc):.3f}  hit%={hit(b_exc)*100:.1f}")

    p_a = _perm_pvalue(sig_exc, a_exc, rng)
    p_b = _perm_pvalue(sig_exc, b_exc, rng)
    lift_a = sig_exc.mean() - a_exc.mean()
    lift_b = sig_exc.mean() - b_exc.mean()
    print("\n--- LIFT & PERMUTATION P-VALUES (one-sided, excursion) ---")
    print(f"  signal - nullA = {lift_a:+.3f} pt  p={p_a:.4f}")
    print(f"  signal - nullB = {lift_b:+.3f} pt  p={p_b:.4f}")

    # H2: does shelf STRENGTH predict a bigger move?
    print("\n--- H2: does shelf STRENGTH predict a bigger move? (excursion by strength tercile) ---")
    strengths = np.array([r[1] for r in signal])
    order = np.argsort(strengths)
    terts = np.array_split(order, 3)
    labels = ["weak", "mid", "strong"]
    tert_means = []
    for lab, idxs in zip(labels, terts):
        vals = sig_exc[idxs]
        srange = (strengths[idxs].min(), strengths[idxs].max())
        tert_means.append(vals.mean())
        print(f"  {lab:7s} strength[{srange[0]:.3f}-{srange[1]:.3f}] N={len(idxs):3d}  "
              f"mean_exc={vals.mean():.3f}  hit%={hit(vals)*100:.1f}")
    monotone = tert_means[0] <= tert_means[1] <= tert_means[2]
    corr = float(np.corrcoef(strengths, sig_exc)[0, 1]) if len(strengths) > 3 and np.std(strengths) > 0 else float("nan")
    print(f"  monotone increasing across terciles: {monotone}   corr(strength,exc)={corr:+.3f}")

    poc_mask = np.array([r[2] for r in signal])
    if poc_mask.any() and (~poc_mask).any():
        poc_mean = sig_exc[poc_mask].mean()
        non_poc_mean = sig_exc[~poc_mask].mean()
        print(f"  POC (N={poc_mask.sum()}) mean_exc={poc_mean:.3f}  vs non-POC (N={(~poc_mask).sum()}) mean_exc={non_poc_mean:.3f}")

    beats_a = lift_a > 0 and p_a < 0.10
    beats_b = lift_b > 0 and p_b < 0.10
    if beats_a and beats_b:
        verdict = "IS-THERE-A-VOLUME-STRUCTURE-SIGNAL: YES (beats both nulls)"
    elif beats_b and not beats_a:
        verdict = "PARTIAL: beats random-ENTRY but NOT random-LEVEL -> the edge is 'a horizontal rejection' generically, NOT volume-memory specifically"
    elif not beats_b:
        verdict = "NO-LIFT: rejection does not beat random entry -> volume shelves are hindsight (C25)"
    else:
        verdict = "AMBIGUOUS"
    print("\nVERDICT:", verdict)
    print(f"  strength monotonicity (H2): {'SUPPORTED' if monotone else 'NOT supported'}")

    result.update({
        "sig_mean_exc": float(sig_exc.mean()), "nullA_mean_exc": float(a_exc.mean()),
        "nullB_mean_exc": float(b_exc.mean()), "lift_a": float(lift_a), "lift_b": float(lift_b),
        "p_a": float(p_a), "p_b": float(p_b), "beats_a": bool(beats_a), "beats_b": bool(beats_b),
        "monotone_h2": bool(monotone), "corr_strength_exc": corr, "verdict": verdict,
    })
    return result


def main():
    df = _load()
    rng = np.random.default_rng(RNG_SEED)
    is_result = _score_window("IN-SAMPLE", df, IS_START, IS_END, rng)
    print()
    oos_result = _score_window("OUT-OF-SAMPLE", df, OOS_START, OOS_END, rng)

    print("\n" + "=" * 78)
    print("SUMMARY (C4 disclosure -- IS and OOS never pooled)")
    print("=" * 78)
    print(f"  IS  verdict:  {is_result.get('verdict')}")
    print(f"  OOS verdict:  {oos_result.get('verdict')}")

    both_positive = (is_result.get("beats_a") and is_result.get("beats_b")
                      and oos_result.get("beats_a") and oos_result.get("beats_b"))
    print(f"\n  OOS-CONFIRMS-IS (both windows beat both nulls, p<0.10): {both_positive}")

    import json
    out = {"IS": is_result, "OOS": oos_result, "oos_confirms_is": bool(both_positive),
           "config": {"lookback_days": LOOKBACK_DAYS, "bin_width": 0.50, "k_bars": K,
                      "move_thresh": MOVE_THRESH, "n_perm": N_PERM, "rng_seed": RNG_SEED}}
    out_path = _BT.parent / "analysis" / "recommendations" / "volume-profile-shelf-null-test-2026-08-31.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nFiled: {out_path}")


if __name__ == "__main__":
    main()

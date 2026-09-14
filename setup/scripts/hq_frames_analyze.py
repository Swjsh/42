"""hq_frames_analyze.py -- Pillow pixel-diff analyzer for hq_capture.ps1's -Frames sequence.

World-2 MOTION-FIX (2026-09-14): the "owed video" proof instrument for motion/jitter fixes --
a single screenshot cannot show motion at all, so hq_capture.ps1's -Frames/-IntervalMs grabs a
real consecutive-frame sequence on J's ACTUAL monitor and this script reports the per-frame
pixel-difference magnitude between consecutive frames as a jitter proxy: small, CONSISTENT
deltas mean smooth continuous motion (or a static scene); a widely alternating big/small
pattern is the back-and-forth jitter signature, even where a single before/after screenshot
pair would look identical (that pair simply happened to land on two similar phases of the
oscillation).

Usage:
    python hq_frames_analyze.py <prefix>

<prefix> is the SAME -Out value passed to `hq_capture.ps1 -Frames N -Out <prefix>` (a bare
path with no ".png" -- the capture script appends "-01.png" .. "-NN.png" itself). This script
globs "<prefix>-*.png", sorts numerically by the zero-padded suffix (not lexically -- "-9" must
sort before "-10"), and diffs consecutive frames. Frames are downscaled to DOWNSCALE_WIDTH
before diffing (pixel-perfect precision isn't needed for a magnitude proxy, and this keeps a
2560x1440 sequence fast to process with pure Pillow -- no numpy dependency, nothing new to
install).

Exit 0 on a normal report (this is a report, not a pass/fail gate -- read the numbers, don't
just check the exit code, per this project's own C7 lesson on silent-success audits); exit 1
only if fewer than 2 frames matched the pattern (nothing to diff).
"""
from __future__ import annotations

import argparse
import glob
import re
import statistics
import sys

from PIL import Image, ImageChops, ImageStat

DOWNSCALE_WIDTH = 480


def _numeric_suffix(path: str) -> int:
    m = re.search(r"-(\d+)\.png$", path)
    return int(m.group(1)) if m else 0


def _load_downscaled(path: str) -> Image.Image:
    img = Image.open(path).convert("RGB")
    if img.width > DOWNSCALE_WIDTH:
        ratio = DOWNSCALE_WIDTH / img.width
        img = img.resize((DOWNSCALE_WIDTH, max(1, int(img.height * ratio))), Image.BILINEAR)
    return img


def analyze(prefix: str) -> int:
    pattern = f"{prefix}-*.png"
    files = sorted(glob.glob(pattern), key=_numeric_suffix)
    if len(files) < 2:
        print(f"[hq_frames_analyze] FAIL: need >=2 frames matching {pattern!r}, found {len(files)}.", file=sys.stderr)
        return 1

    print(f"[hq_frames_analyze] {len(files)} frames matched {pattern!r}:")
    for f in files:
        print(f"  {f}")

    diffs: list[float] = []
    prev = _load_downscaled(files[0])
    for path in files[1:]:
        cur = _load_downscaled(path)
        diff_img = ImageChops.difference(prev, cur)
        stat = ImageStat.Stat(diff_img)
        # Mean absolute per-channel difference, averaged across R/G/B -- a single scalar
        # "how much changed" magnitude per frame pair, on a 0-255 scale.
        magnitude = sum(stat.mean) / len(stat.mean)
        diffs.append(magnitude)
        prev = cur

    mean = statistics.mean(diffs)
    stdev = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
    cv = (stdev / mean) if mean > 0 else 0.0

    print("\n[hq_frames_analyze] per-pair mean |delta| (0-255 scale):")
    for i, d in enumerate(diffs, start=1):
        bar = "#" * min(60, int(d))
        print(f"  {i:02d}->{i + 1:02d}: {d:6.2f}  {bar}")

    print(
        f"\n[hq_frames_analyze] SUMMARY: n_pairs={len(diffs)} mean={mean:.3f} stdev={stdev:.3f} "
        f"max={max(diffs):.3f} min={min(diffs):.3f} coeff_of_variation={cv:.3f}"
    )
    print(
        "[hq_frames_analyze] Read: small+consistent deltas (low stdev, low CoV) = smooth motion "
        "or a static scene; a high CoV (deltas swinging between near-zero and large) is the "
        "back-and-forth jitter signature -- each such swing is one visible direction reversal "
        "landing between two consecutive captured frames."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("prefix", help="Same -Out value passed to hq_capture.ps1 -Frames N (without the -NN.png suffix)")
    args = parser.parse_args(argv)
    return analyze(args.prefix)


if __name__ == "__main__":
    raise SystemExit(main())

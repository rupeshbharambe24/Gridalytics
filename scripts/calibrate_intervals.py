"""Recalibrate served prediction intervals (issue #30).

The evaluation (docs/pi_calibration.md) showed the 90% bands are systematically
over-confident (~80% empirical coverage). This computes a per-model **split-
conformal scale factor** on the holdout — the factor by which the band half-
widths must be multiplied so ~90% of holdout actuals fall inside — and writes it
to each served.json as `pi_scale`. The serving layer multiplies the band
half-widths by `pi_scale` (point stays put), so a nominal 90% band actually
covers ~90%.

  python scripts/calibrate_intervals.py           # compute + write pi_scale
  python scripts/calibrate_intervals.py --dry      # compute + report, write nothing
  python scripts/calibrate_intervals.py --only punjab

Note: the factor is fit on the same holdout used to measure coverage, so the
post-scaling coverage below is in-sample for the conformal step (optimistic on
the n=30 daily holdouts); a cleaner build fits it on a separate calibration split.
Run from a checkout of main with DATABASE_URL -> the canonical DB.
"""
import argparse
import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "scripts"))

import numpy as np

import train_state as T
from retrain_all import MANIFEST
from evaluate_calibration import build_frame, load_served, HOLDOUT, MODELS

TARGET_COV = 0.90
K_MIN, K_MAX = 0.6, 6.0


def conformal_scale(point, lower, upper, y, target=TARGET_COV):
    """Smallest multiplier k on the band half-widths s.t. ~target of y fall inside."""
    point, lower, upper, y = map(np.asarray, (point, lower, upper, y))
    hw_up = np.maximum(upper - point, 1e-9)
    hw_dn = np.maximum(point - lower, 1e-9)
    # one-sided "how many half-widths out" each actual is (0 if dead on the point)
    s = np.where(y >= point, (y - point) / hw_up, (point - y) / hw_dn)
    n = len(s)
    rank = min(int(np.ceil((n + 1) * target)) - 1, n - 1)   # split-conformal quantile index
    k = float(np.sort(s)[rank])
    return float(np.clip(k, K_MIN, K_MAX))


def coverage(point, lower, upper, y, k=1.0):
    point, lower, upper, y = map(np.asarray, (point, lower, upper, y))
    lo = point - k * (point - lower)
    hi = point + k * (upper - point)
    return 100.0 * np.mean((y >= lo) & (y <= hi))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--dry", action="store_true", help="compute + report, do not write served.json")
    args = ap.parse_args()

    items = [m for m in MANIFEST if not args.only or m["state"] == args.only]
    rows = []
    for m in items:
        try:
            df, feats, resolution = build_frame(m)
            if df is None or len(df) <= HOLDOUT[resolution] + 5:
                continue
            model, meta = load_served(m["state"], resolution)
            if model is None:
                continue
            test = df.iloc[-HOLDOUT[resolution]:]
            cols = model.feature_names or feats
            y = test[T.TARGET].to_numpy(float)
            point, lo, hi = (np.asarray(a) for a in model.predict_interval(test[cols]))
            lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
            k = conformal_scale(point, lo, hi, y)
            pre, post = coverage(point, lo, hi, y, 1.0), coverage(point, lo, hi, y, k)
            rows.append((m["state"], resolution, meta.get("served_model"), round(k, 3), round(pre, 1), round(post, 1)))
            print(f"  {m['state']:<16} {resolution:<6} k={k:4.2f}  cov {pre:5.1f}% -> {post:5.1f}%", flush=True)
            if not args.dry:
                p = MODELS / m["state"] / resolution / "served.json"
                d = json.loads(p.read_text())
                d["pi_scale"] = round(k, 3)
                p.write_text(json.dumps(d, indent=2))
        except Exception as e:
            print(f"  SKIP {m['state']}: {type(e).__name__}: {e}", flush=True)

    if rows:
        pre = np.mean([r[4] for r in rows]); post = np.mean([r[5] for r in rows])
        print(f"\n{len(rows)} models | mean coverage {pre:.1f}% -> {post:.1f}% (nominal {TARGET_COV*100:.0f}%) "
              f"| {'DRY (nothing written)' if args.dry else 'pi_scale written to served.json'}")


if __name__ == "__main__":
    main()

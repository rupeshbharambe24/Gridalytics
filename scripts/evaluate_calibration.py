"""Prediction-interval calibration check for the served fleet (issue #28).

Every forecaster emits a 90% prediction interval (quantile models at alpha
0.05 / 0.95). This measures whether that interval actually *covers* realised
demand at the claimed rate, out-of-sample.

Method (honest, leak-free): each served artifact was trained by train_state on
``df[:-holdout]``, so the last ``holdout`` rows are genuinely out-of-sample for
it. We rebuild the exact feature frame (same MANIFEST args, same pipeline),
load the served model, predict intervals on those holdout rows, and report:

  coverage   = fraction of actuals inside [lower, upper]   (target: ~90%)
  mean width = mean(upper - lower) as % of mean demand     (sharpness)
  point MAPE = sanity check on the holdout

  python scripts/evaluate_calibration.py            # whole fleet -> docs/pi_calibration.md
  python scripts/evaluate_calibration.py --only punjab

Run from a checkout of main with DATABASE_URL -> the canonical DB.
"""
import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

WT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "scripts"))

import numpy as np
import pandas as pd

import train_state as T
from retrain_all import MANIFEST
from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster

HOLDOUT = {"5min": 2016, "15min": 672, "hourly": 720, "daily": 30}
NOMINAL = 90.0  # alpha 0.05 / 0.95
MODELS = WT / "models" / "states"


def build_frame(m: dict):
    """Reconstruct (df, feats, resolution) exactly as train_state.main would."""
    source = m.get("source", "state_demand")
    resolution = m.get("resolution") or ("daily" if source == "psp" else "hourly")
    # MANIFEST carries ISO strings; the sub-daily loader expects date objects.
    start = date.fromisoformat(m["start"]) if m.get("start") else None
    end = date.fromisoformat(m["end"]) if m.get("end") else None
    df = T.load_state_series(m["state"], resolution, start=start, end=end, source=source)
    if df.empty:
        return None, None, resolution
    use_weather = not m.get("no_weather") and m["state"] in T.STATE_COORDS
    if use_weather:
        lat, lon = T.STATE_COORDS[m["state"]]
        time.sleep(2.5)  # pace fetches: Open-Meteo throttles bursts, not steady single calls
        wx = T.fetch_weather(lat, lon, df.index.min(), df.index.max())
        for _ in range(4):  # Open-Meteo throttles back-to-back fleet runs; retry transient empties
            if not wx.empty:
                break
            time.sleep(6)
            wx = T.fetch_weather(lat, lon, df.index.min(), df.index.max())
        if wx.empty:
            raise RuntimeError(f"weather fetch empty for {m['state']} after retries (Open-Meteo throttle)")
        if not wx.empty:
            if resolution == "daily":
                wx = wx.resample("1D").agg({c: ("sum" if c == "precipitation_mm" else "mean")
                                            for c in wx.columns})
            df = df.join(wx.reindex(df.index, method="nearest"))
            for c in T._WX:
                col = {"precipitation": "precipitation_mm", "cloud_cover": "cloud_cover_pct"}.get(c, c)
                if col in df.columns:
                    df[col] = df[col].ffill().bfill()
    df, feats = T.build_features(df, resolution, use_weather,
                                 drop_lag365=m.get("no_lag365", False),
                                 event_effect=m.get("event_effect", False))
    return df, feats, resolution


def load_served(state: str, resolution: str):
    p = MODELS / state / resolution / "served.json"
    if not p.exists():
        return None, None
    meta = json.loads(p.read_text())
    cls = XGBoostForecaster if meta.get("served_model") == "XGBoost" else LightGBMForecaster
    return cls.load(MODELS / state / resolution), meta


def evaluate(m: dict):
    state = m["state"]
    df, feats, resolution = build_frame(m)
    if df is None or len(df) <= HOLDOUT[resolution] + 5:
        return None
    model, meta = load_served(state, resolution)
    if model is None:
        return None
    h = HOLDOUT[resolution]
    test = df.iloc[-h:]
    cols = model.feature_names or feats
    y = test[T.TARGET].to_numpy(dtype=float)
    point, lo, hi = model.predict_interval(test[cols])
    point, lo, hi = np.asarray(point), np.asarray(lo), np.asarray(hi)
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)  # guard inverted bands
    k = float(meta.get("pi_scale", 1.0))  # apply conformal recalibration (what serving returns)
    if k != 1.0:
        lo = point - k * (point - lo)
        hi = point + k * (hi - point)
    inside = (y >= lo) & (y <= hi)
    nz = y != 0
    return {
        "state": state,
        "resolution": resolution,
        "served": meta.get("served_model"),
        "n": int(len(y)),
        "coverage": round(100.0 * inside.mean(), 1),
        "width_pct": round(100.0 * np.mean(hi - lo) / np.mean(y), 1),
        "mape": round(100.0 * np.mean(np.abs((y[nz] - point[nz]) / y[nz])), 2),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="evaluate just this state")
    ap.add_argument("--out", default=str(WT / "docs" / "pi_calibration.md"))
    args = ap.parse_args()

    items = [m for m in MANIFEST if not args.only or m["state"] == args.only]
    rows = []
    for m in items:
        try:
            r = evaluate(m)
        except Exception as e:
            print(f"  SKIP {m['state']}: {type(e).__name__}: {e}", flush=True)
            r = None
        if r:
            rows.append(r)
            print(f"  {r['state']:<16} {r['resolution']:<6} {r['served']:<9} "
                  f"cov {r['coverage']:5.1f}%  width {r['width_pct']:5.1f}%  mape {r['mape']:.2f}%  (n={r['n']})",
                  flush=True)

    if not rows:
        print("no models evaluated"); return
    rows.sort(key=lambda r: abs(r["coverage"] - NOMINAL))

    cov = np.array([r["coverage"] for r in rows])
    print(f"\n{'#'*64}\n  {len(rows)} models | nominal {NOMINAL:.0f}% | "
          f"mean coverage {cov.mean():.1f}% | within ±5pts: {int((np.abs(cov-NOMINAL)<=5).sum())}/{len(rows)}")

    # markdown report
    lines = [
        "# Prediction-interval calibration", "",
        f"Out-of-sample coverage of each served model's **{NOMINAL:.0f}% prediction "
        "interval** (quantile models at &alpha; 0.05 / 0.95), measured on the "
        "`holdout` rows the served artifact never trained on. Generated by "
        "`scripts/evaluate_calibration.py`.", "",
        "- **Coverage** — % of actual values that fell inside the interval (target ~90%).",
        "- **Width** — mean interval width as % of mean demand (sharpness; lower is tighter).",
        "- **MAPE** — point-forecast error on the same holdout (sanity).", "",
        "| Model | Res | Served | Coverage | Width | MAPE | n |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        flag = "" if abs(r["coverage"] - NOMINAL) <= 5 else (
            " ⚠︎ under" if r["coverage"] < NOMINAL else " ⚠︎ over")
        lines.append(f"| {r['state']} | {r['resolution']} | {r['served']} | "
                     f"**{r['coverage']:.1f}%**{flag} | {r['width_pct']:.1f}% | {r['mape']:.2f}% | {r['n']} |")
    lines += ["",
        f"**Summary:** {len(rows)} served models, nominal {NOMINAL:.0f}%; mean empirical "
        f"coverage **{cov.mean():.1f}%**, {int((np.abs(cov-NOMINAL)<=5).sum())}/{len(rows)} within ±5 pts. "
        "Models flagged *under* are over-confident (intervals too tight); *over* are "
        "conservative. Delhi's three resolutions use the separate Delhi pipeline and are "
        "not covered here (follow-up).", ""]
    Path(args.out).write_text("\n".join(lines))
    print(f"  report -> {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Recursive day-ahead backtest of the event-effect feature (Idea 1).

This is the test the walk-forward CV can't do. CV scores one-step-ahead with
the true lag columns present, so on an event day the lags already encode the
event and no exogenous feature can help. Production forecasting is different:
`forecast_future` is recursive and does NOT use yesterday's actual as lag_1 for
future steps — it leans on lag_24 / lag_168 (same hour yesterday / last week,
both *normal* days) plus calendar features. On a festival those lags are blind
to the dip, so the model's only lever is the holiday features. That's where a
*signed* `expected_event_effect_pct` (Diwali -10% vs Eid +3%) can beat a bare
binary `is_festival` flag.

Design (leakage-free):
  * Train two LightGBM hourly models on data BEFORE a cutoff — one WITH the
    feature column, one WITHOUT. Only that column differs.
  * For each backtest date D (festival days and control normal days AFTER the
    cutoff), run `forecast_future(..., as_of=D)` so history and the learned
    effect table see only data < D. Compare the 24-hour forecast to actuals.
  * Report day-ahead MAPE on event days vs normal days, WITH vs WITHOUT.

Run (project env + edfs.db):
    python3 scripts/backtest_event_effect.py            # cutoff 2026-01-01
    python3 scripts/backtest_event_effect.py 2025-07-01 # custom cutoff
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.models.lightgbm_model import LightGBMForecaster
from src.forecasting.future import forecast_future

FEATURE = "expected_event_effect_pct"
TARGET = "delhi_mw"
SUB_REGIONAL_COLS = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
RESOLUTION = "hourly"
MIN_HOURS = 20          # a day needs this many hours of actuals to be scored
N_CONTROL = 40          # how many normal control days to sample
SEED = 7
logging.basicConfig(level=logging.ERROR, format="%(message)s")


def build_features():
    with get_session() as session:
        pipe = FeaturePipeline(RESOLUTION, session, include_event_effect=True)
        df = pipe.build()
        features = pipe.get_feature_names(df)
    features = [f for f in features if f not in SUB_REGIONAL_COLS]
    null_pct = df[features].isnull().mean()
    features = [f for f in features if null_pct.get(f, 0) <= 0.1]
    df[features] = df[features].ffill().fillna(0)
    return df, features


def day_mape(pred: dict, actual: pd.Series) -> float | None:
    """MAPE between the 24-h forecast and actual hourly demand, common hours."""
    ts = pd.to_datetime(pred["timestamps"])
    p = pd.Series(pred["predicted_mw"], index=ts.hour)
    a = actual.groupby(actual.index.hour).mean()
    common = p.index.intersection(a.index)
    if len(common) < MIN_HOURS:
        return None
    pa, aa = p.loc[common].to_numpy(), a.loc[common].to_numpy()
    m = np.abs(aa) > 1.0
    if m.sum() == 0:
        return None
    return float(np.mean(np.abs((aa[m] - pa[m]) / aa[m])) * 100)


def main(cutoff: date):
    print(f"\n{'#' * 66}")
    print(f"  Recursive day-ahead backtest — event-effect feature ({RESOLUTION})")
    print(f"  Train < {cutoff}   |   backtest >= {cutoff}")
    print(f"{'#' * 66}")

    df, feats_with = build_features()
    if FEATURE not in feats_with:
        print(f"  !! '{FEATURE}' absent from features — nothing to test.")
        return
    feats_without = [f for f in feats_with if f != FEATURE]

    cutoff_ts = pd.Timestamp(cutoff)
    train = df[df.index < cutoff_ts]
    test = df[df.index >= cutoff_ts]
    print(f"  Train rows: {len(train):,}  ({train.index.min().date()}..{train.index.max().date()})")
    print(f"  Test  rows: {len(test):,}  ({test.index.min().date()}..{test.index.max().date()})")

    # classify backtest days from the data itself (is_holiday marks events)
    days = {}
    for d, g in test.groupby(test.index.normalize()):
        if len(g) < MIN_HOURS:
            continue
        days[d.date()] = (int(g["is_holiday"].max()) == 1, g[TARGET])
    event_days = sorted([d for d, (ev, _) in days.items() if ev])
    normal_days = sorted([d for d, (ev, _) in days.items() if not ev])
    rng = np.random.default_rng(SEED)
    if len(normal_days) > N_CONTROL:
        normal_days = sorted(rng.choice(normal_days, N_CONTROL, replace=False))
    print(f"  Backtest days: {len(event_days)} event, {len(normal_days)} control normal\n")

    # train the two models (only the feature column differs)
    print("  Training model WITHOUT feature ...", flush=True)
    m_off = LightGBMForecaster(resolution=RESOLUTION)
    m_off.fit(train[feats_without], train[TARGET])
    print("  Training model WITH feature ...", flush=True)
    m_on = LightGBMForecaster(resolution=RESOLUTION)
    m_on.fit(train[feats_with], train[TARGET])

    rows = []
    with get_session() as session:
        for grp, dates in (("event", event_days), ("normal", normal_days)):
            for d in dates:
                actual = days[d][1]
                try:
                    r_off = forecast_future(RESOLUTION, d, m_off, session, as_of=d)
                    r_on = forecast_future(RESOLUTION, d, m_on, session, as_of=d)
                except Exception as exc:
                    print(f"    {d} skipped ({exc})")
                    continue
                mo, mn = day_mape(r_off, actual), day_mape(r_on, actual)
                if mo is None or mn is None:
                    continue
                rows.append({"date": d, "group": grp, "mape_off": mo, "mape_on": mn})

    res = pd.DataFrame(rows)
    if res.empty:
        print("  !! No days scored.")
        return

    # per-event detail
    ev = res[res["group"] == "event"].sort_values("mape_off", ascending=False)
    print(f"\n  Event days — day-ahead MAPE:")
    print(f"  {'date':<12} {'off':>7} {'on':>7} {'Δ(on-off)':>10}")
    print(f"  {'-' * 38}")
    for _, r in ev.iterrows():
        print(f"  {str(r['date']):<12} {r['mape_off']:>6.2f}% {r['mape_on']:>6.2f}% "
              f"{r['mape_on'] - r['mape_off']:>+9.2f}%")

    print(f"\n{'=' * 66}")
    for grp in ("event", "normal"):
        s = res[res["group"] == grp]
        if s.empty:
            continue
        off, on = s["mape_off"].mean(), s["mape_on"].mean()
        wins = int((s["mape_on"] < s["mape_off"]).sum())
        print(f"  {grp.upper():<7} (n={len(s):>2})  off={off:5.2f}%  on={on:5.2f}%  "
              f"Δ={on - off:+5.2f}%   feature wins {wins}/{len(s)} days")
    print(f"{'=' * 66}")
    ev_s = res[res["group"] == "event"]
    if not ev_s.empty:
        d = ev_s["mape_on"].mean() - ev_s["mape_off"].mean()
        verdict = "HELPS day-ahead on event days" if d < -0.05 else (
            "neutral" if abs(d) <= 0.05 else "HURTS event days")
        print(f"  => Event-day day-ahead verdict: {verdict} ({d:+.2f}% MAPE).")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cut = date.fromisoformat(args[0]) if args else date(2026, 1, 1)
    main(cut)

#!/usr/bin/env python3
"""A/B test the learned event-effect feature (Idea 1, Phase 1.5).

Measures whether `expected_event_effect_pct` improves forecast accuracy in
walk-forward CV, so champion/challenger has a number to decide on. The design
is the tightest possible apples-to-apples: features are built **once**, and the
only difference between the two variants is whether the model is allowed to see
that one column. Identical rows, identical folds, identical everything else.

It reports three things per resolution:
  1. Walk-forward CV MAPE, WITHOUT vs WITH the feature (the champion metric —
     mean of per-fold MAPE, exactly how `train.py` picks the champion).
  2. Accuracy specifically on **event days** (rows where the learned effect is
     non-zero) — the days this feature is meant to help.
  3. Where `expected_event_effect_pct` ranks in LightGBM feature importance.

NOTE: CV scores one-step-ahead with the true lag columns present, so on an event
day the lags already encode the event and this test structurally cannot reward
the feature. Use scripts/backtest_event_effect.py for the recursive day-ahead
test, which is the real gate. See docs/event_aware_forecasting.md.

Run from the repo root (project env + edfs.db):
    python3 scripts/ab_event_effect.py              # daily (default)
    python3 scripts/ab_event_effect.py hourly       # one resolution
    python3 scripts/ab_event_effect.py daily hourly # several

Nothing is written and no model is saved — this only measures.
"""

from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd

# repo root on path (this file lives in scripts/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.models.lightgbm_model import LightGBMForecaster
from src.evaluation.cross_validation import generate_folds
from src.evaluation.metrics import compute_all_metrics

FEATURE = "expected_event_effect_pct"
# same exclusions train.py applies
SUB_REGIONAL_COLS = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
logging.basicConfig(level=logging.WARNING, format="%(message)s")


def _build_features(resolution: str):
    """Build feature matrix exactly as train.py does (inlined so this script
    needs only the light deps — no mlflow/xgboost/torch import)."""
    with get_session() as session:
        pipeline = FeaturePipeline(resolution, session, include_event_effect=True)
        df = pipeline.build()
        target = pipeline.get_target_name()
        features = pipeline.get_feature_names(df)

    features = [f for f in features if f not in SUB_REGIONAL_COLS]
    null_pct = df[features].isnull().mean()
    bad = null_pct[null_pct > 0.1].index.tolist()
    if bad:
        features = [f for f in features if f not in bad]
    df[features] = df[features].ffill().fillna(0)
    return df, target, features


def _event_mask(df: pd.DataFrame) -> pd.Series:
    """Rows the feature is meant to help: a learned event effect is present."""
    if FEATURE in df.columns:
        return df[FEATURE].abs() > 1e-9
    return pd.Series(False, index=df.index)


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.abs(y_true) > 1.0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def run_resolution(resolution: str) -> dict:
    print(f"\n{'#' * 64}")
    print(f"  A/B: event-effect feature — resolution = {resolution}")
    print(f"{'#' * 64}")

    df, target, feats_with = _build_features(resolution)
    if FEATURE not in feats_with:
        print(f"  !! '{FEATURE}' not in the feature set (all-zero or dropped as "
              f">10% null?). Nothing to A/B at {resolution}.")
        return {}
    feats_without = [f for f in feats_with if f != FEATURE]

    ev = _event_mask(df)
    print(f"  Rows: {len(df):,} | features: {len(feats_with)} "
          f"(with) vs {len(feats_without)} (without)")
    print(f"  Target: {target} (mean={df[target].mean():.0f} MW)")
    print(f"  Event rows (effect != 0): {int(ev.sum()):,} "
          f"({100 * ev.mean():.1f}% of data)")

    folds = generate_folds(len(df), resolution)
    if not folds:
        print("  !! Not enough data for CV at this resolution.")
        return {}
    print(f"  Walk-forward folds: {len(folds)}\n")

    per_fold = []
    pool_actual, pool_with, pool_without, pool_event = [], [], [], []

    print(f"  {'Fold':<5} {'MAPE off':>9} {'MAPE on':>9} {'Δ (on-off)':>11}  "
          f"{'val window':>21}")
    print(f"  {'-' * 58}")
    for fold in folds:
        tr = df.iloc[fold.train_start:fold.train_end]
        va = df.iloc[fold.val_start:fold.val_end]
        y_tr, y_va = tr[target], va[target]

        m_off = LightGBMForecaster(resolution=resolution)
        m_off.fit(tr[feats_without], y_tr, va[feats_without], y_va)
        p_off = m_off.predict(va[feats_without])

        m_on = LightGBMForecaster(resolution=resolution)
        m_on.fit(tr[feats_with], y_tr, va[feats_with], y_va)
        p_on = m_on.predict(va[feats_with])

        mape_off = compute_all_metrics(y_va.values, p_off)["mape"]
        mape_on = compute_all_metrics(y_va.values, p_on)["mape"]
        per_fold.append((mape_off, mape_on))

        pool_actual.extend(y_va.values)
        pool_without.extend(p_off)
        pool_with.extend(p_on)
        pool_event.extend(ev.iloc[fold.val_start:fold.val_end].values)

        print(f"  {fold.fold_idx + 1:<5} {mape_off:>8.2f}% {mape_on:>8.2f}% "
              f"{mape_on - mape_off:>+10.2f}%  "
              f"{str(va.index[0].date())}..{str(va.index[-1].date())}")

    arr = np.array(per_fold)
    mean_off, mean_on = arr[:, 0].mean(), arr[:, 1].mean()
    print(f"  {'-' * 58}")
    print(f"  {'MEAN':<5} {mean_off:>8.2f}% {mean_on:>8.2f}% "
          f"{mean_on - mean_off:>+10.2f}%")

    a = np.array(pool_actual)
    pw = np.array(pool_with)
    po = np.array(pool_without)
    em = np.array(pool_event, dtype=bool)
    print(f"\n  Overall (pooled)   MAPE  off={_mape(a, po):.2f}%  "
          f"on={_mape(a, pw):.2f}%  Δ={_mape(a, pw) - _mape(a, po):+.2f}%")
    if em.sum() >= 5:
        print(f"  Event days (n={int(em.sum())})  MAPE  "
              f"off={_mape(a[em], po[em]):.2f}%  on={_mape(a[em], pw[em]):.2f}%  "
              f"Δ={_mape(a[em], pw[em]) - _mape(a[em], po[em]):+.2f}%   "
              f"<-- the days this feature targets")
    else:
        print(f"  Event days: only {int(em.sum())} in validation — too few to judge "
              f"(try a longer/denser resolution).")

    m_full = LightGBMForecaster(resolution=resolution)
    m_full.fit(df[feats_with], df[target])
    imp = m_full.get_feature_importance()
    if imp is not None and FEATURE in imp.index:
        rank = list(imp.index).index(FEATURE) + 1
        print(f"\n  Feature importance: '{FEATURE}' ranks "
              f"#{rank}/{len(imp)} (gain={imp[FEATURE]:.0f})")

    verdict = "HELPS" if mean_on < mean_off else "does NOT help"
    print(f"\n  => At {resolution}: feature {verdict} "
          f"(mean CV MAPE {mean_on - mean_off:+.2f}%).")
    return {"resolution": resolution, "mape_off": mean_off, "mape_on": mean_on}


def main(resolutions: list[str]):
    summary = [run_resolution(r) for r in resolutions]
    summary = [s for s in summary if s]
    if len(summary) > 1:
        print(f"\n{'=' * 64}\n  SUMMARY\n{'=' * 64}")
        for s in summary:
            d = s["mape_on"] - s["mape_off"]
            print(f"  {s['resolution']:<7} off={s['mape_off']:.2f}%  "
                  f"on={s['mape_on']:.2f}%  Δ={d:+.2f}%  "
                  f"{'(helps)' if d < 0 else '(no help)'}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in ("5min", "hourly", "daily")]
    main(args or ["daily"])

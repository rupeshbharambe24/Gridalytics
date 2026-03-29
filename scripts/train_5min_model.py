"""Train a 5-minute resolution LightGBM model for EDFS v2.

Handles ~200K rows of 5-min demand data (2021-2026).
Uses walk-forward CV (10 folds) then trains a final model on all
data except a 3-day holdout for evaluation.

Optimised for speed on the large 5-min dataset:
  - n_estimators=500 (not 1000)
  - early_stopping patience=30
  - subsample=0.7
"""

import sys
import logging
import warnings
from pathlib import Path
from datetime import date

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.models.lightgbm_model import LightGBMForecaster
from src.evaluation.cross_validation import walk_forward_cv
from src.evaluation.metrics import print_metrics_report, compute_seasonal_metrics
import numpy as np
import pandas as pd


# LightGBM params tuned for the large 5-min dataset
FIVEMIN_LGB_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.7,       # subsample=0.7 for faster training
    "bagging_freq": 5,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "n_estimators": 500,           # capped for speed
    "verbose": -1,
    "n_jobs": -1,
}

# Walk-forward CV settings (matches CV_CONFIGS["5min"])
HOLDOUT_ROWS = 864   # 3 days of 5-min data
EARLY_STOPPING = 30  # patience for early stopping


def train_5min():
    """Train a 5-minute resolution LightGBM model."""

    print(f"\n{'#'*60}")
    print(f"  EDFS v2 - 5-Minute LightGBM Training")
    print(f"{'#'*60}")

    # ── 1. Build features ────────────────────────────────────────
    print("\n[1/6] Building feature matrix (5-min resolution)...")
    with get_session() as session:
        pipeline = FeaturePipeline("5min", session)
        df = pipeline.build(date(2021, 1, 1), date(2026, 3, 28))

    target = pipeline.get_target_name()
    features = pipeline.get_feature_names(df)

    # ── 2. Prepare features ──────────────────────────────────────
    print("\n[2/6] Preparing features...")

    # Remove sub-regional columns
    sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
    features = [f for f in features if f not in sub_regional]

    # Remove non-numeric columns (object, datetime, etc.)
    numeric_dtypes = df[features].select_dtypes(include=["number", "bool"]).columns
    non_numeric = [f for f in features if f not in numeric_dtypes]
    if non_numeric:
        logger.info(f"Dropping {len(non_numeric)} non-numeric features: {non_numeric}")
        features = [f for f in features if f in numeric_dtypes]

    # Drop columns with >10% nulls
    null_pct = df[features].isnull().mean()
    bad_cols = null_pct[null_pct > 0.1].index.tolist()
    if bad_cols:
        logger.info(f"Dropping {len(bad_cols)} features with >10% nulls: {bad_cols}")
        features = [f for f in features if f not in bad_cols]

    # Forward-fill then fill remaining NaN with 0
    df[features] = df[features].fillna(method="ffill").fillna(0)

    print(f"  Data: {len(df):,} rows, {len(features)} features")
    print(f"  Date range: {df.index.min()} to {df.index.max()}")
    print(f"  Target: {target} (mean={df[target].mean():.0f} MW)")

    # ── 3. Walk-forward CV ───────────────────────────────────────
    print(f"\n[3/6] Walk-forward CV (10 folds, 3-day val windows)...")
    cv_results = walk_forward_cv(
        LightGBMForecaster,
        df,
        target,
        features,
        "5min",
        model_kwargs={"params": FIVEMIN_LGB_PARAMS},
    )

    print(f"\n  CV Results:")
    if cv_results.empty:
        print("  (no results - not enough data for CV)")
        return
    print(f"  {'Fold':<6} {'MAPE':>7} {'RMSE':>8} {'MAE':>8} {'R2':>8}")
    print(f"  {'-'*38}")
    for _, row in cv_results.iterrows():
        print(f"  {int(row['fold']):<6} {row['mape']:>6.2f}% {row['rmse']:>7.1f} {row['mae']:>7.1f} {row['r2']:>7.4f}")
    print(f"  {'-'*38}")
    print(f"  {'MEAN':<6} {cv_results['mape'].mean():>6.2f}% {cv_results['rmse'].mean():>7.1f} "
          f"{cv_results['mae'].mean():>7.1f} {cv_results['r2'].mean():>7.4f}")

    # ── 4. Train final model ─────────────────────────────────────
    print(f"\n[4/6] Training final model (holdout = last {HOLDOUT_ROWS} rows / 3 days)...")

    train_df = df.iloc[:-HOLDOUT_ROWS]
    test_df = df.iloc[-HOLDOUT_ROWS:]

    X_train = train_df[features]
    y_train = train_df[target]
    X_test = test_df[features]
    y_test = test_df[target]

    final_model = LightGBMForecaster(resolution="5min", params=FIVEMIN_LGB_PARAMS)
    final_model.fit(X_train, y_train, X_test, y_test)

    # ── 5. Metrics report ────────────────────────────────────────
    print(f"\n[5/6] Evaluation on 3-day holdout...")
    preds = final_model.predict(X_test)
    holdout_metrics = print_metrics_report(
        y_test.values, preds, test_df.index, "LightGBM 5-min (Holdout)"
    )

    # Feature importance
    imp = final_model.get_feature_importance()
    if imp is not None:
        print(f"\n  Top 15 Features:")
        for feat, val in imp.head(15).items():
            print(f"    {feat:<35s} {val:>8.0f}")

    # ── 6. Save model ────────────────────────────────────────────
    print(f"\n[6/6] Saving model...")
    save_dir = Path("models") / "5min" / "lightgbm"
    final_model.save(save_dir)
    model_size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"  Model saved to {save_dir} ({model_size:.1f} MB)")

    # ── 7. Comparison with other resolutions ─────────────────────
    cv_mape = cv_results["mape"].mean()
    cv_rmse = cv_results["rmse"].mean()
    cv_r2 = cv_results["r2"].mean()

    print(f"\n{'='*60}")
    print(f"  MODEL COMPARISON (all resolutions)")
    print(f"{'='*60}")
    print(f"  {'Resolution':<12} {'Model':<12} {'CV MAPE':>9} {'Holdout MAPE':>13}")
    print(f"  {'-'*48}")
    print(f"  {'5-min':<12} {'LightGBM':<12} {cv_mape:>8.2f}% {holdout_metrics['mape']:>12.2f}%")

    # Try to load metrics from existing models for comparison
    import json
    for res, model_name in [("hourly", "xgboost"), ("daily", "lightgbm")]:
        meta_path = Path("models") / res / model_name / "meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            # We don't have saved MAPE in meta, so just note it exists
            print(f"  {res:<12} {model_name:<12} {'(trained)':>9} {'--':>13}")
        else:
            print(f"  {res:<12} {model_name:<12} {'--':>9} {'--':>13}")

    print(f"{'='*60}")

    print(f"\n  5-min model training complete!")
    print(f"  CV MAPE: {cv_mape:.2f}%  |  Holdout MAPE: {holdout_metrics['mape']:.2f}%")
    print(f"  R2: {cv_r2:.4f}  |  RMSE: {cv_rmse:.1f} MW")
    print(f"  Model size: {model_size:.1f} MB  |  Features: {len(features)}")

    return final_model


if __name__ == "__main__":
    train_5min()

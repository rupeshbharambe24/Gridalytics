"""Initial model training and evaluation script.

Trains LightGBM and XGBoost on hourly data with walk-forward CV,
prints evaluation reports, saves the best model.
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
from src.models.xgboost_model import XGBoostForecaster
from src.evaluation.cross_validation import walk_forward_cv
from src.evaluation.metrics import print_metrics_report, compute_seasonal_metrics
import numpy as np
import pandas as pd


def train_and_evaluate(resolution: str = "hourly"):
    """Train models and run walk-forward CV."""

    print(f"\n{'#'*60}")
    print(f"  Gridalytics - Model Training ({resolution} resolution)")
    print(f"{'#'*60}")

    # Build features
    print("\n[1/4] Building feature matrix...")
    with get_session() as session:
        pipeline = FeaturePipeline(resolution, session)
        df = pipeline.build(date(2021, 1, 1), date(2026, 3, 28))

    target = pipeline.get_target_name()
    features = pipeline.get_feature_names(df)

    # Remove sub-regional columns from features (they have nulls and aren't predictive)
    sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
    features = [f for f in features if f not in sub_regional]

    # Drop any remaining columns with too many nulls
    null_pct = df[features].isnull().mean()
    bad_cols = null_pct[null_pct > 0.1].index.tolist()
    if bad_cols:
        logger.info(f"Dropping {len(bad_cols)} features with >10% nulls: {bad_cols}")
        features = [f for f in features if f not in bad_cols]

    # Fill remaining sparse nulls
    df[features] = df[features].ffill().fillna(0)

    print(f"  Data: {len(df):,} rows, {len(features)} features")
    print(f"  Date range: {df.index.min()} to {df.index.max()}")
    print(f"  Target: {target} (mean={df[target].mean():.0f} MW)")

    # Walk-forward CV for LightGBM
    print(f"\n[2/4] Walk-forward CV: LightGBM...")
    lgb_results = walk_forward_cv(
        LightGBMForecaster, df, target, features, resolution
    )
    def print_cv_results(name, results_df):
        print(f"\n  {name} CV Results:")
        if results_df.empty:
            print("  (no results - not enough data for CV)")
            return
        print(f"  {'Fold':<6} {'MAPE':>7} {'RMSE':>8} {'MAE':>8} {'R2':>8}")
        print(f"  {'-'*38}")
        for _, row in results_df.iterrows():
            print(f"  {int(row['fold']):<6} {row['mape']:>6.2f}% {row['rmse']:>7.1f} {row['mae']:>7.1f} {row['r2']:>7.4f}")
        print(f"  {'-'*38}")
        print(f"  {'MEAN':<6} {results_df['mape'].mean():>6.2f}% {results_df['rmse'].mean():>7.1f} "
              f"{results_df['mae'].mean():>7.1f} {results_df['r2'].mean():>7.4f}")

    print_cv_results("LightGBM", lgb_results)

    # Walk-forward CV for XGBoost
    print(f"\n[3/4] Walk-forward CV: XGBoost...")
    xgb_results = walk_forward_cv(
        XGBoostForecaster, df, target, features, resolution
    )
    print_cv_results("XGBoost", xgb_results)

    # Train final model on all data except last month (holdout)
    print(f"\n[4/4] Training final model on full data (holdout = last month)...")
    holdout_size = 720 if resolution == "hourly" else 30 if resolution == "daily" else 8640

    train_df = df.iloc[:-holdout_size]
    test_df = df.iloc[-holdout_size:]

    X_train = train_df[features]
    y_train = train_df[target]
    X_test = test_df[features]
    y_test = test_df[target]

    # Pick the best model
    lgb_mape = lgb_results["mape"].mean() if not lgb_results.empty else 999
    xgb_mape = xgb_results["mape"].mean() if not xgb_results.empty else 999
    best_name = "LightGBM" if lgb_mape <= xgb_mape else "XGBoost"
    best_class = LightGBMForecaster if lgb_mape <= xgb_mape else XGBoostForecaster

    print(f"\n  Best model: {best_name} (CV MAPE: {min(lgb_mape, xgb_mape):.2f}%)")

    best_model = best_class(resolution=resolution)
    best_model.fit(X_train, y_train, X_test, y_test)

    # Final holdout evaluation
    preds = best_model.predict(X_test)
    print_metrics_report(y_test.values, preds, test_df.index, f"{best_name} (Holdout)")

    # Feature importance
    imp = best_model.get_feature_importance()
    if imp is not None:
        print(f"\n  Top 15 Features:")
        for feat, val in imp.head(15).items():
            print(f"    {feat:<35s} {val:>8.0f}")

    # Save model
    save_dir = Path("models") / resolution / best_name.lower()
    best_model.save(save_dir)
    model_size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"\n  Model saved to {save_dir} ({model_size:.1f} MB)")

    # Comparison summary
    print(f"\n{'='*60}")
    print(f"  COMPARISON vs OLD EDFS")
    print(f"{'='*60}")
    print(f"  Metric        Old SARIMAX    New {best_name}")
    print(f"  {'-'*45}")
    best_mape = min(lgb_mape, xgb_mape)
    n_folds = max(len(lgb_results), len(xgb_results))
    print(f"  MAPE          24.77%         {best_mape:.2f}%")
    print(f"  Model Size    ~400 MB        {model_size:.1f} MB")
    print(f"  Features      4              {len(features)}")
    print(f"  Validation    None           {n_folds}-fold walk-forward")
    print(f"{'='*60}")

    return best_model


if __name__ == "__main__":
    resolution = sys.argv[1] if len(sys.argv) > 1 else "hourly"
    train_and_evaluate(resolution)

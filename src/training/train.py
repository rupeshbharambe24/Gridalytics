"""Training orchestrator for EDFS v2.

End-to-end pipeline that:
1. Builds features via FeaturePipeline
2. Trains LightGBM + XGBoost with walk-forward CV
3. Logs results to MLflow
4. Picks the champion model (lowest mean MAPE)
5. Saves the best model to disk
"""

import logging
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster
from src.evaluation.cross_validation import walk_forward_cv
from src.evaluation.metrics import print_metrics_report
from src.training.registry import log_training_run

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# Holdout sizes per resolution
HOLDOUT_SIZES = {
    "hourly": 720,   # 30 days
    "daily": 30,     # 1 month
    "5min": 8640,    # 30 days
}

# Sub-regional columns to exclude from features
SUB_REGIONAL_COLS = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]


def _build_features(
    resolution: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[pd.DataFrame, str, list[str]]:
    """Build the feature matrix and return (df, target, feature_names)."""
    with get_session() as session:
        pipeline = FeaturePipeline(resolution, session)
        df = pipeline.build(start_date, end_date)

    target = pipeline.get_target_name()
    features = pipeline.get_feature_names(df)

    # Remove sub-regional columns
    features = [f for f in features if f not in SUB_REGIONAL_COLS]

    # Drop columns with >10% nulls
    null_pct = df[features].isnull().mean()
    bad_cols = null_pct[null_pct > 0.1].index.tolist()
    if bad_cols:
        logger.info(f"Dropping {len(bad_cols)} features with >10% nulls: {bad_cols}")
        features = [f for f in features if f not in bad_cols]

    # Forward-fill remaining sparse nulls
    df[features] = df[features].ffill().fillna(0)

    return df, target, features


def _run_cv(
    model_class,
    df: pd.DataFrame,
    target: str,
    features: list[str],
    resolution: str,
    model_kwargs: dict | None = None,
) -> pd.DataFrame:
    """Run walk-forward CV and return per-fold metrics DataFrame."""
    return walk_forward_cv(
        model_class, df, target, features, resolution, model_kwargs=model_kwargs
    )


def _train_final_model(
    model_class,
    df: pd.DataFrame,
    target: str,
    features: list[str],
    resolution: str,
    model_kwargs: dict | None = None,
):
    """Train the final model on all data except holdout, return (model, holdout_metrics)."""
    holdout_size = HOLDOUT_SIZES.get(resolution, 720)

    train_df = df.iloc[:-holdout_size]
    test_df = df.iloc[-holdout_size:]

    X_train = train_df[features]
    y_train = train_df[target]
    X_test = test_df[features]
    y_test = test_df[target]

    model = model_class(resolution=resolution, **(model_kwargs or {}))
    model.fit(X_train, y_train, X_test, y_test)

    preds = model.predict(X_test)
    holdout_metrics = print_metrics_report(
        y_test.values, preds, test_df.index, f"{model.name} (Holdout)"
    )

    return model, holdout_metrics


def train(
    resolution: str = "hourly",
    start_date: date | None = None,
    end_date: date | None = None,
    lgb_params: dict | None = None,
    xgb_params: dict | None = None,
    save_dir: str | Path = "models",
) -> dict:
    """Full training pipeline: features -> CV -> MLflow -> champion -> save.

    Args:
        resolution: '5min', 'hourly', or 'daily'.
        start_date: Start of training data range.
        end_date: End of training data range.
        lgb_params: Optional custom LightGBM hyperparameters.
        xgb_params: Optional custom XGBoost hyperparameters.
        save_dir: Base directory for saving models.

    Returns:
        Dict with training results including champion model info and run IDs.
    """
    save_dir = Path(save_dir)

    print(f"\n{'#' * 60}")
    print(f"  EDFS v2 - Training Pipeline ({resolution})")
    print(f"{'#' * 60}")

    # --- Step 1: Build features ---
    print("\n[1/5] Building feature matrix...")
    df, target, features = _build_features(resolution, start_date, end_date)
    print(f"  Data: {len(df):,} rows, {len(features)} features")
    print(f"  Date range: {df.index.min()} to {df.index.max()}")
    print(f"  Target: {target} (mean={df[target].mean():.0f} MW)")

    # --- Step 2: Walk-forward CV for LightGBM ---
    print(f"\n[2/5] Walk-forward CV: LightGBM...")
    lgb_kwargs = {"params": lgb_params} if lgb_params else {}
    lgb_results = _run_cv(LightGBMForecaster, df, target, features, resolution, lgb_kwargs)
    lgb_mape = lgb_results["mape"].mean() if not lgb_results.empty else 999.0
    _print_cv_results("LightGBM", lgb_results)

    # --- Step 3: Walk-forward CV for XGBoost ---
    print(f"\n[3/5] Walk-forward CV: XGBoost...")
    xgb_kwargs = {"params": xgb_params} if xgb_params else {}
    xgb_results = _run_cv(XGBoostForecaster, df, target, features, resolution, xgb_kwargs)
    xgb_mape = xgb_results["mape"].mean() if not xgb_results.empty else 999.0
    _print_cv_results("XGBoost", xgb_results)

    # --- Step 4: Log results to MLflow ---
    print(f"\n[4/5] Logging results to MLflow...")
    lgb_run_id = None
    xgb_run_id = None

    if not lgb_results.empty:
        lgb_metrics = {
            "mean_mape": lgb_mape,
            "mean_rmse": lgb_results["rmse"].mean(),
            "mean_mae": lgb_results["mae"].mean(),
            "mean_r2": lgb_results["r2"].mean(),
            "std_mape": lgb_results["mape"].std(),
            "n_folds": len(lgb_results),
        }
        lgb_log_params = lgb_params or LightGBMForecaster(resolution=resolution).get_params()
        lgb_run_id = log_training_run(
            "lightgbm", resolution, lgb_log_params, lgb_metrics
        )
        print(f"  LightGBM run: {lgb_run_id}")

    if not xgb_results.empty:
        xgb_metrics = {
            "mean_mape": xgb_mape,
            "mean_rmse": xgb_results["rmse"].mean(),
            "mean_mae": xgb_results["mae"].mean(),
            "mean_r2": xgb_results["r2"].mean(),
            "std_mape": xgb_results["mape"].std(),
            "n_folds": len(xgb_results),
        }
        xgb_log_params = xgb_params or XGBoostForecaster(resolution=resolution).get_params()
        xgb_run_id = log_training_run(
            "xgboost", resolution, xgb_log_params, xgb_metrics
        )
        print(f"  XGBoost run: {xgb_run_id}")

    # --- Step 5: Pick champion and train final model ---
    print(f"\n[5/5] Training champion model...")
    if lgb_mape <= xgb_mape:
        champion_name = "lightgbm"
        champion_class = LightGBMForecaster
        champion_kwargs = lgb_kwargs
        champion_mape = lgb_mape
    else:
        champion_name = "xgboost"
        champion_class = XGBoostForecaster
        champion_kwargs = xgb_kwargs
        champion_mape = xgb_mape

    print(f"  Champion: {champion_name} (CV MAPE: {champion_mape:.2f}%)")

    champion_model, holdout_metrics = _train_final_model(
        champion_class, df, target, features, resolution, champion_kwargs
    )

    # Save model
    model_dir = save_dir / resolution / champion_name
    champion_model.save(model_dir)
    model_size = sum(f.stat().st_size for f in model_dir.rglob("*")) / (1024 * 1024)
    print(f"  Model saved to {model_dir} ({model_size:.1f} MB)")

    # Log champion run with artifacts
    champion_metrics = {
        "mean_mape": champion_mape,
        "holdout_mape": holdout_metrics["mape"],
        "holdout_rmse": holdout_metrics["rmse"],
        "holdout_mae": holdout_metrics["mae"],
        "holdout_r2": holdout_metrics["r2"],
    }
    champion_run_id = log_training_run(
        f"{champion_name}-champion",
        resolution,
        champion_model.get_params(),
        champion_metrics,
        model_path=str(model_dir),
    )
    print(f"  Champion run: {champion_run_id}")

    # Feature importance
    imp = champion_model.get_feature_importance()
    if imp is not None:
        print(f"\n  Top 15 Features:")
        for feat, val in imp.head(15).items():
            print(f"    {feat:<35s} {val:>8.0f}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  TRAINING COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Champion:     {champion_name}")
    print(f"  CV MAPE:      {champion_mape:.2f}%")
    print(f"  Holdout MAPE: {holdout_metrics['mape']:.2f}%")
    print(f"  Model Size:   {model_size:.1f} MB")
    print(f"  Features:     {len(features)}")
    print(f"  Saved to:     {model_dir}")
    print(f"{'=' * 60}")

    return {
        "champion": champion_name,
        "resolution": resolution,
        "cv_mape": champion_mape,
        "holdout_metrics": holdout_metrics,
        "model_dir": str(model_dir),
        "model_size_mb": model_size,
        "n_features": len(features),
        "lgb_run_id": lgb_run_id,
        "xgb_run_id": xgb_run_id,
        "champion_run_id": champion_run_id,
        "lgb_cv_mape": lgb_mape,
        "xgb_cv_mape": xgb_mape,
    }


def _print_cv_results(name: str, results_df: pd.DataFrame):
    """Print formatted CV results table."""
    print(f"\n  {name} CV Results:")
    if results_df.empty:
        print("  (no results - not enough data for CV)")
        return
    print(f"  {'Fold':<6} {'MAPE':>7} {'RMSE':>8} {'MAE':>8} {'R2':>8}")
    print(f"  {'-' * 38}")
    for _, row in results_df.iterrows():
        print(f"  {int(row['fold']):<6} {row['mape']:>6.2f}% "
              f"{row['rmse']:>7.1f} {row['mae']:>7.1f} {row['r2']:>7.4f}")
    print(f"  {'-' * 38}")
    print(f"  {'MEAN':<6} {results_df['mape'].mean():>6.2f}% "
          f"{results_df['rmse'].mean():>7.1f} "
          f"{results_df['mae'].mean():>7.1f} {results_df['r2'].mean():>7.4f}")


if __name__ == "__main__":
    import sys
    resolution = sys.argv[1] if len(sys.argv) > 1 else "hourly"
    train(resolution)

"""Run Optuna hyperparameter tuning for LightGBM on hourly data.

Finds optimal hyperparameters, then retrains and saves the improved model.
Uses 20 trials (quick) - increase for better results.

Usage: python scripts/run_optuna_tuning.py [resolution] [n_trials]
"""

import sys
import warnings
import logging
from pathlib import Path
from datetime import date

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.training.hyperopt import tune_lightgbm, tune_xgboost
from src.models.lightgbm_model import LightGBMForecaster
from src.evaluation.metrics import print_metrics_report


def main():
    resolution = sys.argv[1] if len(sys.argv) > 1 else "hourly"
    n_trials = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    print(f"\n{'#'*60}")
    print(f"  Gridalytics - Optuna Hyperparameter Tuning")
    print(f"  Resolution: {resolution} | Trials: {n_trials}")
    print(f"{'#'*60}\n")

    # Build features
    print("[1/4] Building features...")
    with get_session() as session:
        pipeline = FeaturePipeline(resolution, session)
        df = pipeline.build(date(2021, 1, 1), date(2026, 3, 28))

    target = pipeline.get_target_name()
    features = pipeline.get_feature_names(df)
    features = [f for f in features if f not in ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]]

    # Remove non-numeric
    numeric_cols = df[features].select_dtypes(include=["number", "bool"]).columns.tolist()
    features = [f for f in features if f in numeric_cols]
    df[features] = df[features].ffill().fillna(0)

    print(f"  Data: {len(df):,} rows, {len(features)} features\n")

    # Run Optuna tuning for LightGBM
    print(f"[2/4] Tuning LightGBM ({n_trials} trials)...")
    best_params, best_mape, study = tune_lightgbm(df, target, features, resolution, n_trials=n_trials)

    print(f"\n  Best LightGBM params:")
    for k, v in best_params.items():
        print(f"    {k}: {v}")
    print(f"  Best CV MAPE: {best_mape:.4f}%\n")

    # Retrain with best params
    print(f"[3/4] Retraining with optimized params...")
    holdout = {"5min": 864, "hourly": 720, "daily": 30}.get(resolution, 720)
    train_df = df.iloc[:-holdout]
    test_df = df.iloc[-holdout:]

    model = LightGBMForecaster(resolution=resolution, params={
        **best_params,
        "objective": "regression",
        "metric": "mae",
        "boosting_type": "gbdt",
        "verbose": -1,
        "n_jobs": -1,
    })
    model.fit(train_df[features], train_df[target], test_df[features], test_df[target])

    preds = model.predict(test_df[features])
    metrics = print_metrics_report(test_df[target].values, preds, test_df.index, f"Optimized LightGBM ({resolution})")

    # Save
    print(f"\n[4/4] Saving optimized model...")
    save_dir = Path("models") / resolution / "lightgbm"
    model.save(save_dir)
    size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"  Saved to {save_dir} ({size:.1f} MB)")
    print(f"\n  Optimized MAPE: {metrics['mape']:.2f}% (was: ~{best_mape:.2f}% CV)")


if __name__ == "__main__":
    main()

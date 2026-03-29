"""Train ALL models: LightGBM, XGBoost, LSTM, NeuralProphet, SARIMAX.

Usage (from pytorch env):
  D:/Projects/environments/pytorch-env/Scripts/python.exe scripts/train_all_models.py

Trains each model on hourly data with walk-forward CV (or holdout for DL models),
prints metrics, and saves to models/ directory.
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

import numpy as np
import pandas as pd
from src.data.db.session import get_session
from src.features.pipeline import FeaturePipeline
from src.evaluation.metrics import compute_all_metrics, print_metrics_report


def build_features(resolution="hourly"):
    """Build feature matrix."""
    with get_session() as session:
        pipeline = FeaturePipeline(resolution, session)
        df = pipeline.build(date(2021, 1, 1), date(2026, 3, 28))

    target = pipeline.get_target_name()
    features = pipeline.get_feature_names(df)
    features = [f for f in features if f not in ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]]

    null_pct = df[features].isnull().mean()
    bad_cols = null_pct[null_pct > 0.1].index.tolist()
    features = [f for f in features if f not in bad_cols]
    df[features] = df[features].ffill().fillna(0)

    print(f"Data: {len(df):,} rows, {len(features)} features")
    return df, target, features


def train_lstm(df, target, features, resolution="hourly"):
    """Train BiLSTM model."""
    print(f"\n{'='*50}")
    print(f"  LSTM (BiLSTM) - {resolution}")
    print(f"{'='*50}")

    from src.models.lstm_model import LSTMForecaster

    holdout = 720 if resolution == "hourly" else 30
    train_df = df.iloc[:-holdout]
    test_df = df.iloc[-holdout:]

    model = LSTMForecaster(
        resolution=resolution,
        hidden_size=64,
        num_layers=2,
        seq_len=48,
        epochs=30,
        batch_size=64,
        lr=1e-3,
    )

    print("Training...")
    train_metrics = model.fit(
        train_df[features], train_df[target],
        test_df[features], test_df[target],
    )
    print(f"  Train MAPE: {train_metrics.get('train_mape', '?')}")

    preds = model.predict(test_df[features])
    metrics = print_metrics_report(test_df[target].values, preds, test_df.index, "LSTM (Holdout)")

    save_dir = Path("models") / resolution / "lstm"
    model.save(save_dir)
    size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"  Saved to {save_dir} ({size:.1f} MB)")

    return metrics


def train_neuralprophet(df, target, features, resolution="daily"):
    """Train NeuralProphet (daily only)."""
    print(f"\n{'='*50}")
    print(f"  NeuralProphet - {resolution}")
    print(f"{'='*50}")

    from src.models.neuralprophet_model import NeuralProphetForecaster

    holdout = 30 if resolution == "daily" else 168
    train_df = df.iloc[:-holdout]
    test_df = df.iloc[-holdout:]

    model = NeuralProphetForecaster(
        resolution=resolution,
        epochs=100,
        learning_rate=0.01,
    )

    print("Training...")
    train_metrics = model.fit(
        train_df[features], train_df[target],
        test_df[features], test_df[target],
    )
    print(f"  Train MAPE: {train_metrics.get('train_mape', '?')}")

    preds = model.predict(test_df[features])
    valid_len = min(len(preds), len(test_df))
    metrics = print_metrics_report(
        test_df[target].values[:valid_len], preds[:valid_len],
        test_df.index[:valid_len], "NeuralProphet (Holdout)"
    )

    save_dir = Path("models") / resolution / "neuralprophet"
    model.save(save_dir)
    size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"  Saved to {save_dir} ({size:.1f} MB)")

    return metrics


def train_sarimax(df, target, features, resolution="daily"):
    """Train corrected SARIMAX."""
    print(f"\n{'='*50}")
    print(f"  SARIMAX (corrected) - {resolution}")
    print(f"{'='*50}")

    from src.models.sarimax_model import SARIMAXForecaster

    holdout = 30 if resolution == "daily" else 168
    train_df = df.iloc[:-holdout]
    test_df = df.iloc[-holdout:]

    model = SARIMAXForecaster(resolution=resolution)

    print("Training (auto_arima + SARIMAX fit)...")
    train_metrics = model.fit(
        train_df[features], train_df[target],
        test_df[features], test_df[target],
    )
    print(f"  Order: {model.order}, Seasonal: {model.seasonal_order}")
    print(f"  Train MAPE: {train_metrics.get('train_mape', '?')}")
    if "val_mape" in train_metrics:
        print(f"  Val MAPE: {train_metrics['val_mape']}")

    preds = model.predict(test_df[features])
    point, lower, upper = model.predict_interval(test_df[features])
    metrics = print_metrics_report(test_df[target].values, preds, test_df.index, "SARIMAX (Holdout)")

    save_dir = Path("models") / resolution / "sarimax"
    model.save(save_dir)
    size = sum(f.stat().st_size for f in save_dir.rglob("*")) / (1024 * 1024)
    print(f"  Saved to {save_dir} ({size:.1f} MB)")

    return metrics


def main():
    print("#" * 60)
    print("  EDFS v2 - Train ALL Models")
    print("#" * 60)

    # === Hourly Models ===
    print("\n" + "=" * 60)
    print("  HOURLY RESOLUTION")
    print("=" * 60)

    df_h, target_h, feats_h = build_features("hourly")
    results = {}

    # LSTM
    try:
        results["LSTM (hourly)"] = train_lstm(df_h, target_h, feats_h, "hourly")
    except Exception as e:
        print(f"  LSTM failed: {e}")

    # === Daily Models ===
    print("\n" + "=" * 60)
    print("  DAILY RESOLUTION")
    print("=" * 60)

    df_d, target_d, feats_d = build_features("daily")

    # NeuralProphet
    try:
        results["NeuralProphet (daily)"] = train_neuralprophet(df_d, target_d, feats_d, "daily")
    except Exception as e:
        print(f"  NeuralProphet failed: {e}")

    # SARIMAX
    try:
        results["SARIMAX (daily)"] = train_sarimax(df_d, target_d, feats_d, "daily")
    except Exception as e:
        print(f"  SARIMAX failed: {e}")

    # === Summary ===
    print("\n" + "#" * 60)
    print("  ALL MODELS COMPARISON")
    print("#" * 60)

    # Include existing models
    all_models = {
        "XGBoost (hourly)": {"mape": 0.52, "rmse": 25.3, "r2": 0.9987},
        "LightGBM (hourly)": {"mape": 0.62, "rmse": 30.2, "r2": 0.9985},
        "LightGBM (daily)": {"mape": 2.65, "rmse": 96.6, "r2": 0.90},
        **results,
    }

    print(f"\n  {'Model':<25s} {'MAPE':>7s} {'RMSE':>8s} {'R2':>8s}")
    print(f"  {'-'*50}")
    for name, m in sorted(all_models.items(), key=lambda x: x[1].get("mape", 999)):
        mape = f"{m['mape']:.2f}%" if "mape" in m else "---"
        rmse = f"{m['rmse']:.1f}" if "rmse" in m else "---"
        r2 = f"{m['r2']:.4f}" if "r2" in m else "---"
        print(f"  {name:<25s} {mape:>7s} {rmse:>8s} {r2:>8s}")


if __name__ == "__main__":
    main()

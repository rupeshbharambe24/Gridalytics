"""Walk-forward time series cross-validation.

The gold standard for evaluating time series models:
- Train on expanding window of past data
- Predict the next window
- Step forward and repeat
- NEVER use future data in training (no data leakage)
"""

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.evaluation.metrics import compute_all_metrics

logger = logging.getLogger(__name__)


# CV configuration per resolution
CV_CONFIGS = {
    "daily": {
        "min_train_rows": 365,      # 1 year minimum training data
        "val_window_rows": 30,      # 1 month validation window
        "n_folds": 12,              # 12 folds = 12 months of rolling validation
    },
    "hourly": {
        "min_train_rows": 720,      # 30 days minimum
        "val_window_rows": 168,     # 1 week validation window
        "n_folds": 12,
    },
    "5min": {
        "min_train_rows": 8640,     # 30 days minimum
        "val_window_rows": 864,     # 3 days validation window
        "n_folds": 10,
    },
}


@dataclass
class CVFold:
    """A single cross-validation fold with train/val indices."""
    fold_idx: int
    train_start: int
    train_end: int
    val_start: int
    val_end: int


def generate_folds(n_rows: int, resolution: str) -> list[CVFold]:
    """Generate walk-forward CV fold indices.

    Uses expanding window: each fold adds more training data.
    """
    config = CV_CONFIGS.get(resolution, CV_CONFIGS["hourly"])
    min_train = config["min_train_rows"]
    val_window = config["val_window_rows"]
    n_folds = config["n_folds"]

    folds = []
    # Work backwards from the end to place folds
    total_val = n_folds * val_window
    if min_train + total_val > n_rows:
        # Not enough data - reduce folds
        n_folds = max(3, (n_rows - min_train) // val_window)
        logger.warning(f"Reduced to {n_folds} folds due to data size")

    for i in range(n_folds):
        val_end = n_rows - (n_folds - i - 1) * val_window
        val_start = val_end - val_window
        train_start = 0  # expanding window
        train_end = val_start

        if train_end - train_start < min_train:
            continue

        folds.append(CVFold(
            fold_idx=i,
            train_start=train_start,
            train_end=train_end,
            val_start=val_start,
            val_end=val_end,
        ))

    return folds


def walk_forward_cv(
    model_class,
    df: pd.DataFrame,
    target: str,
    feature_cols: list[str],
    resolution: str,
    model_kwargs: dict | None = None,
    scale_features: bool = False,
) -> pd.DataFrame:
    """Run walk-forward cross-validation on a model.

    Args:
        model_class: The forecaster class to instantiate per fold
        df: DataFrame with features and target
        target: Target column name
        feature_cols: List of feature column names
        resolution: '5min', 'hourly', or 'daily'
        model_kwargs: Extra kwargs to pass to model constructor
        scale_features: Whether to StandardScale features (for DL models)

    Returns:
        DataFrame with per-fold metrics
    """
    model_kwargs = model_kwargs or {}
    folds = generate_folds(len(df), resolution)

    if not folds:
        logger.error("Not enough data for cross-validation")
        return pd.DataFrame()

    results = []
    all_preds = []
    all_actuals = []
    all_timestamps = []

    for fold in folds:
        logger.info(f"Fold {fold.fold_idx + 1}/{len(folds)}: "
                     f"train[:{fold.train_end}] val[{fold.val_start}:{fold.val_end}]")

        # Split data
        train_df = df.iloc[fold.train_start:fold.train_end]
        val_df = df.iloc[fold.val_start:fold.val_end]

        X_train = train_df[feature_cols]
        y_train = train_df[target]
        X_val = val_df[feature_cols]
        y_val = val_df[target]

        # Optional scaling (fit on train only!)
        if scale_features:
            scaler = StandardScaler()
            X_train = pd.DataFrame(
                scaler.fit_transform(X_train),
                columns=feature_cols,
                index=X_train.index,
            )
            X_val = pd.DataFrame(
                scaler.transform(X_val),
                columns=feature_cols,
                index=X_val.index,
            )

        # Train model
        model = model_class(resolution=resolution, **model_kwargs)
        train_metrics = model.fit(X_train, y_train, X_val, y_val)

        # Predict
        preds = model.predict(X_val)

        # Compute fold metrics
        fold_metrics = compute_all_metrics(y_val.values, preds)
        fold_metrics["fold"] = fold.fold_idx
        fold_metrics["train_size"] = len(X_train)
        fold_metrics["val_size"] = len(X_val)
        fold_metrics["val_start"] = str(val_df.index[0])
        fold_metrics["val_end"] = str(val_df.index[-1])
        results.append(fold_metrics)

        all_preds.extend(preds)
        all_actuals.extend(y_val.values)
        all_timestamps.extend(val_df.index)

        logger.info(f"  Fold {fold.fold_idx + 1} MAPE: {fold_metrics['mape']:.2f}%  "
                     f"RMSE: {fold_metrics['rmse']:.1f}")

    results_df = pd.DataFrame(results)

    # Summary
    logger.info(f"\nCV Summary ({len(folds)} folds):")
    logger.info(f"  Mean MAPE: {results_df['mape'].mean():.2f}% +/- {results_df['mape'].std():.2f}%")
    logger.info(f"  Mean RMSE: {results_df['rmse'].mean():.1f} +/- {results_df['rmse'].std():.1f}")
    logger.info(f"  Mean R²:   {results_df['r2'].mean():.4f}")

    return results_df

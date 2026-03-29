"""Evaluation metrics for EDFS forecasting models."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)


def compute_all_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute all standard forecasting metrics."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    # Filter out any zero/near-zero actuals for MAPE
    mask = np.abs(y_true) > 1.0
    y_t = y_true[mask]
    y_p = y_pred[mask]

    return {
        "mape": float(np.mean(np.abs((y_t - y_p) / y_t)) * 100),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
        "max_error": float(np.max(np.abs(y_true - y_pred))),
        "n_samples": len(y_true),
    }


def compute_seasonal_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    timestamps: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Break down metrics by Delhi season."""
    seasons = classify_delhi_season(timestamps)
    results = []

    for season in seasons.unique():
        mask = seasons == season
        if mask.sum() < 5:
            continue
        m = compute_all_metrics(y_true[mask], y_pred[mask])
        m["season"] = season
        results.append(m)

    # Overall
    m = compute_all_metrics(y_true, y_pred)
    m["season"] = "ALL"
    results.append(m)

    return pd.DataFrame(results).set_index("season")


def classify_delhi_season(timestamps: pd.DatetimeIndex) -> pd.Series:
    """Classify timestamps into Delhi seasons."""
    month = timestamps.month
    return pd.Series(
        np.select(
            [
                np.isin(month, [11, 12, 1, 2]),
                np.isin(month, [3, 4]),
                np.isin(month, [5, 6]),
                np.isin(month, [7, 8, 9]),
                np.isin(month, [10]),
            ],
            ["Winter", "Spring", "Summer", "Monsoon", "Autumn"],
            default="Unknown",
        ),
        index=timestamps,
    )


def print_metrics_report(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    timestamps: pd.DatetimeIndex,
    model_name: str = "Model",
) -> dict:
    """Print a formatted metrics report and return the metrics dict."""
    overall = compute_all_metrics(y_true, y_pred)
    seasonal = compute_seasonal_metrics(y_true, y_pred, timestamps)

    print(f"\n{'='*55}")
    print(f"  {model_name} - Evaluation Report")
    print(f"{'='*55}")
    print(f"  MAPE:      {overall['mape']:.2f}%")
    print(f"  RMSE:      {overall['rmse']:.1f} MW")
    print(f"  MAE:       {overall['mae']:.1f} MW")
    print(f"  R²:        {overall['r2']:.4f}")
    print(f"  Max Error: {overall['max_error']:.1f} MW")
    print(f"  Samples:   {overall['n_samples']:,}")
    print(f"\n  Seasonal Breakdown:")
    print(f"  {'Season':<10} {'MAPE':>7} {'RMSE':>8} {'MAE':>8} {'N':>6}")
    print(f"  {'-'*41}")
    for season, row in seasonal.iterrows():
        if season == "ALL":
            continue
        print(f"  {season:<10} {row['mape']:>6.2f}% {row['rmse']:>7.1f} {row['mae']:>7.1f} {int(row['n_samples']):>6}")
    print(f"{'='*55}")

    return overall

"""Hyperparameter tuning with Optuna for LightGBM and XGBoost."""

import logging

import optuna
import pandas as pd

from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster
from src.evaluation.cross_validation import walk_forward_cv

logger = logging.getLogger(__name__)


def tune_lightgbm(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    resolution: str,
    n_trials: int = 50,
) -> tuple[dict, float, optuna.Study]:
    """Tune LightGBM hyperparameters using Optuna with walk-forward CV.

    Args:
        df: Feature DataFrame with datetime index.
        target: Target column name.
        features: List of feature column names.
        resolution: '5min', 'hourly', or 'daily'.
        n_trials: Number of Optuna trials to run.

    Returns:
        Tuple of (best_params, best_mape, study).
    """

    def objective(trial: optuna.Trial) -> float:
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 20, 150),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 200, 2000),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": trial.suggest_int("bagging_freq", 1, 10),
        }

        results = walk_forward_cv(
            LightGBMForecaster,
            df,
            target,
            features,
            resolution,
            model_kwargs={"params": params},
        )

        if results.empty:
            return 999.0

        return results["mape"].mean()

    study = optuna.create_study(
        direction="minimize",
        study_name=f"lgb-{resolution}",
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    logger.info(f"LightGBM tuning complete: best MAPE={study.best_value:.2f}%")
    logger.info(f"Best params: {study.best_params}")

    return study.best_params, study.best_value, study


def tune_xgboost(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    resolution: str,
    n_trials: int = 50,
) -> tuple[dict, float, optuna.Study]:
    """Tune XGBoost hyperparameters using Optuna with walk-forward CV.

    Args:
        df: Feature DataFrame with datetime index.
        target: Target column name.
        features: List of feature column names.
        resolution: '5min', 'hourly', or 'daily'.
        n_trials: Number of Optuna trials to run.

    Returns:
        Tuple of (best_params, best_mape, study).
    """

    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 200, 2000),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 50),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "gamma": trial.suggest_float("gamma", 1e-4, 5.0, log=True),
        }

        results = walk_forward_cv(
            XGBoostForecaster,
            df,
            target,
            features,
            resolution,
            model_kwargs={"params": params},
        )

        if results.empty:
            return 999.0

        return results["mape"].mean()

    study = optuna.create_study(
        direction="minimize",
        study_name=f"xgb-{resolution}",
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    logger.info(f"XGBoost tuning complete: best MAPE={study.best_value:.2f}%")
    logger.info(f"Best params: {study.best_params}")

    return study.best_params, study.best_value, study


def run_tuning(
    df: pd.DataFrame,
    target: str,
    features: list[str],
    resolution: str,
    n_trials: int = 50,
) -> dict:
    """Convenience function: tune both LightGBM and XGBoost.

    Args:
        df: Feature DataFrame with datetime index.
        target: Target column name.
        features: List of feature column names.
        resolution: '5min', 'hourly', or 'daily'.
        n_trials: Number of Optuna trials per model.

    Returns:
        Dict with keys 'lightgbm' and 'xgboost', each containing
        'best_params', 'best_mape', and 'study'.
    """
    logger.info(f"Starting hyperparameter tuning for {resolution} resolution "
                f"({n_trials} trials per model)")

    lgb_params, lgb_mape, lgb_study = tune_lightgbm(
        df, target, features, resolution, n_trials
    )
    xgb_params, xgb_mape, xgb_study = tune_xgboost(
        df, target, features, resolution, n_trials
    )

    winner = "lightgbm" if lgb_mape <= xgb_mape else "xgboost"
    logger.info(f"Tuning complete. Winner: {winner} "
                f"(LGB={lgb_mape:.2f}%, XGB={xgb_mape:.2f}%)")

    return {
        "lightgbm": {
            "best_params": lgb_params,
            "best_mape": lgb_mape,
            "study": lgb_study,
        },
        "xgboost": {
            "best_params": xgb_params,
            "best_mape": xgb_mape,
            "study": xgb_study,
        },
        "winner": winner,
    }

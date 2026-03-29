"""Training module: orchestration, MLflow tracking, and hyperparameter tuning."""

from src.training.registry import (
    setup_mlflow,
    log_training_run,
    get_best_run,
    list_experiments,
    compare_runs,
)
from src.training.hyperopt import (
    tune_lightgbm,
    tune_xgboost,
    run_tuning,
)
from src.training.train import train

__all__ = [
    # Registry / MLflow
    "setup_mlflow",
    "log_training_run",
    "get_best_run",
    "list_experiments",
    "compare_runs",
    # Hyperparameter tuning
    "tune_lightgbm",
    "tune_xgboost",
    "run_tuning",
    # Orchestrator
    "train",
]

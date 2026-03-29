"""MLflow experiment tracking and model registry."""

import os
import logging

import mlflow
import pandas as pd

from config.settings import settings

logger = logging.getLogger(__name__)


def setup_mlflow():
    """Initialize MLflow tracking URI and ensure artifact directory exists."""
    mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
    os.makedirs(settings.MLFLOW_ARTIFACT_ROOT, exist_ok=True)


def log_training_run(
    model_name: str,
    resolution: str,
    params: dict,
    metrics: dict,
    model_path: str | None = None,
) -> str:
    """Log a training run to MLflow.

    Args:
        model_name: e.g. 'lightgbm' or 'xgboost'
        resolution: '5min', 'hourly', or 'daily'
        params: Model hyperparameters to log
        metrics: Evaluation metrics to log
        model_path: Optional path to model artifacts directory

    Returns:
        The MLflow run ID.
    """
    setup_mlflow()
    experiment_name = f"edfs-{resolution}"
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name=f"{model_name}-{resolution}"):
        mlflow.log_param("model_name", model_name)
        mlflow.log_param("resolution", resolution)
        mlflow.log_params(params)
        mlflow.log_metrics(metrics)

        if model_path:
            mlflow.log_artifacts(str(model_path))

        run_id = mlflow.active_run().info.run_id
        logger.info(f"Logged run {run_id} to experiment '{experiment_name}'")
        return run_id


def get_best_run(resolution: str) -> dict | None:
    """Get the best run for a resolution by lowest mean MAPE.

    Returns:
        Dict of run info, or None if no runs exist.
    """
    setup_mlflow()
    experiment = mlflow.get_experiment_by_name(f"edfs-{resolution}")
    if not experiment:
        return None

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["metrics.mean_mape ASC"],
        max_results=1,
    )
    if runs.empty:
        return None

    return runs.iloc[0].to_dict()


def list_experiments() -> list[dict]:
    """List all EDFS MLflow experiments with their best runs.

    Returns:
        List of dicts, each with experiment name, resolution, run count,
        best MAPE, and up to 5 recent runs.
    """
    setup_mlflow()
    experiments = mlflow.search_experiments()
    results = []

    for exp in experiments:
        if not exp.name.startswith("edfs-"):
            continue

        runs = mlflow.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["metrics.mean_mape ASC"],
            max_results=5,
        )

        best_mape = None
        if not runs.empty and "metrics.mean_mape" in runs.columns:
            best_mape = runs.iloc[0]["metrics.mean_mape"]

        results.append({
            "experiment": exp.name,
            "resolution": exp.name.replace("edfs-", ""),
            "total_runs": len(runs),
            "best_mape": best_mape,
            "runs": runs.to_dict("records") if not runs.empty else [],
        })

    return results


def compare_runs(resolution: str, top_n: int = 10) -> pd.DataFrame:
    """Return a DataFrame comparing the top N runs for a resolution.

    Useful for printing a leaderboard of model performance.
    """
    setup_mlflow()
    experiment = mlflow.get_experiment_by_name(f"edfs-{resolution}")
    if not experiment:
        return pd.DataFrame()

    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["metrics.mean_mape ASC"],
        max_results=top_n,
    )

    if runs.empty:
        return pd.DataFrame()

    # Select the most useful columns
    cols = [c for c in runs.columns if c.startswith(("metrics.", "params."))]
    cols = ["run_id"] + sorted(cols)
    return runs[[c for c in cols if c in runs.columns]]

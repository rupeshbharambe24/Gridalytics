"""Model registry - loads and serves trained models for the API."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_models = {}


def load_models():
    """Load trained models at startup."""
    from src.models.lightgbm_model import LightGBMForecaster
    from src.models.xgboost_model import XGBoostForecaster

    loaders = [("lightgbm", LightGBMForecaster), ("xgboost", XGBoostForecaster)]
    # Optional heavier models — only loaded if their artifacts exist on disk.
    # Guarded so a missing statsmodels/torch never breaks API startup.
    try:
        from src.models.sarimax_model import SARIMAXForecaster, ARIMAForecaster
        loaders += [("sarimax", SARIMAXForecaster), ("arima", ARIMAForecaster)]
    except Exception as e:  # pragma: no cover
        logger.info(f"SARIMAX/ARIMA not available: {e}")
    try:
        from src.models.neuralprophet_model import NeuralProphetForecaster
        loaders += [("neuralprophet", NeuralProphetForecaster)]
    except Exception as e:  # pragma: no cover
        logger.info(f"NeuralProphet not available: {e}")

    model_dirs = {
        "5min": Path("models/5min"),
        "hourly": Path("models/hourly"),
        "daily": Path("models/daily"),
    }

    for resolution, base_dir in model_dirs.items():
        if not base_dir.exists():
            logger.warning(f"No models found for {resolution} at {base_dir}")
            continue

        for model_name, loader in loaders:
            model_path = base_dir / model_name
            if model_path.exists() and (model_path / "meta.json").exists():
                try:
                    model = loader.load(model_path)
                    _models[f"{resolution}_{model_name}"] = model
                    logger.info(f"Loaded {model_name} model for {resolution}")
                except Exception as e:
                    logger.error(f"Failed to load {model_name}/{resolution}: {e}")

    # Create ensemble from loaded models for each resolution
    from src.models.ensemble import EnsembleForecaster

    for resolution in ["5min", "hourly", "daily"]:
        res_models = [v for k, v in _models.items()
                      if k.startswith(f"{resolution}_") and "ensemble" not in k]
        if len(res_models) >= 2:
            ensemble = EnsembleForecaster(res_models, resolution=resolution)
            ensemble.is_fitted = True
            _models[f"{resolution}_ensemble"] = ensemble
            logger.info(f"Created ensemble for {resolution} from {len(res_models)} models")

    logger.info(f"Total models loaded: {len(_models)} (including ensembles)")


def reload_models() -> dict:
    """Clear and re-load all models from disk (admin hot-reload, no process restart).

    Drops the current in-memory set (so artifacts removed on disk don't linger as
    stale keys) and rebuilds it with load_models(). Returns the new roster.
    """
    _models.clear()
    load_models()
    return get_available_models()


def get_model(resolution: str, model_name: str | None = None):
    """Get a loaded model by resolution and optional name."""
    if model_name:
        key = f"{resolution}_{model_name}"
        return _models.get(key)

    # Prefer LightGBM: it is the reliably-serializable Delhi model. XGBoost is
    # currently unusable in this environment (xgboost 2.1.4 × sklearn 1.9.1 both
    # fails to save and reloads a corrupt model that predicts ~0 — see
    # docs/model_serving.md); keep it reachable by explicit name for comparison,
    # but never let it become the default served model by accident.
    for name in ["lightgbm", "xgboost"]:
        key = f"{resolution}_{name}"
        if key in _models:
            return _models[key]
    return None


def get_available_models() -> dict:
    """Return dict of loaded model keys."""
    return {k: v.name for k, v in _models.items()}

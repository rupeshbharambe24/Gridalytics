"""Model registry - loads and serves trained models for the API."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_models = {}


def load_models():
    """Load trained models at startup."""
    from src.models.lightgbm_model import LightGBMForecaster
    from src.models.xgboost_model import XGBoostForecaster

    model_dirs = {
        "5min": Path("models/5min"),
        "hourly": Path("models/hourly"),
        "daily": Path("models/daily"),
    }

    for resolution, base_dir in model_dirs.items():
        if not base_dir.exists():
            logger.warning(f"No models found for {resolution} at {base_dir}")
            continue

        for model_name, loader in [("lightgbm", LightGBMForecaster), ("xgboost", XGBoostForecaster)]:
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


def get_model(resolution: str, model_name: str | None = None):
    """Get a loaded model by resolution and optional name."""
    if model_name:
        key = f"{resolution}_{model_name}"
        return _models.get(key)

    for name in ["xgboost", "lightgbm"]:
        key = f"{resolution}_{name}"
        if key in _models:
            return _models[key]
    return None


def get_available_models() -> dict:
    """Return dict of loaded model keys."""
    return {k: v.name for k, v in _models.items()}

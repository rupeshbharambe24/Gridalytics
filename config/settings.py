"""Central configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./data/edfs.db"

    # Delhi coordinates
    DELHI_LAT: float = 28.7041
    DELHI_LON: float = 77.1025

    # Data source URLs
    SLDC_BASE_URL: str = "https://www.delhisldc.org/Loaddata.aspx"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    GRID_INDIA_URL: str = "https://report.grid-india.in/psp_report.php"

    # JWT Authentication
    JWT_SECRET: str = "change-this-to-a-random-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60

    # MLflow
    MLFLOW_TRACKING_URI: str = "sqlite:///./mlflow/mlflow.db"
    MLFLOW_ARTIFACT_ROOT: str = "./mlflow/artifacts"

    # Model serving
    MODEL_REGISTRY_PATH: Path = Path("./mlflow/artifacts")
    CHAMPION_MODEL_NAME: str = "edfs-champion"

    # Scheduling
    SCRAPE_INTERVAL_HOURS: int = 6
    RETRAIN_INTERVAL_DAYS: int = 7

    # Optional API keys
    VISUAL_CROSSING_API_KEY: str | None = None

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

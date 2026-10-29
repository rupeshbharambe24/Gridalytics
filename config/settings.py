"""Central configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./data/gridalytics.db"

    # Delhi coordinates
    DELHI_LAT: float = 28.7041
    DELHI_LON: float = 77.1025

    # Data source URLs
    SLDC_BASE_URL: str = "https://www.delhisldc.org/Loaddata.aspx"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_FORECAST_URL: str = "https://api.open-meteo.com/v1/forecast"
    GRID_INDIA_URL: str = "https://report.grid-india.in/psp_report.php"

    # Multi-state SLDC sources (Phase 1 of the all-India rollout).
    # See docs/state_grid_data_sources.md for the full per-state inventory.
    BIHAR_SLDC_URL: str = "https://sldc.bsptcl.co.in:8086/api/SCADA/Get"
    PUNJAB_SLDC_URL: str = "https://sldcapi.pstcl.org/wsDataService.asmx"
    UP_SLDC_URL: str = "https://www.upsldc.org/assets/dataset"
    # Phase 2 (static-HTML snapshots)
    KARNATAKA_SLDC_URL: str = "https://kptclsldc.in/"
    CHHATTISGARH_SLDC_URL: str = "https://sldccg.com/gen.php"
    # Gujarat: deferred — RealTime.php is access-gated (HTTP 403) and the homepage
    # live widget was removed; needs the official SLDC app API or GETCO access.
    GUJARAT_SLDC_URL: str = "https://sldcguj.com/"

    # Bihar & Punjab SLDC servers run old/broken TLS (incomplete cert chain,
    # legacy renegotiation) that Python rejects, though `curl` trusts them via
    # the OS store. Set SLDC_INSECURE_TLS=true in .env to scrape them with
    # relaxed verification. OFF by default — enabling it is a conscious choice
    # to skip cert verification for these specific public-data endpoints.
    SLDC_INSECURE_TLS: bool = False

    # JWT Authentication
    JWT_SECRET: str = "change-this-to-a-random-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60

    # MLflow
    MLFLOW_TRACKING_URI: str = "sqlite:///./mlflow/mlflow.db"
    MLFLOW_ARTIFACT_ROOT: str = "./mlflow/artifacts"

    # Model serving
    MODEL_REGISTRY_PATH: Path = Path("./mlflow/artifacts")
    CHAMPION_MODEL_NAME: str = "gridalytics-champion"

    # Scheduling
    SCRAPE_INTERVAL_HOURS: int = 6
    RETRAIN_INTERVAL_DAYS: int = 7

    # Optional API keys
    VISUAL_CROSSING_API_KEY: str | None = None

    # Drift alerts (optional - set in .env to enable email alerts)
    ALERT_EMAIL: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASS: str | None = None
    ALERT_FROM_EMAIL: str | None = None
    DRIFT_MAPE_THRESHOLD: float = 5.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

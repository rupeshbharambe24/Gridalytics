# EDFS v2 - Electricity Demand Forecasting System

AI-powered electricity demand forecasting for the **Delhi Power Grid**.

Predicts demand at 5-minute, hourly, and daily resolutions using machine learning models trained on 5+ years of historical demand data, weather patterns, holidays, and seasonal cycles.

## Performance

| Model | Resolution | MAPE | R2 | Model Size |
|-------|-----------|------|-----|------------|
| XGBoost | Hourly | **0.52%** | 0.9987 | 24.5 MB |
| LightGBM | Daily | **2.65%** | 0.8997 | 3.0 MB |

Validated with 12-fold walk-forward cross-validation. Real-time prediction tracking shows **0.97% avg MAPE** over 29 days of live evaluation.

**vs Previous System (SARIMAX):** 47x better accuracy, 133x smaller models, proper methodology (no data leakage).

## Architecture

```
FastAPI Backend (Python 3.11)
├── Data Pipeline: SLDC scraper, Open-Meteo weather, AQI, holidays
├── Feature Engineering: 93 features (lags, CDD, cyclical, rolling stats)
├── Models: LightGBM, XGBoost (+ LSTM, TFT planned)
├── Evaluation: Walk-forward CV, seasonal metrics, drift detection
├── Prediction Tracker: Daily predicted vs actual logging
└── Scheduler: Automated data collection + model monitoring

Next.js Frontend (React + Tailwind + Framer Motion)
├── Dashboard: KPI cards, demand chart, heatmap
├── Forecast: Hourly/daily predictions with confidence intervals
├── What-If: Temperature/humidity/holiday scenario explorer
├── Models: Performance comparison, old vs new metrics
├── Analytics: 90-day trends, seasonal patterns
└── Accuracy: Predicted vs actual tracker, drift detection
```

## Quick Start

### 1. Backend

```bash
cd E:/Projects/EDFS-v2

# Install dependencies
pip install pandas numpy sqlalchemy pydantic pydantic-settings python-dotenv \
  requests beautifulsoup4 httpx lightgbm xgboost scikit-learn \
  fastapi uvicorn python-jose passlib holidays apscheduler

# Copy environment config
cp .env.example .env

# Create database and import legacy data
python -c "from src.data.db.session import create_tables; create_tables()"
python scripts/migrate_legacy_data.py

# Backfill demand data to current date
python scripts/backfill_demand.py

# Train models
python scripts/initial_train.py hourly
python scripts/initial_train.py daily

# Start API server
uvicorn src.api.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard: http://localhost:3000

### 3. Continuous Data Collection (optional)

```bash
# Run once to fetch latest data
python -m src.data.scheduler --once

# Run continuously (scrapes every 6 hours, predicts daily)
python -m src.data.scheduler
```

## Data Sources (all free)

| Source | Data | Frequency | API |
|--------|------|-----------|-----|
| Delhi SLDC | 5-min demand (Delhi + 5 sub-regions) | Every 6h | delhisldc.org (scraping) |
| Open-Meteo | Hourly weather (temp, humidity, dew point, wind, solar) | Daily | open-meteo.com (free API) |
| Open-Meteo | 16-day weather forecast | Every 6h | open-meteo.com (free API) |
| Open-Meteo | Air Quality (PM2.5, PM10, AQI) | Daily | open-meteo.com (free API) |
| holidays lib | Indian holidays + festivals | On-demand | Python package |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health/ready` | Health check |
| POST | `/api/v1/auth/register` | Register user |
| POST | `/api/v1/auth/login` | Login (JWT) |
| GET | `/api/v1/forecast/{resolution}?date=` | Forecast (past or future) |
| GET | `/api/v1/forecast/{resolution}/range` | Multi-day forecast |
| POST | `/api/v1/forecast/what-if` | Custom scenario |
| GET | `/api/v1/dashboard/live` | Current demand + weather |
| GET | `/api/v1/dashboard/historical` | Time series data |
| GET | `/api/v1/dashboard/stats/summary` | KPI stats |
| GET | `/api/v1/dashboard/heatmap` | Hour x day demand matrix |
| GET | `/api/v1/dashboard/prediction-history` | Predicted vs actual log |
| GET | `/api/v1/dashboard/accuracy-trend` | Rolling MAPE + drift detection |
| GET | `/api/v1/dashboard/model-performance` | Champion model metrics |

## Feature Engineering (93 features)

- **Lag features** (5): demand at t-1, t-6, t-24, t-168, t-720
- **Diff features** (2): rate of change vs 1h and 24h ago
- **Rolling stats** (21): mean/std/min/max over 6h, 1d, 7d, 30d windows
- **Cyclical encoding** (9): sin/cos for hour, day-of-week, month, day-of-year
- **Fourier terms** (18): seasonality decomposition at daily and weekly periods
- **Weather** (7): temperature, humidity, dew point, precipitation, cloud cover, wind, solar
- **Weather derived** (8): CDD, HDD, heat index, temp^2, temp x hour, temp x humidity, temp ramp
- **Calendar** (11): holiday flags, festival type, IPL season, days to/since holiday, AQI
- **Season** (5): one-hot encoding for Winter/Spring/Summer/Monsoon/Autumn
- **Time flags** (7): is_weekend, is_peak_hour, is_night, is_morning_ramp, quarter

## Database

SQLite (`data/edfs.db`) with tables:
- `demand_5min` - 201,967 rows (2021-2026)
- `weather_hourly` - 45,894 rows (2021-2026)
- `aqi_daily` - Air quality index
- `holidays` - 472 entries (2015-2026)
- `psp_daily` - 3,572 rows (2015-2024)
- `prediction_log` - Daily predicted vs actual tracking
- `model_metrics` - Model performance history
- `users` - JWT authentication

## Project Structure

```
E:/Projects/EDFS-v2/
├── config/settings.py          # Pydantic settings from .env
├── src/
│   ├── data/
│   │   ├── scrapers/           # SLDC, Open-Meteo, AQI, holidays
│   │   ├── db/models.py        # SQLAlchemy ORM (8 tables)
│   │   ├── loaders.py          # DB -> DataFrame at any resolution
│   │   ├── validators.py       # Data quality checks
│   │   └── scheduler.py        # APScheduler (7 automated jobs)
│   ├── features/               # 93 features across 5 modules
│   ├── models/                 # LightGBM, XGBoost, Ensemble
│   ├── evaluation/             # Walk-forward CV, metrics
│   ├── forecasting/
│   │   ├── future.py           # Recursive prediction engine
│   │   └── tracker.py          # Prediction vs actual logging
│   └── api/                    # FastAPI with 15+ endpoints
├── frontend/                   # Next.js 14 + Tailwind + Framer Motion
├── models/                     # Trained model files
├── scripts/                    # Migration, training, backfill
└── docker/                     # Dockerfiles (optional)
```

## License

MIT

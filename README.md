<p align="center">
  <img src="https://img.shields.io/badge/Gridalytics-AI%20Grid%20Intelligence-blue?style=for-the-badge&logo=lightning&logoColor=white" alt="Gridalytics" />
</p>

<h1 align="center">Gridalytics</h1>
<p align="center">
  <strong>AI-Powered Grid Intelligence for Delhi Power Grid</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/PyTorch-2.6-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

<p align="center">
  Predicts electricity demand at <strong>5-minute</strong>, <strong>hourly</strong>, and <strong>daily</strong> resolutions using 7 ML models trained on 5+ years of SCADA data from the Delhi SLDC.
</p>

<p align="center">
  <a href="https://rupeshbharambe24.github.io/Gridalytics/"><img src="https://img.shields.io/badge/▶%20Live-Pipeline%20Walkthrough-bd6a05?style=for-the-badge" alt="Live pipeline walkthrough" /></a>
</p>

<p align="center">
  <strong>Interactive walkthrough of the whole pipeline</strong> — sources → scrapers → storage → features →
  champion/challenger training → forecasts — with a clickable 36-state map:
  <a href="https://rupeshbharambe24.github.io/Gridalytics/">rupeshbharambe24.github.io/Gridalytics</a><br>
  <sub>(served from <code>docs/index.html</code> via GitHub Pages)</sub>
</p>

---

## Performance

Walk-forward cross-validation, **leak-free** (diff/rolling target features end at `t-1`).
Headline MAPE is reported next to a **persistence** (repeat-last-value) baseline — the number that
actually matters for short-term load forecasting.

| Resolution | Champion | MAPE (leak-free) | Persistence MAPE | RMSE | R² |
|:--|:--|--:|--:|--:|--:|
| **Daily (peak)** | LightGBM | **3.92%** | 5.05% | 271.6 MW | 0.69 |
| **Hourly** | LightGBM | **1.31%** | 3.43% | 95.8 MW | 0.98 |
| **5-minute** | LightGBM | _re-running_ | 0.68% | — | — |

> **Correction (Oct 2026).** Earlier headline figures (0.18% / 0.50% / 2.65%) were **inflated by a
> target leak**: the `diff` and rolling features were computed from the value being predicted, so the
> model effectively saw the answer during training. After fixing it (features now end at `t-1`) and
> repairing date-integrity issues in the data, the champions **still beat persistence at every
> resolution**, by a smaller, honest margin. The 5-minute model is being re-measured.
>
> Classical challengers (SARIMAX / ARIMA / NeuralProphet / BiLSTM) are weaker and kept for diversity —
> see [docs/classical_models.md](docs/classical_models.md).

---

## What's New

- **Event-aware forecasting layer** — learns each festival/holiday's measured demand impact (Diwali ≈ −10%, Id-ul-Fitr ≈ +3%) from 10 years of daily history and exposes it as a leakage-free `expected_event_effect_pct` feature. Validated with walk-forward CV **and** a recursive day-ahead backtest; shipped behind a flag (`FeaturePipeline(..., include_event_effect=...)`). → [docs/event_aware_forecasting.md](docs/event_aware_forecasting.md)
- **Classical models use the full feature set** — SARIMAX and a new **ARIMA** variant now take all ~93 engineered features as exogenous regressors (scaled, de-collinearized; target-history columns excluded to avoid linear leakage). Wired as optional challengers: `train(resolution, extra_models=["sarimax", "arima", "neuralprophet"])`. → [docs/classical_models.md](docs/classical_models.md)
- **NeuralProphet completed & wired** — configurable regressors + robust predict; auto-joins the per-resolution ensemble and model registry when trained.
- **Faster frontend** — a shared stale-while-revalidate cache makes tab switches instant (data no longer re-fetches from scratch on every navigation) and chart rendering is lighter. → [docs/frontend_performance.md](docs/frontend_performance.md)

---

## Features

<table>
<tr>
<td width="50%">

### Data Pipeline
- Real-time scraping from Delhi SLDC (5-min SCADA data)
- Weather data from Open-Meteo (free, no API key)
- Air Quality Index from Open-Meteo AQI
- Indian holidays + festivals (Diwali, Holi, IPL, etc.)
- Automated scheduler (7 jobs, runs 24/7)

### ML Models
- **7 models** across 3 resolutions (LightGBM, XGBoost, BiLSTM, NeuralProphet, SARIMAX, ARIMA, Ensemble)
- Champion/challenger retraining — lowest walk-forward CV MAPE wins (classical challengers optional)
- 93 engineered features + optional learned event-effect feature
- Walk-forward cross-validation (no data leakage)
- Future forecasting (recursive prediction, up to 90 days)
- Prediction tracking (daily predicted vs actual)

</td>
<td width="50%">

### API (25 Endpoints)
- Forecast: single day, date range, peak, model selection
- Sub-regional DISCOM forecasting (BRPL, BYPL, NDPL, NDMC, MES)
- What-if scenarios (7 parameters: temp, humidity, AQI, cloud, holiday, festival)
- Dashboard: live demand with 1h forecast, stats, heatmaps, accuracy trend
- Admin: model management, retrain, scraper status, rate limiting
- JWT authentication with bcrypt, admin role gating

### Frontend (10 Pages)
- Real-time dashboard with KPI cards + DISCOM breakdown
- Interactive forecast with model selector + confidence bands
- Model comparison (all 7 models with metrics)
- What-if scenario explorer (7 parameters)
- Prediction accuracy tracker with drift detection
- Seasonal analytics + anomaly detection
- Admin panel (auth-gated, retrain, pipeline status)
- Login/Register with JWT
- Comprehensive "How It Works" guide (10 sections)

</td>
</tr>
</table>

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
       Vercel (free)         → Next.js Frontend (10 pages)
         ↓ API calls
       Render (free)         → FastAPI Backend (27 endpoints)
         ↓ reads/writes
       Supabase (free)       → PostgreSQL Database (252K+ rows)
         ↑ scheduled writes
       GitHub Actions (free) → Data Collection every 6h
```

---

## Quick Start

### 1. Backend

```bash
# Install dependencies
pip install pandas numpy sqlalchemy pydantic pydantic-settings python-dotenv \
  requests beautifulsoup4 httpx lightgbm xgboost scikit-learn \
  fastapi uvicorn python-jose passlib holidays apscheduler

# Setup
cp .env.example .env
python -c "from src.data.db.session import create_tables; create_tables()"

# Import historical data
python scripts/migrate_legacy_data.py
python scripts/backfill_demand.py

# Train models
python scripts/initial_train.py hourly
python scripts/initial_train.py daily
python scripts/train_5min_model.py

# Start API
uvicorn src.api.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend && npm install && npm run dev
```

### 3. Continuous Data Collection

```bash
python -m src.data.scheduler       # Run continuously
python -m src.data.scheduler --once # Run once
```

| Service | URL |
|---------|-----|
| Live Dashboard | https://gridalytics.vercel.app |
| API Docs | https://gridalytics-api.onrender.com/docs |
| Local Dashboard | http://localhost:3000 |
| Local API | http://localhost:8000/docs |

---

## Data Sources (All Free)

| Source | Data | Interval | Coverage |
|--------|------|----------|----------|
| [Delhi SLDC](https://www.delhisldc.org/) | SCADA demand (Delhi + 5 DISCOMs) | 5 min | 2021 - present |
| [Open-Meteo](https://open-meteo.com/) | Weather (temp, humidity, wind, solar) | 1 hour | 2021 - present |
| [Open-Meteo AQI](https://open-meteo.com/) | Air Quality (PM2.5, PM10) | Daily | 2025 - present |
| Open-Meteo Forecast | 16-day weather forecast | 1 hour | Rolling |
| `holidays` library | Indian holidays + curated festivals | Daily | 2015 - 2026 |

---

## API Reference

<details>
<summary><strong>Forecast (5 endpoints)</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/forecast/{resolution}?date=` | Forecast (past or future) |
| `GET` | `/api/v1/forecast/{resolution}/range?start=&end=` | Multi-day forecast (up to 90 days) |
| `GET` | `/api/v1/forecast/{resolution}/peak?date=` | Peak demand + time |
| `POST` | `/api/v1/forecast/what-if` | Custom scenario |
| `GET` | `/api/v1/forecast/models/available` | List loaded models |

</details>

<details>
<summary><strong>Dashboard (9 endpoints)</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/dashboard/live` | Current demand + weather |
| `GET` | `/api/v1/dashboard/historical?days=&resolution=` | Time series data |
| `GET` | `/api/v1/dashboard/stats/summary` | KPI stats |
| `GET` | `/api/v1/dashboard/stats/seasonal` | Seasonal breakdown |
| `GET` | `/api/v1/dashboard/heatmap?days=` | Hour x day matrix |
| `GET` | `/api/v1/dashboard/model-performance` | Champion metrics |
| `GET` | `/api/v1/dashboard/prediction-history?days=` | Predicted vs actual log |
| `GET` | `/api/v1/dashboard/accuracy-trend?days=` | Rolling MAPE + drift |
| `GET` | `/api/v1/dashboard/anomalies?days=` | High-error days |

</details>

<details>
<summary><strong>Auth + Admin (8 endpoints)</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/register` | Register user |
| `POST` | `/api/v1/auth/login` | Login (JWT) |
| `GET` | `/api/v1/auth/me` | Current user |
| `GET` | `/api/v1/admin/models` | Trained models list |
| `POST` | `/api/v1/admin/retrain` | Trigger retraining |
| `GET` | `/api/v1/admin/retrain/status` | Retrain progress |
| `GET` | `/api/v1/admin/scraper-status` | Data pipeline health |
| `GET` | `/api/v1/admin/scheduler-jobs` | Scheduled jobs |

</details>

---

## API Usage Examples

### Get hourly forecast for a date
```bash
curl -s "http://localhost:8000/api/v1/forecast/hourly?date=2026-04-01" | python -m json.tool
```

### Get peak demand prediction
```bash
curl -s "http://localhost:8000/api/v1/forecast/hourly/peak?date=2026-03-28"
# {"date":"2026-03-28","peak_mw":4175.3,"peak_time":"2026-03-28 19:00:00","avg_mw":3649.8,"min_mw":2921.0}
```

### Get DISCOM sub-regional breakdown
```bash
curl -s "http://localhost:8000/api/v1/forecast/hourly/subregion?date=2026-03-28"
```

### Run a what-if scenario (45°C heatwave)
```bash
curl -s -X POST "http://localhost:8000/api/v1/forecast/what-if" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-04-01","resolution":"hourly","overrides":{"temperature":45.0,"humidity":30,"aqi":200}}'
```

### Python client
```python
import requests
BASE = "http://localhost:8000/api/v1"

# Live dashboard
live = requests.get(f"{BASE}/dashboard/live").json()
print(f"Current: {live['current_demand_mw']} MW")
print(f"1h forecast: {live['forecast_1h_mw']} MW")

# Hourly forecast with specific model
forecast = requests.get(f"{BASE}/forecast/hourly",
    params={"date": "2026-04-01", "model": "xgboost"}).json()
print(f"Peak: {max(forecast['predicted_mw']):.0f} MW ({forecast['model_name']})")
```

---

## Feature Engineering (93 Features)

| Category | Count | Examples |
|----------|------:|---------|
| Lag Features | 5 | demand at t-1, t-24, t-168 |
| Diff Features | 2 | rate of change vs 1h/24h ago |
| Rolling Stats | 21 | mean/std/min/max over 6h, 1d, 7d, 30d |
| Raw Weather | 7 | temperature, humidity, dew point, solar |
| Weather Derived | 8 | CDD, HDD, heat index, temp x hour |
| Cyclical Encoding | 9 | sin/cos for hour, day-of-week, month |
| Fourier Terms | 18 | daily and weekly seasonality harmonics |
| Calendar | 11 | holidays, festivals, IPL, AQI |
| Season One-Hot | 5 | Winter, Spring, Summer, Monsoon, Autumn |
| Time Flags | 7 | is_peak_hour, is_night, is_weekend |

---

## Documentation

| Doc | What |
|-----|------|
| [docs/event_aware_forecasting.md](docs/event_aware_forecasting.md) | Event-effect layer: design, methodology, measured CV + backtest results |
| [docs/classical_models.md](docs/classical_models.md) | SARIMAX/ARIMA with the full exogenous feature set + NeuralProphet eval |
| [docs/frontend_performance.md](docs/frontend_performance.md) | Frontend slow-load / tab-switch diagnosis and fixes |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, Tailwind CSS, Framer Motion, Recharts, shadcn/ui |
| Backend | FastAPI, SQLAlchemy, Pydantic, JWT (python-jose + bcrypt) |
| ML | LightGBM, XGBoost, PyTorch (BiLSTM), NeuralProphet, SARIMAX, ARIMA |
| Data | Supabase (PostgreSQL), APScheduler, BeautifulSoup, httpx |
| MLOps | MLflow, Optuna, walk-forward CV, drift detection |
| Deploy | Vercel + Render + Supabase + GitHub Actions ($0/month) |

---

## Project Structure

```
Gridalytics/
├── config/settings.py          # Pydantic settings from .env
├── src/
│   ├── data/
│   │   ├── scrapers/           # SLDC, Open-Meteo, AQI, holidays
│   │   ├── db/models.py        # SQLAlchemy ORM (8 tables)
│   │   ├── loaders.py          # DB -> DataFrame at any resolution
│   │   └── scheduler.py        # 7 automated jobs
│   ├── features/               # 93 features across 5 modules
│   ├── models/                 # 7 model implementations
│   ├── evaluation/             # Walk-forward CV, metrics
│   ├── forecasting/
│   │   ├── future.py           # Recursive prediction engine
│   │   └── tracker.py          # Prediction vs actual logging
│   ├── training/               # MLflow, Optuna, orchestrator
│   └── api/                    # FastAPI (27 endpoints)
├── frontend/                   # Next.js 14 (9 pages)
├── models/                     # Trained model files
├── notebooks/                  # 4 analysis notebooks
├── tests/                      # 50 tests (all passing)
├── scripts/                    # Training, migration, backfill
└── docker/                     # Dockerfiles (optional)
```

---

## Tests

```bash
python -m pytest tests/ -v    # 50/50 passing
```

| Suite | Tests | Coverage |
|-------|------:|----------|
| test_scrapers.py | 6 | SLDC validation, Open-Meteo, holidays |
| test_features.py | 12 | Lags, cyclical encoding, CDD/HDD, rolling stats |
| test_models.py | 8 | LightGBM, XGBoost, Ensemble fit/predict/save |
| test_api.py | 24 | All API endpoints + admin auth |

---

## Author

**Rupesh Bharambe**

---

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 Rupesh Bharambe. All rights reserved.

<p align="center">
  <img src="https://img.shields.io/badge/Gridalytics-AI%20Grid%20Intelligence%20for%20India-blue?style=for-the-badge&logo=lightning&logoColor=white" alt="Gridalytics" />
</p>

<h1 align="center">Gridalytics</h1>
<p align="center">
  <strong>AI-Powered Demand Forecasting for India's Power Grid — state by state</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/PyTorch-2.6-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

<p align="center">
  Forecasts electricity demand for <strong>Indian states</strong> at <strong>5-minute</strong>, <strong>hourly</strong>,
  and <strong>daily</strong> resolutions — one pipeline that scales from a single state to the whole country.
  It began with the Delhi grid; it now maps all <strong>36 states &amp; UTs</strong> and adds them one by one.
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

## State coverage

Every Indian state/UT is mapped in one registry ([`src/data/scrapers/states.py`](src/data/scrapers/states.py)):
its regional grid, DISCOMs, data source, and the scraper that handles it. Each state gets a model the
moment it has data — `python scripts/train_state.py <state>`. Browse it live on the **`/states`** dashboard
page or the [pipeline walkthrough](https://rupeshbharambe24.github.io/Gridalytics/).

**Trained today — 2 states:**

| State | Resolutions | Champion | Leak-free MAPE | vs Persistence | DISCOM-level |
|:--|:--|:--|--:|--:|:--:|
| **Delhi** (reference) | daily · hourly · 5-min | LightGBM / XGBoost | 3.92% / 1.31% / 0.45% | 5.05 / 3.43 / 0.68% | ✅ |
| **Karnataka** | hourly | XGBoost (served via LightGBM) | 2.46% | 4.70% | ✅ (live) |

**Rollout across 36 states/UTs:**

| Tier | Count | States |
|:--|--:|:--|
| **Direct scraper** | 6 | Delhi, Bihar, Punjab, Uttar Pradesh, Karnataka, Chhattisgarh |
| **National fallback** (Grid-India PSP) | 29 | all remaining states/UTs — daily per-state demand |
| **Deferred** (access-gated source) | 1 | Gujarat |

DISCOM-level breakdown is available for **Delhi, Bihar, and Karnataka**; the rest are single-utility or
state-total. Full per-state inventory (sources, methods, how to scrape each): **[docs/state_grid_data_sources.md](docs/state_grid_data_sources.md)**.

---

## Performance — Delhi (reference state)

Walk-forward cross-validation, **leak-free** (diff/rolling target features end at `t-1`).
Headline MAPE is reported next to a **persistence** (repeat-last-value) baseline — the number that
actually matters for short-term load forecasting.

| Resolution | Champion | MAPE (leak-free) | Persistence MAPE | RMSE | R² |
|:--|:--|--:|--:|--:|--:|
| **Daily (peak)** | LightGBM | **3.92%** | 5.05% | 271.6 MW | 0.69 |
| **Hourly** | LightGBM | **1.31%** | 3.43% | 95.8 MW | 0.98 |
| **5-minute** | XGBoost | **0.45%** | 0.68% | 28.9 MW | 0.997 |

Karnataka (hourly) — the first state beyond Delhi — lands at **2.46%** CV MAPE (R² 0.97) vs **4.70%**
persistence, on the same leak-free pipeline.

> **Correction (Oct 2026).** Earlier Delhi headline figures (0.18% / 0.50% / 2.65%) were **inflated by a
> target leak**: the `diff` and rolling features were computed from the value being predicted, so the
> model effectively saw the answer during training. After fixing it (features now end at `t-1`) and
> repairing date-integrity issues in the data, the champions **still beat persistence at every
> resolution**, by a smaller, honest margin.
>
> Classical challengers (SARIMAX / ARIMA / NeuralProphet / BiLSTM) are weaker and kept for diversity —
> see [docs/classical_models.md](docs/classical_models.md).

---

## How it scales to any state

```
Per-state SLDC  ┐
Grid-India PSP  ┼─► scrapers (states.py registry) ─► state_demand / state_demand_discom ─┐
Open-Meteo wx   ┘                                                                        │
                                                                                         ▼
                      leak-free feature pipeline  ─►  champion/challenger CV  ─►  per-state model
                                                                                         │
                                                                                         ▼
                                           FastAPI /api/v1/states  ─►  /states dashboard
```

- **One registry, 36 states** — `states.py` classifies each state as *direct* / *fallback* / *deferred*.
- **Scrapers** — dedicated collectors for the 6 direct states (`src/data/scrapers/state_sldc.py`), a shared
  Grid-India daily-PSP collector for the rest (`state_fallback.py`), plus Open-Meteo weather/AQI (any lat/long,
  so weather scales for free).
- **Long-format storage** — `state_demand` (+ `state_demand_discom`) holds any state; Delhi keeps its wide
  5-min table.
- **State-generic trainer** — `scripts/train_state.py <state>` runs the same leak-free features + champion/
  challenger CV and reports the result against a persistence baseline.
- **State-wise serving** — `/api/v1/states` exposes registry + live collection status + model metrics; the
  `/states` dashboard page renders the coverage map, per-state status, demand and analysis.

---

## What's New

- **All-India rollout** — a state registry, per-state + fallback scrapers, a state-generic trainer, a states
  API, and a `/states` dashboard. Delhi and Karnataka are modelled; the rest light up as data accumulates.
- **Leak-free features** — `diff`/rolling target features now end at `t-1` (no train/serve skew); headline
  numbers re-measured honestly against persistence.
- **Event-aware forecasting layer** — learns each festival/holiday's measured demand impact from ~10 years of
  daily history, exposed as a leakage-free feature. → [docs/event_aware_forecasting.md](docs/event_aware_forecasting.md)
- **Classical + neural challengers** — SARIMAX/ARIMA on the full exogenous feature set, NeuralProphet wired as
  optional challengers. → [docs/classical_models.md](docs/classical_models.md)
- **Faster frontend** — shared stale-while-revalidate cache + downsampled series keep tab-switches and the
  state views instant. → [docs/frontend_performance.md](docs/frontend_performance.md)

---

## Features

<table>
<tr>
<td width="50%">

### Data Pipeline
- Per-state SLDC scrapers (Delhi 5-min SCADA; Bihar/Punjab/UP JSON; Karnataka/Chhattisgarh HTML)
- Grid-India daily PSP as the all-India fallback (every state)
- Weather + AQI from Open-Meteo (free, no key, any coordinates)
- Indian holidays + festivals (Diwali, Holi, Eid, IPL, etc.)
- Automated scheduler (per-state polls + nightly backfills)

### ML Models
- **7 model families** (LightGBM, XGBoost, BiLSTM, NeuralProphet, SARIMAX, ARIMA, Ensemble)
- Champion/challenger retraining — lowest walk-forward CV MAPE wins
- ~93 engineered features, leak-free (strictly causal)
- Walk-forward cross-validation + persistence baselines
- Recursive future forecasting (up to 90 days, Delhi)
- Prediction tracking (daily predicted vs actual)

</td>
<td width="50%">

### API
- **States**: registry, collection status, per-state demand + model metrics
- Forecast: single day, date range, peak, model selection
- Sub-regional DISCOM forecasting (Delhi: BRPL, BYPL, NDPL, NDMC, MES)
- What-if scenarios (temp, humidity, AQI, holiday, …)
- Dashboard: live demand, stats, heatmaps, accuracy trend
- Admin + JWT auth (bcrypt, role gating)

### Frontend
- **State-wise view** — 36-state coverage map + per-state demand & analysis
- Real-time dashboard with KPI cards + DISCOM breakdown
- Interactive forecast with model selector + confidence bands
- Model comparison, what-if explorer, accuracy tracker with drift
- Seasonal analytics, admin panel, "How It Works" guide

</td>
</tr>
</table>

---

## Architecture

```
       Vercel (free)         → Next.js Frontend (state-wise dashboard)
         ↓ API calls
       Render (free)         → FastAPI Backend (forecast + states API)
         ↓ reads/writes
       Supabase (free)       → PostgreSQL (Delhi 5-min + per-state tables)
         ↑ scheduled writes
       GitHub Actions (free) → Per-state data collection + nightly PSP fallback
```

---

## Quick Start

### 1. Backend

```bash
pip install -r requirements.txt

cp .env.example .env
python -c "from src.data.db.session import create_tables; create_tables()"

# Delhi (reference): import history + train
python scripts/migrate_legacy_data.py
python scripts/initial_train.py hourly && python scripts/initial_train.py daily

# Any other state: collect its data, then train
python scripts/collect_states.py --states karnataka            # (+ load-curve backfill for history)
python scripts/train_state.py karnataka --resolution hourly

# Start API
uvicorn src.api.main:app --reload --port 8000
```

> Bihar & Punjab SLDC servers run old TLS — set `SLDC_INSECURE_TLS=true` in `.env` to collect them.

### 2. Frontend

```bash
cd frontend && npm install && npm run dev
```

### 3. Continuous data collection

```bash
python -m src.data.scheduler        # per-state polls + nightly backfills, 24/7
python -m src.data.scheduler --once # one pass
```

| Service | URL |
|---------|-----|
| Pipeline walkthrough | https://rupeshbharambe24.github.io/Gridalytics/ |
| Live Dashboard | https://gridalytics.vercel.app |
| API Docs | https://gridalytics-api.onrender.com/docs |
| Local API | http://localhost:8000/docs |

---

## Data Sources (all free)

| Source | Data | Interval | Coverage |
|--------|------|----------|----------|
| State SLDCs (e.g. [Delhi](https://www.delhisldc.org/), KPTCL, BSPTCL, PSTCL, UPSLDC) | SCADA / portal demand, some DISCOM-level | 5–15 min / hourly | per state, 2021–present |
| [Grid-India](https://report.grid-india.in/) daily PSP | Per-state peak demand / energy — **all states** | Daily | national fallback |
| [Open-Meteo](https://open-meteo.com/) | Weather + AQI (any lat/long) | Hourly / Daily | nationwide |
| `holidays` library + curated festivals | Indian holidays, festivals, IPL | Daily | 2015–present |

Per-state source map and scrape methods: **[docs/state_grid_data_sources.md](docs/state_grid_data_sources.md)**.

---

## API Reference

<details>
<summary><strong>States (all-India)</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/states` | Registry + collection status + model metrics for all 36 |
| `GET` | `/api/v1/states/{code}` | One state's detail |
| `GET` | `/api/v1/states/{code}/demand?days=&max_points=` | Recent demand series (downsampled) |

</details>

<details>
<summary><strong>Forecast</strong></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/forecast/{resolution}?date=` | Forecast (past or future) |
| `GET` | `/api/v1/forecast/{resolution}/range?start=&end=` | Multi-day (up to 90 days) |
| `GET` | `/api/v1/forecast/{resolution}/peak?date=` | Peak demand + time |
| `POST` | `/api/v1/forecast/what-if` | Custom scenario |
| `GET` | `/api/v1/forecast/{resolution}/subregion?date=` | DISCOM breakdown (Delhi) |

</details>

<details>
<summary><strong>Dashboard · Auth · Admin</strong></summary>

Live demand, historical series, seasonal stats, heatmap, model performance, prediction history,
accuracy trend + drift; JWT auth (register / login / me); admin model management, retrain, scraper
and scheduler status.

</details>

---

## Feature Engineering (~93 features, leak-free)

| Category | Count | Examples |
|----------|------:|---------|
| Lag Features | 5 | demand at t-1, t-24, t-168 |
| Diff Features | 2 | causal rate-of-change ending at t-1 |
| Rolling Stats | 21 | mean/std/min/max over 6h–30d, shifted to t-1 |
| Raw + Derived Weather | 15 | temp, humidity, solar, CDD/HDD, heat index |
| Cyclical + Fourier | 27 | sin/cos + seasonal harmonics |
| Calendar | 11 | holidays, festivals, IPL, AQI |
| Season + Time flags | 12 | season one-hot, peak/night/weekend |

---

## Documentation

| Doc | What |
|-----|------|
| [docs/state_grid_data_sources.md](docs/state_grid_data_sources.md) | **All-India source map** — every state's SLDC, method, tier, how to scrape |
| [docs/event_aware_forecasting.md](docs/event_aware_forecasting.md) | Event-effect layer: design, methodology, measured results |
| [docs/classical_models.md](docs/classical_models.md) | SARIMAX/ARIMA full-exog + NeuralProphet eval |
| [docs/frontend_performance.md](docs/frontend_performance.md) | Frontend load / tab-switch diagnosis + fixes |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, Tailwind CSS, Framer Motion, Recharts, shadcn/ui |
| Backend | FastAPI, SQLAlchemy, Pydantic, JWT (python-jose + bcrypt) |
| ML | LightGBM, XGBoost, PyTorch (BiLSTM), NeuralProphet, SARIMAX, ARIMA |
| Data | Supabase (PostgreSQL), APScheduler, BeautifulSoup, httpx, pdfplumber, xlrd |
| MLOps | MLflow, Optuna, walk-forward CV, Alembic migrations, drift detection |
| Deploy | Vercel + Render + Supabase + GitHub Actions ($0/month) |

---

## Project Structure

```
Gridalytics/
├── src/
│   ├── data/
│   │   ├── scrapers/
│   │   │   ├── states.py         # registry of all 36 states/UTs
│   │   │   ├── state_sldc.py     # per-state collectors (Delhi + 5 direct states)
│   │   │   ├── state_fallback.py # Grid-India PSP — all-India fallback
│   │   │   ├── sldc.py · open_meteo.py · aqi.py · grid_india.py · holidays.py
│   │   ├── db/models.py          # ORM: demand_5min + state_demand(+discom) + state_psp_daily + …
│   │   └── scheduler.py          # per-state polls + nightly backfills
│   ├── features/                 # ~93 leak-free features
│   ├── models/                   # 7 model families
│   ├── evaluation/ · forecasting/ · training/
│   └── api/routers/              # forecast, dashboard, states, admin, auth
├── frontend/                     # Next.js 14 (incl. /states state-wise page)
├── scripts/
│   ├── collect_states.py         # multi-state collection CLI
│   ├── train_state.py            # state-generic trainer
│   └── initial_train.py · train_5min_model.py
├── models/{daily,hourly,5min}/   # Delhi champions
├── models/states/<state>/        # per-state champions (e.g. karnataka/hourly)
├── docs/                         # source map + design write-ups + Pages walkthrough
└── tests/
```

---

## Tests

```bash
python -m pytest tests/ -v
```

CI (`.github/workflows/ci.yml`) runs the backend test suite on every push.

---

## Author

**Rupesh Bharambe**

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Rupesh Bharambe.

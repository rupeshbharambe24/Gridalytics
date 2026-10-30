"""Train a demand-forecasting model for a non-Delhi state.

Proves the state -> model path beyond Delhi. Loads a state's demand series from
the long-format ``state_demand`` table, merges weather for the state's load
centre, builds the SAME leak-free features as the Delhi pipeline (reusing
src/features/*), and runs the champion/challenger walk-forward CV.

Usage:
  python scripts/train_state.py karnataka --resolution hourly
  python scripts/train_state.py karnataka --resolution hourly --no-weather

Reports each model's CV MAPE against the persistence baseline and saves the
champion to models/states/<state>/<resolution>/.
"""

import sys
import argparse
import logging
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("train_state")

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import requests
from sqlalchemy import asc

from src.data.db.session import get_session
from src.data.db.models import StateDemandRecord
from src.features.temporal import (
    add_lag_features, add_diff_features, add_cyclical_encoding,
    add_fourier_terms, add_time_features,
)
from src.features.rolling import add_rolling_stats, add_rolling_weather_stats
from src.features.weather import (
    add_heat_index, add_degree_days, add_weather_interactions,
    add_weather_categories, add_solar_features,
)
from src.features.calendar import add_holiday_features
from src.evaluation.cross_validation import walk_forward_cv
from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster

TARGET = "demand_mw"

# Load-centre coordinates per state (for weather). Add states as they come online.
STATE_COORDS = {
    "karnataka": (12.9716, 77.5946),       # Bengaluru
    "bihar": (25.5941, 85.1376),           # Patna
    "punjab": (30.9010, 75.8573),          # Ludhiana
    "uttar_pradesh": (26.8467, 80.9462),   # Lucknow
    "chhattisgarh": (21.2514, 81.6296),    # Raipur
}
_WX = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
       "cloud_cover", "wind_speed_10m", "shortwave_radiation"]


def load_state_series(state: str, resolution: str) -> pd.DataFrame:
    """Load a state's demand from state_demand onto a regular time grid."""
    with get_session() as s:
        rows = (s.query(StateDemandRecord.timestamp, StateDemandRecord.demand_mw)
                .filter(StateDemandRecord.state_code == state,
                        StateDemandRecord.demand_mw.isnot(None))
                .order_by(asc(StateDemandRecord.timestamp)).all())
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", TARGET])
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    freq = {"hourly": "1h", "daily": "1D", "5min": "5min"}[resolution]
    agg = "max" if resolution == "daily" else "mean"   # daily target = peak
    df = df.resample(freq).agg({TARGET: agg})
    # The history has scattered missing hours/days; resampling leaves NaN gaps.
    # Fill them so the series is contiguous (lags/rolling need a regular grid and
    # the CV metrics reject NaN targets). Time-interpolate interior gaps, then
    # ffill/bfill the series ends.
    df[TARGET] = df[TARGET].interpolate(method="time").ffill().bfill()
    return df


def fetch_weather(lat: float, lon: float, start, end) -> pd.DataFrame:
    """Open-Meteo archive hourly weather for the state's load centre (IST)."""
    try:
        r = requests.get("https://archive-api.open-meteo.com/v1/archive", timeout=40, params={
            "latitude": lat, "longitude": lon,
            "start_date": str(start.date()), "end_date": str(end.date()),
            "hourly": ",".join(_WX), "timezone": "Asia/Kolkata",
        })
        j = r.json()["hourly"]
        wx = pd.DataFrame(j)
        wx["time"] = pd.to_datetime(wx["time"])
        wx = wx.set_index("time")
        # name columns to match the feature functions' expectations
        wx = wx.rename(columns={"precipitation": "precipitation_mm",
                                "cloud_cover": "cloud_cover_pct"})
        return wx
    except Exception as e:
        logger.warning(f"weather fetch failed ({e}); training without weather")
        return pd.DataFrame()


def build_features(df: pd.DataFrame, resolution: str, use_weather: bool) -> tuple[pd.DataFrame, list[str]]:
    df = add_time_features(df)
    df = add_cyclical_encoding(df)
    has_wx = use_weather and "temperature_2m" in df.columns
    if has_wx:
        df = add_heat_index(df)
        df = add_degree_days(df)
        df = add_weather_interactions(df)
        df = add_weather_categories(df)
        df = add_solar_features(df)
    with get_session() as s:
        df = add_holiday_features(df, s)
    df = add_rolling_stats(df, TARGET, resolution)      # leak-free (shift(1))
    if has_wx:
        df = add_rolling_weather_stats(df, resolution)
    df = add_lag_features(df, TARGET, resolution)
    df = add_diff_features(df, TARGET, resolution)       # leak-free (ends at t-1)
    df = add_fourier_terms(df, resolution)
    df = df.drop(columns=[c for c in df.columns if df[c].dtype == object], errors="ignore")
    df = df.dropna(subset=[c for c in df.columns if "_lag_" in c])
    feats = [c for c in df.columns if c != TARGET and
             (np.issubdtype(df[c].dtype, np.number) or df[c].dtype == bool)]
    df[feats] = df[feats].ffill().fillna(0)
    return df, feats


def persistence_mape(df: pd.DataFrame, holdout: int) -> float:
    y = df[TARGET].to_numpy()
    naive = df[TARGET].shift(1).to_numpy()
    yt, nv = y[-holdout:], naive[-holdout:]
    m = (yt > 0) & ~np.isnan(nv)
    return float(np.mean(np.abs((yt[m] - nv[m]) / yt[m])) * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--resolution", default="hourly", choices=["hourly", "daily"])
    ap.add_argument("--no-weather", action="store_true")
    args = ap.parse_args()

    print(f"\n{'#'*60}\n  Train state model: {args.state} ({args.resolution})\n{'#'*60}")
    df = load_state_series(args.state, args.resolution)
    if df.empty:
        logger.error(f"No data in state_demand for '{args.state}'. Backfill it first.")
        sys.exit(1)
    print(f"  loaded {len(df):,} rows  {df.index.min()} .. {df.index.max()}  "
          f"(mean {df[TARGET].mean():.0f} MW)")

    use_weather = not args.no_weather and args.state in STATE_COORDS
    if use_weather:
        lat, lon = STATE_COORDS[args.state]
        wx = fetch_weather(lat, lon, df.index.min(), df.index.max())
        if not wx.empty:
            df = df.join(wx.reindex(df.index, method="nearest"))
            for c in _WX:
                col = {"precipitation": "precipitation_mm", "cloud_cover": "cloud_cover_pct"}.get(c, c)
                if col in df.columns:
                    df[col] = df[col].ffill().bfill()
            print(f"  merged weather for {lat},{lon} ({wx.shape[1]} vars)")

    df, feats = build_features(df, args.resolution, use_weather)
    print(f"  features: {len(feats)}  | usable rows after lag warmup: {len(df):,}")

    results = {}
    for name, cls in (("LightGBM", LightGBMForecaster), ("XGBoost", XGBoostForecaster)):
        print(f"\n[CV] {name} ...")
        res = walk_forward_cv(cls, df, TARGET, feats, args.resolution)
        if res.empty:
            print("  (not enough data for CV)"); continue
        mape = res["mape"].mean()
        results[name] = (mape, res)
        print(f"  {name}: mean CV MAPE {mape:.2f}%  RMSE {res['rmse'].mean():.1f}  R2 {res['r2'].mean():.4f}")

    if not results:
        logger.error("No CV results."); sys.exit(1)

    holdout = {"hourly": 720, "daily": 30}[args.resolution]
    pers = persistence_mape(df, holdout)
    champ = min(results, key=lambda k: results[k][0])
    champ_mape = results[champ][0]
    champ_cls = {"LightGBM": LightGBMForecaster, "XGBoost": XGBoostForecaster}[champ]

    print(f"\n{'='*60}")
    print(f"  {args.state} / {args.resolution}")
    for n, (m, _) in sorted(results.items(), key=lambda x: x[1][0]):
        print(f"    {n:<10} {m:>6.2f}% MAPE")
    print(f"    {'persistence':<10} {pers:>6.2f}% MAPE (baseline)")
    print(f"  CHAMPION: {champ} ({champ_mape:.2f}%)  —  beats persistence by "
          f"{pers - champ_mape:.2f} pts" if champ_mape < pers else "  (does not beat persistence)")
    print(f"{'='*60}")

    # train final model on all-but-holdout and save a SERVABLE artifact.
    # If the champion's save fails (e.g. the xgboost 2.1.4 / sklearn 1.9
    # _estimator_type bug), fall back to LightGBM, which persists cleanly and is
    # effectively tied here — so there is always a loadable model to serve.
    train_df, test_df = df.iloc[:-holdout], df.iloc[-holdout:]
    save_dir = Path("models") / "states" / args.state / args.resolution

    def _fit_and_save(cls, label):
        m = cls(resolution=args.resolution)
        m.fit(train_df[feats], train_df[TARGET], test_df[feats], test_df[TARGET])
        m.save(save_dir)
        return label

    served = None
    try:
        served = _fit_and_save(champ_cls, champ)
    except Exception as e:
        logger.warning(f"{champ} save failed ({type(e).__name__}: {e}); "
                       f"falling back to LightGBM as the served model")
        if champ != "LightGBM":
            try:
                served = _fit_and_save(LightGBMForecaster, "LightGBM")
            except Exception as e2:
                logger.warning(f"fallback save also failed ({e2}); no artifact persisted")
    if served:
        # record which model is actually served (champion may differ if save fell back)
        import json
        meta = save_dir / "served.json"
        try:
            meta.write_text(json.dumps({"state": args.state, "resolution": args.resolution,
                                        "served_model": served, "champion": champ,
                                        "champion_cv_mape": round(champ_mape, 3),
                                        "persistence_mape": round(pers, 3),
                                        "features": len(feats)}, indent=2))
        except Exception:
            pass
        print(f"  saved served model '{served}' -> {save_dir}")


if __name__ == "__main__":
    main()

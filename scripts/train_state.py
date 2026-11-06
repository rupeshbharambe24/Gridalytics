"""Train a demand-forecasting model for a non-Delhi state.

Proves the state -> model path beyond Delhi. Loads a state's demand series from
the long-format ``state_demand`` table, merges weather for the state's load
centre, builds the SAME leak-free features as the Delhi pipeline (reusing
src/features/*), and runs the champion/challenger walk-forward CV.

Usage:
  python scripts/train_state.py karnataka --resolution hourly
  python scripts/train_state.py karnataka --resolution hourly --no-weather
  python scripts/train_state.py rajasthan --source psp        # daily peak from state_psp_daily

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
from src.data.db.models import StateDemandRecord, StatePSPDaily
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
from src.evaluation.cross_validation import walk_forward_cv, generate_folds
from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster

TARGET = "demand_mw"

# Load-centre coordinates per state (for weather): the largest load centre, which
# for most states is the capital or main metro. A single point is a simplification
# for large states (e.g. Rajasthan, Maharashtra); see docs/state_models.md.
STATE_COORDS = {
    "delhi": (28.6139, 77.2090),
    "karnataka": (12.9716, 77.5946),       # Bengaluru
    "bihar": (25.5941, 85.1376),           # Patna
    "punjab": (30.9010, 75.8573),          # Ludhiana
    "uttar_pradesh": (26.8467, 80.9462),   # Lucknow
    "chhattisgarh": (21.2514, 81.6296),    # Raipur
    "haryana": (28.4595, 77.0266),         # Gurugram
    "rajasthan": (26.9124, 75.7873),       # Jaipur
    "himachal_pradesh": (31.1048, 77.1734),  # Shimla
    "uttarakhand": (30.3165, 78.0322),     # Dehradun
    "jammu_kashmir": (34.0837, 74.7973),   # Srinagar
    "chandigarh": (30.7333, 76.7794),
    "gujarat": (23.0225, 72.5714),         # Ahmedabad
    "maharashtra": (19.0760, 72.8777),     # Mumbai
    "madhya_pradesh": (23.2599, 77.4126),  # Bhopal
    "goa": (15.4909, 73.8278),             # Panaji
    "dnh_dd": (20.2766, 73.0169),          # Silvassa
    "telangana": (17.3850, 78.4867),       # Hyderabad
    "kerala": (9.9312, 76.2673),           # Kochi
    "tamil_nadu": (13.0827, 80.2707),      # Chennai
    "andhra_pradesh": (16.5062, 80.6480),  # Vijayawada
    "puducherry": (11.9416, 79.8083),
    "odisha": (20.2961, 85.8245),          # Bhubaneswar
    "west_bengal": (22.5726, 88.3639),     # Kolkata
    "jharkhand": (23.3441, 85.3096),       # Ranchi
    "sikkim": (27.3389, 88.6065),          # Gangtok
    "assam": (26.1445, 91.7362),           # Guwahati
    "meghalaya": (25.5788, 91.8933),       # Shillong
    "tripura": (23.8315, 91.2868),         # Agartala
    "manipur": (24.8170, 93.9368),         # Imphal
    "mizoram": (23.7271, 92.7176),         # Aizawl
    "nagaland": (25.6751, 94.1086),        # Kohima
    "arunachal_pradesh": (27.0844, 93.6053),  # Itanagar
}
# Only gaps up to this many steps are interpolated. Longer gaps stay NaN: rows whose
# target or lag features fall in a gap are dropped, so no fabricated value is ever
# trained on or scored (interpolating across weeks/years would invent data).
MAX_INTERP_STEPS = {"hourly": 3, "daily": 2}
_WX = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
       "cloud_cover", "wind_speed_10m", "shortwave_radiation"]


def load_state_series(state: str, resolution: str, source: str = "state_demand") -> pd.DataFrame:
    """Load a state's demand onto a regular time grid.

    source="state_demand": sub-daily SLDC series (hourly mean / daily peak).
    source="psp": daily peak demand met from state_psp_daily (NLDC PSP).
    """
    with get_session() as s:
        if source == "psp":
            rows = (s.query(StatePSPDaily.date, StatePSPDaily.peak_demand_met_mw)
                    .filter(StatePSPDaily.state_code == state,
                            StatePSPDaily.peak_demand_met_mw.isnot(None))
                    .order_by(asc(StatePSPDaily.date)).all())
        else:
            rows = (s.query(StateDemandRecord.timestamp, StateDemandRecord.demand_mw)
                    .filter(StateDemandRecord.state_code == state,
                            StateDemandRecord.demand_mw.isnot(None))
                    .order_by(asc(StateDemandRecord.timestamp)).all())
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", TARGET])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    freq = {"hourly": "1h", "daily": "1D", "5min": "5min"}[resolution]
    agg = "max" if resolution == "daily" else "mean"   # daily target = peak

    # Regular grid (lags/rolling need one); interpolate short gaps only.
    df = df.resample(freq).agg({TARGET: agg})
    missing = df[TARGET].isna()
    df[TARGET] = df[TARGET].interpolate(method="time", limit=MAX_INTERP_STEPS[resolution],
                                        limit_area="inside")
    df.attrs["n_interpolated"] = int((missing & df[TARGET].notna()).sum())
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
    df = df.dropna(subset=[TARGET] + [c for c in df.columns if "_lag_" in c])
    feats = [c for c in df.columns if c != TARGET and
             (np.issubdtype(df[c].dtype, np.number) or df[c].dtype == bool)]
    df[feats] = df[feats].ffill().fillna(0)
    return df, feats


def baseline_mape(df: pd.DataFrame, resolution: str, lag: int) -> float:
    """Naive forecast y[t-lag] (the lag feature, exact on the regular time grid even
    where rows were dropped), scored on exactly the CV validation rows."""
    y = df[TARGET].to_numpy()
    naive = df[f"{TARGET}_lag_{lag}"].to_numpy()
    errs = []
    for f in generate_folds(len(df), resolution):
        yt, nv = y[f.val_start:f.val_end], naive[f.val_start:f.val_end]
        m = (yt > 0) & ~np.isnan(nv)
        errs.append(np.mean(np.abs((yt[m] - nv[m]) / yt[m])) * 100)
    return float(np.mean(errs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--resolution", default="hourly", choices=["hourly", "daily"])
    ap.add_argument("--no-weather", action="store_true")
    ap.add_argument("--source", default="state_demand", choices=["state_demand", "psp"],
                    help="psp = daily peak from state_psp_daily (implies --resolution daily)")
    args = ap.parse_args()
    if args.source == "psp":
        args.resolution = "daily"

    print(f"\n{'#'*60}\n  Train state model: {args.state} ({args.resolution}, {args.source})\n{'#'*60}")
    df = load_state_series(args.state, args.resolution, args.source)
    if df.empty:
        logger.error(f"No {args.source} data for '{args.state}'. Backfill it first.")
        sys.exit(1)
    n_interp = df.attrs.get("n_interpolated", 0)
    span = (df.index.min(), df.index.max())
    print(f"  loaded {len(df):,} rows  {span[0]} .. {span[1]}  "
          f"(mean {df[TARGET].mean():.0f} MW, {n_interp} interpolated)")

    use_weather = not args.no_weather and args.state in STATE_COORDS
    if use_weather:
        lat, lon = STATE_COORDS[args.state]
        wx = fetch_weather(lat, lon, df.index.min(), df.index.max())
        if not wx.empty:
            if args.resolution == "daily":   # day's mean (rain: total), not the midnight value
                wx = wx.resample("1D").agg({c: ("sum" if c == "precipitation_mm" else "mean")
                                            for c in wx.columns})
            df = df.join(wx.reindex(df.index, method="nearest"))
            for c in _WX:
                col = {"precipitation": "precipitation_mm", "cloud_cover": "cloud_cover_pct"}.get(c, c)
                if col in df.columns:
                    df[col] = df[col].ffill().bfill()
            print(f"  merged weather for {lat},{lon} ({wx.shape[1]} vars)")

    df, feats = build_features(df, args.resolution, use_weather)
    span = (df.index.min(), df.index.max())   # rows actually used (after lag warmup / gaps)
    print(f"  features: {len(feats)}  | usable rows after lag warmup: {len(df):,}  "
          f"({span[0].date()} .. {span[1].date()})")

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
    pers = baseline_mape(df, args.resolution, 1)
    seas = baseline_mape(df, args.resolution, {"hourly": 24, "daily": 7}[args.resolution])
    champ = min(results, key=lambda k: results[k][0])
    champ_mape = results[champ][0]
    champ_cls = {"LightGBM": LightGBMForecaster, "XGBoost": XGBoostForecaster}[champ]

    print(f"\n{'='*60}")
    print(f"  {args.state} / {args.resolution}")
    for n, (m, _) in sorted(results.items(), key=lambda x: x[1][0]):
        print(f"    {n:<10} {m:>6.2f}% MAPE")
    print(f"    {'persistence':<10} {pers:>6.2f}% MAPE (baseline, same folds)")
    print(f"    {'seasonal':<10} {seas:>6.2f}% MAPE (y[t-{ {'hourly': 24, 'daily': 7}[args.resolution] }])")
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
                                        "cv_mape": {n: round(m, 3) for n, (m, _) in results.items()},
                                        "persistence_mape": round(pers, 3),
                                        "seasonal_naive_mape": round(seas, 3),
                                        "skill_vs_persistence": round(1 - champ_mape / pers, 3),
                                        "source": args.source,
                                        "data_start": str(span[0].date()),
                                        "data_end": str(span[1].date()),
                                        "rows": len(df), "interpolated_rows": n_interp,
                                        "weather": bool(use_weather),
                                        "features": len(feats)}, indent=2))
        except Exception:
            pass
        print(f"  saved served model '{served}' -> {save_dir}")


if __name__ == "__main__":
    main()

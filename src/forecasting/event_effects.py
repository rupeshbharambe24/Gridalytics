"""Event-effect estimator (Idea 1, Phase 1).

Learns *how much* each holiday/festival moves electricity demand, from the
long, complete daily series (`psp_daily`, ~10 years) rather than the sparse
5-minute data. See `docs/event_aware_forecasting.md` for the full design.

The core discipline, all implemented here:

  * **Counterfactual baseline, weather-adjusted.** For each event occurrence we
    estimate "what demand *would* have been" from nearby same-day-of-week,
    non-holiday days, fitting demand on temperature and evaluating at the
    event day's own temperature. That isolates the event effect from weather.

  * **Causality / no leakage.** `estimate_effects(as_of=<date>)` uses only
    occurrences strictly before `as_of`, so the table can be rebuilt per
    walk-forward fold without peeking at the future.

  * **Pooling + shrinkage.** Per-event samples are small (<=10). Each event's
    estimate is shrunk toward its tier mean (national / festival / sporting)
    by `n / (n + k)`, so a rarely-seen or novel event falls back to its tier.

Design notes:
  - No heavy imports at module load: DB access (SQLAlchemy) is imported lazily
    inside the loaders, so the pure estimator functions run with just
    pandas/numpy, and the file can be executed directly against a sqlite path.
  - Effects are expressed as a fractional deviation of daily demand, e.g.
    -0.136 means ~13.6% below the weather-adjusted normal day.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --- tunables -------------------------------------------------------------
BASELINE_WINDOW_DAYS = 21     # +/- window for same-DOW baseline pool
MIN_BASELINE_DAYS = 3         # need at least this many comparable days
SHRINK_K = 4.0                # shrinkage strength toward tier mean
MIN_EVENT_OCCURRENCES = 1     # keep events seen at least this many times

# Major festivals that behave like full public holidays (demand drops).
# Everything else in category 'festival' is treated as a minor festival.
_MAJOR_FESTIVALS = {
    "diwali", "holi", "dussehra", "eid ul-fitr", "id-ul-fitr", "eid ul-adha",
    "bakrid", "guru nanak jayanti", "janmashtami", "christmas", "good friday",
    "raksha bandhan", "maha shivaratri", "makar sankranti",
}


def tier_of(name: str, type_: str | None, category: str | None) -> str:
    """Map an event to a tier used for pooling/shrinkage."""
    cat = (category or "").lower()
    nm = (name or "").lower()
    if cat == "sporting":
        return "sporting"
    # Name takes priority: the `holidays` lib tags big festivals as
    # 'government', so classify by name before falling back to category.
    # whole-word match: "holi" must not catch "holika dahan"
    if any(re.search(rf"\b{re.escape(f)}\b", nm) for f in _MAJOR_FESTIVALS):
        return "major_festival"
    if cat == "government" or (type_ or "").lower() == "national":
        return "national"
    if cat == "festival":
        return "minor_festival"
    return "other"


# -------------------------------------------------------------------------
# Pure estimator core (pandas/numpy only)
# -------------------------------------------------------------------------

def _weather_adjusted_baseline(
    pool: pd.DataFrame, event_temp: float | None
) -> float | None:
    """Expected demand for a 'normal' day, given the event day's temperature.

    `pool` is nearby same-DOW non-holiday days with columns ['mw', 'temp'].
    Fits mw ~ temp (if temp varies and we have the event temp) and evaluates
    at `event_temp`; otherwise falls back to the pool mean.
    """
    if pool.empty:
        return None
    have_temp = (
        event_temp is not None
        and "temp" in pool.columns
        and pool["temp"].notna().sum() >= MIN_BASELINE_DAYS
        and pool["temp"].nunique() >= 2
    )
    if have_temp:
        p = pool.dropna(subset=["temp", "mw"])
        try:
            slope, intercept = np.polyfit(p["temp"].to_numpy(), p["mw"].to_numpy(), 1)
            return float(slope * event_temp + intercept)
        except Exception:
            pass
    return float(pool["mw"].mean())


def raw_effects(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    window_days: int = BASELINE_WINDOW_DAYS,
    min_baseline: int = MIN_BASELINE_DAYS,
) -> pd.DataFrame:
    """Per-occurrence event effect vs a weather-adjusted same-DOW baseline.

    Args:
        daily: DatetimeIndex, columns ['mw', 'dow', 'temp'(optional)].
        events: columns ['date', 'name', 'type', 'category'].

    Returns one row per usable event occurrence with the fractional effect.
    """
    hol_dates = set(pd.to_datetime(events["date"]).dt.normalize())
    daily = daily.sort_index()
    out = []

    for _, e in events.iterrows():
        d = pd.Timestamp(e["date"]).normalize()
        if d not in daily.index:
            continue
        row = daily.loc[d]
        dow = int(row["dow"])
        event_temp = float(row["temp"]) if "temp" in daily.columns and pd.notna(row.get("temp")) else None

        lo, hi = d - pd.Timedelta(days=window_days), d + pd.Timedelta(days=window_days)
        pool = daily[(daily.index >= lo) & (daily.index <= hi)]
        pool = pool[(pool["dow"] == dow) & (~pool.index.isin(hol_dates))]
        if len(pool) < min_baseline:
            continue

        base = _weather_adjusted_baseline(pool, event_temp)
        if not base or base <= 0:
            continue

        effect = (float(row["mw"]) - base) / base
        out.append({
            "date": d,
            "name": e["name"],
            "tier": tier_of(e["name"], e.get("type"), e.get("category")),
            "effect": effect,
            "event_mw": float(row["mw"]),
            "baseline_mw": round(base, 1),
            "baseline_n": len(pool),
        })

    return pd.DataFrame(out)


def estimate_effects(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    shrink_k: float = SHRINK_K,
    min_occ: int = MIN_EVENT_OCCURRENCES,
) -> pd.DataFrame:
    """Build the learned effect table (one row per event).

    Causal: if `as_of` is given, only occurrences strictly before it are used.
    Each event's mean effect is shrunk toward its tier mean by n/(n+k).
    """
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    if as_of is not None:
        ev = ev[ev["date"] < pd.Timestamp(as_of).normalize()]

    re = raw_effects(daily, ev)
    if re.empty:
        return pd.DataFrame(columns=[
            "name", "tier", "n", "mean_effect", "std_effect",
            "tier_mean", "shrunk_effect",
        ])

    tier_mean = re.groupby("tier")["effect"].mean()

    agg = (
        re.groupby(["name", "tier"])["effect"]
        .agg(n="size", mean_effect="mean", std_effect="std")
        .reset_index()
    )
    agg = agg[agg["n"] >= min_occ]
    agg["tier_mean"] = agg["tier"].map(tier_mean)
    w = agg["n"] / (agg["n"] + shrink_k)
    agg["shrunk_effect"] = agg["tier_mean"] + w * (agg["mean_effect"] - agg["tier_mean"])
    agg["std_effect"] = agg["std_effect"].fillna(0.0)

    return agg.sort_values("shrunk_effect").reset_index(drop=True)


def causal_effect_feature(
    daily: pd.DataFrame,
    events: pd.DataFrame,
    shrink_k: float = SHRINK_K,
) -> pd.Series:
    """Date -> expected event effect, estimated *causally* (expanding window).

    This is the training-time feature. For each event occurrence at date `d`,
    the value is the shrunk mean of that event's occurrences **strictly before
    `d`** (shrunk toward the tier mean of all occurrences before `d`). The first
    time an event is ever seen it falls back to its tier's prior mean, and if
    the tier too is empty, 0. So no row ever sees its own or any future year's
    outcome — the feature is leakage-free inside walk-forward CV.

    Crucially, a value is assigned to **every** event occurrence in `events`,
    including recent/future dates that are not themselves in `daily` (the effect
    source `psp_daily` ends 2024-11, but demand used for training runs to the
    present). Such a date still gets the estimate learned from its prior years —
    which is exactly what we want the model to see on, e.g., Diwali 2025.

    Returns a Series indexed by normalized event-day Timestamp. Non-event days
    are absent; the caller fills them with 0.
    """
    ev = events.copy()
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    ev["tier"] = [
        tier_of(r["name"], r.get("type"), r.get("category")) for _, r in ev.iterrows()
    ]

    # Measured occurrences (those with demand in `daily`) form the *history*.
    re = raw_effects(daily, ev)
    name_hist: dict[str, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    tier_hist: dict[str, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    for _, r in re.iterrows():
        name_hist[str(r["name"]).lower()].append((r["date"], float(r["effect"])))
        tier_hist[r["tier"]].append((r["date"], float(r["effect"])))

    out: dict[pd.Timestamp, float] = {}
    # Assign to every occurrence (measured or not) from strictly-prior history.
    for d, grp in ev.groupby("date"):
        best = 0.0
        for _, r in grp.iterrows():
            nm, tier = str(r["name"]).lower(), r["tier"]
            prior_name = [e for (dt, e) in name_hist.get(nm, []) if dt < d]
            prior_tier = [e for (dt, e) in tier_hist.get(tier, []) if dt < d]
            tier_mean = float(np.mean(prior_tier)) if prior_tier else 0.0
            if prior_name:
                n = len(prior_name)
                name_mean = float(np.mean(prior_name))
                w = n / (n + shrink_k)
                val = tier_mean + w * (name_mean - tier_mean)
            else:
                val = tier_mean  # first-ever sighting → tier fallback (0 if new tier)
            if abs(val) > abs(best):
                best = val
        out[pd.Timestamp(d)] = best

    return pd.Series(out, name="expected_event_effect_pct").sort_index()


def load_feature_map(session=None, db_path: str | None = None) -> pd.Series:
    """Convenience: load data and return the causal date->effect feature series."""
    daily = load_daily(session, db_path)
    events = load_events(session, db_path)
    return causal_effect_feature(daily, events)


@dataclass
class EventEffectTable:
    """Queryable learned effects: event -> fractional demand deviation."""

    table: pd.DataFrame
    _by_name: dict = field(default_factory=dict)
    _by_tier: dict = field(default_factory=dict)

    def __post_init__(self):
        for _, r in self.table.iterrows():
            self._by_name[str(r["name"]).lower()] = float(r["shrunk_effect"])
        if not self.table.empty:
            self._by_tier = (
                self.table.groupby("tier")["shrunk_effect"].mean().to_dict()
            )

    def get_effect(self, name: str, tier: str | None = None) -> float:
        """Return the fractional effect for an event; fall back to tier, then 0."""
        key = (name or "").lower()
        if key in self._by_name:
            return self._by_name[key]
        if tier and tier in self._by_tier:
            return self._by_tier[tier]
        # try tier inferred from the name
        t = tier_of(name, None, "festival" if "festival" not in key else None)
        return self._by_tier.get(t, 0.0)


# -------------------------------------------------------------------------
# DB loaders (lazy — only imported/used when actually loading)
# -------------------------------------------------------------------------

def _read_sql(query: str, session=None, db_path: str | None = None) -> pd.DataFrame:
    if db_path is not None:
        import sqlite3
        con = sqlite3.connect(db_path)
        try:
            return pd.read_sql_query(query, con)
        finally:
            con.close()
    if session is not None:
        return pd.read_sql_query(query, session.bind)
    from src.data.db.session import get_session
    with get_session() as s:
        return pd.read_sql_query(query, s.bind)


def load_daily(session=None, db_path: str | None = None) -> pd.DataFrame:
    """Load daily demand (psp_daily) + daily mean temperature (weather_hourly)."""
    dem = _read_sql(
        "SELECT date, delhi_demand_met_mw AS mw FROM psp_daily "
        "WHERE delhi_demand_met_mw IS NOT NULL",
        session, db_path,
    )
    dem["date"] = pd.to_datetime(dem["date"]).dt.normalize()
    dem = dem.dropna(subset=["mw"]).set_index("date").sort_index()
    dem["dow"] = dem.index.dayofweek

    try:
        w = _read_sql(
            "SELECT timestamp, temperature_2m FROM weather_hourly "
            "WHERE temperature_2m IS NOT NULL",
            session, db_path,
        )
        w["date"] = pd.to_datetime(w["timestamp"]).dt.normalize()
        temp = w.groupby("date")["temperature_2m"].mean().rename("temp")
        dem = dem.join(temp, how="left")
    except Exception as exc:  # weather optional — effects still computable
        logger.warning("No weather join (%s); baselines will be unadjusted", exc)
    return dem


def load_events(session=None, db_path: str | None = None) -> pd.DataFrame:
    """Load holiday/festival events."""
    ev = _read_sql(
        "SELECT date, name, type, category FROM holidays", session, db_path
    )
    ev["date"] = pd.to_datetime(ev["date"]).dt.normalize()
    return ev.drop_duplicates(subset=["date", "name"])


def build_table(
    session=None, db_path: str | None = None, as_of: pd.Timestamp | None = None
) -> EventEffectTable:
    """Convenience: load data and return a queryable EventEffectTable."""
    daily = load_daily(session, db_path)
    events = load_events(session, db_path)
    tbl = estimate_effects(daily, events, as_of=as_of)
    return EventEffectTable(table=tbl)


# -------------------------------------------------------------------------
# CLI / sanity check
# -------------------------------------------------------------------------

def main(db_path: str | None = None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    daily = load_daily(db_path=db_path)
    events = load_events(db_path=db_path)
    print(f"Daily demand: {len(daily):,} days "
          f"({daily.index.min().date()} .. {daily.index.max().date()}) "
          f"| temp: {'yes' if 'temp' in daily.columns else 'no'}")
    print(f"Events: {len(events):,}")

    tbl = estimate_effects(daily, events)
    tbl = tbl[tbl["n"] >= 2]  # show only multi-year events in the summary
    print(f"\nLearned event effects (full sample, weather-adjusted, shrunk; n>=2):")
    show = tbl.copy()
    show["mean_%"] = (show["mean_effect"] * 100).round(1)
    show["shrunk_%"] = (show["shrunk_effect"] * 100).round(1)
    show["std_%"] = (show["std_effect"] * 100).round(1)
    print(show[["name", "tier", "n", "mean_%", "std_%", "shrunk_%"]].to_string(index=False))

    # tier means
    print("\nTier means (shrunk):")
    print((tbl.groupby("tier")["shrunk_effect"].mean() * 100).round(1).to_string())

    # causal spot-check: effect for Diwali as-of its 2024 occurrence (uses only prior years)
    et = EventEffectTable(table=estimate_effects(daily, events, as_of=pd.Timestamp("2024-01-01")))
    print(f"\nCausal check — Diwali effect using only pre-2024 data: "
          f"{et.get_effect('Diwali') * 100:.1f}%")


if __name__ == "__main__":
    import sys
    main(db_path=sys.argv[1] if len(sys.argv) > 1 else None)

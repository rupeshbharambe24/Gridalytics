"""Feasibility: does festival information help a GBM day-ahead daily-peak forecaster?

Corrected psp_daily (pre-2021 shifted -1 day), ERA5 weather (oracle = actual weather),
rolling-origin: train on all years < Y, test on year Y, Y = 2019..2024.
Horizons h=1 (latest lag = D-1) and h=7 (latest lag = D-7).
Feature sets:
  none      no holiday info
  db_flag   binary flag from the repo DB holidays table (as shipped: Holi missing pre-2024)
  full_flag binary flag from complete calendar (holidays lib public+optional, canonical list)
  event_id  full_flag + categorical festival identity
  magnitude full_flag + causal signed magnitude (mean of strictly-prior-year deviations)
"""
import json, sqlite3, sys, importlib.util
import numpy as np, pandas as pd, lightgbm as lgb
import statsmodels.formula.api as smf

DB, WX, ES = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(ES).read().split("# --- controls")[0]
ns = {"__name__": "x", "sys": type("s", (), {"argv": [None, DB, WX]})}
exec(src, ns)
df, ev = ns["df"].copy(), ns["ev"].copy()

con = sqlite3.connect(DB)
dbh = pd.read_sql("select date from holidays where category!='sporting'", con, parse_dates=["date"])
df["db_flag"] = df.index.isin(set(dbh.date)).astype(int)
df["full_flag"] = df.index.isin(set(ev.date)).astype(int)
names = sorted(ev.event.unique())
emap = ev.drop_duplicates("date").set_index("date").event
df["event_id"] = pd.Categorical(df.index.map(emap).fillna("none"), categories=["none"] + names)

# deviation of each event day vs a counterfactual fit on non-event days (weather/calendar only)
t = df["temperature_2m_mean"]
df["cdd"] = np.clip(t - 24, 0, None); df["hdd"] = np.clip(18 - t, 0, None)
df["dow"] = df.index.dayofweek; df["doy"] = df.index.dayofyear; df["year"] = df.index.year
df["covid"] = (((df.index >= "2020-03-23") & (df.index <= "2020-05-31")) |
               ((df.index >= "2021-04-19") & (df.index <= "2021-06-07"))).astype(int)
df["lmw"] = np.log(df.mw)
cf = smf.ols("lmw ~ cdd + I(cdd**2) + hdd + I(hdd**2) + C(dow) + C(year) + np.sin(2*np.pi*doy/365.25)"
             " + np.cos(2*np.pi*doy/365.25) + covid", data=df[df.full_flag == 0]).fit()
df["dev"] = df.lmw - cf.predict(df)
mag = pd.Series(0.0, index=df.index)
for name in names:
    ds = sorted(d for d in ev[ev.event == name].date if d in df.index)
    for i, d in enumerate(ds):
        prior = [df.dev[p] for p in ds[:i]]
        mag[d] = float(np.mean(prior)) if prior else 0.0
df["magnitude"] = mag

WX_COLS = ["temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
           "relative_humidity_2m_mean", "precipitation_sum", "cdd", "hdd"]
BASE = WX_COLS + ["dow", "doy", "year", "covid"]
SETS = {"none": [], "db_flag": ["db_flag"], "full_flag": ["full_flag"],
        "event_id": ["full_flag", "event_id"], "magnitude": ["full_flag", "magnitude"]}


def lagged(h):
    X = df.copy()
    for k in sorted({h, h + 1, 7 * int(np.ceil(h / 7)), 7 * int(np.ceil(h / 7)) + 7, 364}):
        X[f"lag{k}"] = X.mw.shift(k)
    X[f"roll7_{h}"] = X.mw.shift(h).rolling(7).mean()
    # lagged event flag: was the lag day itself a festival? (lets the model discount it)
    X[f"lagflag{h}"] = X.full_flag.shift(h)
    return X.dropna(subset=[c for c in X.columns if c.startswith(("lag", "roll"))])


rows = []
for h in [1, 7]:
    X = lagged(h)
    lagc = [c for c in X.columns if c.startswith(("lag", "roll"))]
    for Y in range(2019, 2025):
        tr, te = X[X.year < Y], X[X.year == Y]
        for s, extra in SETS.items():
            feats = BASE + lagc + extra
            if s == "none" or s == "db_flag":
                feats = [f for f in feats if f != "lagflag%d" % h]
            m = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.03, num_leaves=31,
                                  min_child_samples=10, subsample=0.8, subsample_freq=1,
                                  colsample_bytree=0.8, verbose=-1, random_state=0)
            m.fit(tr[feats], np.log(tr.mw))
            p = np.exp(m.predict(te[feats]))
            ape = np.abs(p - te.mw) / te.mw * 100
            for d, a, fl in zip(te.index, ape, te.full_flag):
                rows.append((h, Y, s, d, a, fl))
        # naive baselines
        for s, k in [("persistence", h), ("seasonal_naive", 7 * int(np.ceil(h / 7)))]:
            p = df.mw.shift(k).reindex(te.index)
            ape = np.abs(p - te.mw) / te.mw * 100
            for d, a, fl in zip(te.index, ape, te.full_flag):
                rows.append((h, Y, s, d, a, fl))

r = pd.DataFrame(rows, columns=["h", "Y", "set", "date", "ape", "event"]).dropna()
r["kind"] = np.where(r.event == 1, "event", "normal")
out = r.groupby(["h", "set", "kind"]).ape.mean().unstack().round(2)
out["all"] = r.groupby(["h", "set"]).ape.mean().round(2)
out["n_event"] = r[r.event == 1].groupby(["h", "set"]).size()
print("MAPE % on test years 2019-2024 (rolling origin):")
print(out.to_string())

# paired comparison on event days: full_flag vs db_flag, magnitude vs full_flag, event_id vs full_flag
from scipy import stats
for h in [1, 7]:
    for a, b in [("db_flag", "none"), ("full_flag", "db_flag"), ("magnitude", "full_flag"), ("event_id", "full_flag")]:
        e = r[(r.h == h) & (r.event == 1)].pivot_table(index="date", columns="set", values="ape")
        dlt = e[a] - e[b]
        w = stats.wilcoxon(dlt) if dlt.abs().sum() > 0 else None
        print(f"h={h} event days {a} - {b}: mean dAPE {dlt.mean():+.2f} pp, median {dlt.median():+.2f}, "
              f"Wilcoxon p={w.pvalue if w else float('nan'):.3g}, n={len(dlt)}")
# top-festival breakdown at h=1 and h=7
for h in [1, 7]:
    e = r[(r.h == h) & (r.event == 1)].copy()
    e["name"] = e.date.map(emap)
    top = ["Holi", "Diwali", "Govardhan Puja", "Bhai Duj", "Republic Day", "Dussehra"]
    print(f"\nh={h} MAPE on major festivals by feature set:")
    print(e[e.name.isin(top)].pivot_table(index="name", columns="set", values="ape").round(1).to_string())

"""Feasibility re-analysis for the festival-effect paper (Angle J).

Event-study regression on psp_daily (Delhi daily peak demand met, 2015-2024):
  log(peak) ~ weather splines + DOW + year-month FE + COVID dummies + festival dummies
with Newey-West (HAC) SEs, a placebo test (festival dates shifted by +-4/5 weeks,
same DOW), and a comparison against the repo's same-DOW +-21d estimator.
Festival calendar = `holidays.India(categories=public+optional)` (includes Holi,
which the repo DB calendar lacks pre-2024). Weather = ERA5 via Open-Meteo archive.
"""
import json, sqlite3, sys
import numpy as np, pandas as pd, holidays
import statsmodels.formula.api as smf

DB, WX = sys.argv[1], sys.argv[2]

dem = pd.read_sql("select date, delhi_demand_met_mw mw from psp_daily", sqlite3.connect(DB))
dem["date"] = pd.to_datetime(dem["date"]); dem = dem.set_index("date").sort_index()  # needs DB fixed by scripts/fix_date_integrity.py
w = json.load(open(WX))["daily"]
wx = pd.DataFrame(w).rename(columns={"time": "date"}); wx["date"] = pd.to_datetime(wx["date"])
df = dem.join(wx.set_index("date"), how="inner")
df = df[df.mw > 500]  # guard against bad rows

# --- canonical festival list (Delhi-relevant) ---------------------------
CANON = {
    "Diwali": ["Diwali (Deepavali)"], "Holi": ["Holi"], "Dussehra": ["Dussehra"],
    "Good Friday": ["Good Friday"], "Id-ul-Fitr": ["Id-ul-Fitr"], "Bakrid": ["Id-ul-Zuha (Bakrid)"],
    "Republic Day": ["Republic Day"], "Independence Day": ["Independence Day"],
    "Gandhi Jayanti": ["Mahatma Gandhi's Jayanti"], "Janmashtami": ["Janmashtami (Vaishnava)", "Janmashtami (Smarta)"],
    "Christmas": ["Christmas"], "Guru Nanak Jayanti": ["Guru Nanak's Jayanti"],
    "Raksha Bandhan": ["Raksha Bandhan"], "Mahavir Jayanti": ["Mahavir Jayanti"],
    "Buddha Purnima": ["Buddha Purnima"], "Muharram": ["Muharram"], "Milad-un-Nabi": ["Milad-un-Nabi"],
    "Maha Shivaratri": ["Maha Shivaratri"], "Govardhan Puja": ["Govardhan Puja"], "Bhai Duj": ["Bhai Duj"],
    "Holika Dahan": ["Holika Dahan"], "Chhath": ["Pratihar Shashthi or Surya Shashthi (Chhath Puja)"],
    "Karwa Chauth": ["Karaka Chaturthi (Karwa Chouth)"], "Ram Navami": ["Ram Navami"],
    "New Year's Day": ["New Year's Day"],
}
h = holidays.India(years=range(2015, 2025), categories=("public", "optional"))
ev = []
for d, names in h.items():
    parts = [p.strip() for p in names.split(";")]
    for canon, aliases in CANON.items():
        if any(p in aliases for p in parts):
            ev.append((pd.Timestamp(d), canon))
ev = pd.DataFrame(ev, columns=["date", "event"]).drop_duplicates()
# If Janmashtami variants fall on 2 days keep the first
ev = ev.sort_values("date").groupby([ev.date.dt.year, "event"]).head(1)
ev_dates = set(ev.date)

# --- controls -------------------------------------------------------------
df["t"] = df["temperature_2m_mean"]
df["cdd"] = np.clip(df.t - 24, 0, None); df["hdd"] = np.clip(18 - df.t, 0, None)
df["cdd2"] = df.cdd ** 2; df["hdd2"] = df.hdd ** 2
df["tmax"] = df["temperature_2m_max"]; df["rh"] = df["relative_humidity_2m_mean"]
df["rain"] = np.log1p(df["precipitation_sum"])
df["cdd_rh"] = df.cdd * df.rh / 100
df["dow"] = df.index.dayofweek.astype(str)
df["ym"] = df.index.strftime("%Y-%m")
df["covid1"] = ((df.index >= "2020-03-23") & (df.index <= "2020-05-31")).astype(int)
df["covid2"] = ((df.index >= "2021-04-19") & (df.index <= "2021-06-07")).astype(int)
df["lmw"] = np.log(df.mw)
# lagged weather (thermal inertia of buildings)
for c in ["cdd", "hdd"]:
    df[c + "_l1"] = df[c].shift(1); df[c + "_l2"] = df[c].shift(2)
df = df.dropna()
BASE = ("lmw ~ cdd + cdd2 + hdd + hdd2 + cdd_l1 + cdd_l2 + hdd_l1 + hdd_l2 + tmax + rh + rain"
        " + cdd_rh + C(dow) + C(ym) + covid1 + covid2")


def add_dummies(frame, events, prefix="E"):
    cols = []
    for name, g in events.groupby("event"):
        c = prefix + "_" + "".join(ch for ch in name if ch.isalnum())
        frame[c] = frame.index.isin(set(g.date)).astype(int)
        if frame[c].sum() >= 3:
            cols.append((name, c))
        else:
            frame.drop(columns=c, inplace=True)
    return cols


cols = add_dummies(df, ev)
m = smf.ols(BASE + " + " + " + ".join(c for _, c in cols), data=df).fit(
    cov_type="HAC", cov_kwds={"maxlags": 7})
print(f"N={int(m.nobs)} days, R2={m.rsquared:.3f}, resid sd={np.std(m.resid)*100:.2f}%")
rows = []
for name, c in cols:
    b, se = m.params[c], m.bse[c]
    rows.append(dict(event=name, n=int(df[c].sum()), effect=(np.exp(b) - 1) * 100,
                     lo=(np.exp(b - 1.96 * se) - 1) * 100, hi=(np.exp(b + 1.96 * se) - 1) * 100,
                     p=m.pvalues[c]))
res = pd.DataFrame(rows).sort_values("effect")
# Benjamini-Hochberg q-values
p = res.p.to_numpy(); order = np.argsort(p); q = np.empty_like(p)
q[order] = np.minimum.accumulate((p[order] * len(p) / (np.arange(len(p)) + 1))[::-1])[::-1]
res["q"] = np.minimum(q, 1)
pd.set_option("display.width", 160)
print("\nEvent-study effects on daily PEAK (% vs counterfactual, 95% HAC CI):")
print(res.round(2).to_string(index=False))

# --- placebo: shift each event by +-28 / +-35 days (same DOW) -------------
plac = []
for shift in [-35, -28, 28, 35]:
    pe = ev.copy(); pe["date"] = pe.date + pd.Timedelta(days=shift)
    pe = pe[~pe.date.isin(ev_dates)]
    d2 = df.drop(columns=[c for _, c in cols]).copy()
    pc = add_dummies(d2, pe, prefix="P")
    mp = smf.ols(BASE + " + " + " + ".join(c for _, c in pc), data=d2).fit(
        cov_type="HAC", cov_kwds={"maxlags": 7})
    for _, c in pc:
        plac.append(dict(shift=shift, eff=(np.exp(mp.params[c]) - 1) * 100, p=mp.pvalues[c]))
plac = pd.DataFrame(plac)
print(f"\nPlacebo ({len(plac)} fake event-coefs): mean {plac.eff.mean():.2f}%, sd {plac.eff.std():.2f}%,"
      f" share p<0.05 = {(plac.p < 0.05).mean():.2%} (nominal 5%)")

# --- heterogeneity: Diwali / Holi per year -------------------------------
resid_model = smf.ols(BASE, data=df[~df.index.isin(ev_dates)]).fit()
pred = resid_model.predict(df)
df["dev"] = (np.exp(df.lmw - pred) - 1) * 100
print("\nPer-year deviation vs counterfactual (model fit on non-event days):")
for name in ["Diwali", "Holi", "Good Friday", "Id-ul-Fitr", "Dussehra", "Republic Day"]:
    ds = ev[ev.event == name].date
    vals = [f"{d.year}:{df.dev.get(d, np.nan):+.1f}" for d in ds if d in df.index]
    print(f"  {name:15s}", " ".join(vals))

# --- event window around Diwali (d-3..d+3) -------------------------------
print("\nDiwali window (mean deviation %, d-3..d+3):")
dw = ev[ev.event == "Diwali"].date
for k in range(-3, 4):
    v = [df.dev.get(d + pd.Timedelta(days=k), np.nan) for d in dw]
    print(f"  d{k:+d}: {np.nanmean(v):+.1f}  (n={np.sum(~np.isnan(v))})")
print("\nHoli window:")
for k in range(-2, 3):
    v = [df.dev.get(d + pd.Timedelta(days=k), np.nan) for d in ev[ev.event == "Holi"].date]
    print(f"  d{k:+d}: {np.nanmean(v):+.1f}  (n={np.sum(~np.isnan(v))})")
res.to_csv(sys.argv[3] if len(sys.argv) > 3 else "/dev/null", index=False)

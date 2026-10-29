#!/usr/bin/env python3
"""Repair three date-integrity defects in an existing database (one-off).

Found during the festival-effects audit (docs/paper_festival_effects.md §3):

  1. psp_daily rows dated <= 2021-01-03 carry the PSP *report* date, i.e. the
     previous day's demand. Fix: shift them back one day.
  2. Legacy demand_5min rows were parsed month-first: for day <= 12 the day and
     month are swapped (stored 2022-06-11 is really 2022-11-06). Fix: swap back.
     (Days > 12 never parsed and were dropped at migration time; they can only
     be recovered by re-migrating the source files or re-scraping SLDC.)
  3. The holidays table came from an older `holidays` lib that omitted Holi and
     the Delhi optional festivals, with inconsistent names. Fix: regenerate it
     from HolidayScraper.

Fixed rows get source='legacy_fixed', so a second run is a no-op for 1-2.
Back up the DB first (scripts/backup_db.py, or copy data/edfs.db).

    python scripts/fix_date_integrity.py           # dry run: diagnostics only
    python scripts/fix_date_integrity.py --apply   # apply all three fixes
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import delete, insert, select, update

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.db.models import DemandRecord, HolidayRecord, PSPDailyReport
from src.data.db.session import get_session
from src.data.scrapers.holidays import HolidayScraper

PSP_CUTOFF = date(2021, 1, 4)
LEGACY, FIXED = "legacy_migration", "legacy_fixed"
CALENDAR_RANGE = (date(2015, 1, 1), date(2027, 12, 31))


def swap_day_month(ts: pd.Series) -> pd.Series:
    """Swap day and month where that's ambiguous (day <= 12 and day != month)."""
    amb = (ts.dt.day <= 12) & (ts.dt.day != ts.dt.month)
    out = ts.copy()
    out[amb] = pd.to_datetime(dict(
        year=ts[amb].dt.year, month=ts[amb].dt.day, day=ts[amb].dt.month,
        hour=ts[amb].dt.hour, minute=ts[amb].dt.minute,
    ))
    return out


def diagnostics(session) -> None:
    """Print the two tests that exposed the defects."""
    bind = session.connection()  # same transaction (sqlite locks other connections)
    psp = pd.read_sql("SELECT date, delhi_demand_met_mw AS mw FROM psp_daily", bind)
    psp["date"] = pd.to_datetime(psp["date"])
    d = psp.set_index("date")["mw"].sort_index().asfreq("D")
    rel = d / d.rolling(7, center=True, min_periods=5).mean()
    era = np.where(rel.index < pd.Timestamp(PSP_CUTOFF), "pre-2021", "2021+")
    prof = rel.groupby([era, rel.index.day_name().str[:3]]).mean().unstack()
    print("psp_daily: two lowest weekdays per era (expect Sat/Sun in both):")
    for e, row in prof.iterrows():
        print(f"  {e:9s} {', '.join(row.nsmallest(2).index)}")

    x = pd.read_sql(
        "SELECT timestamp, delhi_mw, source FROM demand_5min "
        f"WHERE source IN ('{LEGACY}', '{FIXED}')", bind)
    if x.empty:
        print("demand_5min: no legacy rows")
        return
    x["timestamp"] = pd.to_datetime(x["timestamp"])
    g = x.set_index("timestamp")["delhi_mw"].resample("D")
    t = pd.DataFrame({"n": g.count(), "mx": g.max()})
    t = t[t["n"] >= 200]
    t["psp"] = t.index.map(d)
    t = t.dropna()
    ape = (t["mx"] - t["psp"]).abs() / t["psp"] * 100
    print(f"demand_5min legacy daily max vs psp peak (same date): n={len(t)}, "
          f"median APE {ape.median():.1f}%, corr {t['mx'].corr(t['psp']):.3f} "
          f"(expect <~1% and >0.99)")
    print(f"  rows by source: {x['source'].value_counts().to_dict()}")


def fix_psp(session, apply: bool) -> int:
    rows = session.execute(
        select(PSPDailyReport)
        .where(PSPDailyReport.source == LEGACY, PSPDailyReport.date < PSP_CUTOFF)
        .order_by(PSPDailyReport.date)  # ascending: each target date is already free
    ).scalars().all()
    if apply:
        for r in rows:
            r.date = r.date - pd.Timedelta(days=1).to_pytimedelta()
            r.source = FIXED
            session.flush()
    return len(rows)


def fix_5min(session, apply: bool) -> tuple[int, int]:
    cols = ["timestamp", "delhi_mw", "brpl_mw", "bypl_mw", "ndpl_mw",
            "ndmc_mw", "mes_mw", "created_at"]
    df = pd.read_sql(
        select(*[getattr(DemandRecord, c) for c in cols])
        .where(DemandRecord.source == LEGACY), session.connection())
    if df.empty:
        return 0, 0
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    new_ts = swap_day_month(df["timestamp"])
    n_swapped = int((new_ts != df["timestamp"]).sum())

    # Swapping is a permutation of the legacy rows, but a swapped timestamp
    # could land on a live-scraped row; the live row wins.
    others = set(pd.to_datetime(pd.read_sql(
        select(DemandRecord.timestamp).where(DemandRecord.source != LEGACY),
        session.connection())["timestamp"]))
    df["timestamp"] = new_ts
    clash = df["timestamp"].isin(others)
    if apply:
        session.execute(delete(DemandRecord).where(DemandRecord.source == LEGACY))
        recs = df[~clash].assign(source=FIXED)
        recs["created_at"] = pd.to_datetime(recs["created_at"])
        recs = recs.astype(object).where(recs.notna(), None)
        session.execute(insert(DemandRecord), recs.to_dict("records"))
    return n_swapped, int(clash.sum())


def fix_holidays(session, apply: bool) -> tuple[int, int]:
    scraper = HolidayScraper()
    df = scraper.validate(scraper.scrape(*CALENDAR_RANGE))
    old = session.query(HolidayRecord).count()
    if apply:
        session.execute(delete(HolidayRecord))
        session.flush()
        scraper.upsert(df, session)
    return old, len(df)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the fixes")
    args = ap.parse_args()

    with get_session() as session:
        print(f"DB: {session.bind.url.render_as_string(hide_password=True)}\n")
        print("BEFORE"); diagnostics(session)
        n_psp = fix_psp(session, args.apply)
        n_swap, n_clash = fix_5min(session, args.apply)
        n_old, n_new = fix_holidays(session, args.apply)
        verb = "fixed" if args.apply else "would fix"
        print(f"\npsp_daily: {verb} {n_psp} rows (shift -1 day)")
        print(f"demand_5min: {verb} {n_swap} rows (day/month swap); "
              f"{n_clash} rows dropped where a live row already exists")
        print(f"holidays: {n_old} rows -> {n_new} rows (regenerated)")
        if args.apply:
            session.flush()
            print("\nAFTER"); diagnostics(session)
        else:
            print("\nDry run - nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()

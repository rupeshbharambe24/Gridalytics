"""Himachal Pradesh 15-minute demand backfill.

HPSLDC's admin-ajax `demand_day_data` action returns a whole month of 15-minute
block demand (96 blocks x one column per date, "Demand of HP Block Daywise (Values
in MW)"). The daily collector (HimachalPSPScraper) keeps only each day's max; this
stores the full 15-minute series into `state_demand` (state_code=himachal_pradesh,
source=hpsldc_15min). History ~FY2017 onward. Plain HTTPS, no TLS workaround.

Resumable (skips months already loaded) and idempotent (dedupe by timestamp).

Usage:
  python scripts/collect_himachal_15min.py --start 2017-04 --end 2026-10
  python scripts/collect_himachal_15min.py            # 2017-04 .. current month
"""
import sys
import argparse
import io
import re
import time
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
import pandas as pd
from sqlalchemy import func

from src.data.db.session import get_session, create_tables
from src.data.db.models import StateDemandRecord

UA = {"User-Agent": "Mozilla/5.0 (Gridalytics Research Project)"}
URL = "https://hpsldc.com/wp-admin/admin-ajax.php"


def parse_month(html: str) -> list[tuple]:
    """Return (timestamp, demand_mw) for every 15-min block in the month."""
    out = []
    for t in pd.read_html(io.StringIO(html)):
        if t.shape[0] < 50:
            continue
        block = t.iloc[:, 1].astype(str)
        mask = block.str.match(r"\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}").fillna(False)
        if not mask.any():
            continue
        rows = [i for i in range(len(t)) if mask.iloc[i]]
        for ci in range(2, t.shape[1]):
            lab = t.columns[ci]
            lab = lab[-1] if isinstance(lab, tuple) else lab
            try:
                d = pd.to_datetime(str(lab).strip()).date()
            except Exception:
                continue
            for i in rows:
                bt = str(t.iat[i, 1]).split("-")[0].strip()
                m = re.match(r"(\d{1,2}):(\d{2})", bt)
                if not m:
                    continue
                val = pd.to_numeric(t.iat[i, ci], errors="coerce")
                if pd.isna(val) or not (0 < val <= 5000):  # HP peak ~2800; >5000 = parse artifact
                    continue
                ts = datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)))
                out.append((ts, float(val)))
        break
    return out


def months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _d(s):
    return datetime.strptime(s, "%Y-%m").date().replace(day=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=_d, default=date(2017, 4, 1))
    ap.add_argument("--end", type=_d, default=date.today().replace(day=1))
    args = ap.parse_args()
    create_tables()
    # resume: months (year,month) already present
    with get_session() as s:
        done = {(r.year, r.month) for r in s.query(
            func.strftime("%Y", StateDemandRecord.timestamp).label("year"),
            func.strftime("%m", StateDemandRecord.timestamp).label("month")).filter(
            StateDemandRecord.state_code == "himachal_pradesh",
            StateDemandRecord.source == "hpsldc_15min").distinct().all()}
    done = {(int(y), int(m)) for y, m in done}
    ins = 0
    for y, m in months(args.start, args.end):
        if (y, m) in done:
            continue
        try:
            r = requests.post(URL, headers=UA, timeout=50,
                              data={"action": "demand_day_data", "seldatagetyr": y, "seldatagetmonth": m})
            if r.status_code != 200 or not r.text.strip():
                print(f"  {y}-{m:02d}: HTTP {r.status_code}", flush=True)
                continue
            rows = parse_month(r.text)
        except Exception as e:
            print(f"  {y}-{m:02d}: {type(e).__name__}: {e}", flush=True)
            continue
        if not rows:
            continue
        dedup = {}
        for ts, v in rows:
            dedup.setdefault(ts, v)
        with get_session() as s:
            existing = {t for (t,) in s.query(StateDemandRecord.timestamp).filter(
                StateDemandRecord.state_code == "himachal_pradesh",
                StateDemandRecord.source == "hpsldc_15min",
                StateDemandRecord.timestamp >= datetime(y, m, 1)).all()}
            for ts, v in dedup.items():
                if ts in existing:
                    continue
                s.add(StateDemandRecord(state_code="himachal_pradesh", timestamp=ts,
                                        demand_mw=v, source="hpsldc_15min"))
                ins += 1
        print(f"  {y}-{m:02d}: +{len(dedup)} blocks (total ins={ins})", flush=True)
        time.sleep(0.3)
    with get_session() as s:
        tot = s.query(func.count(StateDemandRecord.id)).filter(
            StateDemandRecord.state_code == "himachal_pradesh",
            StateDemandRecord.source == "hpsldc_15min").scalar()
        mn = s.query(func.min(StateDemandRecord.timestamp)).filter(
            StateDemandRecord.state_code == "himachal_pradesh", StateDemandRecord.source == "hpsldc_15min").scalar()
        mx = s.query(func.max(StateDemandRecord.timestamp)).filter(
            StateDemandRecord.state_code == "himachal_pradesh", StateDemandRecord.source == "hpsldc_15min").scalar()
    print(f"DONE: inserted {ins} this run; hpsldc_15min total={tot}, span {mn}..{mx}", flush=True)


if __name__ == "__main__":
    main()

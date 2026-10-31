"""One-off background job: national 15-min SCADA demand+frequency from official
NLDC PSP XLS 'TimeSeries' sheets (webcdn.grid-india.in), enumerated via energymap
source_urls. Stores into state_demand as state_code='all_india',
source='nldc_timeseries'. Resumable: skips dates already loaded."""
import sys, io, re, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
import pandas as pd
from datetime import datetime
from collections import defaultdict
from src.data.db.session import get_session, create_tables
from src.data.db.models import StateDemandRecord
from sqlalchemy import func

UA = {"User-Agent": "Mozilla/5.0 (Gridalytics Research Project)"}
API = "https://api.energymap.in/api/intelligence/posoco-psp"


def enumerate_xls():
    r = requests.get(API, params={"days": 2000, "scope": "state", "state": "tamil-nadu"},
                     headers={**UA, "Accept": "application/json"}, timeout=60)
    xls = defaultdict(set)
    for it in r.json()["items"]:
        u = it.get("source_url")
        if u and u.endswith(".xls"):
            xls[it["date"]].add(u)
    return {d: sorted(v)[-1] for d, v in xls.items()}  # highest report number


def parse_ts(content, d):
    xl = pd.ExcelFile(io.BytesIO(content), engine="xlrd")
    if "TimeSeries" not in xl.sheet_names:
        return []
    ts = xl.parse("TimeSeries", header=None)
    rows = []
    for i in range(len(ts)):
        t = str(ts.iat[i, 0]).strip()
        if not re.fullmatch(r"\d{1,2}:\d{2}", t):
            continue
        try:
            dem = float(ts.iat[i, 2])
        except (TypeError, ValueError):
            continue
        try:
            freq = float(ts.iat[i, 1])
        except (TypeError, ValueError):
            freq = None
        hh, mm = map(int, t.split(":"))
        rows.append((datetime(d.year, d.month, d.day, hh, mm), dem, freq))
    return rows


def main():
    create_tables()
    xls = enumerate_xls()
    print(f"enumerated {len(xls)} dated xls files", flush=True)
    with get_session() as s:
        done = {r[0] for r in s.query(func.date(StateDemandRecord.timestamp)).filter(
            StateDemandRecord.state_code == "all_india",
            StateDemandRecord.source == "nldc_timeseries").distinct().all()}
    print(f"already loaded dates: {len(done)}", flush=True)
    todo = sorted(d for d in xls if d not in done)
    print(f"to fetch: {len(todo)}", flush=True)
    ins = 0
    no_ts = 0
    for k, ds in enumerate(todo):
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        try:
            c = requests.get(xls[ds], headers=UA, timeout=50).content
            rows = parse_ts(c, d)
        except Exception as e:
            print(f"  {ds}: ERR {e}", flush=True)
            continue
        if not rows:
            no_ts += 1
            continue
        dedup = {}  # keep first value per timestamp (sheets occasionally repeat a time)
        for tsr, dem, freq in rows:
            dedup.setdefault(tsr, (dem, freq))
        try:
            with get_session() as s:
                for tsr, (dem, freq) in dedup.items():
                    s.add(StateDemandRecord(state_code="all_india", timestamp=tsr,
                                            demand_mw=dem, frequency_hz=freq,
                                            source="nldc_timeseries"))
            ins += len(dedup)
        except Exception as e:
            print(f"  {ds}: insert skipped ({type(e).__name__})", flush=True)
            continue
        if k % 100 == 0:
            print(f"  [{k}/{len(todo)}] {ds}: +{len(rows)} (total ins={ins}, no_ts={no_ts})", flush=True)
        time.sleep(0.2)
    with get_session() as s:
        tot = s.query(func.count(StateDemandRecord.id)).filter(
            StateDemandRecord.state_code == "all_india",
            StateDemandRecord.source == "nldc_timeseries").scalar()
        mn = s.query(func.min(StateDemandRecord.timestamp)).filter(
            StateDemandRecord.state_code == "all_india", StateDemandRecord.source == "nldc_timeseries").scalar()
        mx = s.query(func.max(StateDemandRecord.timestamp)).filter(
            StateDemandRecord.state_code == "all_india", StateDemandRecord.source == "nldc_timeseries").scalar()
    print(f"DONE: inserted {ins} rows this run; files w/o TimeSeries={no_ts}; "
          f"all_india 15-min total={tot}, span {mn}..{mx}", flush=True)


if __name__ == "__main__":
    main()

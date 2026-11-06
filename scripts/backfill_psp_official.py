"""Fill state_psp_daily gaps from the official NLDC PSP PDFs.

energymap (scripts/collect_psp.py) has no rows for J&K(+Ladakh) or DNH&DD and only
starts MP/UP in 2023; every official daily PSP PDF carries them. This walks month by
month (committing each month, so it can be interrupted and re-run), downloads only
the files for dates where a wanted (state, date) row is missing, and inserts those
rows (source=nldc_psp_official). Never overwrites existing rows.

Usage:
  python scripts/backfill_psp_official.py --start 2021-05-01
  python scripts/backfill_psp_official.py --start 2021-05-01 --states jammu_kashmir dnh_dd
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from src.data.db.session import get_session, create_tables
from src.data.db.models import StatePSPDaily
from src.data.scrapers.state_fallback import OfficialPSPFillScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("backfill_psp_official")


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def months(start: date, end: date):
    cur = start.replace(day=1)
    while cur <= end:
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(cur, start), min(nxt - timedelta(days=1), end)
        cur = nxt


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", type=_d, required=True)
    ap.add_argument("--end", type=_d, default=date.today() - timedelta(days=1))
    ap.add_argument("--states", nargs="*", default=None,
                    help="state codes (default: jammu_kashmir dnh_dd uttar_pradesh madhya_pradesh)")
    args = ap.parse_args()

    create_tables()
    scraper = OfficialPSPFillScraper(args.states)
    total = 0
    for lo, hi in months(args.start, args.end):
        with get_session() as s:
            have = set(s.query(StatePSPDaily.state_code, StatePSPDaily.date)
                       .filter(StatePSPDaily.date >= lo, StatePSPDaily.date <= hi).all())
        df = scraper.validate(scraper.scrape(lo, hi, skip=have))
        with get_session() as s:
            n = scraper.upsert(df, s)
        total += n
        logger.info(f"{lo:%Y-%m}: +{n} rows")

    with get_session() as s:
        rows = (s.query(StatePSPDaily.state_code, func.count(StatePSPDaily.id),
                        func.min(StatePSPDaily.date), func.max(StatePSPDaily.date))
                .filter(StatePSPDaily.state_code.in_(sorted(scraper._only)))
                .group_by(StatePSPDaily.state_code).all())
    logger.info(f"Inserted {total} rows. Coverage now:")
    for code, n, lo, hi in rows:
        logger.info(f"  {code:<16} {n:>5}  {lo} .. {hi}")


if __name__ == "__main__":
    main()

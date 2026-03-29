"""Backfill demand data from SLDC to bring it up to current date."""
import sys
import logging
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

from src.data.scrapers.sldc import SLDCScraper
from src.data.db.session import get_session
from src.data.db.models import DemandRecord
from sqlalchemy import func

# Find where demand data ends
with get_session() as session:
    latest = session.query(func.max(DemandRecord.timestamp)).scalar()

start_date = latest.date() + timedelta(days=1)
end_date = date.today() - timedelta(days=1)  # yesterday (today may be incomplete)

print(f"Backfilling demand from {start_date} to {end_date}")
print(f"That's {(end_date - start_date).days + 1} days to scrape")

scraper = SLDCScraper()
scraper.rate_limit_delay = 0.5  # faster for backfill

# Process in weekly chunks to commit periodically
current = start_date
total_inserted = 0

while current <= end_date:
    chunk_end = min(current + timedelta(days=6), end_date)
    print(f"\n--- Chunk: {current} to {chunk_end} ---")
    
    with get_session() as session:
        count = scraper.run(current, chunk_end, session)
        total_inserted += count
        print(f"  Chunk inserted: {count} rows (total: {total_inserted})")
    
    current = chunk_end + timedelta(days=1)

print(f"\n{'='*50}")
print(f"BACKFILL COMPLETE: {total_inserted} total rows inserted")

# Final stats
with get_session() as session:
    d_min, d_max = session.query(func.min(DemandRecord.timestamp), func.max(DemandRecord.timestamp)).first()
    d_count = session.query(func.count(DemandRecord.id)).scalar()
    print(f"Demand DB: {d_count:,} rows | {str(d_min)[:10]} to {str(d_max)[:10]}")

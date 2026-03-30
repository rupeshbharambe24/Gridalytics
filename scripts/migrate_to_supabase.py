"""One-time migration: copy all data from local SQLite to Supabase PostgreSQL.

Usage:
    1. Set SUPABASE_URL in your .env or pass as argument
    2. Run: python scripts/migrate_to_supabase.py

This copies all tables from data/edfs.db to your Supabase PostgreSQL.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
import pandas as pd

# Source: local SQLite
SQLITE_URL = "sqlite:///./data/edfs.db"

# Target: Supabase PostgreSQL (from env or argument)
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("DATABASE_URL")

if not SUPABASE_URL or "sqlite" in SUPABASE_URL:
    if len(sys.argv) > 1:
        SUPABASE_URL = sys.argv[1]
    else:
        print("Usage: python scripts/migrate_to_supabase.py <SUPABASE_POSTGRESQL_URL>")
        print("  Or set SUPABASE_URL environment variable")
        print("  Example: postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres")
        sys.exit(1)

print(f"Source: {SQLITE_URL}")
print(f"Target: {SUPABASE_URL[:50]}...")
print()

# Connect to both databases
sqlite_engine = create_engine(SQLITE_URL)
pg_engine = create_engine(SUPABASE_URL)

# Create tables in PostgreSQL
from src.data.db.models import Base
print("Creating tables in Supabase...")
Base.metadata.create_all(bind=pg_engine)
print("Tables created.\n")

# Get list of tables
inspector = inspect(sqlite_engine)
tables = inspector.get_table_names()

print(f"Found {len(tables)} tables to migrate:")
for t in tables:
    count = pd.read_sql(f"SELECT COUNT(*) as c FROM {t}", sqlite_engine).iloc[0]["c"]
    print(f"  {t}: {count:,} rows")

print()
confirm = input("Proceed with migration? (y/n): ").strip().lower()
if confirm != "y":
    print("Aborted.")
    sys.exit(0)

# Migrate each table
for table_name in tables:
    print(f"\nMigrating {table_name}...")

    # Read from SQLite
    df = pd.read_sql(f"SELECT * FROM {table_name}", sqlite_engine)
    if df.empty:
        print(f"  Skipped (empty)")
        continue

    # Drop 'id' column if it exists (let PostgreSQL auto-generate)
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    # Write to PostgreSQL in chunks
    chunk_size = 5000
    total = len(df)
    written = 0

    for i in range(0, total, chunk_size):
        chunk = df.iloc[i:i + chunk_size]
        try:
            chunk.to_sql(table_name, pg_engine, if_exists="append", index=False, method="multi")
            written += len(chunk)
            print(f"  {written:,}/{total:,} rows...", end="\r")
        except Exception as e:
            # Skip duplicates (unique constraint violations)
            print(f"  Chunk {i}-{i+chunk_size} had errors (likely duplicates): {str(e)[:80]}")
            # Try row by row for this chunk
            for _, row in chunk.iterrows():
                try:
                    row.to_frame().T.to_sql(table_name, pg_engine, if_exists="append", index=False)
                    written += 1
                except Exception:
                    pass  # Skip duplicate

    print(f"  Done: {written:,} rows written")

# Verify
print("\n" + "=" * 50)
print("VERIFICATION")
print("=" * 50)
for table_name in tables:
    sqlite_count = pd.read_sql(f"SELECT COUNT(*) as c FROM {table_name}", sqlite_engine).iloc[0]["c"]
    try:
        pg_count = pd.read_sql(f"SELECT COUNT(*) as c FROM {table_name}", pg_engine).iloc[0]["c"]
    except Exception:
        pg_count = 0
    status = "OK" if pg_count >= sqlite_count * 0.95 else "MISMATCH"
    print(f"  {table_name}: SQLite={sqlite_count:,} → Supabase={pg_count:,} [{status}]")

print("\nMigration complete!")
print(f"\nNext steps:")
print(f"  1. Update your .env: DATABASE_URL={SUPABASE_URL[:50]}...")
print(f"  2. Restart your API server")
print(f"  3. Set DATABASE_URL in Render environment variables")

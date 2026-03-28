"""One-time migration: Import existing EDFS data into the new database.

Reads Excel/CSV files from the old F:/Projects/EDFS project and inserts
them into the new SQLite database.
"""

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import create_tables, get_session
from src.data.db.models import DemandRecord, WeatherRecord, HolidayRecord, PSPDailyReport


OLD_PROJECT = Path("F:/Projects/EDFS")


def migrate_5min_demand():
    """Import 5-minute demand data from the old project."""
    file_path = OLD_PROJECT / "data" / "interim" / "5-min-data-delhi.xlsx"
    if not file_path.exists():
        # Try the processed version
        file_path = OLD_PROJECT / "data" / "processed" / "5Min-Data-23-24.5.xlsx"

    if not file_path.exists():
        print(f"[SKIP] 5-min demand file not found: {file_path}")
        return

    print(f"[LOAD] Reading {file_path}...")
    df = pd.read_excel(file_path)
    print(f"  Loaded {len(df)} rows, columns: {list(df.columns)}")

    # Detect column names (they vary across files)
    date_col = [c for c in df.columns if "date" in c.lower()][0]
    time_col = [c for c in df.columns if "time" in c.lower() or "hour" in c.lower()][0]
    demand_col = [c for c in df.columns if "demand" in c.lower() or "delhi" in c.lower()]
    if demand_col:
        demand_col = demand_col[0]
    else:
        print(f"  [ERROR] Could not find demand column in: {list(df.columns)}")
        return

    # Parse timestamps
    df["date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
    df["time_parsed"] = pd.to_datetime(df[time_col], format="%H:%M:%S", errors="coerce")
    if df["time_parsed"].isna().all():
        df["time_parsed"] = pd.to_datetime(df[time_col], errors="coerce")

    df["timestamp"] = df["date_parsed"].dt.normalize() + pd.to_timedelta(
        df["time_parsed"].dt.hour * 3600 + df["time_parsed"].dt.minute * 60,
        unit="s",
    )
    df = df.dropna(subset=["timestamp"])
    df["delhi_mw"] = pd.to_numeric(df[demand_col], errors="coerce")
    df = df.dropna(subset=["delhi_mw"])

    print(f"  Parsed {len(df)} valid rows")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Insert into database
    with get_session() as session:
        count = 0
        batch_size = 5000

        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            for _, row in batch.iterrows():
                record = DemandRecord(
                    timestamp=row["timestamp"],
                    delhi_mw=row["delhi_mw"],
                    source="legacy_migration",
                )
                session.add(record)
                count += 1

            session.flush()
            print(f"  Inserted {min(i + batch_size, len(df))}/{len(df)} rows...")

        print(f"  [DONE] Inserted {count} demand records")


def migrate_weather():
    """Import hourly weather data."""
    file_path = OLD_PROJECT / "data" / "interim" / "hourly_weather_data.csv"
    if not file_path.exists():
        print(f"[SKIP] Weather file not found: {file_path}")
        return

    print(f"[LOAD] Reading {file_path}...")
    # Try multiple encodings
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            break
        except (UnicodeDecodeError, Exception):
            continue
    else:
        print(f"  [ERROR] Could not read weather CSV with any encoding")
        return

    print(f"  Loaded {len(df)} rows, columns: {list(df.columns)}")

    # Parse timestamp
    if "Date" in df.columns and "Time" in df.columns:
        df["timestamp"] = pd.to_datetime(
            df["Date"].astype(str) + " " + df["Time"].astype(str),
            dayfirst=True,
            errors="coerce",
        )
    elif "time" in df.columns:
        df["timestamp"] = pd.to_datetime(df["time"], errors="coerce")

    df = df.dropna(subset=["timestamp"])

    # Map column names
    col_map = {}
    for col in df.columns:
        cl = col.lower()
        if "temperature" in cl or "temp" in cl:
            col_map[col] = "temperature_2m"
        elif "humidity" in cl:
            col_map[col] = "relative_humidity_2m"
        elif "dew" in cl:
            col_map[col] = "dew_point_2m"
        elif "precip" in cl:
            col_map[col] = "precipitation_mm"
        elif "cloud" in cl:
            col_map[col] = "cloud_cover_pct"
        elif "wind" in cl:
            col_map[col] = "wind_speed_10m"
        elif "radiation" in cl or "shortwave" in cl:
            col_map[col] = "shortwave_radiation"

    df = df.rename(columns=col_map)
    print(f"  Parsed {len(df)} valid rows")

    with get_session() as session:
        count = 0
        for i in range(0, len(df), 5000):
            batch = df.iloc[i:i + 5000]
            for _, row in batch.iterrows():
                record = WeatherRecord(
                    timestamp=row["timestamp"],
                    temperature_2m=row.get("temperature_2m"),
                    relative_humidity_2m=row.get("relative_humidity_2m"),
                    dew_point_2m=row.get("dew_point_2m"),
                    precipitation_mm=row.get("precipitation_mm"),
                    cloud_cover_pct=row.get("cloud_cover_pct"),
                    wind_speed_10m=row.get("wind_speed_10m"),
                    shortwave_radiation=row.get("shortwave_radiation"),
                    source="legacy_migration",
                )
                session.add(record)
                count += 1
            session.flush()
            print(f"  Inserted {min(i + 5000, len(df))}/{len(df)} rows...")

        print(f"  [DONE] Inserted {count} weather records")


def migrate_daily_demand():
    """Import daily demand from processed data."""
    file_path = OLD_PROJECT / "data" / "processed" / "Daily-Data-15-24.xlsx"
    if not file_path.exists():
        print(f"[SKIP] Daily data file not found: {file_path}")
        return

    print(f"[LOAD] Reading {file_path}...")
    df = pd.read_excel(file_path)
    print(f"  Loaded {len(df)} rows, columns: {list(df.columns)}")

    # Find the date and demand columns
    date_col = [c for c in df.columns if "date" in c.lower()][0]
    demand_col = [c for c in df.columns if "demand" in c.lower()][0]

    df["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df["delhi_demand_met_mw"] = pd.to_numeric(df[demand_col], errors="coerce")
    df = df.dropna(subset=["date", "delhi_demand_met_mw"])

    print(f"  Parsed {len(df)} valid rows")

    with get_session() as session:
        count = 0
        for _, row in df.iterrows():
            record = PSPDailyReport(
                date=row["date"],
                delhi_demand_met_mw=row["delhi_demand_met_mw"],
                source="legacy_migration",
            )
            session.add(record)
            count += 1

        print(f"  [DONE] Inserted {count} daily demand records")


def main():
    print("=" * 60)
    print("EDFS v2 - Legacy Data Migration")
    print("=" * 60)

    print("\n[INIT] Creating database tables...")
    create_tables()
    print("[DONE] Tables created\n")

    print("-" * 60)
    migrate_5min_demand()
    print("-" * 60)
    migrate_weather()
    print("-" * 60)
    migrate_daily_demand()
    print("-" * 60)

    # Print summary
    from src.data.loaders import get_data_summary
    with get_session() as session:
        summary = get_data_summary(session)

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    for key, value in summary.items():
        print(f"  {key}: {value}")
    print("=" * 60)


if __name__ == "__main__":
    main()

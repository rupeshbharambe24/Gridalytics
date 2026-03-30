"""Automated database backup script.

Creates timestamped copies of the SQLite database.
Keeps last 7 backups, deletes older ones.

Usage:
    python scripts/backup_db.py

Add to scheduler for automated daily backups.
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/edfs.db")
BACKUP_DIR = Path("data/backups")
MAX_BACKUPS = 7


def backup():
    """Create a timestamped backup of the database."""
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return False

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"gridalytics_{timestamp}.db"

    shutil.copy2(DB_PATH, backup_path)
    size_mb = backup_path.stat().st_size / (1024 * 1024)
    print(f"Backup created: {backup_path} ({size_mb:.1f} MB)")

    # Clean old backups (keep last MAX_BACKUPS)
    backups = sorted(BACKUP_DIR.glob("gridalytics_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[MAX_BACKUPS:]:
        old.unlink()
        print(f"Deleted old backup: {old.name}")

    remaining = len(list(BACKUP_DIR.glob("gridalytics_*.db")))
    print(f"Total backups: {remaining}/{MAX_BACKUPS}")
    return True


if __name__ == "__main__":
    success = backup()
    sys.exit(0 if success else 1)

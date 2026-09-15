#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.database import Database


def main() -> int:
    settings = Settings.from_env()
    db = Database(settings)
    migrations = sorted((ROOT / "migrations").glob("*.sql"))
    if not migrations:
        raise SystemExit("no migrations found")

    with db.connection() as conn:
        with conn.cursor() as cur:
            for path in migrations:
                cur.execute(path.read_text(encoding="utf-8"))
        conn.commit()
    print(f"applied {len(migrations)} migration file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

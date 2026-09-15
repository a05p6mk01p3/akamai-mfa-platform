#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import Settings
from app.database import Database


def main() -> int:
    ok = Database(Settings.from_env()).ping()
    print({"database": "ok" if ok else "error"})
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Reset local demo state so the CG Dashboard starts fresh.

Deletes the SQLite database and clears runtime mail folders. Sample shipments are untouched.
"""

import shutil
from pathlib import Path

from src.config import settings

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIRS = ("inbox", "processed", "sent")


def _db_path() -> Path:
    path = Path(settings.db_path)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    db = _db_path()
    if db.exists():
        db.unlink()
        print(f"deleted {db}")
    else:
        print(f"missing {db}")

    for name in RUNTIME_DIRS:
        path = ROOT / name
        if path.exists():
            shutil.rmtree(path)
            print(f"deleted {path}")
        else:
            print(f"missing {path}")

    print("demo state reset")


if __name__ == "__main__":
    main()

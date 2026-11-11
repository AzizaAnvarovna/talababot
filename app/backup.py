"""Maʼlumotlar bazasining kunlik zaxira nusxasi (NFR-6): python -m app.backup"""

import contextlib
import gzip
import shutil
import sqlite3
from datetime import date
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import get_settings

KEEP_COPIES = 14
_PREFIX = "talababot-"
_SUFFIX = ".db.gz"


class BackupError(RuntimeError):
    pass


def sqlite_path(url: str) -> Path:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        raise BackupError(
            f"Faqat fayldagi SQLite qoʻllab-quvvatlanadi: {parsed.get_backend_name()}"
        )
    return Path(parsed.database)


def create_backup(source: Path, directory: Path, day: date) -> Path:
    if not source.exists():
        raise BackupError(f"Baza topilmadi: {source}")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{_PREFIX}{day.isoformat()}{_SUFFIX}"
    temporary = directory / f".{target.name}.tmp"
    try:
        # backup() ishlab turgan bazadan ham izchil nusxa oladi, oddiy nusxalash olmaydi.
        with contextlib.closing(sqlite3.connect(source)) as origin:
            with contextlib.closing(sqlite3.connect(temporary)) as copy:
                origin.backup(copy)
                status = copy.execute("PRAGMA integrity_check").fetchone()[0]
        if status != "ok":
            raise BackupError(f"Nusxa buzilgan: {status}")
        with temporary.open("rb") as raw, gzip.open(target, "wb") as packed:
            shutil.copyfileobj(raw, packed)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def rotate(directory: Path, keep: int = KEEP_COPIES) -> list[Path]:
    copies = sorted(directory.glob(f"{_PREFIX}*{_SUFFIX}"), reverse=True)
    removed = copies[keep:]
    for path in removed:
        path.unlink()
    return removed


def main() -> None:
    settings = get_settings()
    directory = Path(settings.backup_dir)
    target = create_backup(sqlite_path(settings.database_url), directory, date.today())
    rotate(directory)
    print(f"Zaxira: {target}")


if __name__ == "__main__":
    main()

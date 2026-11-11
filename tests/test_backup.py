import gzip
import sqlite3
from datetime import date

import pytest

from app.backup import BackupError, create_backup, rotate, sqlite_path

DAY = date(2026, 3, 10)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "db.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("create table t (v text)")
    connection.execute("insert into t values ('qiymat')")
    connection.commit()
    connection.close()
    return path


def restore(backup, tmp_path):
    restored = tmp_path / "restored.sqlite"
    restored.write_bytes(gzip.decompress(backup.read_bytes()))
    connection = sqlite3.connect(restored)
    rows = connection.execute("select v from t").fetchall()
    connection.close()
    return rows


def test_backup_can_be_restored(database, tmp_path):
    backup = create_backup(database, tmp_path / "b", DAY)
    assert backup.name == "talababot-2026-03-10.db.gz"
    assert restore(backup, tmp_path) == [("qiymat",)]
    assert [p.name for p in (tmp_path / "b").iterdir()] == [backup.name]


def test_backup_sees_open_wal_database(database, tmp_path):
    writer = sqlite3.connect(database)
    writer.execute("pragma journal_mode=wal")
    writer.execute("insert into t values ('ikkinchi')")
    writer.commit()
    backup = create_backup(database, tmp_path / "b", DAY)
    writer.close()
    assert ("ikkinchi",) in restore(backup, tmp_path)


def test_missing_database_is_an_error(tmp_path):
    with pytest.raises(BackupError, match="topilmadi"):
        create_backup(tmp_path / "yoq.sqlite", tmp_path / "b", DAY)
    assert not (tmp_path / "yoq.sqlite").exists()


def test_rotation_keeps_newest(tmp_path):
    for day in range(1, 21):
        (tmp_path / f"talababot-2026-03-{day:02d}.db.gz").write_bytes(b"x")
    (tmp_path / "boshqa.txt").write_bytes(b"x")
    removed = rotate(tmp_path, keep=14)
    assert len(removed) == 6
    assert (tmp_path / "talababot-2026-03-20.db.gz").exists()
    assert not (tmp_path / "talababot-2026-03-06.db.gz").exists()
    assert (tmp_path / "boshqa.txt").exists()


def test_sqlite_path():
    assert sqlite_path("sqlite:///./talababot.db").name == "talababot.db"


@pytest.mark.parametrize("url", ["sqlite://", "postgresql://u@h/d"])
def test_unsupported_urls(url):
    with pytest.raises(BackupError):
        sqlite_path(url)

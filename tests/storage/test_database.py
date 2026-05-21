import sqlite3
from pathlib import Path

import pytest

from ota_core.storage import Database


def test_file_database_enables_wal(tmp_path: Path) -> None:
    with Database(tmp_path / "state.db") as db:
        conn = db.connect()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert mode == "wal"
    assert sync == 1
    assert fk == 1
    assert busy == 5000


def test_memory_database_skips_wal_but_keeps_other_pragmas() -> None:
    with Database(":memory:") as db:
        conn = db.connect()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]

    assert mode == "memory"
    assert fk == 1
    assert busy == 5000


def test_parent_directory_auto_created(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "state.db"
    assert not db_path.parent.exists()

    with Database(db_path) as db:
        db.connect()

    assert db_path.exists()
    assert db_path.parent.is_dir()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    with Database(tmp_path / "state.db") as db:
        with db.transaction() as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")
        with db.transaction() as conn:
            conn.execute("INSERT INTO t (v) VALUES (?)", (42,))
        rows = db.connect().execute("SELECT v FROM t").fetchall()

    assert [row["v"] for row in rows] == [42]


def _raise_inside_transaction(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO t (v) VALUES (?)", (1,))
        raise RuntimeError("boom")


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    with Database(tmp_path / "state.db") as db:
        with db.transaction() as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v INTEGER)")

        with pytest.raises(RuntimeError, match="boom"):
            _raise_inside_transaction(db)

        rows = db.connect().execute("SELECT v FROM t").fetchall()

    assert rows == []


def _insert_orphan_child(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")


def test_foreign_keys_enforced(tmp_path: Path) -> None:
    with Database(tmp_path / "state.db") as db:
        with db.transaction() as conn:
            conn.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            conn.execute(
                "CREATE TABLE child ("
                "  id INTEGER PRIMARY KEY,"
                "  parent_id INTEGER REFERENCES parent(id)"
                ")"
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_orphan_child(db)

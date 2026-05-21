from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_IN_MEMORY = ":memory:"


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path: Path | str = path if path == _IN_MEMORY else Path(path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn

        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = str(self.path)
        else:
            target = self.path

        conn = sqlite3.connect(
            target,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        self._apply_pragmas(conn)
        self._conn = conn
        return conn

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")

        if self.path == _IN_MEMORY:
            return

        result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        actual_mode = result[0].lower() if result else ""
        if actual_mode != "wal":
            raise RuntimeError(
                f"failed to enable WAL on {self.path!r}; journal_mode={actual_mode!r}"
            )
        conn.execute("PRAGMA synchronous=NORMAL")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ota_core.storage.database import Database

_TRACKING_TABLE = "_schema_migrations"


@dataclass(frozen=True)
class Migration:
    name: str
    statements: tuple[str, ...]


def _ensure_tracking_table(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_TRACKING_TABLE} ("
            "  name TEXT PRIMARY KEY,"
            "  applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))"
            ")"
        )


def applied_migrations(db: Database) -> set[str]:
    _ensure_tracking_table(db)
    conn = db.connect()
    rows = conn.execute(f"SELECT name FROM {_TRACKING_TABLE}").fetchall()
    return {row["name"] for row in rows}


def apply_pending(db: Database, migrations: Iterable[Migration]) -> list[str]:
    _ensure_tracking_table(db)
    already = applied_migrations(db)
    applied: list[str] = []
    for migration in migrations:
        if migration.name in already:
            continue
        with db.transaction() as conn:
            for stmt in migration.statements:
                conn.execute(stmt)
            conn.execute(
                f"INSERT INTO {_TRACKING_TABLE} (name) VALUES (?)",
                (migration.name,),
            )
        applied.append(migration.name)
    return applied

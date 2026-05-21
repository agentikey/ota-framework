from ota_core.storage import Database, Migration, applied_migrations, apply_pending


def test_apply_pending_runs_each_migration_once() -> None:
    migrations = [
        Migration(
            name="0001_create_widgets",
            statements=("CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",),
        ),
        Migration(
            name="0002_add_widget_color",
            statements=("ALTER TABLE widgets ADD COLUMN color TEXT",),
        ),
    ]
    with Database(":memory:") as db:
        first = apply_pending(db, migrations)
        second = apply_pending(db, migrations)

        assert first == ["0001_create_widgets", "0002_add_widget_color"]
        assert second == []
        assert applied_migrations(db) == {
            "0001_create_widgets",
            "0002_add_widget_color",
        }

        cols = {row["name"] for row in db.connect().execute("PRAGMA table_info(widgets)")}
        assert cols == {"id", "name", "color"}


def test_apply_pending_is_atomic_per_migration() -> None:
    failing = Migration(
        name="0001_bad",
        statements=(
            "CREATE TABLE good (id INTEGER PRIMARY KEY)",
            "CREATE TABLE good (id INTEGER PRIMARY KEY)",
        ),
    )
    with Database(":memory:") as db:
        try:
            apply_pending(db, [failing])
        except Exception:
            pass

        assert applied_migrations(db) == set()
        tables = {
            row["name"]
            for row in db.connect().execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '_%'"
            )
        }
        assert "good" not in tables

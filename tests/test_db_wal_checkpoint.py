from __future__ import annotations

from database.db_manager import DBManager


def test_close_runs_after_wal_write_and_clears_connections(tmp_path):
    db_path = tmp_path / "checkpoint_test.db"
    manager = DBManager(str(db_path))

    manager.conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
    manager.conn.execute("INSERT INTO sample (value) VALUES (?)", ("ok",))
    manager.conn.commit()

    assert manager._connections
    manager.close()

    assert manager._connections == {}
    assert manager._local.conn is None

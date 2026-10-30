"""Clear this application's local database and uploads; preserve schema/configuration.

Stop this workspace's API and worker first. Run with --confirm-reset.
"""
import argparse
from pathlib import Path
import sqlite3
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from app.config import Settings
from app.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-reset", action="store_true", required=True)
    parser.parse_args()
    data_dir = (root / "backend/data").resolve()
    store = Store(Settings(data_dir=data_dir))
    uploads = store.settings.uploads_dir.resolve()
    assert uploads.parent == data_dir and store.settings.db_path.resolve().parent == data_dir
    files = list(uploads.iterdir())
    for path in files:
        if not path.is_file() or path.is_symlink() or path.resolve().parent != uploads:
            raise RuntimeError("Unexpected upload path; reset stopped without deleting database content.")
    with sqlite3.connect(store.settings.db_path, timeout=20) as db:
        db.execute("PRAGMA foreign_keys=OFF")
        db.execute("PRAGMA secure_delete=ON")
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        db.execute("BEGIN IMMEDIATE")
        for table in tables:
            db.execute('DELETE FROM "' + table.replace('"', '""') + '"')
        db.commit()
        assert all(db.execute('SELECT count(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0] == 0 for table in tables)
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("VACUUM")
    for path in files:
        path.unlink()
    print({"database_tables_cleared": len(tables), "remaining_rows": 0, "uploaded_files_removed": len(files)})


if __name__ == "__main__":
    main()

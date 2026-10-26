"""SQLite store: import-settings region and migration of old databases."""

import os
import sqlite3

from utils import db


def test_import_settings_round_trip_region():
    db.save_import_settings("src-org", "key", "api.eu")
    assert db.load_import_settings() == {
        "org_short_name": "src-org",
        "api_key": "key",
        "api_region": "api.eu",
    }


def test_old_database_gains_the_region_column():
    path = os.path.join(db.get_data_dir(), "vcommander.db")
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE IF EXISTS import_settings")
    conn.execute(
        "CREATE TABLE import_settings "
        "(id INTEGER PRIMARY KEY DEFAULT 1, org_short_name TEXT, api_key TEXT)"
    )
    conn.execute("INSERT INTO import_settings VALUES (1, 'old-org', 'old-key')")
    conn.commit()
    conn.close()

    settings = db.load_import_settings()
    assert settings["org_short_name"] == "old-org"
    assert settings["api_region"] == "api"

import os
import sqlite3
import sys


def get_data_dir() -> str:
    """Return the platform-appropriate per-user data directory, creating it
    if it doesn't exist.

    macOS:   ~/Library/Application Support/vCommander
    Windows: %APPDATA%/vCommander  (falls back to ~/vCommander)
    Linux:   $XDG_DATA_HOME/vCommander  (falls back to ~/.local/share/vCommander)
    """
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    data_dir = os.path.join(base, "vCommander")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _get_connection() -> sqlite3.Connection:
    """Open a SQLite connection and ensure the schema exists.

    The CREATE TABLE IF NOT EXISTS calls are cheap (SQLite caches the catalog),
    so running them per-connection is simpler than maintaining a one-time
    init flag.
    """
    db_path = os.path.join(get_data_dir(), "vcommander.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # api_region default is 'api' to match the dropdown options in
    # login_view.py: ('api', 'api.eu', 'api.au'). The previous default 'us'
    # didn't appear in the dropdown and would have desynced the UI.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS credentials (
            id INTEGER PRIMARY KEY DEFAULT 1,
            email TEXT,
            password TEXT,
            org_short_name TEXT,
            api_region TEXT DEFAULT 'api',
            shard TEXT DEFAULT ''
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS import_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            org_short_name TEXT,
            api_key TEXT
        )"""
    )
    conn.commit()
    return conn


def save_credentials(
    email: str, password: str, org_short_name: str, api_region: str, shard: str
):
    """Persist the login credentials, replacing any previous row.

    Uses INSERT OR REPLACE to avoid the brief empty-table window that
    DELETE-then-INSERT would create if interrupted between statements.
    """
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO credentials
               (id, email, password, org_short_name, api_region, shard)
               VALUES (1, ?, ?, ?, ?, ?)""",
            (email, password, org_short_name, api_region, shard),
        )
        conn.commit()
    finally:
        conn.close()


def load_credentials() -> dict | None:
    """Return the saved credential row as a dict, or None if not yet saved."""
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM credentials WHERE id = 1").fetchone()
        if row:
            return {
                "email": row["email"],
                "password": row["password"],
                "org_short_name": row["org_short_name"],
                "api_region": row["api_region"],
                "shard": row["shard"],
            }
        return None
    finally:
        conn.close()


def save_import_settings(org_short_name: str, api_key: str):
    """Persist the external-org connection settings, replacing any previous row."""
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO import_settings
               (id, org_short_name, api_key)
               VALUES (1, ?, ?)""",
            (org_short_name, api_key),
        )
        conn.commit()
    finally:
        conn.close()


def load_import_settings() -> dict | None:
    """Return the saved import settings row as a dict, or None if not yet saved."""
    conn = _get_connection()
    try:
        row = conn.execute("SELECT * FROM import_settings WHERE id = 1").fetchone()
        if row:
            return {
                "org_short_name": row["org_short_name"],
                "api_key": row["api_key"],
            }
        return None
    finally:
        conn.close()

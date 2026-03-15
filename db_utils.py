import sqlite3

from .app_utils import get_app_data_dir

DB_FILE = get_app_data_dir() / "system_data.db"


def initialize_db():
    with sqlite3.connect(str(DB_FILE)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                password TEXT,
                api_type TEXT,
                region TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT,
                last_name TEXT,
                email TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS import_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_short_name TEXT,
                api_key TEXT
            )
        """)
        conn.commit()


def save_connection_data(email, password, api_type, region):
    with sqlite3.connect(str(DB_FILE)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM credentials;
        """)
        cursor.execute(
            """
            INSERT INTO credentials (email, password, api_type, region)
            VALUES (?, ?, ?, ?)
        """,
            (email, password, api_type, region),
        )
        conn.commit()


def get_connection_data():
    with sqlite3.connect(str(DB_FILE)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT email, password, api_type, region FROM credentials;
        """)
        return cursor.fetchone()

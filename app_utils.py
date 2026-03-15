import platform
from pathlib import Path

from constants import APP_NAME


def get_app_data_dir() -> Path:
    """Gets the secure local app data directory based on the OS."""
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        app_dir = home / "Library" / "Application Support" / APP_NAME
    elif system == "Windows":
        app_dir = home / "AppData" / "Local" / APP_NAME
    else:
        app_dir = home / ".config" / APP_NAME

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

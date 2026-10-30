"""Shared fixtures.

The app writes its SQLite DB, prefs and API log under the per-user data
directory, resolved from HOME / XDG_DATA_HOME / APPDATA. Point all three at
a throwaway directory *before* any app module is imported so tests never
touch a developer's real credentials or log.
"""

import os
import sys
import tempfile
import warnings

_DATA_HOME = tempfile.mkdtemp(prefix="vcommander-tests-")
os.environ["HOME"] = _DATA_HOME
os.environ["XDG_DATA_HOME"] = os.path.join(_DATA_HOME, "xdg")
os.environ["APPDATA"] = os.path.join(_DATA_HOME, "appdata")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore", category=DeprecationWarning)

import pytest  # noqa: E402

import theme  # noqa: E402
from utils import session  # noqa: E402


class FakePage:
    """Just enough of ft.Page for views driven outside a running app."""

    def __init__(self):
        self.updates = 0
        self.dialogs = []

    def update(self, *controls):
        self.updates += 1

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        pass


class Event:
    def __init__(self, page, control=None):
        self.page = page
        self.control = control


@pytest.fixture
def page():
    return FakePage()


@pytest.fixture(autouse=True)
def _reset_state():
    """Each test starts logged out, in dark mode, with no registered run."""
    session.clear_session()
    session._active_run = None
    theme.set_theme_mode("dark")
    yield
    session.clear_session()
    session._active_run = None
    theme.set_theme_mode("dark")

"""Run/report progress primitives shared by Commission, Decommission and Users.

- `ProgressHeader`: a determinate-or-indeterminate bar with a live
  "x / y  ·  n failed" label, shown at the top of a run.
- `status_row`: one static icon+label line with a semantic state.
- `StepRow`: one *live* line — a spinner while its step runs, then a state
  icon and result text. `run_step` drives one off a blocking API call.
- `RawLogPanel`: a collapsible "View raw log" disclosure that pulls its
  text lazily (so the log keeps growing during the run).

Colors are looked up from `theme` when a row is drawn (never cached at
import), so rows built after a light/dark switch use the new palette.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import flet as ft

import theme
from utils.executor import _executor
from utils.logger import log_system

# state -> (icon, theme color token). Tokens are resolved at draw time.
_STATUS = {
    "done": (ft.Icons.CHECK_CIRCLE, "SUCCESS"),
    "failed": (ft.Icons.ERROR, "DANGER"),
    "cancelled": (ft.Icons.CANCEL, "WARNING"),
    "pending": (ft.Icons.SCHEDULE_ROUNDED, "TEXT_MUTED"),
    "partial": (ft.Icons.WARNING_AMBER_ROUNDED, "WARNING"),
}


def _status_style(state: str) -> tuple[str, str]:
    """(icon, color) for `state` in the active palette."""
    icon, token = _STATUS.get(state, (ft.Icons.CIRCLE, "TEXT_MUTED"))
    return icon, getattr(theme, token)


def status_row(state: str, label: str, *, detail: str | None = None) -> ft.Row:
    """A single icon + label line for a step/category result."""
    icon_name, color = _status_style(state)
    text = label if not detail else f"{label} — {detail}"
    text_color = color if state in ("failed", "cancelled") else theme.TEXT_SECONDARY
    return ft.Row(
        [
            ft.Icon(icon_name, color=color, size=18),
            ft.Text(text, color=text_color, size=theme.FONT_CAPTION, expand=True),
        ],
        spacing=theme.SPACE_SM,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


class StepRow(ft.Row):
    """A live progress line: spinner + label, then a result icon + text.

    `compact=True` is the smaller variant used for per-item rows nested in a
    category (decommission). Call one of `succeed` / `fail` / `warn` /
    `skip` to finish the row; the caller owns the following page.update().
    """

    def __init__(self, label: str, *, compact: bool = False):
        self._icon_size = 16 if compact else 18
        self._text = ft.Text(
            label, color=theme.TEXT_SECONDARY, size=12 if compact else 13
        )
        spinner = ft.ProgressRing(
            width=self._icon_size - 2,
            height=self._icon_size - 2,
            stroke_width=2,
            color=theme.TEXT_SECONDARY,
        )
        super().__init__([spinner, self._text], spacing=8 if compact else 10)

    @property
    def text(self) -> str:
        return self._text.value

    def _finish(self, state: str, text: str) -> None:
        icon, color = _status_style(state)
        self.controls[0] = ft.Icon(icon, color=color, size=self._icon_size)
        self._text.value = text
        self._text.color = color

    def succeed(self, text: str) -> None:
        self._finish("done", text)

    def fail(self, text: str) -> None:
        self._finish("failed", text)

    def warn(self, text: str) -> None:
        self._finish("partial", text)

    def skip(self, text: str) -> None:
        self._finish("cancelled", text)


async def run_step(
    page,
    column: ft.Column,
    label: str,
    fn: Callable[..., Any],
    *args,
    success_text: str | None = None,
    failure_text: str | None = None,
    compact: bool = False,
) -> tuple[bool, Any, Exception | None]:
    """Append a StepRow to `column`, run `fn(*args)` off the UI loop, settle it.

    The row reads "<label>..." while running, then `success_text` (default
    "<label> — done") or "<failure_text> — <error>" (default
    "<label> — failed: <error>").

    Returns (ok, result, error): `result` is None and `error` is the raised
    exception when the call failed. Never raises for a failed call — the
    caller decides whether a failure stops its flow.
    """
    row = StepRow(f"{label}...", compact=compact)
    column.controls.append(row)
    page.update()
    await asyncio.sleep(0)
    try:
        result = await asyncio.get_running_loop().run_in_executor(
            _executor, fn, *args
        )
    except Exception as ex:
        # Logged so a failed step shows up in the terminal and api_calls.log,
        # not only in its progress row.
        log_system(f"{label} failed: {ex}", level="ERROR")
        row.fail(
            f"{failure_text} — {ex}" if failure_text else f"{label} — failed: {ex}"
        )
        page.update()
        return False, None, ex
    row.succeed(success_text or f"{label} — done")
    page.update()
    return True, result, None


class ProgressHeader(ft.Container):
    """A progress bar + live counts label.

    `determinate=True` drives the bar from done/total (use when the total is
    known up front, e.g. decommission's asset count); otherwise the bar runs
    indeterminate and the label just reports running counts.
    """

    def __init__(self, *, determinate: bool = False):
        super().__init__(padding=ft.Padding.only(bottom=theme.SPACE_MD))
        self._determinate = determinate
        self._bar = ft.ProgressBar(
            value=0.0 if determinate else None,
            color=theme.ACCENT,
            bgcolor=theme.SURFACE_VARIANT,
            bar_height=6,
            border_radius=theme.RADIUS_PILL,
        )
        self._label = ft.Text(
            "Starting…", size=theme.FONT_CAPTION, color=theme.TEXT_SECONDARY
        )
        self.content = ft.Column([self._label, self._bar], spacing=theme.SPACE_SM)

    @property
    def label(self) -> str:
        return self._label.value

    def set_progress(
        self,
        done: int,
        total: int | None = None,
        failed: int = 0,
        *,
        prefix: str | None = None,
    ):
        parts = [prefix] if prefix else []
        parts.append(f"{done} / {total}" if total is not None else f"{done} done")
        if failed:
            parts.append(f"{failed} failed")
        self._label.value = "   ·   ".join(parts)
        self._label.color = theme.DANGER if failed else theme.TEXT_SECONDARY
        if self._determinate:
            self._bar.value = min(1.0, done / total) if total else 1.0

    def complete(self, *, color: str | None = None):
        """Fill the bar and optionally tint it (success/warning/danger)."""
        self._bar.value = 1.0
        if color:
            self._bar.color = color


class RawLogPanel(ft.Column):
    """Collapsible 'View raw log' disclosure backed by a text provider."""

    def __init__(self, get_text: Callable[[], str]):
        super().__init__(spacing=theme.SPACE_SM)
        self._get_text = get_text
        self._body = ft.Container(
            visible=False,
            bgcolor=theme.SURFACE_VARIANT,
            border_radius=theme.RADIUS_MD,
            padding=ft.Padding.all(theme.SPACE_MD),
            content=ft.Text(
                "",
                font_family=theme.FONT_MONO,
                size=theme.FONT_CAPTION,
                color=theme.TEXT_SECONDARY,
                selectable=True,
            ),
        )
        self._chevron = ft.Icon(
            ft.Icons.CHEVRON_RIGHT, size=18, color=theme.TEXT_SECONDARY
        )
        self._toggle_label = ft.Text(
            "View raw log", color=theme.TEXT_SECONDARY, size=theme.FONT_CAPTION
        )
        self._toggle = ft.TextButton(
            content=ft.Row(
                [self._chevron, self._toggle_label],
                spacing=theme.SPACE_XS,
                tight=True,
            ),
            on_click=self._on_toggle,
        )
        self.controls = [self._toggle, self._body]

    def _on_toggle(self, e):
        visible = not self._body.visible
        self._body.visible = visible
        self._body.content.value = self._get_text()
        self._chevron.name = (
            ft.Icons.EXPAND_MORE if visible else ft.Icons.CHEVRON_RIGHT
        )
        self._toggle_label.value = "Hide raw log" if visible else "View raw log"
        e.page.update()

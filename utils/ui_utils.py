import flet as ft

import theme
from components.surfaces import kind_style


def show_toast(
    page: ft.Page,
    message: str,
    *,
    kind: str = "info",
    duration_ms: int = 3000,
):
    """Show a non-blocking bottom-center toast (Flet SnackBar).

    Use for outcomes the user doesn't need to acknowledge — exports
    completed, items copied, validation hints. Reserve `show_alert` for
    blocking confirmations and fatal errors the user must dismiss.

    `kind` (info / success / warning / error) picks the leading icon and its
    color. The toast itself stays on a neutral surface so the message text
    keeps full contrast in both light and dark themes.
    """
    color, icon = kind_style("danger" if kind == "error" else kind)
    snack = ft.SnackBar(
        content=ft.Row(
            [
                ft.Icon(icon, color=color, size=18),
                ft.Text(message, color=theme.TEXT_PRIMARY, expand=True),
            ],
            spacing=theme.SPACE_MD,
        ),
        bgcolor=theme.SURFACE_VARIANT,
        duration=duration_ms,
        behavior=ft.SnackBarBehavior.FLOATING,
        show_close_icon=True,
        close_icon_color=theme.TEXT_SECONDARY,
    )
    # Flet 0.85 shows transient overlays (snackbars, dialogs, pickers) via
    # page.show_dialog(); the older page.open()/overlay-append pattern is gone.
    page.show_dialog(snack)


def show_alert(page: ft.Page, title: str, message: str):
    """Display a modal alert dialog with an OK button.

    Uses Flet's `page.show_dialog(dialog)` / `page.pop_dialog()` API. The
    older `page.overlay.append + dialog.open = True` pattern still appears
    to show the dialog but doesn't reliably dismiss it on click in current
    Flet versions.
    """

    def close_dialog(_e=None):
        page.pop_dialog()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[ft.TextButton("OK", on_click=close_dialog)],
    )
    page.show_dialog(dialog)


def show_confirm(
    page: ft.Page,
    title: str,
    message: str,
    *,
    confirm_label: str,
    on_confirm,
    cancel_label: str = "Cancel",
):
    """Modal two-button dialog; `on_confirm()` runs only on the confirm choice."""

    def close(_e=None):
        page.pop_dialog()

    def confirm(_e=None):
        page.pop_dialog()
        on_confirm()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton(cancel_label, on_click=close),
            ft.TextButton(
                content=ft.Text(confirm_label, color=theme.DANGER),
                on_click=confirm,
            ),
        ],
    )
    page.show_dialog(dialog)

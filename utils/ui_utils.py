import flet as ft

from constants import BG, ERROR, SECONDARY, TEXT_PRIMARY, WARNING


def set_button_loading(
    btn: ft.ElevatedButton, loading: bool, label: str, auto_update: bool = True
):
    """Toggle an ElevatedButton between a loading-spinner state and a normal state.

    The non-loading content is restored with `weight=W_600` because that's the
    weight every button in the project is created with; without it, every
    failed login/connect/load round-trip would leave the button visibly less
    bold than its neighbors.
    """
    if loading:
        btn.content = ft.Row(
            [
                ft.ProgressRing(
                    width=16, height=16, stroke_width=2, color=TEXT_PRIMARY
                ),
                ft.Text(f"  {label}...", color=TEXT_PRIMARY),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )
        btn.disabled = True
    else:
        btn.content = ft.Text(label, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600)
        btn.disabled = False
    if auto_update:
        page = getattr(btn, "page", None)
        if page:
            page.update()


_TOAST_BG = {
    "info": None,        # default Flet SnackBar background
    "success": SECONDARY,
    "warning": WARNING,
    "error": ERROR,
}


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

    `kind` selects the accent color (info / success / warning / error).
    """
    bgcolor = _TOAST_BG.get(kind)
    snack = ft.SnackBar(
        content=ft.Text(message, color=TEXT_PRIMARY),
        bgcolor=bgcolor,
        duration=duration_ms,
        behavior=ft.SnackBarBehavior.FLOATING,
        show_close_icon=True,
    )
    # Newer Flet exposes `page.show_snack_bar`/`page.open()`; fall back to
    # the overlay-append pattern for older runtimes.
    if hasattr(page, "open"):
        page.open(snack)
    else:
        page.overlay.append(snack)
        snack.open = True
        page.update()


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


def create_loading_overlay() -> ft.Container:
    """Build a translucent full-page loading overlay (initially hidden)."""
    return ft.Container(
        content=ft.Column(
            [
                ft.ProgressRing(color=TEXT_PRIMARY),
                ft.Text("Loading...", color=TEXT_PRIMARY, size=14),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=15,
        ),
        bgcolor=ft.Colors.with_opacity(0.7, BG),
        alignment=ft.Alignment(0, 0),
        visible=False,
        expand=True,
    )

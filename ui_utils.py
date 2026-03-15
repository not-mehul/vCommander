import flet as ft

from constants import BORDER_RADIUS, ERROR_COLOR, SUCCESS_COLOR, SURFACE_COLOR


def show_alert(page: ft.Page, message: str, is_error=True, is_breaking=False):
    color = ERROR_COLOR if is_error else SUCCESS_COLOR
    icon = ft.Icons.ERROR_OUTLINE if is_error else ft.Icons.CHECK_CIRCLE_OUTLINE
    if not is_breaking:
        snack_bar = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(icon, color=SURFACE_COLOR, size=20),
                    ft.Text(
                        message,
                        color=SURFACE_COLOR,
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            bgcolor=color,
            behavior=ft.SnackBarBehavior.FLOATING,
            duration=4000,
            margin=ft.margin.all(20),
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS),
        )
    else:
        snack_bar = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(icon, color=SURFACE_COLOR, size=20),
                    ft.Text(
                        message,
                        color=SURFACE_COLOR,
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            bgcolor=color,
            behavior=ft.SnackBarBehavior.FLOATING,
            margin=ft.margin.all(20),
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS),
        )
    page.overlay.append(snack_bar)
    snack_bar.open = True
    page.update()

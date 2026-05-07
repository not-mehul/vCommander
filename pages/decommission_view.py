import asyncio
import csv
import datetime
import os

import flet as ft

from apis.external_api import VerkadaExternalAPIClient
from constants import (
    ASSET_CATEGORIES,
    BG,
    BORDER,
    CARD_PADDING,
    CARD_SHADOW,
    DELETION_ORDER,
    ERROR,
    FIELD_SPACING,
    PAGE_PADDING,
    PRIMARY,
    SECONDARY,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)
from utils.executor import _executor
from utils.session import get_external_client, get_internal_client, set_external_client
from utils.ui_utils import set_button_loading, show_alert

# ---------------------------------------------------------------------------
# Category routing tables
# ---------------------------------------------------------------------------
# Every fetched asset is normalised to a dict with at least 'id' and 'name'
# keys, so we don't need to look up which keys a category uses — they're
# always 'id' and 'name'. The two maps below only describe the variable
# bit (which API method or slug to use).
#
# Categories not in either map are external-API categories that use the
# default get_<slug> getter (currently just "Guest Sites").

# Categories fetched via the internal API's get_object(slug)
_INTERNAL_FETCH_SLUGS = {
    "Sensors": "sensors",
    "Intercoms": "intercoms",
    "Desk Stations": "desk_stations",
    "Mailroom Sites": "mailroom_sites",
    "Command Connectors": "connectors",
    "Access Controllers": "access_controllers",
    "Alarm Devices": "alarm_devices",
    "Alarm Sites": "alarm_sites",
    "Unassigned Devices": "unassigned_devices",
}

# Categories fetched via a named getter on the external API client.
# (Categories not listed here AND not in _INTERNAL_FETCH_SLUGS use the
# special-case branches in _on_scan: "Command Users" excludes the admin,
# "Cameras" applies the intercom-serial filter.)
_EXTERNAL_GETTERS = {
    "Cameras": "get_cameras",
    "Guest Sites": "get_guest_sites",
}

# Categories deleted via the internal API's delete_object(slug, id)
_INTERNAL_DELETE_SLUGS = {
    "Cameras": "cameras",
    "Sensors": "sensors",
    "Desk Stations": "desk_stations",
    "Mailroom Sites": "mailroom_sites",
    "Command Connectors": "connectors",
    "Access Controllers": "access_controllers",
    "Guest Sites": "guest_sites",
    "Alarm Devices": "alarm_devices",
    "Alarm Sites": "alarm_sites",
    "Intercoms": "intercoms",
}

# Categories deleted via a named method on the external API client
_EXTERNAL_DELETERS = {
    "Command Users": "delete_access_user",
}

# State machine
SCAN = "scan"
REVIEW = "review"
SELECT = "select"
PROCESSING = "processing"
COMPLETE = "complete"


# ---------------------------------------------------------------------------
# Small UI factories
# ---------------------------------------------------------------------------


def _make_button(
    text: str,
    on_click,
    *,
    bgcolor: str = PRIMARY,
    height: int = 42,
    width: int | None = None,
    visible: bool = True,
) -> ft.ElevatedButton:
    """Build a styled ElevatedButton consistent with the rest of the app."""
    return ft.ElevatedButton(
        content=ft.Text(text, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
        bgcolor=bgcolor,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        height=height,
        width=width,
        visible=visible,
        on_click=on_click,
    )


def _section_heading(title: str, subtitle: str | None = None) -> list[ft.Control]:
    """Title/subtitle pair shown at the top of each state's content area."""
    out: list[ft.Control] = [
        ft.Text(title, size=18, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
    ]
    if subtitle:
        out.append(ft.Text(subtitle, size=13, color=TEXT_SECONDARY))
    out.append(ft.Container(height=10))
    return out


class DecommissionView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(
            route="/decommission", bgcolor=BG, padding=PAGE_PADDING, **kwargs
        )
        self.push_route = push_route
        self.pop_route = pop_route
        self._state = SCAN
        self._assets: dict[str, list[dict]] = {}
        self._selected_categories: dict[str, bool] = {}
        self._results: dict[str, tuple[int, int]] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # Top-level UI scaffolding
    # ------------------------------------------------------------------

    def _build_ui(self):
        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=TEXT_SECONDARY,
                    on_click=lambda _: self.push_route("/home"),
                ),
                ft.Text(
                    "Decommission Organization",
                    size=22,
                    color=TEXT_PRIMARY,
                    weight=ft.FontWeight.W_600,
                ),
            ],
        )

        self._content_area = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            scroll=ft.ScrollMode.ADAPTIVE,
            expand=True,
            spacing=FIELD_SPACING,
        )

        card = ft.Container(
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING),
            content=self._content_area,
            expand=True,
        )

        self.controls = [
            ft.Column([header, ft.Container(height=10), card], expand=True)
        ]

        self._render_state()

    def _render_state(self):
        self._content_area.controls.clear()
        if self._state == SCAN:
            self._render_scan()
        elif self._state == REVIEW:
            self._render_review()
        elif self._state == SELECT:
            self._render_select()
        elif self._state == PROCESSING:
            self._render_processing()
        elif self._state == COMPLETE:
            self._render_complete()

    # ------------------------------------------------------------------
    # SCAN state
    # ------------------------------------------------------------------

    def _render_scan(self):
        self._scan_btn = _make_button(
            "Scan Organization", self._on_scan, height=45, width=240
        )
        # Prep-step progress rows — populated by _on_scan during the
        # permission-elevation phase, then hidden when the scan loop starts.
        # Lives in the same Column as the scan button so the page composition
        # doesn't shift when prep starts.
        self._prep_progress = ft.Column(spacing=8, visible=False)
        self._content_area.controls = [
            ft.Container(height=30),
            ft.Column(
                [
                    ft.Icon(ft.Icons.SEARCH, size=48, color=PRIMARY),
                    ft.Container(height=10),
                    ft.Text(
                        "Scan Organization",
                        size=20,
                        color=TEXT_PRIMARY,
                        weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        f"Discover all assets across {len(ASSET_CATEGORIES)} categories for removal.",
                        size=13,
                        color=TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=20),
                    self._scan_btn,
                    ft.Container(height=15),
                    self._prep_progress,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ]

    async def _on_scan(self, e):
        set_button_loading(self._scan_btn, True, "Scanning")

        # Reveal the prep-step progress block from the scan layout so the
        # rows we append have somewhere to land.
        self._prep_progress.controls.clear()
        self._prep_progress.visible = True
        e.page.update()
        await asyncio.sleep(0)

        # Clear any stale data from a previous scan so a partial failure never
        # leaves the app in a mixed state.
        self._assets = {}

        try:
            client = get_internal_client()
            loop = asyncio.get_running_loop()

            # Generate a short-lived API key and initialize the external client.
            # The external client constructor handles the token exchange itself.
            api_key = await loop.run_in_executor(
                _executor, client.create_external_api_key
            )
            ext_client = await loop.run_in_executor(
                _executor,
                VerkadaExternalAPIClient,
                api_key,
                client.org_short_name,
            )
            set_external_client(ext_client)

            # Pre-scan permission elevation. Both calls grant the running
            # user the ability to see and delete site-scoped resources that
            # the standard org-admin role might not surface. Without these,
            # access controllers, alarm sites, and similar can be silently
            # missing from the scan results.
            #
            # Both elevations are intentionally NOT reverted afterwards —
            # the user expects to remain elevated for any follow-up admin
            # work after the decommission completes.
            await self._run_prep_step(
                e.page,
                loop,
                "Enabling Global Site Admin",
                client.enable_global_site_admin,
            )
            await self._run_prep_step(
                e.page,
                loop,
                "Granting Access System Admin",
                client.set_access_system_admin,
            )

            # client.session.close()

            # Fetch all categories — internal API for hardware device types,
            # external API for everything else.
            #
            # ASSET_CATEGORIES is ordered so Intercoms are scanned first; their
            # serial numbers are then used to exclude duplicate entries from
            # the Cameras and Access Controllers results (intercoms appear in
            # both endpoints' results, but should only be deleted once).
            #
            # Any fetch failure raises immediately; deletion is only reachable
            # after a fully successful scan.
            intercom_serials: set[str] = set()
            for category in ASSET_CATEGORIES:
                items = await self._scan_category(
                    loop, client, ext_client, category, intercom_serials
                )
                if category == "Intercoms":
                    intercom_serials = {
                        item["serial_number"]
                        for item in items
                        if item.get("serial_number")
                    }
                self._assets[category] = items

            self._state = REVIEW
            self._render_state()
            e.page.update()
        except Exception as ex:
            self._assets = {}
            set_button_loading(self._scan_btn, False, "Scan Organization")
            show_alert(e.page, "Scan Failed", str(ex))

    async def _run_prep_step(
        self, page, loop: asyncio.AbstractEventLoop, label: str, fn
    ) -> None:
        """Run a single prep step (sync callable) with spinner→check UI feedback.

        Mirrors the per-step idiom used by _delete_one and the commission
        view's _run_step. Re-raises on failure so _on_scan's except clause
        can show the alert and reset the button.
        """
        step_icon = ft.ProgressRing(
            width=14, height=14, stroke_width=2, color=TEXT_SECONDARY
        )
        step_text = ft.Text(f"{label}...", color=TEXT_SECONDARY, size=13)
        step_row = ft.Row([step_icon, step_text], spacing=8)
        self._prep_progress.controls.append(step_row)
        page.update()
        await asyncio.sleep(0)

        try:
            await loop.run_in_executor(_executor, fn)
            step_row.controls[0] = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=SECONDARY, size=16
            )
            step_text.value = f"{label} — done"
            step_text.color = SECONDARY
            page.update()
        except Exception:
            step_row.controls[0] = ft.Icon(ft.Icons.ERROR, color=ERROR, size=16)
            step_text.value = f"{label} — failed"
            step_text.color = ERROR
            page.update()
            raise

    async def _scan_category(
        self,
        loop: asyncio.AbstractEventLoop,
        client,
        ext_client,
        category: str,
        intercom_serials: set[str],
    ) -> list[dict]:
        """Fetch one category of assets, applying intercom dedup where needed."""
        try:
            if category in _INTERNAL_FETCH_SLUGS:
                slug = _INTERNAL_FETCH_SLUGS[category]
                items = await loop.run_in_executor(_executor, client.get_object, slug)
                # Access Controllers come back from the internal endpoint
                # with intercom devices mixed in; strip those by serial.
                if category == "Access Controllers" and intercom_serials:
                    items = [
                        item
                        for item in items
                        if item.get("serial_number") not in intercom_serials
                    ]
                return items

            if category == "Command Users":
                # Exclude the logged-in admin from the user list so the
                # decommission flow can't accidentally delete the running session.
                return await loop.run_in_executor(
                    _executor, ext_client.get_users, client.user_id, None
                )

            method_name = _EXTERNAL_GETTERS.get(category)
            if not method_name:
                # Defensive: a category in ASSET_CATEGORIES that isn't in
                # either lookup. Today this branch is unreachable, but
                # returning [] (instead of KeyError-ing) means a future
                # category added to ASSET_CATEGORIES without a routing
                # entry shows up as empty in REVIEW rather than crashing
                # the scan.
                return []
            getter = getattr(ext_client, method_name)
            items = await loop.run_in_executor(_executor, getter)

            # The external Cameras endpoint also returns intercoms; dedup.
            if category == "Cameras" and intercom_serials:
                items = [
                    item
                    for item in items
                    if item.get("serial_number") not in intercom_serials
                ]
            return items
        except Exception as ex:
            raise ConnectionError(f"Failed to scan {category}: {ex}") from ex

    # ------------------------------------------------------------------
    # REVIEW state
    # ------------------------------------------------------------------

    def _render_review(self):
        rows = []
        total = 0
        for category in ASSET_CATEGORIES:
            count = len(self._assets.get(category, []))
            total += count
            rows.append(
                ft.Row(
                    [
                        ft.Text(category, color=TEXT_PRIMARY, expand=True),
                        ft.Text(
                            str(count),
                            color=TEXT_SECONDARY,
                            text_align=ft.TextAlign.RIGHT,
                        ),
                    ],
                )
            )

        self._content_area.controls = [
            *_section_heading(
                "Assets Found",
                f"{total} total assets discovered across "
                f"{len(ASSET_CATEGORIES)} categories.",
            ),
            ft.Column(rows, spacing=8),
            ft.Container(height=15),
            _make_button("Select Assets to Remove", self._go_to_select),
        ]

    def _go_to_select(self, e):
        self._state = SELECT
        self._render_state()
        e.page.update()

    # ------------------------------------------------------------------
    # SELECT state
    # ------------------------------------------------------------------

    def _render_select(self):
        self._category_checkboxes: dict[str, ft.Checkbox] = {}
        tiles = []

        for category in ASSET_CATEGORIES:
            items = self._assets.get(category, [])
            if not items:
                continue

            cb = ft.Checkbox(
                value=True,
                active_color=PRIMARY,
                check_color=TEXT_PRIMARY,
            )
            self._category_checkboxes[category] = cb
            self._selected_categories.setdefault(category, True)

            def on_change(_e, cat=category, checkbox=cb):
                # cb.value is bool | None on flet's stubs; coalesce to bool
                # so _selected_categories stays cleanly typed.
                self._selected_categories[cat] = bool(checkbox.value)

            cb.on_change = on_change

            item_names = ft.Column(
                [
                    ft.Text(
                        f"  • {item.get('name', 'Unknown')}",
                        color=TEXT_SECONDARY,
                        size=12,
                    )
                    for item in items
                ],
                spacing=4,
            )

            tiles.append(
                ft.ExpansionTile(
                    title=ft.Row(
                        [cb, ft.Text(f"{category} ({len(items)})", color=TEXT_PRIMARY)]
                    ),
                    controls=[
                        ft.Container(
                            content=item_names,
                            padding=ft.padding.only(left=40, bottom=10),
                        )
                    ],
                    expanded=False,
                    tile_padding=ft.padding.symmetric(horizontal=10, vertical=5),
                )
            )

        self._delete_btn = _make_button(
            "Delete Selected", self._on_delete, bgcolor=ERROR
        )
        export_btn = ft.OutlinedButton(
            content=ft.Text(
                "Export Asset List (CSV)", color=PRIMARY, weight=ft.FontWeight.W_500
            ),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, PRIMARY),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            height=42,
            on_click=self._export_assets_csv,
        )

        self._content_area.controls = [
            *_section_heading(
                "Select Categories to Remove",
                "Expand categories to see individual assets. Uncheck to skip.",
            ),
            ft.Column(tiles, spacing=4),
            ft.Container(height=15),
            export_btn,
            ft.Container(height=8),
            self._delete_btn,
        ]

    def _export_assets_csv(self, e):
        downloads = os.path.expanduser("~/Downloads")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(downloads, f"vCommander_assets_{timestamp}.csv")
        rows = []
        for category in ASSET_CATEGORIES:
            for item in self._assets.get(category, []):
                rows.append(
                    {
                        "Category": category,
                        "Name": item.get("name", ""),
                        "ID": item.get("id", ""),
                    }
                )
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Category", "Name", "ID"])
                writer.writeheader()
                writer.writerows(rows)
            show_alert(
                e.page,
                "Export Complete",
                f"Saved {len(rows)} assets to:\n{filepath}",
            )
        except Exception as ex:
            show_alert(e.page, "Export Failed", str(ex))

    async def _on_delete(self, e):
        selected = [
            cat for cat, checked in self._selected_categories.items() if checked
        ]
        if not selected:
            show_alert(
                e.page,
                "No Selection",
                "Please select at least one category to delete.",
            )
            return

        self._state = PROCESSING
        self._render_state()
        e.page.update()
        await asyncio.sleep(0)
        await self._run_deletions(e.page, selected)

    # ------------------------------------------------------------------
    # PROCESSING state
    # ------------------------------------------------------------------

    def _render_processing(self):
        self._processing_column = ft.Column(spacing=8)
        self._content_area.controls = [
            *_section_heading(
                "Processing Deletions",
                "Deleting assets in dependency order...",
            ),
            self._processing_column,
        ]

    async def _run_deletions(self, page, selected_categories: list[str]):
        int_client = get_internal_client()
        ext_client = get_external_client()
        loop = asyncio.get_running_loop()
        self._results = {}

        # Iterate in the dependency-aware DELETION_ORDER so dependent objects
        # (e.g. cameras attached to access controllers) are removed before
        # their parents.
        for category in DELETION_ORDER:
            if category not in selected_categories:
                continue
            items = self._assets.get(category, [])
            if not items:
                continue

            # Section header for the category
            self._processing_column.controls.append(
                ft.Text(category, color=PRIMARY, size=14, weight=ft.FontWeight.W_600)
            )
            page.update()

            success = 0
            for item in items:
                if await self._delete_one(
                    page, loop, int_client, ext_client, category, item
                ):
                    success += 1

            self._results[category] = (success, len(items))

        self._state = COMPLETE
        self._render_complete()
        page.update()

    async def _delete_one(
        self,
        page,
        loop: asyncio.AbstractEventLoop,
        int_client,
        ext_client,
        category: str,
        item: dict,
    ) -> bool:
        """Delete a single item, updating its row in the processing column.

        Returns True on success.
        """
        # `or "unknown"` catches both missing keys and empty-string values;
        # the resulting label is harmless and the API call below would fail
        # anyway if the ID is genuinely empty.
        item_id = item.get("id") or "unknown"
        item_name = item.get("name") or item_id

        step_icon = ft.ProgressRing(
            width=14, height=14, stroke_width=2, color=TEXT_SECONDARY
        )
        step_text = ft.Text(f"  Deleting {item_name}...", color=TEXT_SECONDARY, size=12)
        step_row = ft.Row([step_icon, step_text], spacing=8)
        self._processing_column.controls.append(step_row)
        page.update()
        await asyncio.sleep(0)

        try:
            if category in _INTERNAL_DELETE_SLUGS:
                slug = _INTERNAL_DELETE_SLUGS[category]
                # alarm_sites needs both the response_site_id and the
                # parent site_id; everything else is a single string ID.
                if slug == "alarm_sites":
                    delete_id = [item.get("id"), item.get("site_id")]
                else:
                    delete_id = item_id
                await loop.run_in_executor(
                    _executor, int_client.delete_object, slug, delete_id
                )
            else:
                method_name = _EXTERNAL_DELETERS[category]
                delete_fn = getattr(ext_client, method_name)
                await loop.run_in_executor(_executor, delete_fn, item_id)

            step_row.controls[0] = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=SECONDARY, size=16
            )
            step_text.value = f"  Deleted {item_name}"
            step_text.color = SECONDARY
            page.update()
            return True
        except Exception as ex:
            step_row.controls[0] = ft.Icon(ft.Icons.ERROR, color=ERROR, size=16)
            step_text.value = f"  Failed: {item_name} — {ex}"
            step_text.color = ERROR
            page.update()
            return False

    # ------------------------------------------------------------------
    # COMPLETE state
    # ------------------------------------------------------------------

    def _render_complete(self):
        rows = []
        total_success = 0
        total_items = 0
        for category, (success, total) in self._results.items():
            total_success += success
            total_items += total
            all_ok = success == total
            rows.append(
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE if all_ok else ft.Icons.WARNING,
                            color=SECONDARY if all_ok else WARNING,
                            size=18,
                        ),
                        ft.Text(
                            f"{category}: {success}/{total} deleted",
                            color=TEXT_PRIMARY,
                            size=13,
                        ),
                    ],
                    spacing=10,
                )
            )

        overall_ok = total_success == total_items
        overall_color = SECONDARY if overall_ok else WARNING
        self._content_area.controls = [
            ft.Text(
                "Decommission Complete",
                size=18,
                color=overall_color,
                weight=ft.FontWeight.W_600,
            ),
            ft.Text(
                f"{total_success}/{total_items} total assets deleted successfully.",
                size=13,
                color=TEXT_SECONDARY,
            ),
            ft.Container(height=15),
            ft.Column(rows, spacing=8),
            ft.Container(height=20),
            _make_button(
                "Return to Home",
                lambda _: self.push_route("/home"),
                bgcolor=SECONDARY,
            ),
        ]

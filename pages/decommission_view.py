"""Decommission screen.

Lists every asset in the org grouped by ASSET_CATEGORIES, lets the
user select what to remove, and then deletes them in DELETION_ORDER
(both defined in constants.py). The order matters — e.g. intercoms
must be deleted before the cameras/access controllers they're paired
with, alarm devices before alarm sites, users before the hardware
they're tied to."""

import asyncio
import csv
import datetime
import os

import flet as ft

from apis.external_api import VerkadaExternalAPIClient
from constants import (
    _EXTERNAL_DELETERS,
    _EXTERNAL_GETTERS,
    _INTERNAL_DELETERS,
    _INTERNAL_GETTERS,
    ASSET_CATEGORIES,
    BG,
    BORDER,
    CARD_PADDING,
    CARD_SHADOW,
    CATEGORY_GROUPS,
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
from utils.cancellation import CancellationToken
from utils.executor import _executor
from utils.logger import log_system
from utils.session import get_external_client, get_internal_client, set_external_client
from utils.ui_utils import set_button_loading, show_alert, show_toast

# Reverse lookup: child category -> parent group name (built once from
# CATEGORY_GROUPS so the view can ask "which group does this belong to?").
_CATEGORY_TO_GROUP = {
    child: group for group, children in CATEGORY_GROUPS.items() for child in children
}


def _item_serial(item: dict) -> str | None:
    """Return the item's serial number if the scan surfaced one."""
    serial = item.get("serial_number")
    return serial or None


def _item_descriptor(item: dict, *, include_id: bool = True) -> str:
    """Human-readable one-liner for an asset: name · SN · id.

    Serial number is included only when present (sites, doors, floors and
    other logical objects don't have one); the object id is included by
    default so every row is traceable back to the API.
    """
    name = item.get("name") or item.get("id") or "Unknown"
    parts = [str(name)]
    serial = _item_serial(item)
    if serial:
        parts.append(f"SN {serial}")
    if include_id and item.get("id"):
        parts.append(f"id {item['id']}")
    return "  ·  ".join(parts)

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
        self._show_items: bool = False
        self._search_query: str = ""
        # Cooperative cancellation for the delete loop. Tested between
        # items; the in-flight delete is allowed to complete so we never
        # leave a half-deleted asset behind.
        self._cancel_token: CancellationToken | None = None
        self._cancelled_at: str | None = None
        # Per-category UI controls populated when PROCESSING renders, so
        # _delete_one can flip the status icon / counters without
        # appending to a global scrolling column.
        self._category_rows: dict[str, dict] = {}
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
                client.enable_access_admin,
            )

            # Serials that should be filtered out of the Cameras list:
            # Intercoms and Access Station Pros are both surfaced by the
            # camera endpoint, but their deletion lives on their own
            # categories. Without this filter, decommission tries to
            # delete the same device twice (and the second attempt fails
            # because it's already gone or uses the wrong endpoint).
            camera_dedup_serials: set[str] = set()
            for category in ASSET_CATEGORIES:
                items = await self._scan_category(
                    loop, client, ext_client, category, camera_dedup_serials
                )
                if category in ("Intercoms", "Access Station Pro"):
                    camera_dedup_serials |= {
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
        camera_dedup_serials: set[str],
    ) -> list[dict]:
        """Fetch one category of assets.

        camera_dedup_serials accumulates serials of devices (intercoms,
        Access Station Pros) that also appear in the Cameras / Access
        Controllers lists; we filter them out so the same device isn't
        deleted twice through different endpoints.
        """
        try:
            if category in _INTERNAL_GETTERS:
                getter = getattr(client, _INTERNAL_GETTERS[category])
                items = await loop.run_in_executor(_executor, getter)
                if category == "Access Controllers" and camera_dedup_serials:
                    items = [
                        item
                        for item in items
                        if item.get("serial_number") not in camera_dedup_serials
                    ]
                return items

            if category == "Command Users":
                return await loop.run_in_executor(
                    _executor, ext_client.get_users, client.user_id, None
                )

            method_name = _EXTERNAL_GETTERS.get(category)
            if not method_name:
                return []
            getter = getattr(ext_client, method_name)
            items = await loop.run_in_executor(_executor, getter)

            # The external Cameras endpoint also returns intercoms and
            # Access Station Pros; dedup so they're only deleted once.
            if category == "Cameras" and camera_dedup_serials:
                items = [
                    item
                    for item in items
                    if item.get("serial_number") not in camera_dedup_serials
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
        self._group_checkboxes: dict[str, ft.Checkbox] = {}
        # Per-category title Text — updated by _refresh_category_label so
        # the "(N selected / M)" chip stays live as checkboxes change.
        self._category_titles: dict[str, ft.Text] = {}
        self._group_titles: dict[str, ft.Text] = {}
        tiles = []
        rendered_groups: set[str] = set()

        for category in ASSET_CATEGORIES:
            group = _CATEGORY_TO_GROUP.get(category)
            if group:
                # Render the whole group once, at its first child's position;
                # _build_group_tile handles all of the group's children.
                if group in rendered_groups:
                    continue
                rendered_groups.add(group)
                group_tile = self._build_group_tile(group)
                if group_tile:
                    tiles.append(group_tile)
                continue

            items = self._assets.get(category, [])
            if not items:
                continue
            tiles.append(self._build_leaf_tile(category, items))

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

        # Top bar: Select all / Select none / live search + "Show items".
        select_all_btn = ft.TextButton(
            content=ft.Text("Select all", color=PRIMARY, size=13),
            on_click=lambda e: self._bulk_select(e.page, value=True),
        )
        select_none_btn = ft.TextButton(
            content=ft.Text("Select none", color=PRIMARY, size=13),
            on_click=lambda e: self._bulk_select(e.page, value=False),
        )
        search_field = ft.TextField(
            hint_text="Search by name or serial",
            value=self._search_query,
            prefix_icon=ft.Icons.SEARCH,
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            content_padding=ft.padding.symmetric(horizontal=10, vertical=8),
            on_change=self._on_search_change,
            expand=True,
        )
        show_items_switch = ft.Switch(
            value=self._show_items,
            active_color=PRIMARY,
            on_change=self._on_show_items_change,
        )
        top_bar = ft.Row(
            [
                select_all_btn,
                select_none_btn,
                ft.Container(width=10),
                search_field,
                ft.Container(width=10),
                ft.Text("Show items", color=TEXT_SECONDARY, size=12),
                show_items_switch,
            ],
            spacing=4,
        )

        self._content_area.controls = [
            *_section_heading(
                "Select Categories to Remove",
                "Uncheck a category to skip. Toggle Show items to inspect "
                "individual assets.",
            ),
            top_bar,
            ft.Container(height=10),
            ft.Column(tiles, spacing=4),
            ft.Container(height=15),
            export_btn,
            ft.Container(height=8),
            self._delete_btn,
        ]
        # First render: sync every header label so counts are populated
        # before any user interaction. Page update happens via the parent
        # caller's e.page.update() in _render_state.
        for cat in self._category_checkboxes:
            self._refresh_category_label(cat)
        for grp in self._group_checkboxes:
            self._refresh_group_label(grp)

    def _build_leaf_tile(self, category: str, items: list[dict]) -> ft.Control:
        """Build a single category's row: checkbox + live "N / M" title.

        The expandable item list is mounted only when `self._show_items`
        is on; otherwise the row collapses to a single line. The item
        list itself filters live by `self._search_query`.
        """
        # Default to selected on first render; preserve prior selection
        # on re-renders triggered by the search / show-items toggle.
        selected = self._selected_categories.get(category, True)
        cb = ft.Checkbox(
            value=selected, active_color=PRIMARY, check_color=TEXT_PRIMARY
        )
        self._category_checkboxes[category] = cb
        self._selected_categories[category] = selected
        group = _CATEGORY_TO_GROUP.get(category)

        title_text = ft.Text("", color=TEXT_PRIMARY)
        self._category_titles[category] = title_text

        def on_change(e, cat=category, checkbox=cb, grp=group):
            self._selected_categories[cat] = bool(checkbox.value)
            self._refresh_category_label(cat)
            if grp:
                self._refresh_parent(grp)
                self._refresh_group_label(grp)
            e.page.update()

        cb.on_change = on_change

        if self._show_items:
            visible_items = self._filter_items(items)
            item_names = ft.Column(
                [
                    ft.Text(
                        f"  • {_item_descriptor(item)}",
                        color=TEXT_SECONDARY,
                        size=12,
                    )
                    for item in visible_items
                ]
                or [
                    ft.Text(
                        "  (no matches)" if self._search_query else "  (empty)",
                        color=TEXT_SECONDARY,
                        italic=True,
                        size=12,
                    )
                ],
                spacing=4,
            )
            return ft.ExpansionTile(
                title=ft.Row([cb, title_text]),
                controls=[
                    ft.Container(
                        content=item_names,
                        padding=ft.padding.only(left=40, bottom=10),
                    )
                ],
                expanded=False,
                tile_padding=ft.padding.symmetric(horizontal=10, vertical=5),
            )

        # Compact mode: no expansion, just one line per category.
        return ft.Container(
            content=ft.Row([cb, title_text]),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )

    def _build_group_tile(self, group: str) -> ft.ExpansionTile | None:
        """Build a parent tile for a group (Access Control / Alarms).

        The parent checkbox toggles every non-empty child at once and shows
        an indeterminate state when only some children are selected. Returns
        None when the group has no scanned assets (nothing to show).
        """
        child_tiles = []
        for child in CATEGORY_GROUPS[group]:
            items = self._assets.get(child, [])
            if not items:
                continue
            child_tiles.append(self._build_leaf_tile(child, items))

        if not child_tiles:
            return None

        parent_cb = ft.Checkbox(
            # Initial value gets corrected by _refresh_parent below once
            # the children are registered; tristate lets us show "mixed".
            value=True,
            tristate=True,
            active_color=PRIMARY,
            check_color=TEXT_PRIMARY,
        )
        self._group_checkboxes[group] = parent_cb
        # Sync to children we just registered, in case re-rendering hit a
        # state where some are unchecked.
        self._refresh_parent(group)
        title_text = ft.Text(
            "", color=TEXT_PRIMARY, weight=ft.FontWeight.W_600
        )
        self._group_titles[group] = title_text

        def on_parent_change(e, grp=group):
            present = [
                c for c in CATEGORY_GROUPS[grp] if c in self._category_checkboxes
            ]
            # Click semantics: if everything is already on, turn the group
            # off; otherwise turn it all on. (Avoids the confusing tristate
            # cycle for a bulk toggle.)
            all_on = all(self._selected_categories.get(c) for c in present)
            target = not all_on
            for c in present:
                self._category_checkboxes[c].value = target
                self._selected_categories[c] = target
                self._refresh_category_label(c)
            self._refresh_parent(grp)
            self._refresh_group_label(grp)
            e.page.update()

        parent_cb.on_change = on_parent_change

        return ft.ExpansionTile(
            title=ft.Row([parent_cb, title_text]),
            controls=[
                ft.Container(
                    content=ft.Column(child_tiles, spacing=2),
                    padding=ft.padding.only(left=20),
                )
            ],
            # Default expanded so the inner per-category counts are visible
            # without an extra click; users can collapse if they want.
            expanded=True,
            tile_padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )

    def _refresh_parent(self, group: str) -> None:
        """Sync a group's parent checkbox to its children (on/off/mixed)."""
        cb = self._group_checkboxes.get(group)
        if cb is None:
            return
        present = [c for c in CATEGORY_GROUPS[group] if c in self._category_checkboxes]
        values = [bool(self._selected_categories.get(c)) for c in present]
        if values and all(values):
            cb.value = True
        elif not any(values):
            cb.value = False
        else:
            cb.value = None  # indeterminate — some children selected

    # ------------------------------------------------------------------
    # SELECT top-bar helpers (live count chips, bulk select, search,
    # show-items toggle).
    # ------------------------------------------------------------------

    def _refresh_category_label(self, category: str) -> None:
        """Update a leaf's title to reflect "N selected / M total"."""
        title = self._category_titles.get(category)
        if title is None:
            return
        total = len(self._assets.get(category, []))
        selected = total if self._selected_categories.get(category) else 0
        title.value = f"{category}  ({selected} / {total})"

    def _refresh_group_label(self, group: str) -> None:
        """Update a parent group's title to "N selected / M total"."""
        title = self._group_titles.get(group)
        if title is None:
            return
        present = [c for c in CATEGORY_GROUPS[group] if c in self._category_checkboxes]
        total = sum(len(self._assets.get(c, [])) for c in present)
        selected = sum(
            len(self._assets.get(c, []))
            for c in present
            if self._selected_categories.get(c)
        )
        title.value = f"{group}  ({selected} / {total})"

    def _bulk_select(self, page, *, value: bool) -> None:
        """Top-bar Select all / Select none."""
        for cat, cb in self._category_checkboxes.items():
            cb.value = value
            self._selected_categories[cat] = value
            self._refresh_category_label(cat)
        for grp, cb in self._group_checkboxes.items():
            cb.value = value
            self._refresh_group_label(grp)
        page.update()

    def _on_search_change(self, e) -> None:
        self._search_query = (e.control.value or "").strip().lower()
        # Item-list re-render only matters in show-items mode; in compact
        # mode there is no per-item list to filter.
        if self._show_items:
            self._render_state()
            e.page.update()

    def _on_show_items_change(self, e) -> None:
        self._show_items = bool(e.control.value)
        self._render_state()
        e.page.update()

    def _filter_items(self, items: list[dict]) -> list[dict]:
        """Apply the current search query to an item list (name OR serial)."""
        if not self._search_query:
            return items
        q = self._search_query
        out = []
        for item in items:
            name = (item.get("name") or "").lower()
            serial = (item.get("serial_number") or "").lower()
            if q in name or q in serial:
                out.append(item)
        return out

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
                        "Serial Number": _item_serial(item) or "",
                        "ID": item.get("id", ""),
                    }
                )
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["Category", "Name", "Serial Number", "ID"]
                )
                writer.writeheader()
                writer.writerows(rows)
            show_toast(
                e.page,
                f"Exported {len(rows)} assets to {filepath}",
                kind="success",
                duration_ms=4000,
            )
        except Exception as ex:
            show_alert(e.page, "Export Failed", str(ex))

    async def _on_delete(self, e):
        selected = [
            cat for cat, checked in self._selected_categories.items() if checked
        ]
        if not selected:
            show_toast(
                e.page,
                "Please select at least one category to delete.",
                kind="warning",
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

    # ------------------------------------------------------------------
    # PROCESSING state — one collapsible row per category with a live
    # status icon, "n/m deleted" chip, and an items column populated as
    # each delete completes. Cancel sets a token; the loop bails after
    # the current item finishes (in-flight HTTP is allowed to complete).
    # ------------------------------------------------------------------

    def _build_category_row(self, category: str, total: int) -> dict:
        """Build a per-category row for the PROCESSING view.

        Returns the dict of mutable controls stored in self._category_rows
        so _delete_one can flip the icon / counters / append child items
        without rebuilding the row.
        """
        icon = ft.Icon(ft.Icons.SCHEDULE, color=TEXT_SECONDARY, size=18)
        title = ft.Text(
            f"{category}",
            color=TEXT_PRIMARY,
            size=14,
            weight=ft.FontWeight.W_600,
        )
        counter = ft.Text(
            f"0 / {total}",
            color=TEXT_SECONDARY,
            size=13,
        )
        items_column = ft.Column(spacing=4)
        tile = ft.ExpansionTile(
            title=ft.Row(
                [icon, title, ft.Container(expand=True), counter],
                spacing=10,
            ),
            controls=[
                ft.Container(
                    content=items_column,
                    padding=ft.padding.only(left=40, bottom=10),
                )
            ],
            expanded=False,
            tile_padding=ft.padding.symmetric(horizontal=10, vertical=5),
        )
        return {
            "tile": tile,
            "icon": icon,
            "title": title,
            "counter": counter,
            "items": items_column,
            "total": total,
            "success": 0,
            "failed": 0,
        }

    def _set_category_state(self, category: str, state: str) -> None:
        """Flip the leading icon/color to reflect category lifecycle.

        States: pending / running / done / partial / failed / cancelled / skipped.
        """
        row = self._category_rows.get(category)
        if row is None:
            return
        icon = row["icon"]
        if state == "running":
            icon.name = ft.Icons.HOURGLASS_TOP
            icon.color = PRIMARY
        elif state == "done":
            icon.name = ft.Icons.CHECK_CIRCLE
            icon.color = SECONDARY
        elif state == "partial":
            icon.name = ft.Icons.WARNING
            icon.color = WARNING
        elif state == "failed":
            icon.name = ft.Icons.ERROR
            icon.color = ERROR
        elif state == "cancelled":
            icon.name = ft.Icons.CANCEL
            icon.color = WARNING
        elif state == "skipped":
            icon.name = ft.Icons.REMOVE_CIRCLE_OUTLINE
            icon.color = TEXT_SECONDARY
        else:  # pending
            icon.name = ft.Icons.SCHEDULE
            icon.color = TEXT_SECONDARY

    def _render_processing(self):
        # Reset orchestration state on every entry — re-running a
        # decommission from scratch should clear stale rows / counters.
        self._category_rows = {}
        self._results = {}
        self._cancelled_at = None
        self._cancel_token = CancellationToken()

        planned = [
            category
            for category in DELETION_ORDER
            if self._selected_categories.get(category)
            and self._assets.get(category)
        ]

        rows: list[ft.Control] = []
        for category in planned:
            row = self._build_category_row(category, len(self._assets[category]))
            self._category_rows[category] = row
            rows.append(row["tile"])

        self._processing_status = ft.Text(
            f"Deleting {sum(len(self._assets[c]) for c in planned)} assets "
            f"across {len(planned)} categories...",
            color=TEXT_SECONDARY,
            size=13,
        )
        self._cancel_btn = ft.OutlinedButton(
            content=ft.Text("Cancel", color=ERROR, weight=ft.FontWeight.W_500),
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, ERROR),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            height=40,
            on_click=self._on_cancel,
        )

        self._content_area.controls = [
            *_section_heading(
                "Processing Deletions",
                "Click a category to expand its per-item detail. "
                "Cancel stops after the current item completes.",
            ),
            self._processing_status,
            ft.Container(height=10),
            ft.Column(rows, spacing=4),
            ft.Container(height=15),
            ft.Row(
                [self._cancel_btn],
                alignment=ft.MainAxisAlignment.START,
            ),
        ]

    def _on_cancel(self, e):
        """Cancel button — signal the loop and disable further clicks."""
        if self._cancel_token is None:
            return
        self._cancel_token.cancel()
        self._cancel_btn.disabled = True
        if isinstance(self._cancel_btn.content, ft.Text):
            self._cancel_btn.content.value = "Cancelling..."
        self._processing_status.value = (
            "Cancelling — finishing the current item, then stopping."
        )
        self._processing_status.color = WARNING
        e.page.update()

    async def _run_deletions(self, page, selected_categories: list[str]):
        int_client = get_internal_client()
        ext_client = get_external_client()
        loop = asyncio.get_running_loop()

        planned = [
            category
            for category in DELETION_ORDER
            if category in selected_categories and self._assets.get(category)
        ]
        grand_total = sum(len(self._assets[c]) for c in planned)
        log_system(
            "=== Decommission started: "
            f"{grand_total} assets across {len(planned)} categories "
            f"(order: {', '.join(planned) or 'none'}) ==="
        )

        deleted_total = 0
        cancelled = False
        for category in planned:
            if cancelled:
                # Remaining planned categories show as skipped so the user
                # can see what was left untouched by the cancellation.
                self._results[category] = (0, len(self._assets[category]))
                self._set_category_state(category, "skipped")
                row = self._category_rows.get(category)
                if row is not None:
                    row["counter"].value = f"skipped — 0 / {row['total']}"
                page.update()
                continue

            items = self._assets.get(category, [])
            self._set_category_state(category, "running")
            page.update()
            log_system(f"--- {category}: deleting {len(items)} item(s) ---")

            success = 0
            for item in items:
                if self._cancel_token and self._cancel_token.is_cancelled:
                    cancelled = True
                    self._cancelled_at = category
                    break
                if await self._delete_one(
                    page, loop, int_client, ext_client, category, item
                ):
                    success += 1

            row = self._category_rows.get(category)
            if row is not None:
                row["counter"].value = f"{success} / {row['total']}"
            self._results[category] = (success, len(items))
            deleted_total += success
            failed = len(items) - success

            if cancelled:
                self._set_category_state(category, "cancelled")
                log_system(
                    f"--- {category}: cancelled after {success}/{len(items)} "
                    "deleted ---",
                    level="WARN",
                )
            elif failed == 0:
                self._set_category_state(category, "done")
                log_system(f"--- {category}: {success}/{len(items)} deleted ---")
            elif success == 0:
                self._set_category_state(category, "failed")
                log_system(
                    f"--- {category}: {success}/{len(items)} deleted, "
                    f"{failed} failed ---",
                    level="WARN",
                )
            else:
                self._set_category_state(category, "partial")
                log_system(
                    f"--- {category}: {success}/{len(items)} deleted, "
                    f"{failed} failed ---",
                    level="WARN",
                )
            page.update()

        if cancelled:
            log_system(
                f"=== Decommission cancelled at '{self._cancelled_at}': "
                f"{deleted_total}/{grand_total} assets deleted ===",
                level="WARN",
            )
        else:
            log_system(
                f"=== Decommission complete: {deleted_total}/{grand_total} "
                "assets deleted ===",
                level="WARN" if deleted_total != grand_total else "INFO",
            )

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
        """Delete a single item, appending a status row inside the
        category's collapsed body. Returns True on success."""
        item_id = item.get("id") or "unknown"
        item_name = item.get("name") or item_id
        serial = _item_serial(item)
        # Label shown in the UI row: name plus serial when the asset has one.
        row_label = item_name if not serial else f"{item_name}  ·  SN {serial}"
        # Fuller descriptor (name · SN · id) goes to the log for traceability.
        descriptor = _item_descriptor(item)

        cat_row = self._category_rows.get(category)
        items_col = cat_row["items"] if cat_row else None

        step_icon = ft.ProgressRing(
            width=14, height=14, stroke_width=2, color=TEXT_SECONDARY
        )
        step_text = ft.Text(
            f"  Deleting {row_label}...", color=TEXT_SECONDARY, size=12
        )
        step_row = ft.Row([step_icon, step_text], spacing=8)
        if items_col is not None:
            items_col.controls.append(step_row)
        page.update()
        await asyncio.sleep(0)
        log_system(f"{category}: deleting {descriptor}")

        try:
            if category in _INTERNAL_DELETERS:
                # Most deleters take a single id. Two need extra fields, so
                # special-case them to keep the rest of the client API uniform:
                #   - delete_alarm_site takes (alarm_site_id, site_id);
                #     item["id"] from get_alarm_site is the responseSite.id
                #     (alarm_site_id), which the body's responseSiteId expects.
                #   - delete_schedule takes (schedule_id, name, priority) —
                #     the endpoint is an upsert-style PUT and the whole
                #     schedule object must accompany the deleted=True flag.
                deleter = getattr(int_client, _INTERNAL_DELETERS[category])
                if category == "Alarm Sites":
                    await loop.run_in_executor(
                        _executor, deleter, item.get("id"), item.get("site_id")
                    )
                elif category == "Schedules":
                    await loop.run_in_executor(
                        _executor,
                        deleter,
                        item_id,
                        item.get("name") or "",
                        item.get("priority") or "SCHEDULE",
                    )
                else:
                    await loop.run_in_executor(_executor, deleter, item_id)
            else:
                method_name = _EXTERNAL_DELETERS[category]
                delete_fn = getattr(ext_client, method_name)
                await loop.run_in_executor(_executor, delete_fn, item_id)

            step_row.controls[0] = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=SECONDARY, size=16
            )
            step_text.value = f"  Deleted {row_label}"
            step_text.color = SECONDARY
            if cat_row is not None:
                cat_row["success"] += 1
                cat_row["counter"].value = (
                    f"{cat_row['success']} / {cat_row['total']}"
                )
            page.update()
            log_system(f"{category}: deleted {descriptor}")
            return True
        except Exception as ex:
            # Sites get a second chance: a site that refuses deletion is
            # renamed "<name>-<mm/dd/yy>" so its original name is freed
            # for future commissioning runs.
            if category == "Sites":
                renamed_to = await self._rename_site_fallback(
                    loop, int_client, item_id, item_name
                )
                if renamed_to:
                    step_row.controls[0] = ft.Icon(
                        ft.Icons.WARNING, color=WARNING, size=16
                    )
                    step_text.value = (
                        f"  Could not delete {row_label} — renamed to "
                        f"'{renamed_to}'"
                    )
                    step_text.color = WARNING
                    if cat_row is not None:
                        cat_row["success"] += 1
                        cat_row["counter"].value = (
                            f"{cat_row['success']} / {cat_row['total']}"
                        )
                    page.update()
                    log_system(
                        f"{category}: could not delete {descriptor} ({ex}) — "
                        f"renamed to '{renamed_to}'",
                        level="WARN",
                    )
                    return True

            step_row.controls[0] = ft.Icon(ft.Icons.ERROR, color=ERROR, size=16)
            step_text.value = f"  Failed: {row_label} — {ex}"
            step_text.color = ERROR
            if cat_row is not None:
                cat_row["failed"] += 1
            page.update()
            log_system(
                f"{category}: FAILED to delete {descriptor} — {ex}", level="ERROR"
            )
            return False

    async def _rename_site_fallback(
        self,
        loop: asyncio.AbstractEventLoop,
        int_client,
        site_id: str,
        site_name: str,
    ) -> str | None:
        """Rename a site that refused deletion to '<name>-<mm/dd/yy>'.

        Returns the new name on success, None if the rename also failed
        (caller then reports the original delete failure).
        """
        stamp = datetime.datetime.now().strftime("%m/%d/%y")
        new_name = f"{site_name}-{stamp}"
        try:
            await loop.run_in_executor(
                _executor, int_client.rename_site, site_id, new_name
            )
            return new_name
        except Exception as rename_ex:
            log_system(
                f"Sites: rename fallback for '{site_name}' ({site_id}) "
                f"also failed — {rename_ex}",
                level="ERROR",
            )
            return None

    # ------------------------------------------------------------------
    # COMPLETE state
    # ------------------------------------------------------------------

    def _render_complete(self):
        rows = []
        total_success = 0
        total_items = 0
        skipped = bool(self._cancelled_at)
        for category, (success, total) in self._results.items():
            total_success += success
            total_items += total
            # A category counts as "skipped" in the summary when the
            # cancellation hit before we reached it: zero attempts on a
            # non-empty plan.
            skipped_cat = (
                skipped
                and success == 0
                and self._cancelled_at is not None
                and self._category_position(category)
                > self._category_position(self._cancelled_at)
            )
            cancelled_here = skipped and category == self._cancelled_at

            if skipped_cat:
                icon_name, icon_color, label = (
                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                    TEXT_SECONDARY,
                    f"{category}: skipped (cancelled)",
                )
            elif cancelled_here:
                icon_name, icon_color, label = (
                    ft.Icons.CANCEL,
                    WARNING,
                    f"{category}: {success}/{total} deleted (cancelled here)",
                )
            elif success == total:
                icon_name, icon_color, label = (
                    ft.Icons.CHECK_CIRCLE,
                    SECONDARY,
                    f"{category}: {success}/{total} deleted",
                )
            elif success == 0:
                icon_name, icon_color, label = (
                    ft.Icons.ERROR,
                    ERROR,
                    f"{category}: 0/{total} deleted",
                )
            else:
                icon_name, icon_color, label = (
                    ft.Icons.WARNING,
                    WARNING,
                    f"{category}: {success}/{total} deleted",
                )

            rows.append(
                ft.Row(
                    [
                        ft.Icon(icon_name, color=icon_color, size=18),
                        ft.Text(label, color=TEXT_PRIMARY, size=13),
                    ],
                    spacing=10,
                )
            )

        if skipped:
            title = f"Decommission Cancelled at {self._cancelled_at}"
            overall_color = WARNING
            subtitle = (
                f"{total_success}/{total_items} assets deleted before cancellation."
            )
        else:
            overall_ok = total_success == total_items
            title = "Decommission Complete"
            overall_color = SECONDARY if overall_ok else WARNING
            subtitle = (
                f"{total_success}/{total_items} total assets deleted successfully."
            )

        self._content_area.controls = [
            ft.Text(
                title,
                size=18,
                color=overall_color,
                weight=ft.FontWeight.W_600,
            ),
            ft.Text(subtitle, size=13, color=TEXT_SECONDARY),
            ft.Container(height=15),
            ft.Column(rows, spacing=8),
            ft.Container(height=20),
            _make_button(
                "Return to Home",
                lambda _: self.push_route("/home"),
                bgcolor=SECONDARY,
            ),
        ]

    def _category_position(self, category: str) -> int:
        """Return a category's position in DELETION_ORDER (or -1 if absent)."""
        try:
            return DELETION_ORDER.index(category)
        except ValueError:
            return -1

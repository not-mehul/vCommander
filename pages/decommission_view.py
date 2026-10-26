"""Decommission screen.

Lists every asset in the org grouped by ASSET_CATEGORIES, lets the
user select what to remove — whole categories or individual items — and
then deletes the selection in DELETION_ORDER (both defined in
constants.py). The order matters — e.g. intercoms must be deleted before
the cameras/access controllers they're paired with, alarm devices before
alarm sites, users before the hardware they're tied to.

Scanning temporarily changes the org: it creates a public-API key and
turns on Global Site Admin so every site-scoped asset is visible. Both are
undone whenever the flow ends — after a delete run (any outcome), a failed
or cancelled scan, or when the user leaves the screen.
"""

import asyncio
import csv
import datetime
import os

import flet as ft

import theme
from apis.external_api import VerkadaExternalAPIClient
from components import (
    ProgressHeader,
    Stepper,
    StepRow,
    banner,
    card,
    danger_button,
    ghost_button,
    primary_button,
    run_step,
    scroll_area,
    secondary_button,
    section_header,
    set_button_loading,
    stat_row,
    status_row,
    text_field,
)
from constants import (
    _EXTERNAL_DELETERS,
    _EXTERNAL_GETTERS,
    _INTERNAL_DELETERS,
    _INTERNAL_GETTERS,
    ASSET_CATEGORIES,
    CARD_PADDING,
    CATEGORY_GROUPS,
    DELETION_ORDER,
    ERROR,
    FIELD_SPACING,
    INTERNAL_PAGE_SIZE,
    PAGED_CATEGORIES,
    PRIMARY,
    READ_ONLY_CATEGORIES,
    SECONDARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)
from pages.app_shell import ToolView
from utils.cancellation import CancellationToken
from utils.executor import _executor
from utils.export import export_csv
from utils.logger import log_system
from utils.session import begin_run, end_run, get_internal_client
from utils.tasks import spawn
from utils.ui_utils import show_alert, show_toast

# Reverse lookup: child category -> parent group name (built once from
# CATEGORY_GROUPS so the view can ask "which group does this belong to?").
_CATEGORY_TO_GROUP = {
    child: group for group, children in CATEGORY_GROUPS.items() for child in children
}

# Upper bound on re-list passes for a PAGED category, as a guard against a
# list endpoint that keeps returning items that never actually delete.
_MAX_DRAIN_PASSES = 100


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


def _expansion_tile(**kwargs) -> ft.ExpansionTile:
    """ExpansionTile without Material's default top/bottom divider lines.

    Nested tiles otherwise stack those dividers into doubled rules.
    """
    shape = ft.RoundedRectangleBorder(radius=theme.RADIUS_MD)
    return ft.ExpansionTile(
        shape=shape,
        collapsed_shape=shape,
        icon_color=theme.TEXT_SECONDARY,
        collapsed_icon_color=theme.TEXT_SECONDARY,
        **kwargs,
    )


class _ScanCancelled(Exception):
    """Raised inside the scan loop when the user abandons the scan."""


# State machine
SCAN = "scan"
REVIEW = "review"
SELECT = "select"
CONFIRM = "confirm"
PROCESSING = "processing"
COMPLETE = "complete"

# Shared stepper labels and the state -> step-index map driving it.
_DECOMMISSION_STEPS = ["Scan", "Review", "Select", "Confirm", "Run", "Report"]
_STATE_STEP = {
    SCAN: 0,
    REVIEW: 1,
    SELECT: 2,
    CONFIRM: 3,
    PROCESSING: 4,
    COMPLETE: 5,
}


class DecommissionView(ToolView):
    def __init__(self, push_route):
        super().__init__(
            push_route,
            route="/decommission",
            title="Decommission Organization",
            subtitle="Scan an org, choose what to remove, and delete it in a "
            "dependency-safe order.",
        )
        self._state = SCAN
        self._assets: dict[str, list[dict]] = {}
        # Selected item indices per deletable category (indices into
        # self._assets[category]). Read-only categories never appear here.
        self._selected: dict[str, set[int]] = {}
        self._results: dict[str, tuple[int, int]] = {}
        self._show_items: bool = False
        self._search_query: str = ""
        # Persistent SELECT-step controls: rebuilt tiles reuse them so the
        # search field keeps focus while the user types.
        self._search_field: ft.TextField | None = None
        self._show_items_switch: ft.Switch | None = None
        # Cooperative cancellation for the delete loop. Tested between
        # items; the in-flight delete is allowed to complete so we never
        # leave a half-deleted asset behind.
        self._cancel_token: CancellationToken | None = None
        self._cancelled_at: str | None = None
        # What the scan changed in the org, released by _release_org().
        self._int_client = None
        self._ext_client = None
        self._api_key = None
        self._gsa_enabled = False
        # True while a scan or delete run owns the org; that run releases
        # the org itself when it finishes.
        self._busy = False
        self._cleanup: list[tuple[str, str]] = []
        # Per-category UI controls populated when PROCESSING renders, so
        # _delete_one can flip the status icon / counters without
        # appending to a global scrolling column.
        self._category_rows: dict[str, dict] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # Top-level UI scaffolding
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._stepper = Stepper(_DECOMMISSION_STEPS, current=0)
        self._content_area = ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )

        self.mount(
            card(
                ft.Column(
                    [
                        ft.Container(
                            content=self._stepper,
                            padding=ft.Padding.only(bottom=FIELD_SPACING),
                        ),
                        scroll_area(self._content_area),
                    ],
                    expand=True,
                ),
                padding=CARD_PADDING,
                expand=True,
            )
        )

        self._render_state()

    def _render_state(self):
        self._stepper.set_active(_STATE_STEP.get(self._state, 0))
        self._content_area.controls.clear()
        if self._state == SCAN:
            self._render_scan()
        elif self._state == REVIEW:
            self._render_review()
        elif self._state == SELECT:
            self._render_select()
        elif self._state == CONFIRM:
            self._render_confirm()
        elif self._state == PROCESSING:
            self._render_processing()
        elif self._state == COMPLETE:
            self._render_complete()

    def _set_state(self, page, state: str) -> None:
        self._state = state
        self._render_state()
        page.update()

    # ------------------------------------------------------------------
    # Org changes made by the scan, and their release
    # ------------------------------------------------------------------

    def on_leave(self) -> None:
        """Undo the scan's org changes when the user leaves the screen.

        A running scan/delete was already cancelled by the navigation guard
        and releases the org itself when it stops; otherwise release now.
        """
        if not self._busy:
            spawn(self._release_org())

    async def _release_org(self) -> None:
        """Turn Global Site Admin back off and delete the temporary API key.

        Idempotent: each change is forgotten before it is undone, so a second
        call is a no-op. Access System/User Admin, also granted by the scan,
        are deliberately left in place. Results are logged and collected in
        self._cleanup for the report.
        """
        client = self._int_client
        loop = asyncio.get_running_loop()

        if self._gsa_enabled and client is not None:
            self._gsa_enabled = False
            try:
                await loop.run_in_executor(_executor, client.disable_global_site_admin)
                log_system("Disabled Global Site Admin.")
                self._cleanup.append(("done", "Global Site Admin turned back off"))
            except Exception as ex:
                log_system(f"Could not disable Global Site Admin: {ex}", level="WARN")
                self._cleanup.append(
                    ("partial", f"Global Site Admin could not be turned off: {ex}")
                )

        key, self._api_key = self._api_key, None
        if key is not None and client is not None:
            if not key.key_id:
                self._cleanup.append(
                    ("partial", "Temporary API key could not be identified — "
                     "delete it under Org Settings > API Keys.")
                )
            else:
                try:
                    await loop.run_in_executor(
                        _executor, client.delete_external_api_key, key.key_id
                    )
                    log_system("Deleted temporary API key.")
                    self._cleanup.append(("done", "Temporary API key deleted"))
                except Exception as ex:
                    log_system(f"Could not delete temporary API key: {ex}", level="WARN")
                    self._cleanup.append(
                        ("partial", f"Temporary API key could not be deleted: {ex}")
                    )

    # ------------------------------------------------------------------
    # SCAN state
    # ------------------------------------------------------------------

    def _render_scan(self):
        self._scan_btn = primary_button(
            "Scan Organization", on_click=self._on_scan, height=45, width=240
        )
        # Prep-step progress rows — populated by _on_scan during the
        # permission-elevation phase, then hidden when the scan loop starts.
        # Lives in the same Column as the scan button so the page composition
        # doesn't shift when prep starts.
        self._prep_progress = ft.Column(spacing=8, visible=False, width=440)
        # Determinate progress + live status for the per-category scan loop.
        self._scan_progress = ProgressHeader(determinate=True)
        self._scan_progress_box = ft.Container(
            content=self._scan_progress, width=440, visible=False
        )
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
                    ft.Container(height=12),
                    ft.Container(
                        width=560,
                        content=banner(
                            "Scanning creates a temporary API key and turns on "
                            "Global Site Admin so every site's assets are "
                            "visible. Both are undone when you finish or leave.",
                            kind="info",
                        ),
                    ),
                    ft.Container(height=12),
                    self._scan_btn,
                    ft.Container(height=15),
                    self._prep_progress,
                    ft.Container(height=8),
                    self._scan_progress_box,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        ]

    async def _prep_step(self, page, label: str, fn, *args):
        """Run one pre-scan step with a live row; re-raise so the scan aborts."""
        ok, result, error = await run_step(
            page, self._prep_progress, label, fn, *args
        )
        if not ok:
            raise error
        return result

    async def _on_scan(self, e):
        # Capture the page now: _render_state() at the end detaches the scan
        # button that fired this event, so reading `e.page` afterwards would
        # raise. Use this reference for every page touch in the flow.
        page = e.page
        try:
            client = get_internal_client()
        except RuntimeError as ex:
            show_alert(page, "Not Logged In", str(ex))
            return
        token = CancellationToken()
        if not begin_run("Decommission scan", token):
            show_toast(
                page,
                "Another run is still stopping — try again in a moment.",
                kind="warning",
            )
            return
        self._busy = True
        self._int_client = client
        set_button_loading(self._scan_btn, True, "Scanning")

        # Reveal the prep-step progress block from the scan layout so the
        # rows we append have somewhere to land.
        self._prep_progress.controls.clear()
        self._prep_progress.visible = True
        page.update()
        await asyncio.sleep(0)

        # Clear any stale data from a previous scan so a partial failure never
        # leaves the app in a mixed state.
        self._assets = {}
        self._selected = {}

        try:
            loop = asyncio.get_running_loop()

            # Short-lived public-API key for the external client. Deleted by
            # _release_org() when the flow ends.
            self._api_key = await self._prep_step(
                page, "Creating temporary API key", client.create_external_api_key
            )
            self._ext_client = await self._prep_step(
                page,
                "Connecting to the public API",
                VerkadaExternalAPIClient,
                self._api_key.key,
                client.org_short_name,
                client.public_api_region,
            )

            # Pre-scan permission elevation. Both calls grant the running
            # user the ability to see and delete site-scoped resources that
            # the standard org-admin role might not surface. Without these,
            # access controllers, alarm sites, and similar can be silently
            # missing from the scan results.
            #
            # Global Site Admin is org-wide, so _release_org() turns it back
            # off whenever the flow ends. Access System/User Admin only
            # affect the running user and are left granted. The flag is set
            # before the call: a request that times out may still have
            # applied, and turning GSA off again is harmless either way.
            self._gsa_enabled = True
            await self._prep_step(
                page, "Enabling Global Site Admin", client.enable_global_site_admin
            )
            await self._prep_step(
                page, "Granting Access System Admin", client.enable_access_admin
            )

            # Serials that should be filtered out of the Cameras list:
            # Intercoms and Access Station Pros are both surfaced by the
            # camera endpoint, but their deletion lives on their own
            # categories. Without this filter, decommission tries to
            # delete the same device twice (and the second attempt fails
            # because it's already gone or uses the wrong endpoint).
            camera_dedup_serials: set[str] = set()
            total = len(ASSET_CATEGORIES)
            self._scan_progress_box.visible = True
            self._scan_progress.set_progress(0, total, prefix="Starting scan")
            page.update()
            for i, category in enumerate(ASSET_CATEGORIES):
                if token.is_cancelled:
                    raise _ScanCancelled
                # Surface which category is being scanned before the (blocking)
                # request so the bar + status update as the scan progresses.
                self._scan_progress.set_progress(
                    i, total, prefix=f"Scanning {category}"
                )
                page.update()
                await asyncio.sleep(0)
                items = await self._scan_category(
                    loop, client, self._ext_client, category, camera_dedup_serials
                )
                if category in ("Intercoms", "Access Station Pro"):
                    camera_dedup_serials |= {
                        item["serial_number"]
                        for item in items
                        if item.get("serial_number")
                    }
                self._assets[category] = items

            self._scan_progress.set_progress(total, total, prefix="Scan complete")
            # Everything deletable starts selected; the user narrows it down.
            self._selected = {
                category: set(range(len(items)))
                for category, items in self._assets.items()
                if category not in READ_ONLY_CATEGORIES and items
            }
            self._set_state(page, REVIEW)
        except Exception as ex:
            self._assets = {}
            self._selected = {}
            await self._release_org()
            if not isinstance(ex, _ScanCancelled):
                set_button_loading(self._scan_btn, False, "Scan Organization")
                show_alert(page, "Scan Failed", str(ex))
        finally:
            self._busy = False
            end_run(token)

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
    # Selection model helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _may_be_truncated(category: str, count: int) -> bool:
        """True when a one-page category came back full (more may exist)."""
        return category in PAGED_CATEGORIES and count >= INTERNAL_PAGE_SIZE

    def _count_label(self, category: str) -> str:
        count = len(self._assets.get(category, []))
        return f"{count}+" if self._may_be_truncated(category, count) else str(count)

    def _selectable_categories(self) -> list[str]:
        return [c for c in ASSET_CATEGORIES if c in self._selected]

    def _is_fully_selected(self, category: str) -> bool:
        return len(self._selected.get(category, ())) == len(
            self._assets.get(category, [])
        )

    def _category_value(self, category: str) -> bool | None:
        """Checkbox value for a category: all / none / mixed (None)."""
        count = len(self._selected.get(category, ()))
        if count == 0:
            return False
        return True if self._is_fully_selected(category) else None

    def _matching(self, category: str) -> list[tuple[int, dict]]:
        """(index, item) pairs matching the search query (all when empty)."""
        items = list(enumerate(self._assets.get(category, [])))
        q = self._search_query
        if not q:
            return items
        return [
            (i, item)
            for i, item in items
            if q in (item.get("name") or "").lower()
            or q in (item.get("serial_number") or "").lower()
            or q in str(item.get("id") or "").lower()
        ]

    def _deletion_plan(self) -> list[tuple[str, list[dict]]]:
        """[(category, selected items)] in DELETION_ORDER, skipping empties."""
        plan = []
        for category in DELETION_ORDER:
            indices = self._selected.get(category)
            if indices:
                items = self._assets[category]
                plan.append((category, [items[i] for i in sorted(indices)]))
        return plan

    def _drains(self, category: str) -> bool:
        """Whether the delete loop should keep re-listing this category."""
        return self._is_fully_selected(category) and self._may_be_truncated(
            category, len(self._assets.get(category, []))
        )

    # ------------------------------------------------------------------
    # REVIEW state
    # ------------------------------------------------------------------

    def _render_review(self):
        rows = []
        empty: list[str] = []
        total = 0
        truncated = False
        for category in ASSET_CATEGORIES:
            count = len(self._assets.get(category, []))
            total += count
            truncated |= self._may_be_truncated(category, count)
            if count == 0:
                empty.append(category)
                continue
            label = (
                f"{category} (read-only)" if category in READ_ONLY_CATEGORIES else category
            )
            rows.append(stat_row(label, self._count_label(category), accent=PRIMARY))

        if total == 0:
            # Empty state — nothing to delete, so skip straight to a friendly
            # message + a way out rather than a wall of zeros.
            self._content_area.controls = [
                ft.Container(height=40),
                ft.Column(
                    [
                        ft.Icon(
                            ft.Icons.CHECK_CIRCLE_OUTLINE,
                            size=48,
                            color=SECONDARY,
                        ),
                        ft.Container(height=10),
                        ft.Text(
                            "No assets found",
                            size=20,
                            color=TEXT_PRIMARY,
                            weight=ft.FontWeight.W_600,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "This organization is already clean — nothing to "
                            "decommission.",
                            size=13,
                            color=TEXT_SECONDARY,
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Container(height=20),
                        secondary_button(
                            "Return to Home",
                            on_click=lambda _: self.push_route("/home"),
                            width=240,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ]
            return

        controls = [
            section_header(
                "Assets Found",
                f"{total}{'+' if truncated else ''} assets in "
                f"{len(rows)} of {len(ASSET_CATEGORIES)} categories.",
            ),
            ft.Container(height=10),
            ft.Column(rows, spacing=8),
        ]
        if empty:
            # The empty categories are listed in one muted line rather than
            # as dozens of zero rows that push the next step off-screen.
            controls.append(
                ft.Text(
                    "Nothing found in: " + ", ".join(empty) + ".",
                    size=theme.FONT_CAPTION,
                    color=theme.TEXT_MUTED,
                )
            )
        controls.append(ft.Container(height=15))
        if truncated:
            controls += [
                banner(
                    f"Categories marked + list at most {INTERNAL_PAGE_SIZE} items "
                    "per scan. If you delete a whole category, the rest are found "
                    "and deleted during the run.",
                    kind="info",
                ),
                ft.Container(height=10),
            ]
        controls.append(
            primary_button("Select Assets to Remove", on_click=self._go_to_select)
        )
        self._content_area.controls = controls

    def _go_to_select(self, e):
        self._set_state(e.page, SELECT)

    # ------------------------------------------------------------------
    # SELECT state — category and item checkboxes, live search
    # ------------------------------------------------------------------

    def _render_select(self):
        if self._search_field is None:
            self._search_field = text_field(
                hint="Search by name, serial or id",
                value=self._search_query,
                prefix_icon=ft.Icons.SEARCH,
                on_change=self._on_search_change,
                expand=True,
                compact=True,
            )
            self._show_items_switch = ft.Switch(
                value=self._show_items,
                active_color=PRIMARY,
                on_change=self._on_show_items_change,
            )
        self._selection_hint = ft.Text("", color=TEXT_SECONDARY, size=12)
        self._tiles_column = ft.Column(self._build_tiles(), spacing=4)
        self._refresh_selection_hint()

        export_btn = secondary_button(
            "Export asset list (CSV)",
            on_click=self._export_assets_csv,
            icon=ft.Icons.DOWNLOAD,
            tone="accent",
        )
        top_bar = ft.Row(
            [
                ft.TextButton(
                    content=ft.Text("Select all", color=PRIMARY, size=13),
                    on_click=lambda e: self._bulk_select(e.page, value=True),
                ),
                ft.TextButton(
                    content=ft.Text("Select none", color=PRIMARY, size=13),
                    on_click=lambda e: self._bulk_select(e.page, value=False),
                ),
                ft.Container(width=10),
                self._search_field,
                ft.Container(width=10),
                ft.Text("Show items", color=TEXT_SECONDARY, size=12),
                self._show_items_switch,
            ],
            spacing=4,
        )

        self._content_area.controls = [
            section_header(
                "Select Assets to Remove",
                "Tick whole categories, or turn on Show items to pick "
                "individual assets. Only ticked assets are deleted.",
            ),
            ft.Container(height=10),
            top_bar,
            self._selection_hint,
            ft.Container(height=6),
            self._tiles_column,
            ft.Container(height=15),
            ft.Row(
                [
                    export_btn,
                    primary_button(
                        "Review Selection",
                        on_click=self._on_review_selection,
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
        ]

    def _build_tiles(self) -> list[ft.Control]:
        """(Re)build every category/group tile from the selection state."""
        self._category_checkboxes: dict[str, ft.Checkbox] = {}
        self._category_titles: dict[str, ft.Text] = {}
        self._item_checkboxes: dict[str, dict[int, ft.Checkbox]] = {}
        self._group_checkboxes: dict[str, ft.Checkbox] = {}
        self._group_titles: dict[str, ft.Text] = {}
        tiles: list[ft.Control] = []
        rendered_groups: set[str] = set()

        for category in ASSET_CATEGORIES:
            group = _CATEGORY_TO_GROUP.get(category)
            if group:
                # Render the whole group once, at its first child's position.
                if group not in rendered_groups:
                    rendered_groups.add(group)
                    tile = self._build_group_tile(group)
                    if tile:
                        tiles.append(tile)
                continue
            if not self._assets.get(category):
                continue
            if category in READ_ONLY_CATEGORIES:
                tiles.append(self._build_read_only_tile(category))
            else:
                tiles.append(self._build_leaf_tile(category))

        for category in self._category_checkboxes:
            self._refresh_category(category)
        for group in self._group_checkboxes:
            self._refresh_group(group)
        return tiles

    def _checkbox(self, value, on_change, *, tristate: bool = False) -> ft.Checkbox:
        return ft.Checkbox(
            value=value,
            tristate=tristate,
            active_color=PRIMARY,
            check_color=theme.ON_ACCENT,
            on_change=on_change,
        )

    def _build_read_only_tile(self, category: str) -> ft.Control:
        """A category that can be listed but not deleted — no checkbox."""
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LOCK_OUTLINE, size=18, color=TEXT_SECONDARY),
                    ft.Text(
                        f"{category}  ({len(self._assets[category])}) — read-only, "
                        "Verkada has no delete endpoint for these",
                        color=TEXT_SECONDARY,
                    ),
                ],
                spacing=10,
            ),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        )

    def _build_leaf_tile(self, category: str) -> ft.Control:
        """One category: tristate checkbox + "N / M" title, items optional."""
        cb = self._checkbox(
            self._category_value(category),
            lambda e, c=category: self._toggle_category(e, c),
            tristate=True,
        )
        self._category_checkboxes[category] = cb
        title = ft.Text("", color=TEXT_PRIMARY)
        self._category_titles[category] = title

        if not self._show_items:
            return ft.Container(
                content=ft.Row([cb, title]),
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
            )

        matches = self._matching(category)
        item_boxes: dict[int, ft.Checkbox] = {}
        rows: list[ft.Control] = []
        selected = self._selected.get(category, set())
        for index, item in matches:
            item_cb = self._checkbox(
                index in selected,
                lambda e, c=category, i=index: self._toggle_item(e, c, i),
            )
            item_boxes[index] = item_cb
            rows.append(
                ft.Row(
                    [
                        item_cb,
                        ft.Text(
                            _item_descriptor(item), color=TEXT_SECONDARY, size=12
                        ),
                    ],
                    spacing=4,
                )
            )
        self._item_checkboxes[category] = item_boxes
        if not rows:
            rows = [
                ft.Text(
                    "  (no matches)" if self._search_query else "  (empty)",
                    color=TEXT_SECONDARY,
                    italic=True,
                    size=12,
                )
            ]
        return _expansion_tile(
            title=ft.Row([cb, title]),
            controls=[
                ft.Container(
                    content=ft.Column(rows, spacing=0),
                    padding=ft.Padding.only(left=30, bottom=10),
                )
            ],
            # While searching, open the categories that have matches.
            expanded=bool(self._search_query and matches),
            tile_padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        )

    def _build_group_tile(self, group: str) -> ft.Control | None:
        """Build a parent tile for a group (Access Control / Alarms).

        The parent checkbox toggles every non-empty child at once and shows
        an indeterminate state when only some are selected. Returns None
        when the group has no scanned assets (nothing to show).
        """
        child_tiles = [
            self._build_leaf_tile(child)
            for child in CATEGORY_GROUPS[group]
            if self._assets.get(child) and child not in READ_ONLY_CATEGORIES
        ]
        if not child_tiles:
            return None

        parent_cb = self._checkbox(
            True, lambda e, g=group: self._toggle_group(e, g), tristate=True
        )
        self._group_checkboxes[group] = parent_cb
        title = ft.Text("", color=TEXT_PRIMARY, weight=ft.FontWeight.W_600)
        self._group_titles[group] = title

        return _expansion_tile(
            title=ft.Row([parent_cb, title]),
            controls=[
                ft.Container(
                    content=ft.Column(child_tiles, spacing=2),
                    padding=ft.Padding.only(left=20),
                )
            ],
            # Default expanded so the inner per-category counts are visible
            # without an extra click; users can collapse if they want.
            expanded=True,
            tile_padding=ft.Padding.symmetric(horizontal=10, vertical=5),
        )

    def _group_children(self, group: str) -> list[str]:
        return [c for c in CATEGORY_GROUPS[group] if c in self._category_checkboxes]

    # -- selection events ------------------------------------------------
    # Tristate checkboxes cycle through values on click; the handlers ignore
    # that cycle and apply bulk semantics instead: fully selected -> clear,
    # anything else -> select everything.

    def _toggle_category(self, e, category: str) -> None:
        if self._is_fully_selected(category):
            self._selected[category] = set()
        else:
            self._selected[category] = set(range(len(self._assets[category])))
        self._after_selection_change(e.page, [category])

    def _toggle_item(self, e, category: str, index: int) -> None:
        selected = self._selected.setdefault(category, set())
        if e.control.value:
            selected.add(index)
        else:
            selected.discard(index)
        self._after_selection_change(e.page, [category])

    def _toggle_group(self, e, group: str) -> None:
        children = self._group_children(group)
        target = not all(self._is_fully_selected(c) for c in children)
        for child in children:
            count = len(self._assets[child])
            self._selected[child] = set(range(count)) if target else set()
        self._after_selection_change(e.page, children)

    def _bulk_select(self, page, *, value: bool) -> None:
        """Top-bar Select all / Select none.

        With a search query these apply only to the matching items, so a
        search can be used to build a selection ("Select none", search
        "lab", "Select all").
        """
        categories = self._selectable_categories()
        for category in categories:
            matched = {i for i, _ in self._matching(category)}
            if value:
                self._selected[category] |= matched
            else:
                self._selected[category] -= matched
        self._after_selection_change(page, categories)

    def _after_selection_change(self, page, categories: list[str]) -> None:
        for category in categories:
            self._refresh_category(category)
        for group in self._group_checkboxes:
            self._refresh_group(group)
        self._refresh_selection_hint()
        page.update()

    def _refresh_category(self, category: str) -> None:
        """Sync a category's checkbox, item checkboxes and "N / M" title."""
        selected = self._selected.get(category, set())
        cb = self._category_checkboxes.get(category)
        if cb is not None:
            cb.value = self._category_value(category)
        for index, item_cb in self._item_checkboxes.get(category, {}).items():
            item_cb.value = index in selected
        title = self._category_titles.get(category)
        if title is not None:
            title.value = (
                f"{category}  ({len(selected)} / {self._count_label(category)})"
            )

    def _refresh_group(self, group: str) -> None:
        children = self._group_children(group)
        cb = self._group_checkboxes[group]
        if children and all(self._is_fully_selected(c) for c in children):
            cb.value = True
        elif not any(self._selected.get(c) for c in children):
            cb.value = False
        else:
            cb.value = None
        selected = sum(len(self._selected.get(c, ())) for c in children)
        total = sum(len(self._assets.get(c, [])) for c in children)
        self._group_titles[group].value = f"{group}  ({selected} / {total})"

    def _refresh_selection_hint(self) -> None:
        selected = sum(len(s) for s in self._selected.values())
        hint = f"{selected} asset{'s' if selected != 1 else ''} selected for deletion."
        if self._search_query:
            matches = sum(
                len(self._matching(c)) for c in self._selectable_categories()
            )
            hint += (
                f"  Select all / none apply to the {matches} item"
                f"{'s' if matches != 1 else ''} matching “{self._search_query}”."
            )
        self._selection_hint.value = hint

    def _on_search_change(self, e) -> None:
        self._search_query = (e.control.value or "").strip().lower()
        if self._search_query and not self._show_items:
            # Searching only makes sense with the item lists showing.
            self._show_items = True
            self._show_items_switch.value = True
        self._rebuild_tiles(e.page)

    def _on_show_items_change(self, e) -> None:
        self._show_items = bool(e.control.value)
        self._rebuild_tiles(e.page)

    def _rebuild_tiles(self, page) -> None:
        # Only the tile list is rebuilt; the search field is the same control,
        # so it keeps focus while the user types.
        self._tiles_column.controls = self._build_tiles()
        self._refresh_selection_hint()
        page.update()

    def _export_assets_csv(self, e):
        downloads = os.path.expanduser("~/Downloads")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(downloads, f"vCommander_assets_{timestamp}.csv")
        rows = []
        for category in ASSET_CATEGORIES:
            selected = self._selected.get(category, set())
            for index, item in enumerate(self._assets.get(category, [])):
                rows.append(
                    {
                        "Category": category,
                        "Name": item.get("name", ""),
                        "Serial Number": _item_serial(item) or "",
                        "ID": item.get("id", ""),
                        "Selected": "yes" if index in selected else "no",
                    }
                )
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["Category", "Name", "Serial Number", "ID", "Selected"]
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

    # ------------------------------------------------------------------
    # CONFIRM state — final destructive summary before deletion
    # ------------------------------------------------------------------

    def _on_review_selection(self, e):
        """SELECT -> CONFIRM: show exactly what will be deleted."""
        if not self._deletion_plan():
            show_toast(
                e.page,
                "Please select at least one asset to delete.",
                kind="warning",
            )
            return
        self._set_state(e.page, CONFIRM)

    def _back_to_select(self, e):
        self._set_state(e.page, SELECT)

    def _render_confirm(self):
        plan = self._deletion_plan()
        total = sum(len(items) for _, items in plan)
        drains = any(self._drains(category) for category, _ in plan)
        rows: list[ft.Control] = []
        for category, items in plan:
            available = len(self._assets[category])
            value = (
                self._count_label(category)
                if len(items) == available
                else f"{len(items)} of {self._count_label(category)}"
            )
            rows.append(stat_row(category, value, accent=ERROR))

        count_text = f"{total}{'+' if drains else ''}"
        noun = "asset" if total == 1 and not drains else "assets"
        confirm_btn = danger_button(
            f"Delete {count_text} {noun.capitalize()}", on_click=self._on_delete
        )
        back_btn = ghost_button(
            "Back",
            on_click=self._back_to_select,
            color=TEXT_SECONDARY,
            icon=ft.Icons.ARROW_BACK,
        )

        controls = [
            section_header(
                "Confirm Deletion",
                f"{count_text} {noun} across {len(plan)} "
                f"categor{'ies' if len(plan) != 1 else 'y'} "
                "will be permanently removed.",
            ),
            ft.Container(height=10),
            banner(
                "This permanently deletes the selected assets in dependency "
                "order and cannot be undone.",
                kind="danger",
            ),
        ]
        if drains:
            controls += [
                ft.Container(height=6),
                banner(
                    "Categories marked + may hold more than one scan page; the "
                    "rest are found and deleted during the run.",
                    kind="info",
                ),
            ]
        controls += [
            ft.Container(height=10),
            ft.Column(rows, spacing=8),
            ft.Container(height=15),
            ft.Row([back_btn, confirm_btn], spacing=10),
        ]
        self._content_area.controls = controls

    async def _on_delete(self, e):
        # Capture the page up front: _render_state() detaches the button that
        # fired this event, and after the await below `e.page` would raise
        # ("Control must be added to the page first").
        page = e.page
        plan = self._deletion_plan()
        if not plan:
            show_toast(
                page,
                "Please select at least one asset to delete.",
                kind="warning",
            )
            return
        token = CancellationToken()
        if not begin_run("Decommission", token):
            show_toast(
                page,
                "Another run is still stopping — try again in a moment.",
                kind="warning",
            )
            return
        self._busy = True
        self._cancel_token = token
        self._set_state(page, PROCESSING)
        await asyncio.sleep(0)
        try:
            await self._run_deletions(page, plan)
        except Exception as ex:
            log_system(f"Decommission stopped by an unexpected error: {ex}", level="ERROR")
            self._cleanup.append(("failed", f"Run stopped by an unexpected error: {ex}"))
        finally:
            await self._release_org()
            self._busy = False
            end_run(token)
        self._progress_header.complete(
            color=WARNING if (self._cancelled_at or self._failed_total) else SECONDARY
        )
        self._set_state(page, COMPLETE)

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
        tile = _expansion_tile(
            title=ft.Row(
                [icon, title, ft.Container(expand=True), counter],
                spacing=10,
            ),
            controls=[
                ft.Container(
                    content=items_column,
                    padding=ft.Padding.only(left=40, bottom=10),
                )
            ],
            expanded=False,
            tile_padding=ft.Padding.symmetric(horizontal=10, vertical=5),
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
        self._failed_total = 0
        self._cleanup = []

        plan = self._deletion_plan()
        total = sum(len(items) for _, items in plan)
        rows: list[ft.Control] = []
        for category, items in plan:
            row = self._build_category_row(category, len(items))
            self._category_rows[category] = row
            rows.append(row["tile"])

        # Determinate progress — the selected asset count is known up front
        # (one-page categories may add more as they are re-listed).
        self._progress_header = ProgressHeader(determinate=True)
        self._progress_header.set_progress(0, total, failed=0)
        self._processing_status = ft.Text(
            f"Deleting {total} assets across {len(plan)} categories...",
            color=TEXT_SECONDARY,
            size=13,
        )
        self._cancel_btn = secondary_button(
            "Cancel", on_click=self._on_cancel, tone="danger", icon=ft.Icons.STOP
        )

        self._content_area.controls = [
            section_header(
                "Processing Deletions",
                "Click a category to expand its per-item detail. "
                "Cancel stops after the current item completes.",
            ),
            ft.Container(height=10),
            self._progress_header,
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
        self._cancel_btn.content.controls[1].value = "Cancelling..."
        self._processing_status.value = (
            "Cancelling — finishing the current item, then stopping."
        )
        self._processing_status.color = WARNING
        e.page.update()

    async def _run_deletions(self, page, plan: list[tuple[str, list[dict]]]):
        int_client = self._int_client
        ext_client = self._ext_client
        loop = asyncio.get_running_loop()
        token = self._cancel_token

        grand_total = sum(len(items) for _, items in plan)
        log_system(
            "=== Decommission started: "
            f"{grand_total} assets across {len(plan)} categories "
            f"(order: {', '.join(c for c, _ in plan) or 'none'}) ==="
        )

        deleted_total = 0
        cancelled = False
        for category, items in plan:
            row = self._category_rows.get(category)
            if cancelled:
                # Remaining planned categories show as skipped so the user
                # can see what was left untouched by the cancellation.
                self._results[category] = (0, len(items))
                self._set_category_state(category, "skipped")
                if row is not None:
                    row["counter"].value = f"skipped — 0 / {row['total']}"
                page.update()
                continue

            self._set_category_state(category, "running")
            page.update()
            log_system(f"--- {category}: deleting {len(items)} item(s) ---")

            success = 0
            planned = len(items)
            attempted_ids = {item.get("id") for item in items}
            batch = items
            # A one-page category that was deleted wholesale is re-listed
            # after each pass until nothing new comes back, so assets past
            # the first page are deleted too.
            page_full = self._drains(category)
            for _ in range(_MAX_DRAIN_PASSES):
                for item in batch:
                    if token.is_cancelled:
                        cancelled = True
                        self._cancelled_at = category
                        break
                    if await self._delete_one(
                        page, loop, int_client, ext_client, category, item
                    ):
                        success += 1
                    self._progress_header.set_progress(
                        deleted_total + success,
                        grand_total,
                        failed=self._failed_total + (row["failed"] if row else 0),
                    )
                if cancelled or not page_full:
                    break
                try:
                    fresh = await self._scan_category(
                        loop, int_client, ext_client, category, set()
                    )
                except Exception as ex:
                    log_system(f"--- {category}: re-list failed, stopping: {ex}", level="WARN")
                    break
                page_full = len(fresh) >= INTERNAL_PAGE_SIZE
                batch = [i for i in fresh if i.get("id") not in attempted_ids]
                if not batch:
                    break
                attempted_ids |= {i.get("id") for i in batch}
                planned += len(batch)
                grand_total += len(batch)
                if row is not None:
                    row["total"] = planned
                    row["counter"].value = f"{row['success']} / {planned}"
                log_system(f"--- {category}: found {len(batch)} more item(s) ---")
                page.update()

            if row is not None:
                row["counter"].value = f"{success} / {row['total']}"
            self._results[category] = (success, planned)
            deleted_total += success
            # Items that were tried and failed. Items never reached because
            # of a cancel are reported as skipped, not as failures.
            failed = row["failed"] if row is not None else planned - success
            self._failed_total += failed
            self._progress_header.set_progress(
                deleted_total, grand_total, failed=self._failed_total
            )

            if cancelled:
                self._set_category_state(category, "cancelled")
                log_system(
                    f"--- {category}: cancelled after {success}/{planned} "
                    "deleted ---",
                    level="WARN",
                )
            elif success == planned:
                self._set_category_state(category, "done")
                log_system(f"--- {category}: {success}/{planned} deleted ---")
            else:
                self._set_category_state(category, "failed" if success == 0 else "partial")
                log_system(
                    f"--- {category}: {success}/{planned} deleted, "
                    f"{planned - success} failed ---",
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
        step_row = StepRow(f"Deleting {row_label}...", compact=True)
        if cat_row is not None:
            cat_row["items"].controls.append(step_row)
        page.update()
        await asyncio.sleep(0)
        log_system(f"{category}: deleting {descriptor}")

        try:
            if category in _INTERNAL_DELETERS:
                # Most deleters take a single id. Two need extra data, so
                # special-case them to keep the rest of the client API uniform:
                #   - delete_alarm_site takes (alarm_site_id, site_id);
                #     item["id"] from get_alarm_site is the responseSite.id
                #     (alarm_site_id), which the body's responseSiteId expects.
                #   - delete_schedule takes the full raw schedule object(s)
                #     (an upsert PUT echoes them back with deleted=True),
                #     bundled by get_schedule into item["delete_objects"].
                deleter = getattr(int_client, _INTERNAL_DELETERS[category])
                if category == "Alarm Sites":
                    await loop.run_in_executor(
                        _executor, deleter, item.get("id"), item.get("site_id")
                    )
                elif category == "Schedules":
                    await loop.run_in_executor(
                        _executor, deleter, item.get("delete_objects") or []
                    )
                else:
                    await loop.run_in_executor(_executor, deleter, item_id)
            else:
                method_name = _EXTERNAL_DELETERS[category]
                delete_fn = getattr(ext_client, method_name)
                await loop.run_in_executor(_executor, delete_fn, item_id)

            step_row.succeed(f"Deleted {row_label}")
            if cat_row is not None:
                cat_row["success"] += 1
                cat_row["counter"].value = (
                    f"{cat_row['success']} / {cat_row['total']}"
                )
            page.update()
            log_system(f"{category}: deleted {descriptor}")
            return True
        except Exception as ex:
            if cat_row is not None:
                cat_row["failed"] += 1
            # Sites get a second chance: a site that refuses deletion is
            # renamed "<name>-<mm/dd/yy>" so its original name is freed
            # for future commissioning runs. The rename is a *fallback*, not a
            # deletion — it is reported as a warning and NOT counted as a
            # successful removal (the site still exists in the org).
            if category == "Sites":
                renamed_to = await self._rename_site_fallback(
                    loop, int_client, item_id, item_name
                )
                if renamed_to:
                    step_row.warn(
                        f"Could not delete {row_label} — renamed to "
                        f"'{renamed_to}' (not deleted)"
                    )
                    page.update()
                    log_system(
                        f"{category}: could not delete {descriptor} ({ex}) — "
                        f"renamed to '{renamed_to}' (counted as not deleted)",
                        level="WARN",
                    )
                    return False

            step_row.fail(f"Failed: {row_label} — {ex}")
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
        failures = []
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
                state, label = "pending", f"{category}: skipped (cancelled)"
            elif cancelled_here:
                state = "cancelled"
                label = f"{category}: {success}/{total} deleted (cancelled here)"
            elif success == total:
                state, label = "done", f"{category}: {success}/{total} deleted"
            elif success == 0:
                state, label = "failed", f"{category}: 0/{total} deleted"
            else:
                state, label = "partial", f"{category}: {success}/{total} deleted"
            rows.append(status_row(state, label))
            # Surface anything that didn't fully delete (and wasn't a pure
            # skip) in a failures-first section.
            if not skipped_cat and success < total:
                failures.append(
                    status_row(
                        "failed" if success == 0 else "partial",
                        category,
                        detail=f"{success}/{total} deleted",
                    )
                )

        if skipped:
            title = f"Decommission Cancelled at {self._cancelled_at}"
            report_kind = "warning"
            subtitle = (
                f"{total_success}/{total_items} assets deleted before cancellation."
            )
        else:
            overall_ok = total_success == total_items
            title = "Decommission Complete"
            report_kind = "success" if overall_ok else "warning"
            if overall_ok:
                subtitle = f"All {total_items} assets deleted successfully."
            else:
                remaining = total_items - total_success
                subtitle = (
                    f"{total_success}/{total_items} assets deleted — "
                    f"{remaining} could not be removed."
                )

        actions = ft.Row(
            [
                secondary_button(
                    "Copy report", on_click=self._on_copy_report, icon=ft.Icons.COPY
                ),
                secondary_button(
                    "Export report (CSV)",
                    on_click=self._on_export_report,
                    icon=ft.Icons.DOWNLOAD,
                ),
                primary_button(
                    "Return to Home", on_click=lambda _: self.push_route("/home")
                ),
            ],
            spacing=10,
        )
        controls: list[ft.Control] = [
            section_header(title),
            ft.Container(height=10),
            banner(subtitle, kind=report_kind),
            actions,
        ]
        if failures:
            controls.append(ft.Container(height=8))
            controls.append(
                section_header(
                    "Needs attention",
                    f"{len(failures)} categor"
                    f"{'ies' if len(failures) != 1 else 'y'} did not fully delete",
                )
            )
            controls.extend(failures)
        if self._cleanup:
            controls.append(ft.Container(height=8))
            controls.append(section_header("Cleanup"))
            controls.extend(status_row(state, text) for state, text in self._cleanup)
        controls.append(ft.Container(height=12))
        controls.append(section_header("All categories"))
        controls.append(ft.Column(rows, spacing=8))
        self._content_area.controls = controls

    # ------------------------------------------------------------------
    # Report export
    # ------------------------------------------------------------------

    def _report_rows(self) -> list[dict]:
        """Per-category deletion results as flat dict rows."""
        return [
            {
                "Category": category,
                "Deleted": success,
                "Total": total,
                "Status": "OK" if success == total else "INCOMPLETE",
            }
            for category, (success, total) in self._results.items()
        ]

    def _report_text(self) -> str:
        return "\n".join(
            f"{r['Status']:11} {r['Category']}: {r['Deleted']}/{r['Total']}"
            for r in self._report_rows()
        )

    async def _on_copy_report(self, e):
        try:
            await e.page.clipboard.set(self._report_text())
            show_toast(e.page, "Report copied to clipboard.", kind="success")
        except Exception:
            show_toast(e.page, "Couldn't access the clipboard.", kind="warning")

    def _on_export_report(self, e):
        try:
            path = export_csv(
                self._report_rows(),
                ["Category", "Deleted", "Total", "Status"],
                "decommission_report",
            )
            show_toast(
                e.page, f"Report saved to {path}", kind="success", duration_ms=4000
            )
        except Exception as ex:
            show_alert(e.page, "Export Failed", str(ex))

    def _category_position(self, category: str) -> int:
        """Return a category's position in DELETION_ORDER (or -1 if absent)."""
        try:
            return DELETION_ORDER.index(category)
        except ValueError:
            return -1

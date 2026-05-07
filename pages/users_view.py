import asyncio
from datetime import datetime, timedelta

import flet as ft

from apis.external_api import VerkadaExternalAPIClient
from constants import (
    BG,
    BORDER,
    CARD_PADDING,
    CARD_SHADOW,
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
from utils.db import load_import_settings, save_import_settings
from utils.executor import _executor
from utils.session import get_external_client, get_internal_client, set_external_client
from utils.ui_utils import set_button_loading, show_alert

# Step labels in display order. Used by both the indicator builder and
# (implicitly) by _go_to_step which uses indices into this list.
_STEP_LABELS = ["API Key", "Site & Date", "Review", "Invite"]


# ---------------------------------------------------------------------------
# Small UI factories
# ---------------------------------------------------------------------------
# These exist to cut down on the dozens of repeated keyword arguments that
# show up every time we create a styled text field or primary button. The
# defaults match the original styling exactly; pass overrides as kwargs.


def _make_text_field(
    label: str = "",
    *,
    value: str = "",
    password: bool = False,
    can_reveal_password: bool = False,
) -> ft.TextField:
    """Build a styled TextField with the project's standard look."""
    return ft.TextField(
        label=label,
        value=value,
        password=password,
        can_reveal_password=can_reveal_password,
        border_color=BORDER,
        focused_border_color=PRIMARY,
        color=TEXT_PRIMARY,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
    )


def _make_button(
    text: str,
    on_click,
    *,
    primary: bool = True,
    visible: bool = True,
) -> ft.ElevatedButton:
    """Build a styled ElevatedButton with the project's standard look."""
    return ft.ElevatedButton(
        content=ft.Text(text, color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
        bgcolor=PRIMARY if primary else SECONDARY,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
        height=42,
        visible=visible,
        on_click=on_click,
    )


def _section_heading(title: str, subtitle: str | None = None) -> list[ft.Control]:
    """Build the title/subtitle pair shown at the top of each step."""
    out: list[ft.Control] = [
        ft.Text(title, size=16, color=TEXT_PRIMARY, weight=ft.FontWeight.W_500),
    ]
    if subtitle:
        out.append(ft.Text(subtitle, size=13, color=TEXT_SECONDARY))
    out.append(ft.Container(height=10))
    return out


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


class UsersView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(route="/users", bgcolor=BG, padding=PAGE_PADDING, **kwargs)
        self.push_route = push_route
        self.pop_route = pop_route
        self._current_step = 0
        self._sites: list[dict] = []
        self._participants: list[dict] = []
        self._selected_date = datetime.now()

        # Populated by _build_step_indicators(); a parallel list to _STEP_LABELS
        # holding the circle Containers so we can re-color them by index without
        # walking the row's controls.
        self._step_circles: list[ft.Container] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # Top-level UI scaffolding
    # ------------------------------------------------------------------

    def _build_ui(self):
        self._step_indicators = self._build_step_indicators()
        self._steps = [
            self._build_step_1(),
            self._build_step_2(),
            self._build_step_3(),
            self._build_step_4(),
        ]
        for i, step in enumerate(self._steps):
            step.visible = i == 0

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=TEXT_SECONDARY,
                    on_click=self._on_back,
                ),
                ft.Text(
                    "User Management",
                    size=22,
                    color=TEXT_PRIMARY,
                    weight=ft.FontWeight.W_600,
                ),
            ],
        )

        card_content: list[ft.Control] = [self._step_indicators]
        card_content.extend(self._steps)

        card = ft.Container(
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING),
            content=ft.Column(
                card_content,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                scroll=ft.ScrollMode.ADAPTIVE,
                spacing=FIELD_SPACING,
            ),
            expand=True,
        )

        self.controls = [
            ft.Column([header, ft.Container(height=10), card], expand=True)
        ]

    # ------------------------------------------------------------------
    # Step indicator strip
    # ------------------------------------------------------------------

    def _build_step_indicators(self) -> ft.Row:
        indicators: list[ft.Control] = []
        self._step_circles.clear()
        for i, label in enumerate(_STEP_LABELS):
            color = PRIMARY if i == 0 else BORDER
            circle = ft.Container(
                width=32,
                height=32,
                border_radius=16,
                bgcolor=color,
                content=ft.Text(
                    str(i + 1),
                    color=TEXT_PRIMARY,
                    size=14,
                    text_align=ft.TextAlign.CENTER,
                ),
                alignment=ft.Alignment.CENTER,
            )
            self._step_circles.append(circle)
            indicators.append(
                ft.Column(
                    [
                        circle,
                        ft.Text(
                            label,
                            size=11,
                            color=TEXT_SECONDARY,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=4,
                )
            )
            if i < len(_STEP_LABELS) - 1:
                indicators.append(
                    ft.Container(
                        width=40,
                        height=2,
                        bgcolor=BORDER,
                        margin=ft.margin.only(bottom=18),
                    )
                )
        return ft.Row(indicators, alignment=ft.MainAxisAlignment.CENTER, spacing=8)

    def _update_step_indicators(self):
        """Recolor the circles based on _current_step. Uses the saved circle
        list so we don't have to re-walk the indicator row's children."""
        for i, circle in enumerate(self._step_circles):
            if i < self._current_step:
                circle.bgcolor = SECONDARY
            elif i == self._current_step:
                circle.bgcolor = PRIMARY
            else:
                circle.bgcolor = BORDER

    # ------------------------------------------------------------------
    # Step 1: API Key
    # ------------------------------------------------------------------

    def _build_step_1(self) -> ft.Column:
        settings = load_import_settings()
        self._api_key_field = _make_text_field(
            label="API Key",
            password=True,
            can_reveal_password=True,
            value=settings["api_key"] if settings else "",
        )
        self._import_org_field = _make_text_field(
            label="Org Short Name (External)",
            value=settings["org_short_name"] if settings else "",
        )
        self._connect_btn = _make_button("Connect", self._on_connect)

        return ft.Column(
            [
                *_section_heading(
                    "External Organization",
                    "Enter the API key and org short name for the external organization.",
                ),
                self._api_key_field,
                ft.Container(height=FIELD_SPACING),
                self._import_org_field,
                ft.Container(height=FIELD_SPACING + 5),
                self._connect_btn,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    async def _on_connect(self, e):
        api_key = _strip(self._api_key_field.value)
        org = _strip(self._import_org_field.value)
        if not api_key or not org:
            show_alert(
                e.page,
                "Validation Error",
                "Please fill in both API key and org short name.",
            )
            return

        set_button_loading(self._connect_btn, True, "Connecting")
        await asyncio.sleep(0)

        try:
            loop = asyncio.get_running_loop()
            client = await loop.run_in_executor(
                _executor, VerkadaExternalAPIClient, api_key, org
            )
            set_external_client(client)
            save_import_settings(org, api_key)

            # Load sites for step 2
            self._sites = await loop.run_in_executor(_executor, client.get_sites)
            self._site_dropdown.options = [
                ft.dropdown.Option(key=s["site_id"], text=s["name"])
                for s in self._sites
            ]
            if self._sites:
                self._site_dropdown.value = self._sites[0]["site_id"]

            self._go_to_step(1, e.page)
        except Exception as ex:
            set_button_loading(self._connect_btn, False, "Connect")
            show_alert(e.page, "Connection Failed", str(ex))

    # ------------------------------------------------------------------
    # Step 2: Site & Date
    # ------------------------------------------------------------------

    def _build_step_2(self) -> ft.Column:
        self._site_dropdown = ft.Dropdown(
            label="Site",
            options=[],
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
        )

        self._date_label = ft.Text(
            f"Date: {self._selected_date.strftime('%B %d, %Y')}",
            color=TEXT_PRIMARY,
            size=14,
        )
        self._date_btn = ft.OutlinedButton(
            content=self._date_label,
            style=ft.ButtonStyle(
                side=ft.BorderSide(1, BORDER),
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            height=50,
            on_click=self._open_date_picker,
        )

        self._step2_next_btn = _make_button(
            "Load Participants", self._on_load_participants
        )

        return ft.Column(
            [
                *_section_heading(
                    "Select Site & Date",
                    "Choose the site and date to load guest visits.",
                ),
                self._site_dropdown,
                ft.Container(height=FIELD_SPACING),
                self._date_btn,
                ft.Container(height=FIELD_SPACING + 5),
                self._step2_next_btn,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _open_date_picker(self, e):
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)

        date_picker = ft.DatePicker(
            first_date=one_year_ago,
            last_date=today,
            value=self._selected_date,
            on_change=self._on_date_change,
        )
        e.page.overlay.append(date_picker)
        date_picker.open = True
        e.page.update()

    def _on_date_change(self, e):
        if e.control.value:
            self._selected_date = e.control.value
            self._date_label.value = (
                f"Date: {self._selected_date.strftime('%B %d, %Y')}"
            )
            e.page.update()

    async def _on_load_participants(self, e):
        site_id = self._site_dropdown.value
        if not site_id:
            show_alert(e.page, "Validation Error", "Please select a site.")
            return

        set_button_loading(self._step2_next_btn, True, "Loading")
        await asyncio.sleep(0)

        try:
            client = get_external_client()
            start_ts = int(
                self._selected_date.replace(hour=0, minute=0, second=0).timestamp()
            )
            end_ts = int(
                self._selected_date.replace(hour=23, minute=59, second=59).timestamp()
            )
            loop = asyncio.get_running_loop()
            self._participants = await loop.run_in_executor(
                _executor, client.get_guest_visits, site_id, start_ts, end_ts
            )

            self._rebuild_participants_list()
            self._go_to_step(2, e.page)
        except Exception as ex:
            set_button_loading(self._step2_next_btn, False, "Load Participants")
            show_alert(e.page, "Load Failed", str(ex))

    # ------------------------------------------------------------------
    # Step 3: Review Participants
    # ------------------------------------------------------------------

    def _build_step_3(self) -> ft.Column:
        self._participants_column = ft.Column(spacing=8)
        # Live count rendered next to the heading. Updated whenever the
        # participants list changes (load, add, remove).
        self._participant_count_text = ft.Text(
            "0 participants", size=13, color=TEXT_SECONDARY
        )
        add_btn = ft.TextButton(
            content=ft.Text("+ Add Participant", color=PRIMARY),
            on_click=self._add_participant_row,
        )
        self._invite_btn = _make_button("Invite All", self._on_invite_all)

        return ft.Column(
            [
                *_section_heading(
                    "Review Participants",
                    "Edit the participant list before inviting.",
                ),
                ft.Row(
                    [self._participant_count_text],
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Row(
                    [
                        ft.Text("First Name", color=TEXT_SECONDARY, expand=1, size=12),
                        ft.Text("Last Name", color=TEXT_SECONDARY, expand=1, size=12),
                        ft.Text("Email", color=TEXT_SECONDARY, expand=2, size=12),
                        ft.Container(width=40),
                    ],
                    spacing=10,
                ),
                ft.Divider(color=BORDER, height=1),
                self._participants_column,
                add_btn,
                ft.Container(height=10),
                self._invite_btn,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _update_participant_count(self) -> None:
        """Refresh the live count shown in Step 3's header."""
        n = len(self._participants_column.controls)
        self._participant_count_text.value = (
            "1 participant" if n == 1 else f"{n} participants"
        )

    def _rebuild_participants_list(self):
        self._participants_column.controls.clear()
        for p in self._participants:
            self._participants_column.controls.append(
                self._create_participant_row(
                    p.get("first_name", ""),
                    p.get("last_name", ""),
                    p.get("email", ""),
                )
            )
        self._update_participant_count()

    def _create_participant_row(
        self, first: str = "", last: str = "", email: str = ""
    ) -> ft.Row:
        # Compact inline-style fields (no labels, smaller padding) — different
        # enough from _make_text_field's default look that we keep this inline.
        compact_padding = ft.padding.symmetric(horizontal=10, vertical=8)

        def _participant_field(value: str, expand: int) -> ft.TextField:
            return ft.TextField(
                value=value,
                border_color=BORDER,
                focused_border_color=PRIMARY,
                color=TEXT_PRIMARY,
                content_padding=compact_padding,
                expand=expand,
            )

        first_f = _participant_field(first, expand=1)
        last_f = _participant_field(last, expand=1)
        email_f = _participant_field(email, expand=2)

        row = ft.Row(spacing=10)
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ERROR,
            icon_size=18,
            on_click=lambda _, r=row: self._remove_participant_row(r),
        )
        row.controls = [first_f, last_f, email_f, delete_btn]
        return row

    def _add_participant_row(self, e):
        self._participants_column.controls.append(self._create_participant_row())
        self._update_participant_count()
        e.page.update()

    def _remove_participant_row(self, row):
        if row in self._participants_column.controls:
            self._participants_column.controls.remove(row)
            self._update_participant_count()
            page = getattr(self, "page", None)
            if page:
                page.update()

    async def _on_invite_all(self, e):
        rows = self._participants_column.controls
        if not rows:
            show_alert(
                e.page, "No Participants", "Add at least one participant to invite."
            )
            return

        self._go_to_step(3, e.page)
        await asyncio.sleep(0)
        await self._run_invites(e.page)

    # ------------------------------------------------------------------
    # Step 4: Invite Progress
    # ------------------------------------------------------------------

    def _build_step_4(self) -> ft.Column:
        self._invite_progress = ft.Column(spacing=8)
        # Holds (first, last, email) tuples for participants that were
        # successfully invited. Populated by _run_invites; consumed by
        # _on_copy_invited.
        self._invited_records: list[tuple[str, str, str]] = []
        self._copy_btn = _make_button(
            "Copy Invited List",
            self._on_copy_invited,
            primary=True,
            visible=False,
        )
        self._done_btn = _make_button(
            "Return to Home",
            lambda _: self.push_route("/home"),
            primary=False,
            visible=False,
        )
        return ft.Column(
            [
                *_section_heading("Inviting Participants"),
                self._invite_progress,
                ft.Container(height=15),
                ft.Row(
                    [self._copy_btn, self._done_btn],
                    alignment=ft.MainAxisAlignment.START,
                    spacing=10,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    async def _run_invites(self, page):
        client = get_internal_client()
        loop = asyncio.get_running_loop()
        success_count = 0
        total = 0
        # Reset any prior run's records (defensive — _build_step_4 also inits
        # this, but the user could conceivably rerun a flow without rebuilding
        # the step).
        self._invited_records = []

        for control in self._participants_column.controls:
            if not isinstance(control, ft.Row):
                continue  # only ft.Row instances are added by _create_participant_row
            row: ft.Row = control
            fields = [c for c in row.controls if isinstance(c, ft.TextField)]
            if len(fields) < 3:
                continue
            first = _strip(fields[0].value)
            last = _strip(fields[1].value)
            email_val = _strip(fields[2].value)
            if not email_val:
                continue
            total += 1

            ok = await self._run_invite_step(page, loop, client, first, last, email_val)
            if ok:
                success_count += 1
                self._invited_records.append((first, last, email_val))

        # Final summary line — green if everything succeeded, red otherwise.
        # If `total` ended up at zero (no rows had a non-empty email), report
        # that explicitly rather than showing "0/0 invited".
        if total == 0:
            summary = "No participants with an email were invited."
            color = WARNING
        else:
            summary = f"Complete: {success_count}/{total} invited successfully"
            color = SECONDARY if success_count == total else ERROR

        self._invite_progress.controls.append(
            ft.Container(
                content=ft.Text(summary, color=color, weight=ft.FontWeight.W_600),
                padding=ft.padding.only(top=10),
            )
        )
        # Only show the copy button if there's something to copy.
        self._copy_btn.visible = bool(self._invited_records)
        self._done_btn.visible = True
        page.update()

    async def _run_invite_step(
        self, page, loop, client, first: str, last: str, email_val: str
    ) -> bool:
        """Append a progress row, attempt the invite, and update the row.
        Returns True on success."""
        step_icon = ft.ProgressRing(
            width=16, height=16, stroke_width=2, color=TEXT_SECONDARY
        )
        step_text = ft.Text(
            f"Inviting {first} {last} ({email_val})...",
            color=TEXT_SECONDARY,
            size=13,
        )
        step_row = ft.Row([step_icon, step_text], spacing=10)
        self._invite_progress.controls.append(step_row)
        page.update()
        await asyncio.sleep(0)

        try:
            await loop.run_in_executor(
                _executor, client.invite_user, email_val, first, last
            )
            step_row.controls[0] = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=SECONDARY, size=18
            )
            step_text.value = f"Invited {first} {last} ({email_val})"
            step_text.color = SECONDARY
            page.update()
            return True
        except Exception as ex:
            step_row.controls[0] = ft.Icon(ft.Icons.ERROR, color=ERROR, size=18)
            step_text.value = f"Failed: {first} {last} — {ex}"
            step_text.color = ERROR
            page.update()
            return False

    def _on_copy_invited(self, e):
        """Copy the successfully-invited participants to the clipboard as a
        two-line, tab-separated transposition that pastes cleanly into a
        spreadsheet (one cell per name/email):

            Name One<TAB>Name Two<TAB>Name Three
            one@name.com<TAB>two@name.com<TAB>three@name.com
        """
        if not self._invited_records:
            return  # button shouldn't be visible without records, but be safe

        names = "\t".join(
            f"{first} {last}".strip() for first, last, _ in self._invited_records
        )
        emails = "\t".join(email for _, _, email in self._invited_records)
        text = f"{names}\n{emails}"

        # Flet's new clipboard service is async; schedule it from this sync
        # handler with page.run_task. (page.set_clipboard was removed around
        # Flet 0.28 in favor of ft.Clipboard().set.)
        async def _copy() -> None:
            await ft.Clipboard().set(text)

        e.page.run_task(_copy)

        # Lightweight visual feedback: swap the button label. Doesn't auto-revert
        # because there's no clean way without scheduling a task; users can tell
        # by the clipboard contents.
        if isinstance(self._copy_btn.content, ft.Text):
            self._copy_btn.content.value = "Copied!"
            e.page.update()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_step(self, step: int, page):
        self._current_step = step
        for i, s in enumerate(self._steps):
            s.visible = i == step
        self._update_step_indicators()
        page.update()

    def _on_back(self, e):
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1, e.page)
        else:
            self.push_route("/home")

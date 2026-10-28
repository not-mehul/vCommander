"""Users screen — guest invitation workflow.

Four-step wizard:
  1. Connect to an external Verkada org (org short name + API key; its
     shard and public-API region are looked up from the short name).
  2. Pick a date range and pull guest participants from that org.
  3. Review/edit the list, optionally trim rows.
  4. Send invites against the currently logged-in (internal) org and
     show a copy-able summary of who was invited.
"""

import asyncio
from datetime import datetime, timedelta

import flet as ft

import theme
from apis.external_api import VerkadaExternalAPIClient
from apis.internal_api import (
    PARALLEL_REQUESTS,
    OrgNotFoundError,
    validate_org_short_name,
)
from components import (
    ProgressHeader,
    Stepper,
    StepRow,
    banner,
    card,
    dropdown,
    ghost_button,
    primary_button,
    run_step,
    scroll_area,
    secondary_button,
    section_header,
    set_button_loading,
    text_field,
)
from constants import (
    BORDER,
    CARD_PADDING,
    COMMAND_GROUP_NAME,
    ERROR,
    FIELD_SPACING,
    PRIMARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    load_internal_invite_defaults,
)
from pages.app_shell import ToolView
from utils.cancellation import CancellationToken
from utils.db import load_import_settings, save_import_settings
from utils.executor import _executor
from utils.session import (
    begin_run,
    end_run,
    get_external_client,
    get_internal_client,
    set_external_client,
)
from utils.ui_utils import show_alert, show_toast
from utils.validation import is_valid_email

_STEP_LABELS = ["API Key", "Site & Date", "Review", "Invite"]


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


class UsersView(ToolView):
    def __init__(self, push_route):
        super().__init__(
            push_route,
            route="/users",
            title="User Management",
            subtitle="Invite guest-visit participants from another org into "
            "this one.",
        )
        self._current_step = 0
        self._sites: list[dict] = []
        self._participants: list[dict] = []
        self._selected_date = datetime.now()

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

        steps = ft.Column(
            self._steps,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )
        self.mount(
            card(
                ft.Column(
                    [self._step_indicators, scroll_area(steps)],
                    expand=True,
                ),
                padding=CARD_PADDING,
                expand=True,
            )
        )

    # ------------------------------------------------------------------
    # Step indicator strip
    # ------------------------------------------------------------------

    def _build_step_indicators(self) -> ft.Control:
        """Build the shared Stepper for the four invite steps."""
        self._stepper = Stepper(_STEP_LABELS, current=0)
        return ft.Container(
            content=self._stepper,
            padding=ft.Padding.only(bottom=18),
        )

    def _update_step_indicators(self):
        """Advance the shared Stepper to the current step."""
        self._stepper.set_active(self._current_step)

    # ------------------------------------------------------------------
    # Step 1: API Key
    # ------------------------------------------------------------------

    def _build_step_1(self) -> ft.Column:
        settings = load_import_settings()
        defaults = load_internal_invite_defaults() or {}

        api_key_default = (settings["api_key"] if settings else "") or defaults.get(
            "api_key", ""
        )
        org_default = (settings["org_short_name"] if settings else "") or defaults.get(
            "org_short_name", ""
        )

        self._api_key_field = text_field(
            label="API Key",
            password=True,
            can_reveal_password=True,
            value=api_key_default,
        )
        self._import_org_field = text_field(
            label="Org Short Name (External)",
            value=org_default,
            on_change=self._clear_field_error,
        )
        self._connect_btn = primary_button("Connect", on_click=self._on_connect)

        return ft.Column(
            [
                section_header(
                    "External Organization",
                    "The org your participants visited as guests. Use a public "
                    "API key from that org's Command settings.",
                ),
                ft.Container(height=10),
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
            show_toast(
                e.page,
                "Please fill in both API key and org short name.",
                kind="warning",
            )
            return

        set_button_loading(self._connect_btn, True, "Connecting")
        await asyncio.sleep(0)

        try:
            loop = asyncio.get_running_loop()
            # The source org may live on a different shard/region than the
            # org this session is logged in to; look it up by short name.
            shard = await loop.run_in_executor(
                _executor, validate_org_short_name, org
            )
            client = await loop.run_in_executor(
                _executor,
                VerkadaExternalAPIClient,
                api_key,
                org,
                shard.public_api_region,
            )
            set_external_client(client)
            save_import_settings(org, api_key, shard.public_api_region)
            self._source_org_text.value = (
                f"Connected to {shard.org_name or org}"
                + (f" · {shard.readable_name}" if shard.readable_name else "")
            )

            # Load sites for step 2
            self._sites = await loop.run_in_executor(_executor, client.get_sites)
            self._site_dropdown.options = [
                ft.dropdown.Option(key=s["site_id"], text=s["name"])
                for s in self._sites
            ]
            if self._sites:
                self._site_dropdown.value = self._sites[0]["site_id"]

            self._go_to_step(1, e.page)
        except OrgNotFoundError as ex:
            set_button_loading(self._connect_btn, False, "Connect")
            self._import_org_field.error = str(ex)
            e.page.update()
        except Exception as ex:
            set_button_loading(self._connect_btn, False, "Connect")
            show_alert(e.page, "Connection Failed", str(ex))

    # ------------------------------------------------------------------
    # Step 2: Site & Date
    # ------------------------------------------------------------------

    def _build_step_2(self) -> ft.Column:
        self._source_org_text = ft.Text(
            "", size=theme.FONT_CAPTION, color=theme.TEXT_MUTED
        )
        self._site_dropdown = dropdown("Guest site", [])
        self._date_btn = secondary_button(
            self._date_text(),
            on_click=self._open_date_picker,
            icon=ft.Icons.CALENDAR_MONTH,
            height=52,
            width=240,
        )
        self._step2_next_btn = primary_button(
            "Load Participants", on_click=self._on_load_participants, expand=True
        )

        return ft.Column(
            [
                section_header(
                    "Select Site & Date",
                    "Participants are the guests who visited this site on "
                    "this day.",
                ),
                self._source_org_text,
                ft.Container(height=10),
                ft.Row(
                    [self._site_dropdown, self._date_btn],
                    spacing=FIELD_SPACING,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(height=FIELD_SPACING + 5),
                ft.Row([self._back_button(0), self._step2_next_btn], spacing=10),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def _date_text(self) -> str:
        return self._selected_date.strftime("%B %d, %Y")

    def _back_button(self, to_step: int) -> ft.Control:
        """Step back without losing what was loaded (Esc leaves the tool)."""
        return ghost_button(
            "Back",
            on_click=lambda e: self._go_to_step(to_step, e.page),
            color=TEXT_SECONDARY,
            icon=ft.Icons.ARROW_BACK,
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
        # Flet 0.85 presents the picker via show_dialog rather than the old
        # overlay-append + .open pattern.
        e.page.show_dialog(date_picker)

    def _on_date_change(self, e):
        if e.control.value:
            self._selected_date = e.control.value
            self._date_btn.content.controls[1].value = self._date_text()
            e.page.update()

    async def _on_load_participants(self, e):
        site_id = self._site_dropdown.value
        if not site_id:
            show_toast(e.page, "Please select a site.", kind="warning")
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
        self._participant_count_text = ft.Text(
            "0 participants", size=13, color=TEXT_SECONDARY
        )
        add_btn = ft.Row(
            [
                ghost_button(
                    "Add participant",
                    on_click=self._add_participant_row,
                    icon=ft.Icons.PERSON_ADD_ALT_1,
                )
            ]
        )
        self._invite_btn = primary_button(
            "Invite All", on_click=self._on_invite_all, expand=True
        )

        # Gates the group step in _run_invites. On by default: the common
        # case is that every invited participant belongs in the group.
        self._add_to_group_switch = ft.Switch(
            label=f" Add invited users to '{COMMAND_GROUP_NAME}'",
            value=True,
            active_color=PRIMARY,
            label_text_style=ft.TextStyle(color=TEXT_PRIMARY),
        )

        return ft.Column(
            [
                section_header(
                    "Review Participants",
                    "Edit the participant list before inviting.",
                ),
                ft.Container(height=10),
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
                self._add_to_group_switch,
                ft.Container(height=10),
                ft.Row([self._back_button(1), self._invite_btn], spacing=10),
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
        def _participant_field(value: str, expand: int) -> ft.TextField:
            return text_field(
                value=value or "",
                expand=expand,
                compact=True,
                on_change=self._clear_field_error,
            )

        first_f = _participant_field(first, expand=1)
        last_f = _participant_field(last, expand=1)
        email_f = _participant_field(email, expand=2)

        row = ft.Row(spacing=10)
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ERROR,
            icon_size=18,
            tooltip="Remove",
            on_click=lambda _, r=row: self._remove_participant_row(r),
        )
        row.controls = [first_f, last_f, email_f, delete_btn]
        return row

    @staticmethod
    def _clear_field_error(e) -> None:
        if e.control.error:
            e.control.error = None
            e.page.update()

    def _validate_emails(self) -> bool:
        """Mark malformed emails; rows with no email are skipped as before."""
        ok = True
        for row in self._participants_column.controls:
            fields = [c for c in row.controls if isinstance(c, ft.TextField)]
            if len(fields) == 3:
                email = _strip(fields[2].value)
                if email and not is_valid_email(email):
                    fields[2].error = "Enter a valid email"
                    ok = False
        return ok

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
            show_toast(
                e.page, "Add at least one participant to invite.", kind="warning"
            )
            return
        if not self._validate_emails():
            show_toast(
                e.page,
                "Fix the highlighted emails, or remove those rows.",
                kind="warning",
            )
            e.page.update()
            return

        token = CancellationToken()
        if not begin_run("Invite", token):
            show_toast(
                e.page,
                "Another run is still stopping — try again in a moment.",
                kind="warning",
            )
            return
        self._go_to_step(3, e.page)
        await asyncio.sleep(0)
        try:
            await self._run_invites(e.page, token)
        finally:
            end_run(token)

    # ------------------------------------------------------------------
    # Step 4: Invite Progress
    # ------------------------------------------------------------------

    def _build_step_4(self) -> ft.Column:
        self._invite_progress = ft.Column(spacing=8)
        self._invite_header = ProgressHeader(determinate=True)
        self._invite_result = ft.Container(visible=False)
        # Holds (first, last, email) tuples for participants that were
        # successfully invited. Populated by _run_invites; consumed by
        # _on_copy_invited.
        self._invited_records: list[tuple[str, str, str]] = []
        self._copy_btn = primary_button(
            "Copy Invited List", on_click=self._on_copy_invited
        )
        self._copy_btn.visible = False
        self._done_btn = secondary_button(
            "Return to Home", on_click=lambda _: self.push_route("/home")
        )
        self._done_btn.visible = False
        return ft.Column(
            [
                section_header("Inviting Participants"),
                ft.Container(height=10),
                self._invite_header,
                self._invite_result,
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

    async def _run_invites(self, page, token: CancellationToken):
        client = get_internal_client()
        success_count = 0
        self._invited_records = []
        invited_user_ids: list[str] = []

        # Participants with an email, in list order (rows without one are
        # skipped, as before). Collected first so progress has a total.
        people = []
        for row in self._participants_column.controls:
            fields = [c for c in row.controls if isinstance(c, ft.TextField)]
            if len(fields) == 3 and _strip(fields[2].value):
                people.append(tuple(_strip(f.value) for f in fields))
        total = len(people)
        self._invite_header.set_progress(0, total)
        done = 0

        # People already in the org (one user list call) are not re-invited
        # — the invite would be refused — but still join the Command group.
        # If the lookup fails, everyone is invited as before.
        already_count = 0
        if people:
            ok, existing = await self._progress_step(
                page,
                "Checking for existing users",
                "Checked for existing users",
                "Could not check for existing users",
                client.get_user_ids_by_email,
            )
            existing = (existing or {}) if ok else {}
            remaining = []
            for first, last, email_val in people:
                user_id = existing.get(email_val.lower())
                if user_id is None:
                    remaining.append((first, last, email_val))
                    continue
                who = f"{first} {last}".strip()
                row = StepRow(email_val)
                row.succeed(f"Already in the org: {who} ({email_val})")
                self._invite_progress.controls.append(row)
                invited_user_ids.append(user_id)
                done += 1
                success_count += 1
                already_count += 1
            people = remaining
            self._invite_header.set_progress(done, total)
            page.update()

        # Invites go out PARALLEL_REQUESTS at a time (one progress row each,
        # in list order); cancelling stops before the next chunk.
        for start in range(0, len(people), PARALLEL_REQUESTS):
            chunk = people[start : start + PARALLEL_REQUESTS]
            if token.is_cancelled:
                for _first, _last, email_val in chunk:
                    row = StepRow(email_val)
                    row.skip(f"Skipped {email_val} (cancelled)")
                    self._invite_progress.controls.append(row)
                continue

            results = await asyncio.gather(
                *(
                    self._run_invite_step(page, client, first, last, email_val)
                    for first, last, email_val in chunk
                )
            )
            for (first, last, email_val), (ok, user_id) in zip(chunk, results, strict=True):
                done += 1
                if ok:
                    success_count += 1
                    self._invited_records.append((first, last, email_val))
                    if user_id:
                        invited_user_ids.append(user_id)
            self._invite_header.set_progress(
                done, total, failed=done - success_count
            )
            page.update()

        # Group membership runs once for the whole batch — add_users_to_group
        # takes the id list, so one call covers everyone invited this run.
        # Skipped entirely when the Step 3 toggle is off.
        if self._add_to_group_switch.value and not token.is_cancelled:
            if invited_user_ids:
                await self._add_invited_to_command_group(
                    page, client, invited_user_ids
                )
            elif success_count:
                self._invite_progress.controls.append(
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_ROUNDED, color=WARNING, size=18),
                            ft.Text(
                                f"Invited users carried no user id — skipped "
                                f"'{COMMAND_GROUP_NAME}'.",
                                color=WARNING,
                                size=13,
                            ),
                        ],
                        spacing=10,
                    )
                )

        if total == 0:
            summary, kind = "No participants with an email were invited.", "warning"
        elif token.is_cancelled:
            summary = f"Stopped: {success_count}/{total} invited before cancelling."
            kind = "warning"
        elif success_count == total and already_count:
            summary = (
                f"{total - already_count} invited; {already_count} already in "
                f"the org."
            )
            kind = "success"
        elif success_count == total:
            summary, kind = f"All {total} participants invited.", "success"
        else:
            summary = (
                f"{success_count}/{total} invited — "
                f"{total - success_count} could not be invited."
            )
            kind = "warning"
        self._invite_header.complete(
            color=theme.SUCCESS if kind == "success" else theme.WARNING
        )
        self._invite_result.content = banner(summary, kind=kind)
        self._invite_result.visible = True
        self._copy_btn.visible = bool(self._invited_records)
        self._done_btn.visible = True
        page.update()

    async def _progress_step(
        self,
        page,
        label: str,
        success_label: str,
        fail_label: str,
        fn,
        *args,
    ) -> tuple[bool, object]:
        """Run `fn` with a live progress row; returns (ok, result)."""
        ok, result, _ = await run_step(
            page,
            self._invite_progress,
            label,
            fn,
            *args,
            success_text=success_label,
            failure_text=fail_label,
        )
        return ok, result

    async def _run_invite_step(
        self, page, client, first: str, last: str, email_val: str
    ) -> tuple[bool, str | None]:
        """Append a progress row, attempt the invite, and update the row.

        Returns (ok, user_id). user_id is None when the invite failed, or
        when it succeeded but the response carried no user details — such a
        user cannot be added to a group here.
        """
        who = f"{first} {last}".strip()
        ok, result = await self._progress_step(
            page,
            f"Inviting {who} ({email_val})",
            f"Invited {who} ({email_val})",
            f"Failed: {who}",
            client.invite_user,
            email_val,
            first,
            last,
        )
        return ok, (result or {}).get("user_id")

    async def _add_invited_to_command_group(
        self, page, client, user_ids: list[str]
    ) -> bool:
        """
        Add the freshly invited users to the shared Command group, creating
        the group the first time it is needed.

        Reuses an existing group by name so repeated invite runs collect
        into one group. Note that get_group() hides Verkada-managed groups,
        so only a group created by this tool (or by hand) is ever matched.
        """
        ok, groups = await self._progress_step(
            page,
            f"Looking up group '{COMMAND_GROUP_NAME}'",
            f"Looked up group '{COMMAND_GROUP_NAME}'",
            "Failed: group lookup",
            client.get_group,
        )
        if not ok:
            return False

        group_id = next(
            (g["id"] for g in groups or [] if g.get("name") == COMMAND_GROUP_NAME),
            None,
        )
        if not group_id:
            ok, group_id = await self._progress_step(
                page,
                f"Creating group '{COMMAND_GROUP_NAME}'",
                f"Created group '{COMMAND_GROUP_NAME}'",
                f"Failed: creating group '{COMMAND_GROUP_NAME}'",
                client.create_group,
                COMMAND_GROUP_NAME,
            )
            if not ok:
                return False

        count = len(user_ids)
        plural = "" if count == 1 else "s"
        ok, _ = await self._progress_step(
            page,
            f"Adding {count} user{plural} to '{COMMAND_GROUP_NAME}'",
            f"Added {count} user{plural} to '{COMMAND_GROUP_NAME}'",
            f"Failed: adding users to '{COMMAND_GROUP_NAME}'",
            client.add_users_to_group,
            user_ids,
            group_id,
        )
        return ok

    def _on_copy_invited(self, e):
        """Copy the successfully-invited participants to the clipboard as a
        two-line, tab-separated transposition that pastes cleanly into a
        spreadsheet (one cell per name/email):

            Name One<TAB>Name Two<TAB>Name Three
            one@name.com<TAB>two@name.com<TAB>three@name.com
        """
        if not self._invited_records:
            return  # button shouldn't be visible without records, but be safe
        sorted_records = sorted(
            self._invited_records, key=lambda r: f"{r[0]} {r[1]}".strip().lower()
        )

        # 2. Build the tab-separated strings from the sorted list
        names = "\t".join(
            f"{first} {last}".strip() for first, last, _ in sorted_records
        )
        emails = "\t".join(email for _, _, email in sorted_records)
        text = f"{names}\n{emails}"

        async def _copy() -> None:
            await ft.Clipboard().set(text)

        e.page.run_task(_copy)
        show_toast(
            e.page,
            f"Copied {len(sorted_records)} invited participants to clipboard.",
            kind="success",
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_step(self, step: int, page):
        self._current_step = step
        for i, s in enumerate(self._steps):
            s.visible = i == step
        self._update_step_indicators()
        page.update()

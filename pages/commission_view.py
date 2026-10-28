"""Commission screen.

Drives one of the predefined org-setup flows (ESS / ACSL / ACSE / VSSL /
VSSE / AS — see TEMPLATE_FIELDS in constants.py). The user picks a template
and a kit (assets/kits.csv), confirms the auto-filled device serials
and supporting users, then `_run_step` walks through site/building/
device creation against the internal API. Each step's success/failure
is rendered in the live progress panel.

The run's outcome is derived from the step counters, never tracked by
hand. Every step goes through the internal API, as the Command web app
does, so a run needs no temporary public-API key."""

import asyncio
import csv
import functools
import os
from typing import Any

import flet as ft

import theme
from apis.internal_api import PARALLEL_REQUESTS, normalize_serial
from components import (
    ProgressHeader,
    RawLogPanel,
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
    stat_row,
    status_row,
    text_field,
)
from constants import (
    ACSL_ACCESS_STATION_PRO_DOOR_NAME,
    ACSL_ACCESS_STATION_PRO_NAME,
    ACSL_ADDRESS,
    ACSL_BUILDING_NAME,
    ACSL_FLOORS,
    ACSL_MFA_DOOR_SCHEDULE_NAME,
    ACSL_SITE_NAME,
    AS_ACCESS_LEVEL_NAME,
    AS_ADDRESS,
    AS_ALARM_ADDRESS,
    AS_BUILDING_NAME,
    AS_CONTROLLER_NAME,
    AS_DOME_NAME,
    AS_DOOR_NAME,
    AS_FLOORS,
    AS_KEYPAD_NAME,
    AS_PANEL_NAME,
    AS_SITE_NAME,
    AS_STROBE_OUTPUT_NAME,
    AS_STROBE_OUTPUT_PIN,
    BORDER,
    BUILDING_PROVISION_SECONDS,
    CARD_PADDING,
    ERROR,
    ESS_ACCESS_STATION_PRO_DOOR_NAME,
    ESS_ACCESS_STATION_PRO_NAME,
    ESS_ADDRESS,
    ESS_ALARM_ADDRESS,
    ESS_BUILDING_NAME,
    ESS_CAMERA_NAME,
    ESS_FLOORS,
    ESS_GUEST_ADDRESS,
    ESS_PANEL_NAME,
    ESS_SITE_NAME,
    FIELD_SPACING,
    HQ_TIMEZONE,
    LICENSE_PLATE_FIELD,
    PRIMARY,
    ROLE_PROPAGATION_SECONDS,
    SECONDARY,
    TEMPLATE_DISPLAY_NAMES,
    TEMPLATE_FIELDS,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    VSS_ACCESS_GROUP_NAME,
    VSS_ACCESS_LEVEL_NAME,
    VSS_ADDRESS,
    VSS_BUILDING_NAME,
    VSS_BULLET_NAME,
    VSS_CONNECTOR_NAME,
    VSS_CONTROLLER_NAME,
    VSS_DOOR_NAME,
    VSS_EXAM_BULLET_NAME,
    VSS_EXAM_DOME_NAME,
    VSS_EXAM_FISHEYE_NAME,
    VSS_EXAM_SITE_NAME,
    VSS_FLOORS,
    VSS_PTZ_NAME,
    VSS_SITE_NAME,
    WARNING,
)
from pages.app_shell import ToolView
from utils.cancellation import CancellationToken
from utils.export import export_csv
from utils.session import begin_run, end_run, get_internal_client
from utils.ui_utils import show_alert, show_toast
from utils.validation import (
    SERIAL_DISPLAY_LEN,
    SERIAL_PLACEHOLDER,
    format_serial,
    is_valid_email,
    is_valid_serial,
)

_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)

_COMMISSION_STEPS = ["Configure", "Review", "Run", "Report"]


class CommissionView(ToolView):
    def __init__(self, push_route):
        super().__init__(
            push_route,
            route="/commission",
            title="Commission Organization",
            subtitle="Build a training org from a template, then invite "
            "supporting users.",
        )
        self._kits: dict[str, dict[str, str]] = {}
        self._device_fields: dict[str, ft.TextField] = {}
        # Cooperative cancel for the commission step loop. Checked
        # between steps; the in-flight step is allowed to complete.
        self._cancel_token: CancellationToken | None = None
        # Run tracking for the structured progress/report screen.
        self._steps_done = 0
        self._steps_failed = 0
        self._failures: list[tuple[str, str]] = []
        self._run_log: list[str] = []
        self._load_kits()
        self._build_ui()

    # ------------------------------------------------------------------
    # CSV / data loading
    # ------------------------------------------------------------------

    def _load_kits(self):
        internal = os.path.join(_ASSETS_DIR, "kits.internal.csv")
        public = os.path.join(_ASSETS_DIR, "kits.csv")
        path = internal if os.path.exists(internal) else public
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                kit_name = r["Kit Name"]
                if kit_name not in self._kits:
                    self._kits[kit_name] = {}
                self._kits[kit_name][r["Device Type"]] = r["Serial Number"]

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        template_options = [
            ft.dropdown.Option(key=code, text=TEMPLATE_DISPLAY_NAMES[code])
            for code in TEMPLATE_FIELDS
        ]
        self.template_dropdown = dropdown(
            "Template", template_options, on_select=self._on_template_change
        )

        kit_options = [
            ft.dropdown.Option(key="", text="No kit — enter serials manually")
        ] + [ft.dropdown.Option(k) for k in self._kits]
        self.kit_dropdown = dropdown("Kit", kit_options, on_select=self._on_kit_change)

        self._devices_column = ft.Column(
            [self._devices_hint("Choose a template to see the devices it needs.")],
            spacing=FIELD_SPACING,
        )

        self.face_analytics_switch = ft.Switch(
            label=" Face Analytics",
            value=True,
            active_color=PRIMARY,
            label_text_style=ft.TextStyle(color=TEXT_PRIMARY),
            visible=False,
        )

        self._users_column = ft.Column(spacing=10)
        add_user_btn = ft.Row(
            [
                ghost_button(
                    "Add supporting user",
                    on_click=self._add_user_row,
                    icon=ft.Icons.PERSON_ADD_ALT_1,
                )
            ]
        )

        # Configure-step primary action advances to the Review summary
        # rather than running immediately.
        self.commission_btn = primary_button(
            "Review", on_click=self._on_review, height=45, expand=True
        )
        # Cancel is shown during the Run step (next to the live progress),
        # hidden otherwise.
        self.cancel_btn = secondary_button(
            "Cancel", on_click=self._on_cancel, tone="danger"
        )
        self.cancel_btn.visible = False
        self._button_row = ft.Row([self.commission_btn], spacing=10)

        self._progress_column = ft.Column(spacing=8, visible=False)

        self._form_section = ft.Column(
            [
                ft.Row(
                    [self.template_dropdown, self.kit_dropdown],
                    spacing=FIELD_SPACING,
                ),
                ft.Container(height=4),
                self._devices_column,
                self.face_analytics_switch,
                ft.Divider(color=BORDER, height=1),
                section_header(
                    "Supporting users",
                    "Optional. Invited as Org Admins once the org is set up.",
                ),
                self._users_column,
                add_user_btn,
                ft.Container(height=8),
                self._button_row,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )

        # Configure -> Review -> Run -> Report stepper, plus the Review and
        # Run panels (hidden until their step). The form_section is the
        # Configure step; _progress_column is the Run/Report step.
        self._stepper = Stepper(_COMMISSION_STEPS, current=0)
        self._review_section = ft.Column(
            visible=False,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )
        # Total commission steps aren't known up front (flows branch by
        # template), so the run bar is indeterminate and reports live counts.
        self._progress_header = ProgressHeader(determinate=False)
        self._run_section = ft.Column(
            [
                self._progress_header,
                ft.Row([self.cancel_btn]),
                self._progress_column,
            ],
            visible=False,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )

        sections = ft.Column(
            [self._form_section, self._review_section, self._run_section],
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
                        scroll_area(sections),
                    ],
                    expand=True,
                ),
                padding=CARD_PADDING,
                expand=True,
            )
        )

    @staticmethod
    def _devices_hint(text: str) -> ft.Control:
        return ft.Text(text, size=theme.FONT_CAPTION, color=theme.TEXT_MUTED)

    def _make_device_field(self, device_type: str, expand=None) -> ft.TextField:
        # License Plate holds a plate string rather than a device serial, so
        # it keeps a plain free-text field — no mask, no length cap.
        is_serial = device_type != LICENSE_PLATE_FIELD
        field = text_field(
            f"{device_type} S/N" if is_serial else device_type,
            expand=expand,
            hint=SERIAL_PLACEHOLDER if is_serial else None,
            max_length=SERIAL_DISPLAY_LEN if is_serial else None,
            on_change=self._on_serial_change if is_serial else None,
        )
        self._device_fields[device_type] = field
        return field

    def _on_serial_change(self, e) -> None:
        """
        Re-apply the serial mask on every keystroke so the field can only
        ever hold well-formed input: upper-cased, separators inserted, and
        anything else dropped as it is typed.
        """
        field = e.control
        masked = format_serial(field.value)
        if masked != field.value:
            field.value = masked
            e.page.update()

    # ------------------------------------------------------------------
    # Form event handlers
    # ------------------------------------------------------------------

    def _on_template_change(self, e):
        code = self.template_dropdown.value
        if not code or code not in TEMPLATE_FIELDS:
            self._devices_column.controls = [
                self._devices_hint("Choose a template to see the devices it needs.")
            ]
            self.face_analytics_switch.visible = False
            e.page.update()
            return

        config = TEMPLATE_FIELDS[code]
        self._device_fields.clear()
        devices = config["devices"]
        rows = []
        for i in range(0, len(devices), 2):
            pair = devices[i : i + 2]
            row_fields: list[ft.Control] = [
                self._make_device_field(d, expand=1) for d in pair
            ]
            rows.append(ft.Row(row_fields, spacing=FIELD_SPACING))
        self._devices_column.controls = rows or [
            self._devices_hint("This template doesn't claim any devices.")
        ]
        self.face_analytics_switch.visible = config["face_analytics"]
        self.face_analytics_switch.value = config["face_analytics"]

        if self.kit_dropdown.value:
            self._fill_from_kit(self.kit_dropdown.value)

        e.page.update()

    def _on_kit_change(self, e):
        kit_name = self.kit_dropdown.value
        if kit_name:
            self._fill_from_kit(kit_name)
        else:
            for field in self._device_fields.values():
                field.value = ""
        e.page.update()

    def _fill_from_kit(self, kit_name: str):
        kit_data = self._kits.get(kit_name, {})
        for device_type, field in self._device_fields.items():
            value = kit_data.get(device_type, "")
            # Kit values go through the same mask, so a serial field always
            # shows what typing the same characters would have produced.
            field.value = (
                value if device_type == LICENSE_PLATE_FIELD else format_serial(value)
            )

    def _add_user_row(self, e):
        row = self._create_user_row()
        self._users_column.controls.append(row)
        e.page.update()

    def _create_user_row(self) -> ft.Row:
        def field(label: str, expand: int) -> ft.TextField:
            return text_field(
                label, expand=expand, compact=True, on_change=self._clear_field_error
            )

        row = ft.Row(spacing=10)
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ERROR,
            tooltip="Remove",
            on_click=lambda _, r=row: self._remove_user_row(r),
        )
        row.controls = [
            field("First name", 1),
            field("Last name", 1),
            field("Email", 2),
            delete_btn,
        ]
        return row

    @staticmethod
    def _clear_field_error(e) -> None:
        if e.control.error:
            e.control.error = None
            e.page.update()

    def _remove_user_row(self, row):
        if row in self._users_column.controls:
            self._users_column.controls.remove(row)
            page = getattr(self, "page", None)
            if page:
                page.update()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _device_serial(self, device_type: str) -> str:
        """Return the trimmed value of a device field, '' if missing/empty."""
        field = self._device_fields.get(device_type)
        return (field.value or "").strip() if field else ""

    def _validate_form(self, e) -> tuple[bool, str | None]:
        """
        Returns (ok, code). When ok is False, an alert has already been shown.
        When ok is True, code is the selected template code.
        """
        code = self.template_dropdown.value
        if not code or code not in TEMPLATE_FIELDS:
            show_toast(e.page, "Please select a template.", kind="warning")
            return False, None

        config = TEMPLATE_FIELDS[code]
        for device_type in config["devices"]:
            value = self._device_serial(device_type)
            is_serial = device_type != LICENSE_PLATE_FIELD
            if not value:
                show_toast(
                    e.page,
                    f"Please enter the {device_type} serial number."
                    if is_serial
                    else f"Please enter the {device_type}.",
                    kind="warning",
                )
                return False, None
            # The mask keeps the field well-formed while typing; this
            # catches the half-typed case (e.g. "A1A1-B2") on submit.
            if is_serial and not is_valid_serial(value):
                show_toast(
                    e.page,
                    f"{device_type} serial number must look like "
                    f"{SERIAL_PLACEHOLDER}.",
                    kind="warning",
                )
                return False, None

        if not self._validate_supporting_users():
            show_toast(
                e.page,
                "Fix the highlighted supporting users, or remove those rows.",
                kind="warning",
            )
            e.page.update()
            return False, None

        return True, code

    def _user_rows(self) -> list[list[ft.TextField]]:
        """[first, last, email] fields for each supporting-user row."""
        rows = []
        for row in self._users_column.controls:
            fields = [c for c in row.controls if isinstance(c, ft.TextField)]
            if len(fields) == 3:
                rows.append(fields)
        return rows

    def _validate_supporting_users(self) -> bool:
        """Flag rows that are partly filled or have a malformed email.

        Fully empty rows are ignored. Anything else must be complete, so the
        Review count always matches who is actually invited.
        """
        ok = True
        for fields in self._user_rows():
            values = [(f.value or "").strip() for f in fields]
            if not any(values):
                continue
            for f, v in zip(fields, values, strict=True):
                if not v:
                    f.error = "Required"
                    ok = False
            email = fields[2]
            if values[2] and not is_valid_email(values[2]):
                email.error = "Enter a valid email"
                ok = False
        return ok

    # ------------------------------------------------------------------
    # Review step
    # ------------------------------------------------------------------

    def _collect_supporting_users(self) -> list[tuple[str, str, str]]:
        """(first, last, email) for each complete supporting-user row.

        Same rule as the invite step, so Review shows exactly who is invited.
        """
        users: list[tuple[str, str, str]] = []
        for fields in self._user_rows():
            first, last, email = ((f.value or "").strip() for f in fields)
            if first and last and email:
                users.append((first, last, email))
        return users

    def _on_review(self, e):
        """Configure -> Review: validate, then show the pre-flight summary."""
        ok, code = self._validate_form(e)
        if not ok:
            return
        self._review_section.controls = self._build_review_summary(code)
        self._stepper.set_active(1)
        self._form_section.visible = False
        self._review_section.visible = True
        self._run_section.visible = False
        e.page.update()

    def _on_edit(self, e):
        """Review -> Configure: go back to editing the form."""
        self._stepper.set_active(0)
        self._form_section.visible = True
        self._review_section.visible = False
        e.page.update()

    def _build_review_summary(self, code: str) -> list[ft.Control]:
        """Build the Review panel: what will be created + Edit/Confirm."""
        config = TEMPLATE_FIELDS[code]
        rows: list[ft.Control] = [
            stat_row("Template", TEMPLATE_DISPLAY_NAMES.get(code, code)),
            stat_row("Kit", (self.kit_dropdown.value or "").strip() or "—"),
        ]
        for device_type in config["devices"]:
            rows.append(
                stat_row(device_type, self._device_serial(device_type) or "—")
            )
        if config.get("face_analytics"):
            rows.append(
                stat_row(
                    "Face Analytics",
                    "On" if self.face_analytics_switch.value else "Off",
                )
            )
        users = self._collect_supporting_users()
        rows.append(stat_row("Supporting Users", len(users)))
        for first, last, email in users:
            rows.append(
                ft.Text(
                    f"   • {first} {last}  ·  {email}".rstrip(),
                    size=12,
                    color=TEXT_SECONDARY,
                )
            )

        inset = ft.Container(
            bgcolor=theme.SURFACE_VARIANT,
            border=ft.Border.all(1, BORDER),
            border_radius=theme.RADIUS_MD,
            padding=ft.Padding.all(CARD_PADDING),
            content=ft.Column(rows, spacing=theme.SPACE_SM),
        )

        confirm_btn = primary_button(
            "Commission Organization",
            on_click=self._on_commission,
            height=45,
            expand=True,
        )

        return [
            section_header(
                "Review", "Confirm what will be created before commissioning."
            ),
            inset,
            ft.Row(
                [
                    ghost_button(
                        "Edit", on_click=self._on_edit, icon=ft.Icons.ARROW_BACK
                    ),
                    confirm_btn,
                ],
                spacing=10,
            ),
        ]

    # ------------------------------------------------------------------
    # Commission orchestration
    # ------------------------------------------------------------------

    async def _on_commission(self, e):
        page = e.page
        ok, code = self._validate_form(e)
        if not ok:
            return
        try:
            client = get_internal_client()
        except RuntimeError as ex:
            show_alert(page, "Not Logged In", str(ex))
            return
        token = CancellationToken()
        if not begin_run("Commission", token):
            show_toast(
                page,
                "Another run is still stopping — try again in a moment.",
                kind="warning",
            )
            return

        # Review -> Run: swap panels, advance the stepper, arm cancellation.
        self._stepper.set_active(2)
        self._form_section.visible = False
        self._review_section.visible = False
        self._run_section.visible = True
        self._progress_column.controls.clear()
        self._progress_column.visible = True
        # Reset run tracking for the structured progress header / report.
        self._steps_done = 0
        self._steps_failed = 0
        self._failures = []
        self._run_log = []
        self._progress_header.set_progress(0, failed=0)
        self._cancel_token = token
        self.cancel_btn.visible = True
        self.cancel_btn.disabled = False
        if isinstance(self.cancel_btn.content, ft.Text):
            self.cancel_btn.content.value = "Cancel"
        page.update()
        await asyncio.sleep(0)

        try:
            await self._commission(page, code, client)
        except Exception as ex:
            # A bug in flow code must still end in a report, not a frozen
            # Run screen; count it as a failed step.
            self._record_step("Unexpected error", ok=False, error=ex)
        finally:
            end_run(token)
        self._render_summary(page)

    async def _commission(self, page, code: str, client) -> None:
        """Run the shared prelude, the template's flow and the user invites."""

        async def step(label: str, fn, *args):
            return await self._run_step(page, label, fn, *args)

        # ── Common prelude (every template) ──
        await step("Enabling Custom Roles", client.enable_custom_roles)
        self._progress_note(page, "Waiting for roles to propagate...")
        await asyncio.sleep(ROLE_PROPAGATION_SECONDS)
        await step("Disabling Global Site Admin", client.disable_global_site_admin)

        # ── Per-template flows ──
        if code == "ESS":
            await self._run_ess_flow(step, page, client)
        elif code == "ACSL":
            await self._run_acsl_flow(step, page, client)
        elif code == "ACSE":
            # No additional steps beyond the prelude.
            pass
        elif code == "VSSL":
            await self._run_vssl_flow(step, page, client)
        elif code == "VSSE":
            await self._run_vsse_flow(step, page, client)
        elif code == "AS":
            await self._run_as_flow(step, page, client)

        # ── Supporting users — shared across all templates ──
        await self._invite_supporting_users(step, page, client, "Org Admin")

    # ------------------------------------------------------------------
    # Per-template flows
    # ------------------------------------------------------------------

    async def _run_ess_flow(self, step, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        panel_serial = self._device_serial("Alarm Panel")
        access_station_pro_serial = self._device_serial("Access Station Pro")

        site_id = await step("Creating Site", client.create_or_reuse_site, ESS_SITE_NAME)

        camera_id, panel_id, access_station_pro_id = await self._add_devices(
            step,
            client,
            [
                (f"Adding Camera ({dome_serial})", ESS_CAMERA_NAME, dome_serial),
                (f"Adding Alarm Panel ({panel_serial})", ESS_PANEL_NAME, panel_serial),
                (f"Adding Access Station Pro ({access_station_pro_serial})", ESS_ACCESS_STATION_PRO_NAME, access_station_pro_serial),
            ],
        )

        floor_id = await step(
            "Creating Building",
            client.create_or_reuse_building,
            ESS_BUILDING_NAME,
            ESS_ADDRESS,
            ESS_FLOORS,
        )

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        if camera_id and site_id:
            _ = await step(
                "Configuring Camera",
                client.configure_cameras,
                [camera_id],
                site_id,
                ESS_ADDRESS,
            )

        _ = await step(
            "Enabling Org Features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )

        _ = await step(
            "Enabling Org Face-Unlock",
            client.enable_org_face_unlock,
        )

        if self.face_analytics_switch.value and camera_id:
            _ = await step(
                "Enabling Camera Analytics",
                client.enable_camera_analytics,
                [camera_id],
            )

        if site_id:
            alarm_response_id = await step(
                "Creating Alarm Site",
                client.create_alarm_site,
                "Verkada",
                ESS_ALARM_ADDRESS,
                site_id,
            )

            if alarm_response_id:
                _ = await step(
                    "Setting response to Self-Monitored",
                    client.set_alarm_self_monitored,
                    site_id,
                    alarm_response_id,
                )

            _ = await step(
                "Creating Guest Site",
                client.create_guest_site,
                ESS_GUEST_ADDRESS,
                site_id,
            )

        if panel_id and site_id:
            alarm_system_id = await step(
                "Creating Alarm System",
                client.create_alarm_system,
                site_id,
            )
            if alarm_system_id:
                _ = await step(
                    "Configuring Alarm Panel",
                    client.configure_alarm_panel,
                    panel_id,
                    ESS_PANEL_NAME,
                    alarm_system_id,
                )

        if access_station_pro_id and site_id:
            access_station_pro_controller_id = await step(
                "Configuring Access Station Pro",
                client.configure_access_station_pro,
                access_station_pro_id,
                ESS_ACCESS_STATION_PRO_NAME,
                site_id,
                ESS_ADDRESS
            )

            # No separate face-unlock step: the Access Station Pro door is
            # created with face-unlock-enabled (as the Command web app does).
            if access_station_pro_controller_id:
                _ = await step(
                    "Creating Door",
                    client.create_access_station_pro_door,
                    access_station_pro_controller_id,
                    ESS_ACCESS_STATION_PRO_DOOR_NAME,
                    floor_id,
                )

    async def _run_acsl_flow(self, step, page, client) -> None:
        access_station_pro_serial = self._device_serial("Access Station Pro")

        site_id = await step("Creating Site", client.create_or_reuse_site, ACSL_SITE_NAME)

        access_station_pro_id = await step(
            f"Adding Access Station Pro ({access_station_pro_serial})",
            client.add_device,
            ACSL_ACCESS_STATION_PRO_NAME,
            access_station_pro_serial,
        )

        floor_id = await step(
            "Creating Building",
            client.create_or_reuse_building,
            ACSL_BUILDING_NAME,
            ACSL_ADDRESS,
            ACSL_FLOORS,
        )

        _ = await step(
            "Enabling Org Face-Unlock",
            client.enable_org_face_unlock,
        )

        if access_station_pro_id and site_id:
            access_station_pro_controller_id = await step(
                "Configuring Access Station Pro",
                client.configure_access_station_pro,
                access_station_pro_id,
                ACSL_ACCESS_STATION_PRO_NAME,
                site_id,
                ACSL_ADDRESS
            )
            door_id = None
            if access_station_pro_controller_id:
                # Face unlock and the three two-factor modes (card + code,
                # face + card, face + code) come with the door's create
                # configs, as in the Command web app.
                door_id = await step(
                    "Creating Door",
                    functools.partial(client.create_access_station_pro_door, mfa=True),
                    access_station_pro_controller_id,
                    ACSL_ACCESS_STATION_PRO_DOOR_NAME,
                    floor_id,
                )

            if door_id and access_station_pro_controller_id:
                _ = await step(
                    "Creating MFA Door Schedule",
                    client.create_mfa_schedule,
                    door_id,
                    ACSL_MFA_DOOR_SCHEDULE_NAME,
                )

    async def _run_vssl_flow(self, step, page, client) -> None:
        bullet_serial = self._device_serial("Bullet")
        ptz_serial = self._device_serial("PTZ")
        connector_serial = self._device_serial("Command Connector")
        controller_serial = self._device_serial("Access Controller")
        license_plate = self._device_serial("License Plate")

        site_id = await step("Creating Site", client.create_or_reuse_site, VSS_SITE_NAME)

        bullet_id, ptz_id, connector_id, controller_id = await self._add_devices(
            step,
            client,
            [
                (f"Adding Camera ({bullet_serial})", VSS_BULLET_NAME, bullet_serial),
                (f"Adding PTZ ({ptz_serial})", VSS_PTZ_NAME, ptz_serial),
                (f"Adding Command Connector ({connector_serial})", VSS_CONNECTOR_NAME, connector_serial),
                (f"Adding Access Controller ({controller_serial})", VSS_CONTROLLER_NAME, controller_serial),
            ],
        )

        floor_id = await step(
            "Creating Building",
            client.create_or_reuse_building,
            VSS_BUILDING_NAME,
            VSS_ADDRESS,
            VSS_FLOORS,
        )

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        cameras = [c for c in (bullet_id, ptz_id) if c]
        if cameras and site_id:
            _ = await step(
                f"Configuring cameras ({len(cameras)})",
                client.configure_cameras,
                cameras,
                site_id,
                VSS_ADDRESS,
            )

        if connector_id and site_id:
            _ = await step(
                "Configuring Connector",
                client.configure_connector,
                connector_id,
                VSS_CONNECTOR_NAME,
                site_id,
                VSS_ADDRESS,
            )

        door_id = None
        if controller_id and site_id:
            access_controller_id = await step(
                "Configuring Access Controller",
                client.configure_access_controller,
                controller_id,
                VSS_CONTROLLER_NAME,
                site_id,
                floor_id,
                HQ_TIMEZONE,
            )
            if access_controller_id:
                # LPR door: created with the LPR config up front (v2 has no
                # retroactive flag-flip), then the camera is paired below.
                door_id = await step(
                    "Creating Door",
                    functools.partial(
                        client.create_door,
                        access_controller_id,
                        VSS_DOOR_NAME,
                        floor_id,
                        lpr=True,
                    ),
                )

        _ = await step(
            "Enabling Org Features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )

        if self.face_analytics_switch.value and ptz_id:
            _ = await step(
                "Enabling Camera Analytics",
                client.enable_camera_analytics,
                [ptz_id],
            )

        if bullet_id:
            _ = await step(
                "Enabling LPR mode",
                client.enable_camera_lpr,
                [bullet_id],
            )

        if ptz_id:
            _ = await step(
                "Disabling PTZ Installation Mode",
                client.disable_camera_install_mode,
                [ptz_id],
            )

        if door_id and bullet_id:
            _ = await step(
                "Linking LPR Camera to Door",
                client.pair_lpr_camera,
                door_id,
                bullet_id,
            )

        group_id = await step(
            "Creating Access Group",
            client.create_access_group,
            VSS_ACCESS_GROUP_NAME,
        )

        _ = await step(
            "Adding User to Access Group",
            client.add_user_to_access_group,
            client.user_id,
            group_id,
        )

        _ = await step(
            "Adding License Plate to Access User",
            client.add_license_plate_to_user,
            client.user_id,
            license_plate,
        )

        if door_id:
            _ = await step(
                "Creating Access Level",
                client.create_access_level,
                door_id,
                VSS_ACCESS_LEVEL_NAME,
                site_id,
                group_id,
            )

    async def _run_vsse_flow(self, step, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        fisheye_serial = self._device_serial("Fisheye")
        bullet_serial = self._device_serial("Bullet")

        site_id = await step(
            "Creating Site", client.create_or_reuse_site, VSS_EXAM_SITE_NAME
        )

        dome_id, bullet_id, fisheye_id = await self._add_devices(
            step,
            client,
            [
                (f"Adding Dome ({dome_serial})", VSS_EXAM_DOME_NAME, dome_serial),
                (f"Adding Bullet ({bullet_serial})", VSS_EXAM_BULLET_NAME, bullet_serial),
                (f"Adding Fisheye ({fisheye_serial})", VSS_EXAM_FISHEYE_NAME, fisheye_serial),
            ],
        )

        cameras = [c for c in (dome_id, fisheye_id, bullet_id) if c]
        if cameras and site_id:
            _ = await step(
                f"Configuring cameras ({len(cameras)})",
                client.configure_cameras,
                cameras,
                site_id,
                VSS_ADDRESS,
            )

        _ = await step(
            "Enabling Org Features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )

        if self.face_analytics_switch.value and (dome_id or fisheye_id):
            cams = [c for c in (dome_id, fisheye_id) if c]
            _ = await step(
                "Enabling Camera Analytics",
                client.enable_camera_analytics,
                cams,
            )

        if bullet_id:
            _ = await step(
                "Enabling LPR mode",
                client.enable_camera_lpr,
                [bullet_id],
            )

    async def _run_as_flow(self, step, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        controller_serial = self._device_serial("Access Controller")
        panel_serial = self._device_serial("Alarm Panel")
        keypad_serial = self._device_serial("Keypad")

        site_id = await step("Creating Site", client.create_or_reuse_site, AS_SITE_NAME)

        dome_id, controller_id, panel_id, keypad_id = await self._add_devices(
            step,
            client,
            [
                (f"Adding Camera ({dome_serial})", AS_DOME_NAME, dome_serial),
                (f"Adding Access Controller ({controller_serial})", AS_CONTROLLER_NAME, controller_serial),
                (f"Adding Alarm Panel ({panel_serial})", AS_PANEL_NAME, panel_serial),
                (f"Adding Alarm Keypad ({keypad_serial})", AS_KEYPAD_NAME, keypad_serial),
            ],
        )

        floor_id = await step(
            "Creating Building",
            client.create_or_reuse_building,
            AS_BUILDING_NAME,
            AS_ADDRESS,
            AS_FLOORS,
        )

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        door_id = None
        access_controller_id = None
        if controller_id and site_id:
            access_controller_id = await step(
                "Configuring Access Controller",
                client.configure_access_controller,
                controller_id,
                AS_CONTROLLER_NAME,
                site_id,
                floor_id,
                HQ_TIMEZONE,
            )
            if access_controller_id:
                door_id = await step(
                    "Creating Door",
                    client.create_door,
                    access_controller_id,
                    AS_DOOR_NAME,
                    floor_id,
                )

        if door_id:
            _ = await step(
                "Creating Access Level",
                client.create_access_level,
                door_id,
                AS_ACCESS_LEVEL_NAME,
                site_id,
                "",
            )

            _ = await step(
                "Deleting Door",
                client.delete_door,
                door_id,
            )

            _ = await step(
                "Deleting Access Controller",
                client.delete_access_controller,
                access_controller_id
            )

        if dome_id and site_id:
            _ = await step(
                "Configuring Camera",
                client.configure_cameras,
                [dome_id],
                site_id,
                AS_ADDRESS,
            )

        _ = await step(
            "Enabling Org Features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )

        if self.face_analytics_switch.value and dome_id:
            _ = await step(
                "Enabling Camera Analytics",
                client.enable_camera_analytics,
                [dome_id],
            )

        if site_id:
            alarm_response_id = await step(
                "Creating Alarm Site",
                client.create_alarm_site,
                "Verkada",
                AS_ALARM_ADDRESS,
                site_id,
            )

            if alarm_response_id:
                _ = await step(
                    "Setting response to Self-Monitored",
                    client.set_alarm_self_monitored,
                    site_id,
                    alarm_response_id,
                )

        if panel_id and keypad_id and site_id:
            # Alarm panels and keypads attach to an alarm system, which
            # must be created first. The keypad step needs the system id.
            alarm_system_id = await step(
                "Creating Alarm System",
                client.create_alarm_system,
                site_id,
            )

            if alarm_system_id:
                _ = await step(
                    "Configuring Alarm Panel",
                    client.configure_alarm_panel,
                    panel_id,
                    AS_PANEL_NAME,
                    alarm_system_id,
                )

                _ = await step(
                    "Configuring Alarm Keypad",
                    client.configure_keypad,
                    keypad_id,
                    AS_KEYPAD_NAME,
                    alarm_system_id,
                    keypad_serial,
                )

                _ = await step(
                    "Configuring Wired Strobe",
                    client.create_wired_output,
                    AS_STROBE_OUTPUT_NAME,
                    alarm_system_id,
                    panel_id,
                    AS_STROBE_OUTPUT_PIN
                )

                _ = await step(
                    "Setting up General Keycode",
                    client.set_alarm_keycode,
                    alarm_system_id,
                )

    # ------------------------------------------------------------------
    # Supporting steps
    # ------------------------------------------------------------------

    async def _invite_supporting_users(self, step, page, client, role: str) -> None:
        """Invite every complete supporting-user row (validated on Review),
        PARALLEL_REQUESTS at a time, one progress row each. People already
        in the org (one user list call) are reported, not re-invited."""
        users = self._collect_supporting_users()
        if not users:
            return
        existing = await step("Checking for existing users", client.get_user_ids_by_email)
        to_invite = []
        for first, last, email in users:
            if email.lower() in (existing or {}):
                label = f"Adding user {first} {last}"
                row = StepRow(label)
                row.succeed(f"{label} — already in the org")
                self._progress_column.controls.append(row)
                self._record_step(label, ok=True)
            else:
                to_invite.append((first, last, email))
        page.update()
        for start in range(0, len(to_invite), PARALLEL_REQUESTS):
            await asyncio.gather(
                *(
                    step(
                        f"Adding user {first} {last}",
                        client.invite_user,
                        email,
                        first,
                        last,
                        role,
                    )
                    for first, last, email in to_invite[start : start + PARALLEL_REQUESTS]
                )
            )

    # ------------------------------------------------------------------
    # UI helpers used by the orchestrator
    # ------------------------------------------------------------------

    def _progress_note(self, page, text: str) -> None:
        """
        Append a gray italic note to the progress column. Used for
        "Waiting for X..." messages that aren't backed by an API call and
        therefore don't go through _run_step.
        """
        self._progress_column.controls.append(
            ft.Text(text, color=TEXT_SECONDARY, size=12)
        )
        page.update()

    def _render_summary(self, page) -> None:
        """Run -> Report: a structured result with failures surfaced first.

        The outcome is derived from the step counters. Branches on the
        cancel token so a user-aborted run shows a clear "Cancelled" header
        instead of the success/partial-success line.
        """
        self._stepper.set_active(3)

        cancelled = bool(self._cancel_token and self._cancel_token.is_cancelled)
        if cancelled:
            kind = "warning"
            message = "Commission cancelled."
            bar_color = WARNING
        elif self._steps_failed == 0:
            kind = "success"
            message = f"Commission complete — {self._steps_done} steps, 0 failed."
            bar_color = SECONDARY
        else:
            kind = "warning"
            message = (
                f"Commission completed with errors — {self._steps_done} done, "
                f"{self._steps_failed} failed."
            )
            bar_color = WARNING

        self.cancel_btn.visible = False
        self._progress_header.set_progress(
            self._steps_done, failed=self._steps_failed
        )
        self._progress_header.complete(color=bar_color)

        # Hide the live chronological step list behind the raw-log disclosure;
        # the report leads with the outcome and any failures.
        self._progress_column.visible = False

        report: list[ft.Control] = [banner(message, kind=kind)]

        if self._failures:
            failure_rows = [
                status_row("failed", label, detail=err)
                for label, err in self._failures
            ]
            report.append(ft.Container(height=8))
            report.append(
                section_header(
                    "Failed steps", f"{len(self._failures)} step(s) need attention"
                )
            )
            report.extend(failure_rows)

        report.append(ft.Container(height=8))
        report.append(RawLogPanel(lambda: "\n".join(self._run_log) or "(no steps)"))
        report.append(ft.Container(height=12))
        report.append(
            ft.Row(
                [
                    secondary_button(
                        "Copy log", on_click=self._on_copy_log, height=42
                    ),
                    secondary_button(
                        "Export report (CSV)",
                        on_click=self._on_export_report,
                        height=42,
                    ),
                    primary_button(
                        "Return to Home",
                        on_click=lambda _: self.push_route("/home"),
                        height=42,
                    ),
                ],
                spacing=10,
            )
        )
        self._run_section.controls.append(
            ft.Column(report, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        )
        page.update()

    async def _on_copy_log(self, e):
        try:
            await e.page.clipboard.set("\n".join(self._run_log))
            show_toast(e.page, "Run log copied to clipboard.", kind="success")
        except Exception:
            show_toast(e.page, "Couldn't access the clipboard.", kind="warning")

    def _on_export_report(self, e):
        rows = [
            {
                "Step": label,
                "Result": "FAILED",
                "Detail": err,
            }
            for label, err in self._failures
        ]
        # Include the full chronological log so a clean run still exports.
        for line in self._run_log:
            result = "FAILED" if line.startswith("[FAIL]") else "OK"
            rows.append({"Step": line, "Result": result, "Detail": ""})
        try:
            path = export_csv(
                rows, ["Step", "Result", "Detail"], "commission_report"
            )
            show_toast(e.page, f"Report saved to {path}", kind="success", duration_ms=4000)
        except Exception as ex:
            show_alert(e.page, "Export Failed", str(ex))

    def _on_cancel(self, e):
        """Cancel button: trip the token and disable further clicks.

        The in-flight API call is allowed to finish; the next step sees
        the token and renders as 'skipped (cancelled)'.
        """
        if self._cancel_token is None:
            return
        self._cancel_token.cancel()
        self.cancel_btn.disabled = True
        if isinstance(self.cancel_btn.content, ft.Text):
            self.cancel_btn.content.value = "Cancelling..."
        self._progress_note(
            e.page,
            "Cancelling — the current step will finish, then commission will stop.",
        )

    def _record_step(self, label: str, *, ok: bool, error=None) -> None:
        """Count one finished step; the report's outcome is derived from this."""
        if ok:
            self._steps_done += 1
            self._run_log.append(f"[ok]   {label}")
        else:
            self._steps_failed += 1
            self._failures.append((label, str(error)))
            self._run_log.append(f"[FAIL] {label}: {error}")
        self._progress_header.set_progress(
            self._steps_done, failed=self._steps_failed
        )

    async def _add_devices(self, step, client, devices) -> list:
        """
        Claim a template's devices with one batch/commission call, as the
        Command web app does, while keeping one progress row per device.

        `devices` is [(row label, device name, serial)]. The first row makes
        the call; every row then reports its own device from the result.
        Returns the device ids in order (None for a device that failed).
        """
        batch: dict[str, Any] = {}

        def claim_all():
            if "error" in batch:
                raise batch["error"]
            if "result" not in batch:
                try:
                    batch["result"] = client.add_devices([(n, s) for _, n, s in devices])
                except Exception as ex:
                    batch["error"] = ex
                    raise
            return batch["result"]

        ids = []
        for label, _name, serial in devices:
            def one(serial=serial):
                outcome = claim_all()[normalize_serial(serial)]
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            ids.append(await step(label, one))
        return ids

    async def _run_step(self, page, label: str, fn, *args):
        """
        Run one commissioning step off the UI loop with a live progress row.

        `fn` is a sync callable from the API clients. Returns its result,
        or None when the step failed (the error is shown in the row and
        recorded for the report) or was skipped because the run was
        cancelled — the in-flight step always completes first.
        """
        if self._cancel_token and self._cancel_token.is_cancelled:
            row = StepRow(label)
            row.skip(f"{label} — skipped (cancelled)")
            self._progress_column.controls.append(row)
            page.update()
            return None

        ok, result, error = await run_step(
            page, self._progress_column, label, fn, *args
        )
        self._record_step(label, ok=ok, error=error)
        page.update()
        return result if ok else None

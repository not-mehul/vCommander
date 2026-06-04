"""Commission screen.

Drives one of the predefined org-setup flows (ESS / VSSL / VSSE / AS /
ACS — see TEMPLATE_FIELDS in constants.py). The user picks a template
and a kit (assets/kits.csv), confirms the auto-filled device serials
and supporting users, then `_run_step` walks through site/building/
device creation against the internal API. Each step's success/failure
is rendered in the live progress panel on the right."""

import asyncio
import csv
import functools
import os

import flet as ft

from apis.external_api import VerkadaExternalAPIClient
from constants import (
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
    BG,
    BORDER,
    BUILDING_PROVISION_SECONDS,
    CARD_PADDING,
    CARD_SHADOW,
    ERROR,
    ESS_ADDRESS,
    ESS_ALARM_ADDRESS,
    ESS_BUILDING_NAME,
    ESS_CAMERA_NAME,
    ESS_FLOORS,
    ESS_GUEST_ADDRESS,
    ESS_PANEL_NAME,
    ESS_PARTITION_NAME,
    ESS_SITE_NAME,
    FIELD_SPACING,
    HQ_TIMEZONE,
    PAGE_PADDING,
    PRIMARY,
    ROLE_PROPAGATION_SECONDS,
    SECONDARY,
    SURFACE,
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
from utils.executor import _executor
from utils.session import get_internal_client, set_external_client
from utils.ui_utils import set_button_loading, show_alert

_ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets"
)


class CommissionView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(
            route="/commission", bgcolor=BG, padding=PAGE_PADDING, **kwargs
        )
        self.push_route = push_route
        self.pop_route = pop_route
        self._kits: dict[str, dict[str, str]] = {}
        self._device_fields: dict[str, ft.TextField] = {}
        self._load_kits()
        self._build_ui()

    # ------------------------------------------------------------------
    # CSV / data loading
    # ------------------------------------------------------------------

    def _load_kits(self):
        internal = os.path.join(_ASSETS_DIR, "kits.internal.csv")
        public = os.path.join(_ASSETS_DIR, "kits.csv")
        path = internal if os.path.exists(internal) else public
        with open(os.path.join(_ASSETS_DIR, path), newline="") as f:
            print(f"[commission] loaded kits: {list(self._kits.keys())}")
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
        self.template_dropdown = ft.Dropdown(
            label="Template",
            options=template_options,
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            on_select=self._on_template_change,
        )

        kit_options = [ft.dropdown.Option("")] + [
            ft.dropdown.Option(k) for k in self._kits
        ]
        self.kit_dropdown = ft.Dropdown(
            label="Kit",
            options=kit_options,
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            on_select=self._on_kit_change,
        )

        self._devices_column = ft.Column(spacing=FIELD_SPACING)

        self.face_analytics_switch = ft.Switch(
            label=" Face Analytics",
            value=True,
            active_color=PRIMARY,
            label_text_style=ft.TextStyle(color=TEXT_PRIMARY),
            visible=False,
        )

        self._users_column = ft.Column(spacing=10)
        add_user_btn = ft.TextButton(
            content=ft.Text("+ Add Supporting User", color=PRIMARY),
            on_click=self._add_user_row,
        )

        self.commission_btn = ft.ElevatedButton(
            content=ft.Text(
                "Commission Organization",
                color=TEXT_PRIMARY,
                weight=ft.FontWeight.W_600,
            ),
            bgcolor=PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            height=45,
            on_click=self._on_commission,
        )

        self._progress_column = ft.Column(spacing=8, visible=False)

        self._form_section = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(content=self.template_dropdown, expand=1),
                        ft.Container(content=self.kit_dropdown, expand=1),
                    ],
                    spacing=FIELD_SPACING,
                ),
                ft.Container(height=4),
                self._devices_column,
                self.face_analytics_switch,
                ft.Divider(color=BORDER, height=1),
                ft.Text(
                    "Supporting Users",
                    size=14,
                    color=TEXT_SECONDARY,
                    weight=ft.FontWeight.W_500,
                ),
                self._users_column,
                add_user_btn,
                ft.Container(height=8),
                self.commission_btn,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            spacing=FIELD_SPACING,
        )

        form_card = ft.Container(
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING),
            content=ft.Column(
                [self._form_section, self._progress_column],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                scroll=ft.ScrollMode.ADAPTIVE,
                spacing=FIELD_SPACING,
            ),
            expand=True,
        )

        header = ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    icon_color=TEXT_SECONDARY,
                    on_click=lambda _: self.push_route("/home"),
                ),
                ft.Text(
                    "Commission Organization",
                    size=22,
                    color=TEXT_PRIMARY,
                    weight=ft.FontWeight.W_600,
                ),
            ],
        )

        self.controls = [
            ft.Column(
                [header, ft.Container(height=10), form_card],
                expand=True,
            )
        ]

    def _make_device_field(self, device_type: str, expand=None) -> ft.TextField:
        field = ft.TextField(
            label=f"{device_type} S/N",
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            expand=expand,
        )
        self._device_fields[device_type] = field
        return field

    # ------------------------------------------------------------------
    # Form event handlers
    # ------------------------------------------------------------------

    def _on_template_change(self, e):
        code = self.template_dropdown.value
        if not code or code not in TEMPLATE_FIELDS:
            self._devices_column.controls.clear()
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
        self._devices_column.controls = rows
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
            field.value = kit_data.get(device_type, "")

    def _add_user_row(self, e):
        row = self._create_user_row()
        self._users_column.controls.append(row)
        e.page.update()

    def _create_user_row(self) -> ft.Row:
        first = ft.TextField(
            label="First Name",
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            expand=1,
        )
        last = ft.TextField(
            label="Last Name",
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            expand=1,
        )
        email = ft.TextField(
            label="Email",
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            expand=2,
        )

        row = ft.Row(spacing=10)
        delete_btn = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=ERROR,
            on_click=lambda _, r=row: self._remove_user_row(r),
        )
        row.controls = [first, last, email, delete_btn]
        return row

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
            show_alert(e.page, "Validation Error", "Please select a template.")
            return False, None

        config = TEMPLATE_FIELDS[code]
        for device_type in config["devices"]:
            if not self._device_serial(device_type):
                show_alert(
                    e.page,
                    "Validation Error",
                    f"Please enter the {device_type} serial number.",
                )
                return False, None

        return True, code

    # ------------------------------------------------------------------
    # Commission orchestration
    # ------------------------------------------------------------------

    async def _on_commission(self, e):
        ok, code = self._validate_form(e)
        if not ok:
            return

        set_button_loading(self.commission_btn, True, "Commissioning")
        self._progress_column.controls.clear()
        self._progress_column.visible = True
        e.page.update()
        await asyncio.sleep(0)

        client = get_internal_client()
        loop = asyncio.get_running_loop()

        api_key = await loop.run_in_executor(_executor, client.create_external_api_key)
        ext_client = await loop.run_in_executor(
            _executor,
            VerkadaExternalAPIClient,
            api_key,
            client.org_short_name,
        )
        set_external_client(ext_client)

        page = e.page

        async def step(label: str, fn, *args) -> tuple[bool, object]:
            return await self._run_step(page, loop, label, fn, *args)

        all_success = True

        def track(ok_value: bool) -> None:
            nonlocal all_success
            all_success = ok_value and all_success

        # ── Common prelude ──
        if code in ("ESS", "ACS", "VSSL", "VSSE", "AS"):
            ok, _ = await step("Enabling custom roles", client.enable_custom_roles)
            track(ok)
            self._progress_note(page, "Waiting for roles to propagate...")
            await asyncio.sleep(ROLE_PROPAGATION_SECONDS)
            ok, _ = await step(
                "Disabling global site admin", client.disable_global_site_admin
            )
            track(ok)

        # ── Per-template flows ──
        if code == "ESS":
            await self._run_ess_flow(step, track, page, client)
        elif code == "ACS":
            # No additional steps beyond the prelude.
            pass
        elif code == "VSSL":
            await self._run_vssl_flow(step, track, page, client, ext_client)
        elif code == "VSSE":
            await self._run_vsse_flow(step, track, page, client)
        elif code == "AS":
            await self._run_as_flow(step, track, page, client)

        # ── Supporting users — shared across all templates ──
        user_role = "Org Admin"
        await self._invite_supporting_users(step, track, client, user_role)

        # ── Final summary card ──
        self._render_summary(page, all_success)

    # ------------------------------------------------------------------
    # Per-template flows
    # ------------------------------------------------------------------

    async def _run_ess_flow(self, step, track, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        panel_serial = self._device_serial("Alarm Panel")

        ok, site_id = await step("Creating site", client.create_site, ESS_SITE_NAME)
        track(ok)

        ok, camera_id = await step(
            f"Adding camera ({dome_serial})",
            client.add_device,
            ESS_CAMERA_NAME,
            dome_serial,
        )
        track(ok)

        ok, panel_id = await step(
            f"Adding alarm panel ({panel_serial})",
            client.add_device,
            ESS_PANEL_NAME,
            panel_serial,
        )
        track(ok)

        ok, floor_id = await step(
            "Creating building",
            client.create_building,
            ESS_BUILDING_NAME,
            ESS_ADDRESS,
            ESS_FLOORS,
        )
        track(ok)

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        if camera_id and site_id:
            ok, _ = await step(
                "Configuring camera",
                client.configure_camera,
                camera_id,
                ESS_CAMERA_NAME,
                site_id,
                ESS_ADDRESS,
            )
            track(ok)

        ok, _ = await step(
            "Enabling org features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )
        track(ok)

        if self.face_analytics_switch.value and camera_id:
            ok, _ = await step(
                "Enabling camera analytics",
                client.enable_camera_analytics,
                [camera_id],
            )
            track(ok)

        if site_id:
            ok, _ = await step(
                "Creating alarm site",
                client.create_alarm_site,
                "Verkada",
                ESS_ALARM_ADDRESS,
                site_id,
            )
            track(ok)

            ok, _ = await step(
                "Creating guest site",
                client.create_guest_site,
                ESS_GUEST_ADDRESS,
                site_id,
            )
            track(ok)

        if panel_id and site_id:
            ok, alarm_system_id = await step(
                "Creating alarm system",
                client.create_alarm_system,
                site_id,
            )
            track(ok)
            if alarm_system_id:
                ok, _ = await step(
                    "Configuring alarm panel",
                    client.configure_alarm_panel,
                    panel_id,
                    ESS_PANEL_NAME,
                    alarm_system_id,
                )
                track(ok)

                ok, partition = await step(
                    "Configuring Alarm Partition",
                    client.create_alarm_partition,
                    alarm_system_id,
                    ESS_PARTITION_NAME,
                )
                track(ok)

                # create_alarm_partition returns [partition_id, alarm_response_id]
                alarm_response_id = partition[1] if partition else None
                if alarm_response_id:
                    ok, _ = await step(
                        "Setting response to Self-Monitored",
                        client.set_alarm_self_monitored,
                        site_id,
                        alarm_response_id,
                    )
                    track(ok)

    async def _run_vssl_flow(self, step, track, page, client, ext_client) -> None:
        bullet_serial = self._device_serial("Bullet")
        ptz_serial = self._device_serial("PTZ")
        connector_serial = self._device_serial("Command Connector")
        controller_serial = self._device_serial("Access Controller")
        license_plate = self._device_serial("License Plate")

        ok, site_id = await step("Creating site", client.create_site, VSS_SITE_NAME)
        track(ok)

        ok, bullet_id = await step(
            f"Adding camera ({bullet_serial})",
            client.add_device,
            VSS_BULLET_NAME,
            bullet_serial,
        )
        track(ok)

        ok, ptz_id = await step(
            f"Adding PTZ ({ptz_serial})",
            client.add_device,
            VSS_PTZ_NAME,
            ptz_serial,
        )
        track(ok)

        ok, connector_id = await step(
            f"Adding command connector ({connector_serial})",
            client.add_device,
            VSS_CONNECTOR_NAME,
            connector_serial,
        )
        track(ok)

        ok, controller_id = await step(
            f"Adding access controller ({controller_serial})",
            client.add_device,
            VSS_CONTROLLER_NAME,
            controller_serial,
        )
        track(ok)

        ok, floor_id = await step(
            "Creating building",
            client.create_building,
            VSS_BUILDING_NAME,
            VSS_ADDRESS,
            VSS_FLOORS,
        )
        track(ok)

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        if bullet_id and site_id:
            ok, _ = await step(
                "Configuring bullet",
                client.configure_camera,
                bullet_id,
                VSS_BULLET_NAME,
                site_id,
                VSS_ADDRESS,
            )
            track(ok)

        if ptz_id and site_id:
            ok, _ = await step(
                "Configuring PTZ",
                client.configure_camera,
                ptz_id,
                VSS_PTZ_NAME,
                site_id,
                VSS_ADDRESS,
            )
            track(ok)

        if connector_id and site_id:
            ok, _ = await step(
                "Configuring connector",
                client.configure_connector,
                connector_id,
                VSS_CONNECTOR_NAME,
                site_id,
                VSS_ADDRESS,
            )
            track(ok)

        door_id = None
        if controller_id and site_id:
            ok, access_controller_id = await step(
                "Configuring access controller",
                client.configure_access_controller,
                controller_id,
                VSS_CONTROLLER_NAME,
                site_id,
                floor_id,
                HQ_TIMEZONE,
            )
            track(ok)
            if access_controller_id:
                # LPR door: created with the LPR config up front (v2 has no
                # retroactive flag-flip), then the camera is paired below.
                ok, door_id = await step(
                    "Creating door",
                    functools.partial(
                        client.create_door,
                        access_controller_id,
                        VSS_DOOR_NAME,
                        floor_id,
                        lpr=True,
                    ),
                )
                track(ok)

        ok, _ = await step(
            "Enabling org features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )
        track(ok)

        if self.face_analytics_switch.value and ptz_id:
            ok, _ = await step(
                "Enabling camera analytics",
                client.enable_camera_analytics,
                [ptz_id],
            )
            track(ok)

        if bullet_id:
            ok, _ = await step(
                "Enabling LPR mode",
                client.enable_camera_lpr,
                [bullet_id],
            )
            track(ok)

        if door_id and bullet_id:
            ok, _ = await step(
                "Linking LPR camera to door",
                client.pair_lpr_camera,
                door_id,
                bullet_id,
            )
            track(ok)

        ok, group_id = await step(
            "Creating Access Group",
            ext_client.create_access_group,
            VSS_ACCESS_GROUP_NAME,
        )
        track(ok)

        ok, _ = await step(
            "Adding User to Access Group",
            ext_client.add_user_to_access_group,
            client.user_id,
            group_id,
        )
        track(ok)

        ok, _ = await step(
            "Adding License Plate to Access User",
            ext_client.add_license_plate_to_user,
            client.user_id,
            license_plate,
        )
        track(ok)

        if door_id:
            ok, _ = await step(
                "Creating Access Level",
                client.create_access_level,
                door_id,
                VSS_ACCESS_LEVEL_NAME,
                site_id,
                group_id,
            )
            track(ok)

    async def _run_vsse_flow(self, step, track, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        fisheye_serial = self._device_serial("Fisheye")
        bullet_serial = self._device_serial("Bullet")

        ok, site_id = await step(
            "Creating site", client.create_site, VSS_EXAM_SITE_NAME
        )
        track(ok)

        ok, dome_id = await step(
            f"Adding dome ({dome_serial})",
            client.add_device,
            VSS_EXAM_DOME_NAME,
            dome_serial,
        )
        track(ok)

        ok, bullet_id = await step(
            f"Adding bullet ({bullet_serial})",
            client.add_device,
            VSS_EXAM_BULLET_NAME,
            bullet_serial,
        )
        track(ok)

        ok, fisheye_id = await step(
            f"Adding fisheye ({fisheye_serial})",
            client.add_device,
            VSS_EXAM_FISHEYE_NAME,
            fisheye_serial,
        )
        track(ok)

        for cam_id, cam_name in (
            (dome_id, VSS_EXAM_DOME_NAME),
            (fisheye_id, VSS_EXAM_FISHEYE_NAME),
            (bullet_id, VSS_EXAM_BULLET_NAME),
        ):
            if cam_id and site_id:
                ok, _ = await step(
                    f"Configuring {cam_name.lower()}",
                    client.configure_camera,
                    cam_id,
                    cam_name,
                    site_id,
                    VSS_ADDRESS,
                )
                track(ok)

        ok, _ = await step(
            "Enabling org features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )
        track(ok)

        if self.face_analytics_switch.value and (dome_id or fisheye_id):
            cams = [c for c in (dome_id, fisheye_id) if c]
            ok, _ = await step(
                "Enabling camera analytics",
                client.enable_camera_analytics,
                cams,
            )
            track(ok)

        if bullet_id:
            ok, _ = await step(
                "Enabling LPR mode",
                client.enable_camera_lpr,
                [bullet_id],
            )
            track(ok)

    async def _run_as_flow(self, step, track, page, client) -> None:
        dome_serial = self._device_serial("Dome")
        controller_serial = self._device_serial("Access Controller")
        panel_serial = self._device_serial("Alarm Panel")
        keypad_serial = self._device_serial("Keypad")

        ok, site_id = await step("Creating site", client.create_site, AS_SITE_NAME)
        track(ok)

        ok, dome_id = await step(
            f"Adding camera ({dome_serial})",
            client.add_device,
            AS_DOME_NAME,
            dome_serial,
        )
        track(ok)

        ok, controller_id = await step(
            f"Adding access controller ({controller_serial})",
            client.add_device,
            AS_CONTROLLER_NAME,
            controller_serial,
        )
        track(ok)

        ok, panel_id = await step(
            f"Adding alarm panel ({panel_serial})",
            client.add_device,
            AS_PANEL_NAME,
            panel_serial,
        )
        track(ok)

        ok, keypad_id = await step(
            f"Adding alarm keypad ({keypad_serial})",
            client.add_device,
            AS_KEYPAD_NAME,
            keypad_serial,
        )
        track(ok)

        ok, floor_id = await step(
            "Creating building",
            client.create_building,
            AS_BUILDING_NAME,
            AS_ADDRESS,
            AS_FLOORS,
        )
        track(ok)

        self._progress_note(page, "Waiting for building to provision...")
        await asyncio.sleep(BUILDING_PROVISION_SECONDS)

        door_id = None
        if controller_id and site_id:
            ok, access_controller_id = await step(
                "Configuring access controller",
                client.configure_access_controller,
                controller_id,
                AS_CONTROLLER_NAME,
                site_id,
                floor_id,
                HQ_TIMEZONE,
            )
            track(ok)
            if access_controller_id:
                ok, door_id = await step(
                    "Creating door",
                    client.create_door,
                    access_controller_id,
                    AS_DOOR_NAME,
                    floor_id,
                )
                track(ok)

        if door_id:
            ok, _ = await step(
                "Creating Access Level",
                client.create_access_level,
                door_id,
                AS_ACCESS_LEVEL_NAME,
                site_id,
                "",
            )
            track(ok)

        if dome_id and site_id:
            ok, _ = await step(
                "Configuring camera",
                client.configure_camera,
                dome_id,
                AS_DOME_NAME,
                site_id,
                AS_ADDRESS,
            )
            track(ok)

        ok, _ = await step(
            "Enabling org features",
            client.enable_org_features,
            self.face_analytics_switch.value,
        )
        track(ok)

        if self.face_analytics_switch.value and dome_id:
            ok, _ = await step(
                "Enabling camera analytics",
                client.enable_camera_analytics,
                [dome_id],
            )
            track(ok)

        if site_id:
            ok, _ = await step(
                "Creating alarm site",
                client.create_alarm_site,
                "Verkada",
                AS_ALARM_ADDRESS,
                site_id,
            )
            track(ok)

        if panel_id and keypad_id and site_id:
            # Alarm panels and keypads attach to an alarm system, which
            # must be created first. The keypad step needs the system id.
            ok, alarm_system_id = await step(
                "Creating alarm system",
                client.create_alarm_system,
                site_id,
            )
            track(ok)

            if alarm_system_id:
                ok, _ = await step(
                    "Configuring alarm panel",
                    client.configure_alarm_panel,
                    panel_id,
                    AS_PANEL_NAME,
                    alarm_system_id,
                )
                track(ok)

                ok, _ = await step(
                    "Configuring alarm keypad",
                    client.configure_keypad,
                    keypad_id,
                    AS_KEYPAD_NAME,
                    alarm_system_id,
                    keypad_serial,
                )
                track(ok)

    # ------------------------------------------------------------------
    # Supporting steps
    # ------------------------------------------------------------------

    async def _invite_supporting_users(self, step, track, client, role: str) -> None:
        """Walk the user rows and invite each one with non-empty fields."""
        for control in self._users_column.controls:
            if not isinstance(control, ft.Row):
                continue  # only ft.Row instances are added by _create_user_row
            row: ft.Row = control
            fields = [c for c in row.controls if isinstance(c, ft.TextField)]
            if len(fields) < 3:
                continue
            first = (fields[0].value or "").strip()
            last = (fields[1].value or "").strip()
            email_val = (fields[2].value or "").strip()
            if not (first and last and email_val):
                continue
            ok, _ = await step(
                f"Adding user {first} {last}",
                client.invite_user,
                email_val,
                first,
                last,
                role,
            )
            track(ok)

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

    def _render_summary(self, page, all_success: bool) -> None:
        """Hide the form, show a final status row plus a 'Return to Home' button."""
        status_color = SECONDARY if all_success else WARNING
        self._form_section.visible = False
        self._progress_column.controls.append(ft.Container(height=8))
        self._progress_column.controls.append(
            ft.Row(
                [
                    ft.Icon(
                        ft.Icons.CHECK_CIRCLE if all_success else ft.Icons.WARNING,
                        color=status_color,
                    ),
                    ft.Text(
                        "Commission complete!"
                        if all_success
                        else "Commission completed with some errors",
                        color=status_color,
                        weight=ft.FontWeight.W_600,
                    ),
                ]
            )
        )
        self._progress_column.controls.append(
            ft.ElevatedButton(
                content=ft.Text(
                    "Return to Home", color=TEXT_PRIMARY, weight=ft.FontWeight.W_600
                ),
                bgcolor=SECONDARY,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                height=42,
                on_click=lambda _: self.push_route("/home"),
            )
        )
        page.update()

    async def _run_step(self, page, loop, label: str, fn, *args) -> tuple[bool, object]:
        """
        Run a single commissioning step in the executor with UI feedback.

        Renders a spinner+label row, awaits the function (which should be a
        sync callable from the API clients — it will be offloaded to the
        thread executor), then swaps the spinner for a check or error icon.

        Returns (ok, result). On failure result is None and the exception
        text is shown in the row.
        """
        step_icon = ft.ProgressRing(
            width=16, height=16, stroke_width=2, color=TEXT_SECONDARY
        )
        step_text = ft.Text(f"{label}...", color=TEXT_SECONDARY, size=13)
        step_row = ft.Row([step_icon, step_text], spacing=10)
        self._progress_column.controls.append(step_row)
        page.update()
        await asyncio.sleep(0)

        try:
            result = await loop.run_in_executor(_executor, fn, *args)
            step_row.controls[0] = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=SECONDARY, size=18
            )
            step_text.value = f"{label} — done"
            step_text.color = SECONDARY
            page.update()
            return True, result
        except Exception as ex:
            step_row.controls[0] = ft.Icon(ft.Icons.ERROR, color=ERROR, size=18)
            step_text.value = f"{label} — failed: {ex}"
            step_text.color = ERROR
            page.update()
            return False, None

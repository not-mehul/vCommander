import logging
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_reporting import generate_report
from tools.verkada_utilities import sanitize_list

logger = logging.getLogger(__name__)

# Flow states
FLOW_SCAN = "scan"
FLOW_REVIEW = "review"
FLOW_SELECT = "select"
FLOW_PROCESSING = "processing"
FLOW_COMPLETE = "complete"

# Styling constants
CONTROL_WIDTH = 320
CARD_BG_COLOR = "#333333"
CARD_BG = ("gray95", "gray17")
HEADER_FONT = ("Verdana", 22, "bold")
TITLE_FONT = ("Verdana", 18, "bold")
LABEL_FONT = ("Verdana", 12)

# Deletion order - strictly follows dependency requirements
# Format: (category, api_type)
# api_type: "external" = use external_client.delete_user
#           "internal" = use internal_client.delete_object
DELETION_ORDER = [
    ("Users", "external"),
    ("Sensors", "internal"),
    ("Intercoms", "internal"),
    ("Desk Stations", "internal"),
    ("Mailroom Sites", "internal"),
    ("Guest Sites", "internal"),
    ("Access Controllers", "internal"),
    ("Cameras", "internal"),
    ("Alarm Devices", "internal"),
    ("Alarm Sites", "internal"),
]


class DecommissionTool(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # API clients - use controller's internal client
        self.internal_client = controller.client
        self.external_client = None

        # Inventory data
        self.inventory = {}
        self.flattened_assets = []
        self.selected_assets = set()

        # Results
        self.success_count = 0
        self.fail_count = 0
        self.deleted_items = []
        self.failed_items = []

        self._setup_layout()

    def _setup_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(0, weight=1)

        self.content = ctk.CTkFrame(container, corner_radius=15)
        self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        self.controls = ctk.CTkFrame(
            container, corner_radius=15, width=CONTROL_WIDTH, fg_color=CARD_BG
        )
        self.controls.grid(row=0, column=1, sticky="nsew")
        self.controls.grid_propagate(False)
        self.controls.grid_columnconfigure(0, weight=1)

        # Start at SCAN flow (ready to scan state)
        self.current_flow = FLOW_SCAN
        self._refresh_ui()

    def _set_flow(self, flow):
        self.current_flow = flow
        self._refresh_ui()

    def _refresh_ui(self):
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        if self.current_flow == FLOW_SCAN:
            self.content.grid_remove()
            self.controls.grid(
                row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20
            )
            self._build_scan_controls()
            return

        else:
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=3)
            self.content.master.grid_columnconfigure(1, weight=1)
        self.controls.grid(row=0, column=1, sticky="nsew")

        builders = {
            FLOW_REVIEW: (self._build_review_content, self._build_review_controls),
            FLOW_SELECT: (self._build_select_content, self._build_select_controls),
            FLOW_PROCESSING: (
                self._build_processing_content,
                self._build_processing_controls,
            ),
            FLOW_COMPLETE: (
                self._build_complete_content,
                self._build_complete_controls,
            ),
        }

        content_builder, controls_builder = builders.get(
            self.current_flow, (None, None)
        )
        if content_builder:
            content_builder()
        if controls_builder:
            controls_builder()

    # Scan Flow

    def _build_scan_controls(self):
        center = ctk.CTkFrame(self.controls, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5)
        center.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(center, text="Scan", font=HEADER_FONT).grid(
            row=0, column=0, pady=(0, 10)
        )
        ctk.CTkLabel(
            center,
            text="Click 'Start' to gather all inventory\nfrom the organization.",
            font=LABEL_FONT,
            justify="center",
            text_color="gray",
        ).grid(row=1, column=0, pady=(0, 30))

        ctk.CTkButton(
            center,
            text="Start Scan",
            font=("Verdana", 14, "bold"),
            height=50,
            command=self._start_scan,
        ).grid(row=3, column=0, sticky="ew", pady=(20, 0))

    def _start_scan(self):
        # Transition to scanning state with content showing
        self._set_scanning_state()
        threading.Thread(target=self._execute_scan, daemon=True).start()

    def _set_scanning_state(self):
        """Show the scanning state with spinner and progress."""
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        # Show content area for scanning progress
        self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        self.content.master.grid_columnconfigure(0, weight=3)
        self.content.master.grid_columnconfigure(1, weight=1)
        self.controls.grid(row=0, column=1, sticky="nsew")

        # Scanning content (spinner)
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self.scan_spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.scan_spinner.pack(pady=(0, 20))
        ctk.CTkLabel(
            center, text="Scanning Organization...", font=("Verdana", 20, "bold")
        ).pack()
        self.scan_status = ctk.CTkLabel(
            center, text="Initializing...", font=LABEL_FONT, text_color="gray"
        )
        self.scan_status.pack(pady=(10, 0))

        self._animate_scan_spinner()

        # Scanning controls (info)
        ctk.CTkLabel(self.controls, text="Scanning", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        info = ctk.CTkFrame(self.controls, fg_color="transparent")
        info.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            info,
            text="Gathering all assets from\nthe organization...",
            font=LABEL_FONT,
            text_color="gray",
            justify="center",
        ).pack()

    def _animate_scan_spinner(self, frame=0):
        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "scan_spinner") and self.scan_spinner.winfo_exists():
            self.scan_spinner.configure(text=spinners[frame % 4])
            self.after(500, lambda: self._animate_scan_spinner(frame + 1))

    def _execute_scan(self):
        try:
            self.after(
                0, lambda: self.scan_status.configure(text="Setting up admin access...")
            )
            self.internal_client.set_access_system_admin()
            self.internal_client.enable_global_site_admin()

            if self.external_client is None:
                self.after(
                    0, lambda: self.scan_status.configure(text="Creating API key...")
                )
                external_api_key = self.internal_client.create_external_api_key()
                self.external_client = VerkadaExternalAPIClient(
                    external_api_key, self.internal_client.org_short_name
                )
            else:
                self.after(
                    0,
                    lambda: self.scan_status.configure(
                        text="Using Existing API key..."
                    ),
                )

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching intercoms...")
            )
            intercoms = self.internal_client.get_object("intercoms")

            self.after(
                0,
                lambda: self.scan_status.configure(
                    text="Fetching access controllers..."
                ),
            )
            access_controllers = sanitize_list(
                intercoms, self.internal_client.get_object("access_controllers")
            )

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching cameras...")
            )
            cameras = sanitize_list(
                intercoms, self.external_client.get_object("cameras")
            )

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching sensors...")
            )
            sensors = self.internal_client.get_object("sensors")

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching desk stations...")
            )
            desk_stations = self.internal_client.get_object("desk_stations")

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching mailroom sites...")
            )
            mailroom_sites = self.internal_client.get_object("mailroom_sites")

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching guest sites...")
            )
            guest_sites = self.external_client.get_object("guest_sites")

            self.after(0, lambda: self.scan_status.configure(text="Fetching users..."))
            users = self.external_client.get_users(
                exclude_user_id=self.internal_client.user_id
            )

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching alarm sites...")
            )
            alarm_sites = self.internal_client.get_object("alarm_sites")

            self.after(
                0, lambda: self.scan_status.configure(text="Fetching alarm devices...")
            )
            alarm_devices = self.internal_client.get_object("alarm_devices")

            self.inventory = {
                "Users": users,
                "Sensors": sensors,
                "Intercoms": intercoms,
                "Desk Stations": desk_stations,
                "Mailroom Sites": mailroom_sites,
                "Access Controllers": access_controllers,
                "Cameras": cameras,
                "Guest Sites": guest_sites,
                "Alarm Devices": alarm_devices,
                "Alarm Sites": alarm_sites,
            }

            self._flatten_inventory()

            total = sum(len(items) for items in self.inventory.values())
            logger.info(f"Scan complete. Found {total} assets.")
            self.after(0, lambda: self._set_flow(FLOW_REVIEW))

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            self.after(0, lambda: self._set_flow(FLOW_SCAN))

    def _flatten_inventory(self):
        """Flatten inventory into a list for display and selection."""
        self.flattened_assets = []
        for category, items in self.inventory.items():
            for item in items:
                asset_id = (
                    item.get("id") or item.get("user_id") or item.get("alarm_site_id")
                )
                name = (
                    item.get("email")
                    or item.get("name")
                    or item.get("businessName")
                    or item.get("serial_number")
                    or "Unknown"
                )
                serial = item.get("serial_number", "N/A")
                self.flattened_assets.append(
                    {
                        "id": asset_id,
                        "category": category,
                        "name": name,
                        "serial": serial,
                        "data": item,
                    }
                )

    # Review Flow

    def _build_review_content(self):
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))

        total = len(self.flattened_assets)
        ctk.CTkLabel(header, text=f"Inventory ({total} assets)", font=HEADER_FONT).pack(
            side="left"
        )

        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(10, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        if not self.flattened_assets:
            empty = ctk.CTkFrame(list_frame, fg_color="transparent")
            empty.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                empty,
                text="No Assets Found",
                font=("Verdana", 18, "bold"),
                text_color="gray",
            ).pack()
            return

        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Assets found:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        for i, asset in enumerate(self.flattened_assets, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=3)

            badge = ctk.CTkFrame(
                card, fg_color="#1F6AA5", width=30, height=30, corner_radius=15
            )
            badge.pack(side="left", padx=10, pady=10)
            badge.pack_propagate(False)
            ctk.CTkLabel(
                badge, text=str(i), font=("Verdana", 10, "bold"), text_color="white"
            ).place(relx=0.5, rely=0.5, anchor="center")

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=10)

            name_text = asset["name"]
            if len(name_text) > 40:
                name_text = name_text[:37] + "..."
            ctk.CTkLabel(info, text=name_text, font=("Verdana", 12, "bold")).pack(
                anchor="w"
            )

            detail_text = f"{asset['category']}"
            if asset["serial"] != "N/A":
                detail_text += f" • S/N: {asset['serial']}"
            ctk.CTkLabel(
                info, text=detail_text, font=("Verdana", 10), text_color="gray"
            ).pack(anchor="w")

    def _build_review_controls(self):
        # Summary
        summary = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        summary.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

        total = len(self.flattened_assets)
        ctk.CTkLabel(summary, text="Summary", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        for category, items in self.inventory.items():
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=1)
            ctk.CTkLabel(
                row, text=f"{category}:", font=LABEL_FONT, text_color="gray"
            ).pack(side="left")
            ctk.CTkLabel(row, text=str(len(items)), font=("Verdana", 11, "bold")).pack(
                side="right"
            )

        ctk.CTkFrame(summary, height=1, fg_color=("gray80", "gray30")).pack(
            fill="x", padx=15, pady=8
        )

        total_row = ctk.CTkFrame(summary, fg_color="transparent")
        total_row.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkLabel(total_row, text="Total:", font=("Verdana", 12, "bold")).pack(
            side="left"
        )
        ctk.CTkLabel(
            total_row,
            text=str(total),
            font=("Verdana", 14, "bold"),
            text_color="#1F6AA5",
        ).pack(side="right")

        # Buttons
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(20, 10))
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Save CSV Report",
            font=LABEL_FONT,
            height=45,
            command=self._save_report,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        btn_row = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_row,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=self._reset,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        ctk.CTkButton(
            btn_row,
            text="Select Assets",
            font=LABEL_FONT,
            height=45,
            command=lambda: self._set_flow(FLOW_SELECT),
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _save_report(self):
        """Generate and save a formatted text report."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"{self.internal_client.org_short_name}_report.txt",
        )
        if not file_path:
            return

        try:
            generate_report(
                org_name=self.internal_client.org_short_name,
                inventory=self.inventory,
                file_path=file_path,
            )
            logger.info(f"Report saved to: {file_path}")
            messagebox.showinfo("Success", f"Report saved to:\n{file_path}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            messagebox.showerror("Error", f"Failed to save report:\n{e}")

    # Select Flow

    def _build_select_content(self):
        self.content.grid_rowconfigure(1, weight=1)  # Only 2 rows now

        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(10, 5))

        total = len(self.flattened_assets)
        ctk.CTkLabel(
            header, text=f"Select Assets ({total} total)", font=HEADER_FONT
        ).pack(side="left")

        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(
            header,
            text="Select All",
            variable=self.select_all_var,
            font=("Verdana", 11),
            command=self._toggle_select_all,
        )
        self.select_all_cb.pack(side="right")

        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(5, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Select assets:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        self.asset_vars = {}
        for i, asset in enumerate(self.flattened_assets, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=3)

            var = ctk.BooleanVar(value=False)
            var.trace_add(
                "write", lambda *args, a=asset["id"], v=var: self._on_asset_toggle(a, v)
            )
            self.asset_vars[asset["id"]] = var

            cb = ctk.CTkCheckBox(card, text="", variable=var, width=20)
            cb.pack(side="left", padx=10)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=8)

            name_text = asset["name"]
            if len(name_text) > 35:
                name_text = name_text[:32] + "..."
            ctk.CTkLabel(
                info, text=f"{i}. {name_text}", font=("Verdana", 11, "bold")
            ).pack(anchor="w")

            detail_text = f"{asset['category']}"
            if asset["serial"] != "N/A":
                detail_text += f" • S/N: {asset['serial']}"
            ctk.CTkLabel(
                info, text=detail_text, font=("Verdana", 10), text_color="gray"
            ).pack(anchor="w")

    def _build_select_controls(self):
        # Selection counter
        self.selection_frame = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        self.selection_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        ctk.CTkLabel(
            self.selection_frame, text="Selected", font=("Verdana", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        self.selected_count_label = ctk.CTkLabel(
            self.selection_frame,
            text="0",
            font=("Verdana", 36, "bold"),
            text_color="#1F6AA5",
        )
        self.selected_count_label.pack()

        ctk.CTkLabel(
            self.selection_frame,
            text=f"/ {len(self.flattened_assets)} assets",
            font=LABEL_FONT,
            text_color="gray",
        ).pack(pady=(0, 15))

        # Warning
        warning = ctk.CTkFrame(self.controls, fg_color="transparent")
        warning.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        ctk.CTkLabel(
            warning,
            text="Warning: This will delete the asset from the organization\nThis action cannot be undone!",
            font=("Verdana", 11),
            text_color="#FF5555",
            wraplength=280,
            justify="center",
        ).pack()

        # Buttons
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_REVIEW),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        self.btn_confirm_select = ctk.CTkButton(
            btn_frame,
            text="Decommission",
            font=("Verdana", 12, "bold"),
            height=45,
            fg_color="#FF5555",
            hover_color="#CC4444",
            state="disabled",
            command=self._start_deletion,
        )
        self.btn_confirm_select.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _toggle_select_all(self):
        select_all = self.select_all_var.get()
        for var in self.asset_vars.values():
            var.set(select_all)

    def _on_asset_toggle(self, asset_id, var):
        if var.get():
            self.selected_assets.add(asset_id)
        else:
            self.selected_assets.discard(asset_id)

        count = len(self.selected_assets)
        self.selected_count_label.configure(text=str(count))

        if count > 0:
            self.btn_confirm_select.configure(state="normal")
        else:
            self.btn_confirm_select.configure(state="disabled")

        # Update select all checkbox state
        if count == len(self.flattened_assets):
            self.select_all_var.set(True)
        elif count == 0:
            self.select_all_var.set(False)

    # Processing Flow

    def _build_processing_content(self):
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self.process_spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.process_spinner.pack(pady=(0, 20))
        ctk.CTkLabel(
            center, text="Decommissioning...", font=("Verdana", 20, "bold")
        ).pack()
        self.process_status = ctk.CTkLabel(
            center, text="Starting deletion...", font=LABEL_FONT, text_color="gray"
        )
        self.process_status.pack(pady=(10, 0))

        self._animate_process_spinner()

    def _build_processing_controls(self):
        ctk.CTkLabel(self.controls, text="Deleting", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        progress = ctk.CTkFrame(self.controls, fg_color="transparent")
        progress.place(relx=0.5, rely=0.4, anchor="center")

        self.progress_count = ctk.CTkLabel(
            progress, text="0", font=("Verdana", 48, "bold"), text_color="#FF5555"
        )
        self.progress_count.pack()
        ctk.CTkLabel(
            progress,
            text=f"/ {len(self.selected_assets)} assets",
            font=LABEL_FONT,
            text_color="gray",
        ).pack()

        self.progress_bar = ctk.CTkProgressBar(
            self.controls, height=8, corner_radius=4, progress_color="#FF5555"
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=30, pady=(200, 0))
        self.progress_bar.set(0)

        self.current_deletion = ctk.CTkLabel(
            self.controls,
            text="Preparing...",
            font=("Verdana", 11),
            text_color="gray",
            wraplength=280,
        )
        self.current_deletion.grid(row=2, column=0, pady=(15, 0), padx=20)

    def _animate_process_spinner(self, frame=0):
        if self.current_flow != FLOW_PROCESSING:
            return
        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "process_spinner") and self.process_spinner.winfo_exists():
            self.process_spinner.configure(text=spinners[frame % 4])
            self.after(500, lambda: self._animate_process_spinner(frame + 1))

    def _start_deletion(self):
        self._set_flow(FLOW_PROCESSING)
        threading.Thread(target=self._execute_deletion, daemon=True).start()

    def _execute_deletion(self):
        self.success_count = 0
        self.fail_count = 0
        self.deleted_items = []
        self.failed_items = []

        # Create a lookup for assets by ID
        asset_lookup = {a["id"]: a for a in self.flattened_assets}

        # Get selected assets
        selected_list = [
            asset_lookup[a_id] for a_id in self.selected_assets if a_id in asset_lookup
        ]
        total = len(selected_list)

        # Group by category for ordered deletion
        for category, api_type in DELETION_ORDER:
            items_in_category = [a for a in selected_list if a["category"] == category]

            for item in items_in_category:
                try:
                    self.after(
                        0,
                        lambda c=category, n=item["name"]: (
                            self.current_deletion.configure(
                                text=f"Deleting {category}: {n[:30]}..."
                            )
                        ),
                    )

                    self._delete_single_item(item, category, api_type)
                    self.success_count += 1
                    self.deleted_items.append(item)
                    logger.info(f"Deleted {category}: {item['name']}")
                except Exception as e:
                    self.fail_count += 1
                    self.failed_items.append((item, str(e)))
                    logger.error(f"Failed to delete {category} {item['name']}: {e}")

                progress = (self.success_count + self.fail_count) / total
                self.after(
                    0,
                    lambda p=progress, s=self.success_count: self._update_progress(
                        p, s
                    ),
                )

        self.after(0, lambda: self._set_flow(FLOW_COMPLETE))

    def _delete_single_item(self, item, category, api_type):
        """Delete a single item using the appropriate API."""
        item_data = item["data"]

        if category == "Users":
            if self.external_client is None:
                raise RuntimeError("External client not initialized")
            self.external_client.delete_user(item_data["id"])
        elif category == "Alarm Sites":
            # Special handling for alarm sites
            if item_data.get("alarm_system_id"):
                self.internal_client.delete_object(
                    "alarm_systems", item_data["alarm_system_id"]
                )
            self.internal_client.delete_object(
                "alarm_sites", [item_data["alarm_site_id"], item_data["site_id"]]
            )
        else:
            # All other items use internal client's delete_object
            category_key = category.lower().replace(" ", "_")
            self.internal_client.delete_object(category_key, item_data["id"])

    def _update_progress(self, progress, count):
        if hasattr(self, "progress_bar"):
            self.progress_bar.set(progress)
        if hasattr(self, "progress_count"):
            self.progress_count.configure(text=str(count))

    # Complete Flow

    def _build_complete_content(self):
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        if self.fail_count == 0:
            icon, color, msg = (
                "✓",
                "#2CC985",
                f"All {self.success_count} assets deleted successfully!",
            )
        elif self.success_count > 0:
            icon, color, msg = (
                "⚠",
                "orange",
                f"{self.success_count} of {self.success_count + self.fail_count} assets deleted",
            )
        else:
            icon, color, msg = "✗", "#FF5555", "No assets could be deleted"

        ctk.CTkLabel(center, text=icon, font=("Verdana", 80), text_color=color).pack(
            pady=(0, 20)
        )
        ctk.CTkLabel(center, text="Complete!", font=("Verdana", 24, "bold")).pack()
        ctk.CTkLabel(center, text=msg, font=("Verdana", 14), text_color=color).pack(
            pady=(15, 0)
        )

        if self.failed_items:
            failed_frame = ctk.CTkFrame(
                center, fg_color=("gray90", "gray20"), corner_radius=8
            )
            failed_frame.pack(fill="x", padx=40, pady=(20, 0))

            ctk.CTkLabel(
                failed_frame, text="Failed Items:", font=("Verdana", 12, "bold")
            ).pack(anchor="w", padx=15, pady=(10, 5))

            for item, error in self.failed_items[:5]:
                ctk.CTkLabel(
                    failed_frame,
                    text=f"• {item['name']}: {error[:40]}...",
                    font=("Verdana", 10),
                    text_color="gray",
                ).pack(anchor="w", padx=15)

            if len(self.failed_items) > 5:
                ctk.CTkLabel(
                    failed_frame,
                    text=f"... and {len(self.failed_items) - 5} more",
                    font=("Verdana", 10),
                    text_color="gray",
                ).pack(anchor="w", padx=15, pady=(0, 10))

    def _build_complete_controls(self):
        ctk.CTkLabel(self.controls, text="Done!", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        results = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        results.place(relx=0.5, rely=0.4, anchor="center", relwidth=0.85)

        ctk.CTkLabel(results, text="Results", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        for label, value, col in [
            ("Successful:", str(self.success_count), "#2CC985"),
            (
                "Failed:",
                str(self.fail_count),
                "#FF5555" if self.fail_count > 0 else "white",
            ),
            ("Total:", str(self.success_count + self.fail_count), "white"),
        ]:
            row = ctk.CTkFrame(results, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, font=LABEL_FONT).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=("Verdana", 12, "bold"), text_color=col
            ).pack(side="right")

        ctk.CTkButton(
            self.controls,
            text="Start New Decommission",
            font=("Arial", 14, "bold"),
            height=50,
            command=self._reset,
        ).grid(row=10, column=0, sticky="ew", padx=20, pady=(0, 20))

    # Helpers

    def _reset(self):
        """Reset the tool to initial state."""
        self.inventory = {}
        self.flattened_assets = []
        self.selected_assets = set()
        self.deleted_items = []
        self.failed_items = []
        self.success_count = 0
        self.fail_count = 0
        self._set_flow(FLOW_SCAN)

import logging
import threading
from datetime import datetime, timedelta

import customtkinter as ctk
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_utilities import get_env_var

logger = logging.getLogger(__name__)

FLOW_CONFIGURE = "configure"
FLOW_SELECT = "select"
FLOW_PREVIEW = "preview"
FLOW_CONFIRM = "confirm"
FLOW_PROCESSING = "processing"
FLOW_COMPLETE = "complete"

# Styling constants
CONTROL_WIDTH = 320
CARD_BG_COLOR = "#333333"
CARD_BG = ("gray95", "gray17")
HEADER_FONT = ("Verdana", 22, "bold")
TITLE_FONT = ("Verdana", 18, "bold")
LABEL_FONT = ("Verdana", 12)


class AddUserTool(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.import_client = None
        self.selected_site_id = None
        self.selected_site_name = None
        self.selected_date_str = datetime.now().strftime("%m/%d/%Y")
        self.pending_visits = []
        self.sites_cache = getattr(controller, "shared_sites_cache", None)
        self.successful_imports = 0

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

        self.current_flow = FLOW_SELECT if self.sites_cache else FLOW_CONFIGURE
        self._refresh_ui()

    def _set_flow(self, flow):
        self.current_flow = flow
        self._refresh_ui()

    def _refresh_ui(self):
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        if self.current_flow == FLOW_CONFIGURE:
            self.content.grid_remove()
            self.controls.grid(
                row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20
            )
            self._build_configure_controls()
            return

        if self.current_flow == FLOW_SELECT:
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=1)
            self.content.master.grid_columnconfigure(1, weight=2)
        else:
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=3)
            self.content.master.grid_columnconfigure(1, weight=1)
        self.controls.grid(row=0, column=1, sticky="nsew")

        builders = {
            FLOW_SELECT: (self._build_select_content, self._build_select_controls),
            FLOW_PREVIEW: (self._build_preview_content, self._build_preview_controls),
            FLOW_PROCESSING: (
                self._build_processing_contents,
                self._build_processing_controls,
            ),
            FLOW_COMPLETE: (
                self._build_complete_contents,
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

    # Configure Flow

    def _build_configure_controls(self):
        center = ctk.CTkFrame(self.controls, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5)
        center.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(center, text="Configuration", font=HEADER_FONT).grid(
            row=0, column=0, pady=(0, 10)
        )
        ctk.CTkLabel(
            center,
            text="Enter Import Organization credentials:",
            font=LABEL_FONT,
            text_color="gray",
        ).grid(row=1, column=0, pady=(0, 30))

        card = ctk.CTkFrame(
            center, corner_radius=15, border_width=2, border_color=CARD_BG_COLOR
        )
        card.grid(row=2, column=0, sticky="ew", pady=20)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="Org. Short Name", font=("Verdana", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=30, pady=(30, 5)
        )
        self.entry_org = ctk.CTkEntry(card, height=45, font=LABEL_FONT)
        self.entry_org.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 15))

        ctk.CTkLabel(card, text="API Key", font=("Verdana", 13, "bold")).grid(
            row=2, column=0, sticky="w", padx=30, pady=(10, 5)
        )

        key_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_frame.grid(row=3, column=0, sticky="ew", padx=30, pady=(0, 30))
        key_frame.grid_columnconfigure(0, weight=1)
        key_frame.grid_columnconfigure(1, weight=0)

        self.entry_key = ctk.CTkEntry(
            key_frame,
            placeholder_text="Enter API key",
            height=45,
            font=LABEL_FONT,
            show="•",
        )
        self.entry_key.grid(row=0, column=0, sticky="ew")

        self.btn_show_key = ctk.CTkButton(
            key_frame,
            text="Show",
            width=60,
            height=45,
            font=("Verdana", 12),
            fg_color="transparent",
            text_color="#888888",
            hover_color="#333333",
            command=self._toggle_key_visibility,
        )
        self.btn_show_key.grid(row=0, column=1, padx=(4, 0))

        self.btn_connect = ctk.CTkButton(
            center,
            text="Connect",
            font=("Verdana", 14, "bold"),
            height=50,
            command=self._load_sites,
        )
        self.btn_connect.grid(row=3, column=0, sticky="ew", pady=(20, 0))

        # Auto-fill from env
        if key := get_env_var("LEGAL_API_KEY"):
            self.entry_key.insert(0, key)
        if org := get_env_var("LEGAL_ORG_SHORT_NAME"):
            self.entry_org.insert(0, org)

    # Select Flow

    def _build_select_content(self):
        self.content.grid_rowconfigure(2, weight=1)
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        ctk.CTkLabel(header, text="Select Site:", font=HEADER_FONT).pack(side="left")

        self.search_bar = ctk.CTkEntry(
            self.content, placeholder_text="Search", height=38, font=LABEL_FONT
        )
        self.search_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 10))
        self.search_bar.bind("<KeyRelease>", self._filter_sites)

        self.scroll_frame = ctk.CTkScrollableFrame(
            self.content,
            label_text="Sites:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))

        self.site_var = ctk.StringVar(value="")
        self.site_var.trace_add("write", self._on_site_change)
        self.site_widgets = []

        if self.sites_cache:
            self._populate_sites(self.sites_cache)

    def _build_select_controls(self):
        ctk.CTkLabel(self.controls, text="Date:", font=("Verdana", 14, "bold")).grid(
            row=0, column=0, pady=(25, 10), padx=20, sticky="w"
        )

        self.date_display = ctk.CTkEntry(
            self.controls, justify="center", font=("Verdana", 16, "bold"), height=40
        )
        self.date_display.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.date_display.insert(0, self.selected_date_str)
        self.date_display.bind("<FocusOut>", self._on_date_manual_entry)
        self.date_display.bind("<Return>", self._on_date_manual_entry)

        week_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        week_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=5)
        for i in range(7):
            week_frame.grid_columnconfigure(i, weight=1)

        today = datetime.now()
        for i in range(7):
            day = today - timedelta(days=6 - i)
            day_str = day.strftime("%m/%d/%Y")
            is_selected = day_str == self.selected_date_str
            btn = ctk.CTkButton(
                week_frame,
                text=f"{day.strftime('%a')}\n{day.strftime('%d')}",
                width=38,
                height=50,
                font=("Verdana", 10),
                fg_color="#1F6AA5" if is_selected else "transparent",
                border_width=0 if is_selected else 1,
                hover_color="#144870" if is_selected else ("gray85", "gray25"),
                command=lambda d=day_str: self._set_date(d),
            )
            btn.grid(row=0, column=i, padx=2, sticky="ew")

        ctk.CTkFrame(self.controls, height=2, fg_color=("gray80", "gray30")).grid(
            row=3, column=0, sticky="ew", padx=20, pady=20
        )
        ctk.CTkLabel(
            self.controls, text="Selected Site:", font=LABEL_FONT, text_color="gray"
        ).grid(row=4, column=0, padx=20, sticky="w")
        self.site_lbl = ctk.CTkLabel(
            self.controls, text="None", font=("Verdana", 14, "bold"), wraplength=270
        )
        self.site_lbl.grid(row=5, column=0, padx=20, sticky="w")

        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=6, column=0, sticky="ew", padx=20, pady=(20, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=40,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_CONFIGURE),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_preview = ctk.CTkButton(
            btn_frame,
            text="Load",
            font=("Verdana", 12, "bold"),
            height=40,
            state="disabled",
            command=self._load_preview,
        )
        self.btn_preview.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # Preview Flow

    def _build_preview_content(self):
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))
        ctk.CTkLabel(
            header, text=f"Visitors ({len(self.pending_visits)}):", font=HEADER_FONT
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text=f"{self.selected_site_name} • {self.selected_date_str}",
            font=LABEL_FONT,
            text_color="gray",
        ).pack(side="right")

        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(10, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        if not self.pending_visits:
            empty = ctk.CTkFrame(list_frame, fg_color="transparent")
            empty.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(
                empty,
                text="No Visitors Found",
                font=("Verdana", 18, "bold"),
                text_color="gray",
            ).pack()
            ctk.CTkLabel(
                empty,
                text="No guest visitors found for selected site and date.",
                font=LABEL_FONT,
                text_color="gray",
            ).pack()
            return

        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Review visitors:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        for i, visit in enumerate(self.pending_visits, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=4)

            badge = ctk.CTkFrame(
                card, fg_color="#1F6AA5", width=35, height=35, corner_radius=17
            )
            badge.pack(side="left", padx=12, pady=12)
            badge.pack_propagate(False)
            ctk.CTkLabel(
                badge, text=str(i), font=("Verdana", 12, "bold"), text_color="white"
            ).place(relx=0.5, rely=0.5, anchor="center")

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=12)
            name = (
                f"{visit.get('first_name', '')} {visit.get('last_name', '')}".strip()
                or "Unknown"
            )
            ctk.CTkLabel(info, text=name, font=("Verdana", 14, "bold")).pack(anchor="w")
            ctk.CTkLabel(
                info,
                text=visit.get("email", "No email"),
                font=("Verdana", 11),
                text_color="gray",
            ).pack(anchor="w")

    def _build_preview_controls(self):
        summary = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        summary.grid(row=0, column=0, sticky="ew", padx=20, pady=(25, 10))
        ctk.CTkLabel(summary, text="Summary", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        for label, value in [
            (
                "Site:",
                (self.selected_site_name or "None")[:25] + "..."
                if len(self.selected_site_name or "") > 25
                else self.selected_site_name or "None",
            ),
            ("Date:", self.selected_date_str),
            ("Visitors:", str(len(self.pending_visits))),
        ][:2]:
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, font=LABEL_FONT, text_color="gray").pack(
                side="left"
            )
            ctk.CTkLabel(row, text=value, font=("Verdana", 12, "bold")).pack(
                side="right"
            )

        row = ctk.CTkFrame(summary, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=(2, 15))
        ctk.CTkLabel(row, text="Visitors:", font=LABEL_FONT, text_color="gray").pack(
            side="left"
        )
        ctk.CTkLabel(
            row,
            text=str(len(self.pending_visits)),
            font=("Verdana", 12, "bold"),
            text_color="#2CC985" if self.pending_visits else "gray",
        ).pack(side="right")

        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(20, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_SELECT),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        if self.pending_visits:
            ctk.CTkButton(
                btn_frame,
                text="Add Users",
                font=("Verdana", 12, "bold"),
                height=45,
                fg_color="#2CC985",
                hover_color="#229965",
                command=self._start_import,
            ).grid(row=0, column=1, sticky="ew", padx=(5, 0))
        else:
            ctk.CTkButton(
                btn_frame,
                text="No Visitors",
                font=("Verdana", 12, "bold"),
                height=45,
                state="disabled",
                fg_color="gray",
            ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # Processing Flow

    def _build_processing_contents(self):
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self.spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.spinner.pack(pady=(0, 20))
        ctk.CTkLabel(
            center, text="Adding Users to Organization...", font=("Verdana", 20, "bold")
        ).pack()
        ctk.CTkLabel(
            center, text="Please wait...", font=LABEL_FONT, text_color="gray"
        ).pack(pady=(10, 0))

        self._animate_spinner()

    def _build_processing_controls(self):
        ctk.CTkLabel(self.controls, text="Processing", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        progress = ctk.CTkFrame(self.controls, fg_color="transparent")
        progress.place(relx=0.5, rely=0.4, anchor="center")

        self.progress_count = ctk.CTkLabel(
            progress, text="0", font=("Verdana", 48, "bold"), text_color="#1F6AA5"
        )
        self.progress_count.pack()
        ctk.CTkLabel(
            progress,
            text=f"/ {len(self.pending_visits)} users",
            font=LABEL_FONT,
            text_color="gray",
        ).pack()

        self.progress_bar = ctk.CTkProgressBar(self.controls, height=8, corner_radius=4)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=30, pady=(200, 0))
        self.progress_bar.set(0)

        self.current_user = ctk.CTkLabel(
            self.controls,
            text="Starting...",
            font=("Verdana", 11),
            text_color="gray",
            wraplength=280,
        )
        self.current_user.grid(row=2, column=0, pady=(15, 0), padx=20)

    def _animate_spinner(self, frame=0):
        """Animate processing spinner."""
        if self.current_flow != FLOW_PROCESSING:
            return
        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "spinner") and self.spinner.winfo_exists():
            self.spinner.configure(text=spinners[frame % 4])
            self.after(500, lambda: self._animate_spinner(frame + 1))

    # Complete Flow

    def _build_complete_contents(self):
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        success = self.successful_imports
        total = len(self.pending_visits)

        if success == total:
            icon, color, msg = "✓", "#2CC985", f"All {total} invitations sent!"
        elif success > 0:
            icon, color, msg = "⚠", "orange", f"{success} of {total} invitations sent"
        else:
            icon, color, msg = "✗", "#FF5555", "No invitations could be sent"

        ctk.CTkLabel(center, text=icon, font=("Arial", 80), text_color=color).pack(
            pady=(0, 20)
        )
        ctk.CTkLabel(center, text="Complete!", font=("Arial", 24, "bold")).pack()
        ctk.CTkLabel(center, text=msg, font=("Arial", 14), text_color=color).pack(
            pady=(15, 0)
        )

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
            ("Successful:", str(self.successful_imports), "#2CC985"),
            ("Total:", str(len(self.pending_visits)), "white"),
        ]:
            row = ctk.CTkFrame(results, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, font=LABEL_FONT).pack(side="left")
            ctk.CTkLabel(
                row, text=value, font=("Verdana", 12, "bold"), text_color=col
            ).pack(side="right")

        ctk.CTkButton(
            self.controls,
            text="Start New Import",
            font=("Arial", 14, "bold"),
            height=50,
            command=self._reset,
        ).grid(row=10, column=0, sticky="ew", padx=20, pady=(0, 20))

    # Helpers

    def _control_header(self, title, subtitle):
        """Add standard control panel header."""
        ctk.CTkLabel(self.controls, text=title, font=TITLE_FONT).grid(
            row=0, column=0, pady=(25, 10), padx=20, sticky="w"
        )
        ctk.CTkLabel(
            self.controls,
            text=subtitle,
            font=LABEL_FONT,
            text_color="gray",
            wraplength=280,
            justify="left",
        ).grid(row=1, column=0, pady=(0, 20), padx=20, sticky="w")
        ctk.CTkFrame(self.controls, height=2, fg_color=("gray80", "gray30")).grid(
            row=2, column=0, sticky="ew", padx=20, pady=10
        )

    def _set_date(self, date_str):
        self.selected_date_str = date_str
        if hasattr(self, "date_display"):
            self.date_display.delete(0, "end")
            self.date_display.insert(0, date_str)
        if self.current_flow == FLOW_SELECT:
            self._refresh_ui()

    def _on_date_manual_entry(self, event=None):
        """Handle manual date entry with validation."""
        date_str = self.date_display.get().strip()
        try:
            datetime.strptime(date_str, "%m/%d/%Y")
            self.selected_date_str = date_str
            self._refresh_ui()
        except ValueError:
            self.date_display.delete(0, "end")
            self.date_display.insert(0, self.selected_date_str)

    def _on_site_change(self, *args):
        site_id = self.site_var.get()
        if site_id:
            self.selected_site_id = site_id
            for rb, name in self.site_widgets:
                if rb.cget("value") == site_id:
                    self.selected_site_name = name
                    break
            display = (
                (self.selected_site_name or "None")[:30] + "..."
                if len(self.selected_site_name or "") > 30
                else self.selected_site_name
            )
            if hasattr(self, "site_lbl"):
                self.site_lbl.configure(text=display)
            if hasattr(self, "btn_preview"):
                self.btn_preview.configure(state="normal")

    def _populate_sites(self, sites):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.site_widgets.clear()

        if not sites:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No sites found",
                font=LABEL_FONT,
                text_color="gray",
            ).pack(pady=20)
            return

        for site in sites:
            rb = ctk.CTkRadioButton(
                self.scroll_frame,
                text=site["name"],
                variable=self.site_var,
                value=site["id"],
                font=LABEL_FONT,
                radiobutton_width=20,
                radiobutton_height=20,
            )
            rb.pack(anchor="w", pady=6, padx=10, fill="x")
            self.site_widgets.append((rb, site["name"]))

    def _filter_sites(self, event):
        query = self.search_bar.get().lower()
        for rb, name in self.site_widgets:
            rb.pack(
                anchor="w", pady=6, padx=10, fill="x"
            ) if query in name.lower() else rb.pack_forget()

    def _toggle_key_visibility(self):
        if self.entry_key.cget("show") == "•":
            self.entry_key.configure(show="")
            self.btn_show_key.configure(text="Hide")
        else:
            self.entry_key.configure(show="•")
            self.btn_show_key.configure(text="Show")

    def _load_sites(self):
        """Load sites from API."""
        api_key = self.entry_key.get().strip()
        org_name = self.entry_org.get().strip()

        if not api_key or not org_name:
            logger.error("Missing API Key or Organization Short Name")
            return

        self.btn_connect.configure(state="disabled", text="Connecting...")

        def fetch():
            try:
                self.import_client = VerkadaExternalAPIClient(api_key, org_name)
                sites = self.import_client.get_object("guest_sites")
                self.sites_cache = sites
                self.controller.shared_sites_cache = sites
                self.after(0, lambda: self._set_flow(FLOW_SELECT))
                logger.info(f"Loaded {len(sites)} sites")
            except Exception as e:
                logger.error(f"Error loading sites: {e}")
                self.after(
                    0,
                    lambda: self.btn_connect.configure(
                        state="normal", text="Connect & Load Sites"
                    ),
                )

        threading.Thread(target=fetch, daemon=True).start()

    def _load_preview(self):
        site_id = self.site_var.get()
        if not site_id:
            return

        if not self.import_client:
            logger.error("Import client not initialized")
            return

        self.btn_preview.configure(state="disabled", text="Loading...")

        def fetch():
            try:
                start_dt = datetime.strptime(self.selected_date_str, "%m/%d/%Y")
                start_ts = int(start_dt.timestamp())
                end_ts = int(
                    (start_dt + timedelta(days=1) - timedelta(seconds=1)).timestamp()
                )

                if self.import_client is not None:
                    visits = self.import_client.get_guest_visits(
                        site_id, start_ts, end_ts
                    )
                    self.pending_visits = visits or []
                    self.after(0, lambda: self._set_flow(FLOW_PREVIEW))
                    logger.info(f"Found {len(self.pending_visits)} visitors")
            except Exception as e:
                logger.error(f"Error loading visitors: {e}")
                self.after(
                    0,
                    lambda: self.btn_preview.configure(
                        state="normal", text="Load Visitors →"
                    ),
                )

        threading.Thread(target=fetch, daemon=True).start()

    def _start_import(self):
        self._set_flow(FLOW_PROCESSING)
        threading.Thread(target=self._execute_import, daemon=True).start()

    def _execute_import(self):
        self.successful_imports = 0
        total = len(self.pending_visits)

        for i, visit in enumerate(self.pending_visits, 1):
            if not self.controller.client:
                logger.error("Client session lost")
                break

            try:
                name = f"{visit.get('first_name', '')} {visit.get('last_name', '')}".strip()
                self.after(
                    0, lambda n=name: self.current_user.configure(text=f"Inviting: {n}")
                )

                self.controller.client.invite_user(
                    visit["first_name"],
                    visit["last_name"],
                    visit["email"],
                    org_admin=True,
                )
                self.successful_imports += 1
                logger.info(f"Invited: {name}")
            except Exception as e:
                logger.error(f"Failed to invite: {e}")

            progress = i / total
            self.after(0, lambda p=progress, c=i: self._update_progress(p, c))

        self.after(0, lambda: self._set_flow(FLOW_COMPLETE))

    def _update_progress(self, progress, count):
        if hasattr(self, "progress_bar"):
            self.progress_bar.set(progress)
        if hasattr(self, "progress_count"):
            self.progress_count.configure(text=str(count))

    def _reset(self):
        self.pending_visits = []
        self.selected_site_id = None
        self.site_var.set("")
        self.successful_imports = 0
        self._set_flow(FLOW_SELECT)

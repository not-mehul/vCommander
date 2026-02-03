import os
import threading
from datetime import datetime, timedelta

import customtkinter as ctk

# Import your backend client
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_utilities import get_env_var


class AddUserTool(ctk.CTkFrame):
    FLOW_SELECT_SITE = "select_site"
    FLOW_PREVIEW_USERS = "preview_users"
    FLOW_PROCESSING = "processing"
    FLOW_COMPLETE = "complete"

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- STATE ---
        self.legal_client = None
        self.selected_site_id = None
        self.selected_site_name = None
        self.selected_date_str = datetime.now().strftime("%m/%d/%Y")
        self.pending_visits = []  # Store visits to be imported

        # Cache for sites
        self.sites_cache = getattr(self.controller, "shared_sites_cache", None)

        # Layout Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. Header & Credentials
        self.setup_header()

        # 2. Main Content
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # 3. Dynamic Control Frame (Right side)
        self.control_frame = ctk.CTkFrame(self.content_frame, width=300)
        self.control_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.control_frame.grid_rowconfigure(0, weight=1)
        self.control_frame.grid_propagate(False)

        # Left side container (changes based on flow)
        self.left_container = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.left_container.grid(row=0, column=0, sticky="nsew")

        # Current flow state
        self.current_flow = self.FLOW_SELECT_SITE

        # Initialize UI
        self.show_site_selection_ui()

        # Auto-load if cache exists
        if self.sites_cache:
            self.populate_site_list(self.sites_cache)
        else:
            api_key = get_env_var("LEGAL_API_KEY")
            org_name = get_env_var("LEGAL_ORG_SHORT_NAME")
            if api_key and org_name:
                self.entry_api_key.insert(0, api_key)
                self.entry_org_name.insert(0, org_name)
                self.load_sites()

    def setup_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))

        title = ctk.CTkLabel(
            header_frame, text="User Invitation Tool", font=("Arial", 20, "bold")
        )
        title.pack(side="left")

        self.config_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.config_frame.pack(side="right")

        self.entry_org_name = ctk.CTkEntry(
            self.config_frame, placeholder_text="Legal Org Short Name", width=150
        )
        self.entry_org_name.pack(side="left", padx=5)

        self.entry_api_key = ctk.CTkEntry(
            self.config_frame, placeholder_text="Legal API Key", width=200, show="*"
        )
        self.entry_api_key.pack(side="left", padx=5)

        self.btn_connect = ctk.CTkButton(
            self.config_frame, text="Load Sites", width=100, command=self.load_sites
        )
        self.btn_connect.pack(side="left", padx=5)

    def clear_left_container(self):
        """Clear the left side container for view switching"""
        for widget in self.left_container.winfo_children():
            widget.destroy()

    def update_control_frame(self):
        """Update the right control frame based on current flow"""
        # Clear existing controls
        for widget in self.control_frame.winfo_children():
            widget.destroy()

        if self.current_flow == self.FLOW_SELECT_SITE:
            self._build_site_controls()
        elif self.current_flow == self.FLOW_PREVIEW_USERS:
            self._build_preview_controls()
        elif self.current_flow == self.FLOW_PROCESSING:
            self._build_processing_controls()
        elif self.current_flow == self.FLOW_COMPLETE:
            self._build_complete_controls()

    def _build_site_controls(self):
        """Build controls for site selection phase"""
        lbl_date = ctk.CTkLabel(
            self.control_frame, text="Select Date", font=("Arial", 14, "bold")
        )
        lbl_date.pack(pady=(20, 10))

        self.date_display = ctk.CTkEntry(
            self.control_frame, justify="center", font=("Arial", 16)
        )
        self.date_display.insert(0, self.selected_date_str)
        self.date_display.pack(pady=5, padx=20, fill="x")

        # Week view buttons
        week_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        week_frame.pack(pady=10, padx=10, fill="x")

        today = datetime.now()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.strftime("%m/%d/%Y")
            day_lbl = day.strftime("%a\n%d")

            fg = "transparent"
            border = 1
            if i == 0:
                fg = "#1F6AA5"
                border = 0

            btn = ctk.CTkButton(
                week_frame,
                text=day_lbl,
                width=35,
                height=40,
                font=("Arial", 10),
                fg_color=fg,
                border_width=border,
                border_color="gray",
                command=lambda d=day_str: self.set_date(d),
            )
            btn.pack(side="left", padx=2, expand=True)

        # Status
        ctk.CTkFrame(self.control_frame, height=2, fg_color="gray").pack(
            fill="x", pady=20, padx=20
        )

        self.status_lbl = ctk.CTkLabel(
            self.control_frame, text="Select a site and date", text_color="gray"
        )
        self.status_lbl.pack(pady=10)

        # Preview button (disabled until site selected)
        self.btn_preview = ctk.CTkButton(
            self.control_frame,
            text="Preview Users",
            font=("Arial", 14, "bold"),
            height=40,
            fg_color="#1F6AA5",
            hover_color="#144870",
            command=self.load_preview,
            state="disabled",
        )
        self.btn_preview.pack(side="bottom", pady=20, padx=20, fill="x")

    def _build_preview_controls(self):
        """Build controls for preview/confirmation phase"""
        # Summary info
        info_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        info_frame.pack(pady=(20, 10), padx=20, fill="x")

        ctk.CTkLabel(
            info_frame, text="Ready to Import", font=("Arial", 16, "bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame, text=f"Site: {self.selected_site_name}", font=("Arial", 12)
        ).pack(anchor="w", pady=(10, 0))

        ctk.CTkLabel(
            info_frame, text=f"Date: {self.selected_date_str}", font=("Arial", 12)
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_frame,
            text=f"Users: {len(self.pending_visits)}",
            font=("Arial", 12),
            text_color="#2CC985",
        ).pack(anchor="w")

        # Warning
        ctk.CTkFrame(self.control_frame, height=2, fg_color="gray").pack(
            fill="x", pady=20, padx=20
        )

        warning_lbl = ctk.CTkLabel(
            self.control_frame,
            text="⚠️ This will send email invitations\nto all listed users as Org Admins",
            font=("Arial", 11),
            text_color="orange",
            justify="center",
        )
        warning_lbl.pack(pady=10)

        # Buttons
        btn_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=20)

        ctk.CTkButton(
            btn_frame,
            text="← Back",
            font=("Arial", 12),
            width=80,
            fg_color="transparent",
            border_width=1,
            border_color="gray",
            command=self.go_back_to_selection,
        ).pack(side="left")

        self.btn_confirm = ctk.CTkButton(
            btn_frame,
            text="CONFIRM IMPORT",
            font=("Arial", 14, "bold"),
            fg_color="#2CC985",
            hover_color="#229965",
            command=self.run_import_thread,
        )
        self.btn_confirm.pack(side="right")

    def _build_processing_controls(self):
        """Build controls for processing phase"""
        spinner_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        spinner_frame.pack(expand=True)

        # Animated dots label
        self.processing_lbl = ctk.CTkLabel(
            spinner_frame, text="Processing...", font=("Arial", 16, "bold")
        )
        self.processing_lbl.pack(pady=20)

        self.progress_lbl = ctk.CTkLabel(
            spinner_frame,
            text="0 / 0 users invited",
            font=("Arial", 12),
            text_color="gray",
        )
        self.progress_lbl.pack()

        # Animate dots
        self.animate_processing()

    def _build_complete_controls(self):
        """Build controls for completion phase"""
        complete_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        complete_frame.pack(expand=True)

        ctk.CTkLabel(
            complete_frame,
            text="✓ Complete!",
            font=("Arial", 20, "bold"),
            text_color="#2CC985",
        ).pack(pady=20)

        self.result_lbl = ctk.CTkLabel(
            complete_frame,
            text=f"Successfully invited {getattr(self, 'success_count', 0)} users",
            font=("Arial", 12),
        )
        self.result_lbl.pack()

        ctk.CTkButton(
            self.control_frame,
            text="Start New Import",
            font=("Arial", 14),
            command=self.reset_flow,
        ).pack(side="bottom", pady=20, padx=20, fill="x")

    def animate_processing(self, dot_count=0):
        """Animate the processing dots"""
        if self.current_flow != self.FLOW_PROCESSING:
            return
        dots = "." * (dot_count % 4)
        self.processing_lbl.configure(text=f"Processing{dots}")
        self.after(500, lambda: self.animate_processing(dot_count + 1))

    def show_site_selection_ui(self):
        """Show the site selection view"""
        self.clear_left_container()
        self.current_flow = self.FLOW_SELECT_SITE

        # Site list frame
        site_frame = ctk.CTkFrame(self.left_container, corner_radius=10)
        site_frame.pack(fill="both", expand=True)

        # Search Bar
        self.search_bar = ctk.CTkEntry(
            site_frame, placeholder_text="Search Sites...", height=35
        )
        self.search_bar.pack(fill="x", padx=10, pady=10)
        self.search_bar.bind("<KeyRelease>", self.filter_sites)

        # Scrollable List
        self.scroll_frame = ctk.CTkScrollableFrame(
            site_frame, label_text="Select Guest Site"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.site_var = ctk.StringVar(value="")
        self.site_var.trace_add("write", self.on_site_selected)
        self.site_widgets = []

        self.update_control_frame()

        if self.sites_cache:
            self.populate_site_list(self.sites_cache)

    def show_preview_ui(self):
        """Show the user preview view"""
        self.clear_left_container()
        self.current_flow = self.FLOW_PREVIEW_USERS

        # Preview frame
        preview_frame = ctk.CTkFrame(self.left_container, corner_radius=10)
        preview_frame.pack(fill="both", expand=True)

        # Header
        header = ctk.CTkFrame(preview_frame, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=15)

        ctk.CTkLabel(
            header,
            text=f"Users to Invite ({len(self.pending_visits)})",
            font=("Arial", 16, "bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            header,
            text=f"{self.selected_site_name} • {self.selected_date_str}",
            font=("Arial", 12),
            text_color="gray",
        ).pack(side="right")

        # Users list
        users_scroll = ctk.CTkScrollableFrame(
            preview_frame, label_text="Review before confirming"
        )
        users_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Add each user to preview
        for i, visit in enumerate(self.pending_visits, 1):
            user_card = ctk.CTkFrame(users_scroll, fg_color=("gray90", "gray20"))
            user_card.pack(fill="x", padx=5, pady=3)

            # Number badge
            num_lbl = ctk.CTkLabel(
                user_card, text=str(i), font=("Arial", 12, "bold"), width=30
            )
            num_lbl.pack(side="left", padx=10)

            # User info
            info_frame = ctk.CTkFrame(user_card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, pady=10)

            name = f"{visit.get('first_name', '')} {visit.get('last_name', '')}".strip()
            ctk.CTkLabel(
                info_frame, text=name or "Unknown", font=("Arial", 13, "bold")
            ).pack(anchor="w")

            email = visit.get("email", "No email")
            ctk.CTkLabel(
                info_frame, text=email, font=("Arial", 11), text_color="gray"
            ).pack(anchor="w")

            # Role badge
            role_lbl = ctk.CTkLabel(
                user_card,
                text="ORG ADMIN",
                font=("Arial", 9, "bold"),
                fg_color="#2CC985",
                text_color="white",
                corner_radius=4,
                width=80,
            )
            role_lbl.pack(side="right", padx=10)

        self.update_control_frame()

    def on_site_selected(self, *args):
        """Enable preview button when site selected"""
        if hasattr(self, "btn_preview"):
            if self.site_var.get():
                self.btn_preview.configure(state="normal")
            else:
                self.btn_preview.configure(state="disabled")

    def set_date(self, date_str):
        self.selected_date_str = date_str
        if hasattr(self, "date_display"):
            self.date_display.delete(0, "end")
            self.date_display.insert(0, date_str)

    def load_sites(self):
        api_key = self.entry_api_key.get().strip()
        org_name = self.entry_org_name.get().strip()

        if not api_key or not org_name:
            print("Error: Missing Legal API Key or Org Name.")
            return

        self.btn_connect.configure(state="disabled", text="Loading...")

        def _fetch():
            try:
                print("Connecting to Legal Org...")
                self.legal_client = VerkadaExternalAPIClient(api_key, org_name)
                sites = self.legal_client.get_object("guest_sites")

                self.sites_cache = sites
                self.controller.shared_sites_cache = sites

                self.after(0, lambda: self.populate_site_list(sites))
                print(f"Successfully loaded {len(sites)} sites.")
            except Exception as e:
                print(f"Error loading sites: {e}")
            finally:
                self.after(
                    0,
                    lambda: self.btn_connect.configure(
                        state="normal", text="Reload Sites"
                    ),
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def populate_site_list(self, sites):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.site_widgets.clear()

        for site in sites:
            rb = ctk.CTkRadioButton(
                self.scroll_frame,
                text=site["name"],
                variable=self.site_var,
                value=site["id"],
                font=("Arial", 14),
            )
            rb.pack(anchor="w", pady=5, padx=10)
            rb.site_name = site["name"]  # Store name for later
            self.site_widgets.append((rb, site["name"]))

    def filter_sites(self, event):
        query = event.widget.get().lower()
        for rb, name in self.site_widgets:
            if query in name.lower():
                rb.pack(anchor="w", pady=5, padx=10)
            else:
                rb.pack_forget()

    def load_preview(self):
        """Fetch visits and show preview"""
        site_id = self.site_var.get()
        if not site_id:
            return

        # Get site name
        for rb, name in self.site_widgets:
            if rb.cget("value") == site_id:
                self.selected_site_name = name
                break

        date_str = self.selected_date_str

        # Show loading in control frame
        for widget in self.control_frame.winfo_children():
            widget.destroy()

        ctk.CTkLabel(
            self.control_frame, text="Loading visits...", font=("Arial", 14)
        ).pack(expand=True)

        def _fetch_visits():
            try:
                start_dt = datetime.strptime(date_str, "%m/%d/%Y")
                end_dt = start_dt + timedelta(days=1) - timedelta(seconds=1)

                start_ts = int(start_dt.timestamp())
                end_ts = int(end_dt.timestamp())

                print(f"Fetching visits for {date_str}...")
                visits = self.legal_client.get_guest_visits(site_id, start_ts, end_ts)

                self.pending_visits = visits or []

                self.after(0, self.show_preview_ui)

            except Exception as e:
                print(f"Error loading preview: {e}")
                self.after(0, self.show_site_selection_ui)

        threading.Thread(target=_fetch_visits, daemon=True).start()

    def go_back_to_selection(self):
        """Return to site selection"""
        self.pending_visits = []
        self.show_site_selection_ui()

    def run_import_thread(self):
        """Start the import process"""
        if not self.pending_visits:
            return

        self.current_flow = self.FLOW_PROCESSING
        self.update_control_frame()

        threading.Thread(target=self.execute_import, daemon=True).start()

    def execute_import(self):
        """Execute the actual import"""
        try:
            count = 0
            total = len(self.pending_visits)

            for i, visit in enumerate(self.pending_visits, 1):
                if not self.controller.client:
                    print("Error: Internal Client session lost.")
                    break

                self.controller.client.invite_user(
                    visit["first_name"],
                    visit["last_name"],
                    visit["email"],
                    org_admin=True,
                )
                count += 1

                # Update progress
                self.after(
                    0,
                    lambda c=count, t=total: self.progress_lbl.configure(
                        text=f"{c} / {t} users invited"
                    ),
                )

            self.success_count = count
            print(f"Completed! Invited {count} users.")

        except Exception as e:
            print(f"Error during import: {e}")
        finally:
            self.after(0, self.show_complete)

    def show_complete(self):
        """Show completion state"""
        self.current_flow = self.FLOW_COMPLETE
        self.update_control_frame()

    def reset_flow(self):
        """Reset to start"""
        self.pending_visits = []
        self.selected_site_id = None
        self.site_var.set("")
        self.show_site_selection_ui()

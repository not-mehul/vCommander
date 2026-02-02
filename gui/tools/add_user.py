import os
import threading
from datetime import datetime, timedelta

import customtkinter as ctk

# Import your backend client
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_utilities import get_env_var


class AddUserTool(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # --- STATE ---
        self.legal_client = None
        self.selected_site_id = None
        self.selected_date_str = datetime.now().strftime("%m/%d/%Y")  # Default to today

        # Cache for sites so we don't refetch on every tab switch
        # Structure: [{'id': '...', 'name': '...'}, ...]
        self.sites_cache = getattr(self.controller, "shared_sites_cache", None)

        # Layout Configuration
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)  # Main content expands

        # 1. Header & Credentials
        self.setup_header()

        # 2. Main Content (Split into Site Selection & Date/Action)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        self.content_frame.grid_columnconfigure(0, weight=1)  # Site List
        self.content_frame.grid_columnconfigure(1, weight=0)  # Controls (Right side)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # Left Column: Site List
        self.setup_site_list_ui()

        # Right Column: Date Picker & Actions
        self.setup_controls_ui()

        # 3. Auto-Load if cache exists, otherwise wait for user
        if self.sites_cache:
            self.populate_site_list(self.sites_cache)
        else:
            # Check if env vars exist to auto-connect
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

        # Config Inputs (Collapsible or just small inputs at top)
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

    def setup_site_list_ui(self):
        # Container
        site_frame = ctk.CTkFrame(self.content_frame, corner_radius=10)
        site_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Search Bar
        search_bar = ctk.CTkEntry(
            site_frame, placeholder_text="Search Sites...", height=35
        )
        search_bar.pack(fill="x", padx=10, pady=10)
        search_bar.bind("<KeyRelease>", self.filter_sites)  # Live filtering

        # Scrollable List
        self.scroll_frame = ctk.CTkScrollableFrame(
            site_frame, label_text="Select Guest Site"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # We will keep references to the radio buttons here
        self.site_var = ctk.StringVar(value="")
        self.site_widgets = []

    def setup_controls_ui(self):
        control_frame = ctk.CTkFrame(self.content_frame, width=250)
        control_frame.grid(row=0, column=1, sticky="nsew")

        # --- Date Selection Section ---
        lbl_date = ctk.CTkLabel(
            control_frame, text="Select Date", font=("Arial", 14, "bold")
        )
        lbl_date.pack(pady=(20, 10))

        # Date Display
        self.date_display = ctk.CTkEntry(
            control_frame, justify="center", font=("Arial", 16)
        )
        self.date_display.insert(0, self.selected_date_str)
        self.date_display.pack(pady=5, padx=20, fill="x")

        # Custom "Week View" Buttons
        week_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        week_frame.pack(pady=10, padx=10, fill="x")

        # Generate last 7 days buttons
        today = datetime.now()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.strftime("%m/%d/%Y")
            day_lbl = day.strftime("%a\n%d")  # "Mon\n25"

            # Highlight today
            fg = "transparent"
            border = 1
            if i == 0:
                fg = "#1F6AA5"  # Blue for today
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

        # Spacer
        ctk.CTkFrame(control_frame, height=2, fg_color="gray").pack(
            fill="x", pady=20, padx=20
        )

        # --- Action Section ---
        self.btn_run = ctk.CTkButton(
            control_frame,
            text="RUN IMPORT",
            font=("Arial", 16, "bold"),
            height=50,
            fg_color="#2CC985",  # Green
            hover_color="#229965",
            command=self.run_import_thread,
        )
        self.btn_run.pack(side="bottom", pady=20, padx=20, fill="x")

        status_lbl = ctk.CTkLabel(
            control_frame, text="Ready to process", text_color="gray"
        )
        status_lbl.pack(side="bottom", pady=5)
        self.status_lbl = status_lbl

    # --- Logic ---

    def set_date(self, date_str):
        self.selected_date_str = date_str
        self.date_display.delete(0, "end")
        self.date_display.insert(0, date_str)

    def load_sites(self):
        api_key = self.entry_api_key.get().strip()
        org_name = self.entry_org_name.get().strip()

        if not api_key or not org_name:
            print("Error: Missing Legal API Key or Org Name.")
            return

        # Disable button while loading
        self.btn_connect.configure(state="disabled", text="Loading...")

        def _fetch():
            try:
                # Initialize External Client
                print("Connecting to Legal Org...")
                self.legal_client = VerkadaExternalAPIClient(api_key, org_name)
                sites = self.legal_client.get_object("guest_sites")

                # Update Cache
                self.sites_cache = sites
                self.controller.shared_sites_cache = sites  # Save to main controller

                # Update UI
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
        # Clear existing
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.site_widgets.clear()

        # Create Radio Buttons
        for site in sites:
            rb = ctk.CTkRadioButton(
                self.scroll_frame,
                text=site["name"],
                variable=self.site_var,
                value=site["id"],
                font=("Arial", 14),
            )
            rb.pack(anchor="w", pady=5, padx=10)
            self.site_widgets.append((rb, site["name"]))  # Store for filtering

    def filter_sites(self, event):
        query = event.widget.get().lower()
        for rb, name in self.site_widgets:
            if query in name.lower():
                rb.pack(anchor="w", pady=5, padx=10)
            else:
                rb.pack_forget()

    def run_import_thread(self):
        # 1. Validation
        site_id = self.site_var.get()
        if not site_id:
            print("Error: No site selected.")
            return

        date_str = self.date_display.get()
        if not date_str:
            print("Error: No date selected.")
            return

        if not self.legal_client:
            print("Error: Legal client not connected.")
            return

        # 2. Confirm execution
        self.btn_run.configure(state="disabled", text="PROCESSING...")

        # 3. Threaded Execution
        threading.Thread(
            target=self.execute_import, args=(site_id, date_str), daemon=True
        ).start()

    def execute_import(self, site_id, date_str):
        try:
            # Parse Date
            # Simple helper logic locally if verkada_utilities is missing get_datetime
            start_dt = datetime.strptime(date_str, "%m/%d/%Y")
            end_dt = start_dt + timedelta(days=1) - timedelta(seconds=1)

            # Timestamps for API
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())

            print(f"Fetching visits for {date_str}...")
            visits = self.legal_client.get_guest_visits(site_id, start_ts, end_ts)

            if not visits:
                print("No visits found for this date.")
                return

            print(f"Found {len(visits)} visits. Starting invites...")

            count = 0
            for visit in visits:
                # Use the SHARED internal client from main controller
                if not self.controller.client:
                    print("Error: Internal Client session lost. Please login again.")
                    break

                self.controller.client.invite_user(
                    visit["first_name"],
                    visit["last_name"],
                    visit["email"],
                    org_admin=True,  # As per your requirement
                )
                count += 1
                # Small delay to prevent rate limits if needed, or just let it rip

            print(f"Completed! Invited {count} users.")

        except Exception as e:
            print(f"Error during import: {e}")
        finally:
            self.after(
                0, lambda: self.btn_run.configure(state="normal", text="RUN IMPORT")
            )

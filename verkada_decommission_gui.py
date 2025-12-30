import logging
import queue
import sys
import threading
from tkinter import messagebox
from typing import Any, Dict, List

import customtkinter as ctk

# Import existing logic
from verkada_api_clients import VerkadaExternalAPIClient, VerkadaInternalAPIClient
from verkada_utilities import sanitize_list

# --- Theme Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# --- Constants & Colors ---
COLOR_BG = "#121212"  # Deep black/grey for main background
COLOR_PANEL = "#1e1e1e"  # Slightly lighter for the sidebar
COLOR_CARD = "#2b2b2b"  # Cards
COLOR_ACCENT = "#1f6aa5"  # Verkada/Professional Blue
COLOR_ACCENT_HOVER = "#144d7a"
COLOR_DANGER = "#cf6679"  # Error/Delete Red
COLOR_SUCCESS = "#4caf50"  # Success Green
COLOR_TEXT_MAIN = "#ffffff"
COLOR_TEXT_DIM = "#808080"
COLOR_LOG_TEXT = "#a0a0a0"  # Subtle grey for logs
COLOR_SELECTED = "#2a2a2a"  # Selected category background

logger = logging.getLogger(__name__)


class QueueHandler(logging.Handler):
    """
    Thread-safe logging handler.
    Simply pushes records to a queue. UI thread polls this queue.
    """

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))


class GUIInternalClient(VerkadaInternalAPIClient):
    """
    Internal client that pauses background execution to ask the main thread for MFA.
    """

    def __init__(self, email, password, org_short_name, shard, mfa_callback):
        super().__init__(email, password, org_short_name, shard)
        self.mfa_callback = mfa_callback

    def _handle_mfa(self, login_url, base_payload, mfa=None):
        if mfa:
            code = mfa
        else:
            # Block this thread and wait for the GUI to provide the code
            code = self.mfa_callback()

        if not code:
            raise ValueError("MFA Operation Cancelled.")

        super()._handle_mfa(login_url, base_payload, mfa=code)


class DecommissionApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Project Decommission")
        self.geometry("1100x800")
        self.configure(fg_color=COLOR_BG)

        # Grid: Left Panel (Status/Logs) | Right Panel (Main Workspace)
        self.grid_columnconfigure(0, weight=0)  # Fixed width sidebar
        self.grid_columnconfigure(1, weight=1)  # Flexible main area
        self.grid_rowconfigure(0, weight=1)

        # --- State Management ---
        self.internal_client = None
        self.external_client = None
        self.inventory = {}
        self.active_category_buttons = {}  # To track selected state

        # Persistent storage for credentials
        self.session_state = {"email": "", "org": "", "shard": "prod1"}

        # Threading & Events
        self.log_queue = queue.Queue()
        self.mfa_code = None
        self.mfa_event = threading.Event()

        # --- Layout Initialization ---
        self._setup_logging()
        self._setup_sidebar()
        self._setup_main_area()

        # Start Log Polling Loop (Anti-Lag Mechanism)
        self.after(100, self.process_log_queue)

        # Initial View
        self.show_login_view()

    def _setup_logging(self):
        # Attach our queue handler to the ROOT logger to capture logs from all modules
        queue_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S")
        queue_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        # Clear existing handlers to prevent duplicates
        root_logger.handlers = []
        root_logger.addHandler(queue_handler)
        root_logger.setLevel(logging.INFO)

        # SILENCE NOISY LIBRARIES to prevent UI Lag
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)

        # Also print to console for debugging
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    def process_log_queue(self):
        """
        Runs on the Main Thread every 100ms.
        Batches updates to reduce UI calls and eliminate lag.
        """
        messages = []
        # Limit processing to 50 messages per tick to prevent freezing
        # if a massive amount of logs come in at once.
        for _ in range(50):
            if self.log_queue.empty():
                break
            try:
                messages.append(self.log_queue.get_nowait())
            except queue.Empty:
                break

        if messages:
            full_text = "\n".join(messages) + "\n"
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", full_text)
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")

        # Schedule next check
        self.after(100, self.process_log_queue)

    def _setup_sidebar(self):
        """Left Sidebar: Clean, minimal status and integrated log stream."""
        self.sidebar = ctk.CTkFrame(
            self, width=280, corner_radius=0, fg_color=COLOR_PANEL
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)  # Force width
        self.sidebar.grid_rowconfigure(3, weight=1)  # Log area expands

        # App Title
        ctk.CTkLabel(
            self.sidebar,
            text="PROJECT\nDECOMMISSION",
            font=ctk.CTkFont(size=20, weight="bold", family="Helvetica"),
            text_color=COLOR_TEXT_MAIN,
            justify="left",
        ).pack(anchor="w", padx=25, pady=(40, 5))

        # Version/Subtitle
        ctk.CTkLabel(
            self.sidebar,
            text="Verkada Asset Management",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=25, pady=(0, 30))

        # Status Badge
        self.lbl_status_title = ctk.CTkLabel(
            self.sidebar,
            text="CURRENT STATE",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLOR_TEXT_DIM,
        )
        self.lbl_status_title.pack(anchor="w", padx=25, pady=(0, 5))

        self.lbl_status = ctk.CTkLabel(
            self.sidebar,
            text="Idle",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff",
        )
        self.lbl_status.pack(anchor="w", padx=25, pady=(0, 20))

        # Divider
        ctk.CTkFrame(self.sidebar, height=1, fg_color="#333333").pack(
            fill="x", padx=20, pady=10
        )

        # Log Header
        ctk.CTkLabel(
            self.sidebar,
            text="LIVE ACTIVITY",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=COLOR_TEXT_DIM,
        ).pack(anchor="w", padx=25, pady=(10, 5))

        # Log Area
        self.log_textbox = ctk.CTkTextbox(
            self.sidebar,
            fg_color="transparent",
            text_color=COLOR_LOG_TEXT,
            font=("Consolas", 11),
            activate_scrollbars=False,
        )
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        self.log_textbox.configure(state="disabled")

    def _setup_main_area(self):
        """Right Area: Holds the dynamic views."""
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        # Container View
        self.view_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.view_container.grid(row=0, column=0, sticky="nsew", padx=30, pady=30)

    # --- VIEWS (Switching Logic) ---

    def clear_view(self):
        for widget in self.view_container.winfo_children():
            widget.destroy()

    def show_login_view(self):
        self.clear_view()
        self.lbl_status.configure(text="Ready to Connect", text_color="#ffffff")

        # Center Card
        card = ctk.CTkFrame(self.view_container, fg_color=COLOR_CARD, corner_radius=15)
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.6, relheight=0.7)

        # Header
        ctk.CTkLabel(
            card, text="Organization Access", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(40, 10))

        ctk.CTkLabel(
            card,
            text="Enter Admin Credentials to begin scan",
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 30))

        # Input Fields
        self.entry_email = ctk.CTkEntry(
            card, placeholder_text="Admin Email", width=340, height=45
        )
        self.entry_email.pack(pady=8)

        self.entry_pass = ctk.CTkEntry(
            card, placeholder_text="Password", show="*", width=340, height=45
        )
        self.entry_pass.pack(pady=8)

        # Row for Org and Shard
        row_frame = ctk.CTkFrame(card, fg_color="transparent")
        row_frame.pack(pady=8)

        self.entry_org = ctk.CTkEntry(
            row_frame, placeholder_text="Org Short Name", width=230, height=45
        )
        self.entry_org.pack(side="left", padx=(0, 10))

        self.entry_shard = ctk.CTkEntry(
            row_frame, placeholder_text="Shard", width=100, height=45
        )
        self.entry_shard.pack(side="left")
        self.entry_shard.insert(0, "prod1")

        # Action Button
        self.btn_login = ctk.CTkButton(
            card,
            text="Connect & Scan",
            width=340,
            height=50,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.start_login_thread,
        )
        self.btn_login.pack(pady=(30, 20))

    def show_mfa_view(self):
        """Called if API hits 2FA requirement."""
        self.clear_view()
        self.lbl_status.configure(text="Waiting for Input", text_color=COLOR_ACCENT)

        card = ctk.CTkFrame(self.view_container, fg_color=COLOR_CARD, corner_radius=15)
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5, relheight=0.5)

        ctk.CTkLabel(
            card, text="2FA Verification", font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=(50, 20))

        ctk.CTkLabel(
            card, text="Enter the code sent to your device", text_color=COLOR_TEXT_DIM
        ).pack(pady=(0, 20))

        self.entry_mfa = ctk.CTkEntry(
            card,
            placeholder_text="000000",
            width=220,
            height=55,
            justify="center",
            font=ctk.CTkFont(size=24, weight="bold", family="Consolas"),
        )
        self.entry_mfa.pack(pady=10)
        self.entry_mfa.bind("<Return>", lambda e: self.submit_mfa_code())
        self.entry_mfa.focus()

        self.btn_verify = ctk.CTkButton(
            card,
            text="Verify Code",
            width=220,
            height=50,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            command=self.submit_mfa_code,
        )
        self.btn_verify.pack(pady=20)

    def show_dashboard_view(self):
        """Displays inventory summary with interactive categories."""
        self.clear_view()
        self.active_category_buttons = {}  # Reset

        org_name = self.session_state["org"]
        self.lbl_status.configure(text="Connected", text_color=COLOR_SUCCESS)

        # --- Top Bar ---
        header = ctk.CTkFrame(self.view_container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            header,
            text=f"ORGANIZATION: {org_name.upper()}",
            font=ctk.CTkFont(size=16, weight="bold", family="Roboto"),
            text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        # CHANGED: Button now exits the application
        ctk.CTkButton(
            header,
            text="Exit Application",
            width=120,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color=COLOR_TEXT_DIM,
            text_color=COLOR_TEXT_DIM,
            hover_color="#333333",
            command=self.quit_app,
        ).pack(side="right")

        # --- Inventory Overview Section (Top) ---
        self.cat_frame = ctk.CTkFrame(self.view_container, fg_color="transparent")
        self.cat_frame.pack(fill="x", pady=(10, 0))

        # Grid layout for categories
        row, col = 0, 0
        total_assets = 0
        sorted_keys = sorted(self.inventory.keys())
        first_valid_category = None

        for category in sorted_keys:
            items = self.inventory[category]
            count = len(items)

            # CHANGED: Filter out categories with 0 items
            if count == 0:
                continue

            total_assets += count
            if not first_valid_category:
                first_valid_category = category

            # Category Button
            btn = ctk.CTkButton(
                self.cat_frame,
                text=f"{category}\n{count}",
                font=ctk.CTkFont(size=13, weight="bold"),
                width=160,
                height=60,
                fg_color=COLOR_CARD,
                hover_color=COLOR_ACCENT_HOVER,
                text_color=COLOR_TEXT_MAIN,
                command=lambda c=category: self.select_category(c),
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="ew")
            self.active_category_buttons[category] = btn

            # Simple grid math for layout (5 columns max)
            col += 1
            if col > 4:
                col = 0
                row += 1

        # --- Details Section (Bottom) ---
        self.lbl_detail_header = ctk.CTkLabel(
            self.view_container,
            text="SELECT A CATEGORY TO VIEW ASSETS",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT_DIM,
        )
        self.lbl_detail_header.pack(fill="x", pady=(20, 5), anchor="w")

        # Scrollable area for item details
        self.detail_frame = ctk.CTkScrollableFrame(
            self.view_container, fg_color=COLOR_CARD, corner_radius=10
        )
        self.detail_frame.pack(fill="both", expand=True, pady=10)

        # --- Footer ---
        footer = ctk.CTkFrame(self.view_container, fg_color="transparent")
        footer.pack(fill="x", pady=(10, 0), ipady=5)

        info_text = f"Total Assets: {total_assets}"
        if total_assets == 0:
            info_text = "No Assets Found"

        ctk.CTkLabel(
            footer, text=info_text, font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        self.btn_nuke = ctk.CTkButton(
            footer,
            text="DECOMMISSION ALL ASSETS",
            fg_color=COLOR_DANGER,
            hover_color="#8a2e2e",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=45,
            width=280,
            command=self.confirm_deletion,
        )
        self.btn_nuke.pack(side="right")

        if total_assets == 0:
            self.btn_nuke.configure(state="disabled", fg_color="#444444")

        # Check if we should immediately show success view (e.g. org is empty)
        # But allow user to see dashboard first if they want,
        # unless it is strictly requested to show success immediately if empty?
        # Prompt says: "once there are no devices... The view should tell them that"
        # I'll stick to dashboard showing "No Assets Found" initially,
        # but trigger success view if they hit delete on empty?
        # Actually, let's keep the logic in check_completion for dynamic updates.

        # Auto-select first non-empty category
        if first_valid_category:
            self.select_category(first_valid_category)
        else:
            ctk.CTkLabel(
                self.detail_frame, text="No assets detected in scan.", text_color="gray"
            ).pack(pady=20)

    def select_category(self, category_name):
        """Updates the detail view with items from the selected category."""
        # 1. Update Buttons State
        for name, btn in self.active_category_buttons.items():
            if name == category_name:
                btn.configure(fg_color=COLOR_ACCENT, text_color="white")
            else:
                btn.configure(fg_color=COLOR_CARD, text_color=COLOR_TEXT_MAIN)

        # 2. Update Header
        items = self.inventory.get(category_name, [])
        self.lbl_detail_header.configure(text=f"{category_name.upper()} ({len(items)})")

        # 3. Clear Details List
        for widget in self.detail_frame.winfo_children():
            widget.destroy()

        # 4. Populate Details
        if not items:
            ctk.CTkLabel(
                self.detail_frame,
                text="No items found in this category.",
                text_color="gray",
            ).pack(pady=20)
            return

        for item in items:
            self._render_asset_row(item)

    def _render_asset_row(self, item):
        """Helper to create a nice row for an asset."""
        name = item.get("name") or item.get("email") or "(No Name)"
        item_id = str(item.get("id"))

        row = ctk.CTkFrame(self.detail_frame, fg_color="transparent")
        row.pack(fill="x", pady=2)

        # Name
        ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=13), anchor="w").pack(
            side="left", padx=10
        )

        # ID (Monospace for alignment)
        ctk.CTkLabel(
            row,
            text=item_id,
            font=ctk.CTkFont(size=12, family="Consolas"),
            text_color=COLOR_TEXT_DIM,
        ).pack(side="right", padx=10)

        # Simple separator line
        ctk.CTkFrame(self.detail_frame, height=1, fg_color="#3a3a3a").pack(
            fill="x", pady=(2, 2)
        )

    def remove_asset_from_ui(self, category, item_id):
        """
        Called by background thread via self.after.
        Removes asset from memory and updates UI in real-time.
        """
        if category in self.inventory:
            # 1. Update Data
            original_count = len(self.inventory[category])
            self.inventory[category] = [
                i for i in self.inventory[category] if str(i.get("id")) != str(item_id)
            ]
            new_count = len(self.inventory[category])

            # 2. Update Dashboard Button
            if category in self.active_category_buttons:
                btn = self.active_category_buttons[category]
                if new_count == 0:
                    # Remove category button if empty
                    btn.destroy()
                    del self.active_category_buttons[category]
                else:
                    btn.configure(text=f"{category}\n{new_count}")

            # 3. Refresh Details if currently viewing this category
            current_header = self.lbl_detail_header.cget("text")
            if current_header.startswith(category.upper()):
                self.select_category(category)

        # 4. Check if we are done
        self.check_completion()

    def check_completion(self):
        """Checks if all decommissioning is complete (ignoring Unassigned)."""
        relevant_total = 0
        for cat, items in self.inventory.items():
            if cat == "Unassigned Devices":
                continue
            relevant_total += len(items)

        if relevant_total == 0:
            self.show_success_view()

    def show_success_view(self):
        """Replaces the dashboard with the celebration screen."""
        self.clear_view()
        self.lbl_status.configure(text="Complete", text_color=COLOR_SUCCESS)

        container = ctk.CTkFrame(self.view_container, fg_color="transparent")
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container,
            text="You've done it! 👏",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLOR_SUCCESS,
        ).pack(pady=20)

        ctk.CTkLabel(
            container,
            text="Organization Decommissioned Successfully",
            font=ctk.CTkFont(size=16),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=10)

        # Large Exit Button
        ctk.CTkButton(
            container,
            text="Exit Application",
            width=200,
            height=50,
            fg_color=COLOR_CARD,
            hover_color="#333333",
            command=self.quit_app,
        ).pack(pady=30)

    # --- ACTION LOGIC ---

    def start_login_thread(self):
        email = self.entry_email.get().strip()
        pwd = self.entry_pass.get().strip()
        org = self.entry_org.get().strip()
        shard = self.entry_shard.get().strip()

        if not all([email, pwd, org]):
            messagebox.showwarning("Incomplete", "Please fill in all fields.")
            return

        self.session_state["email"] = email
        self.session_state["org"] = org
        self.session_state["shard"] = shard

        self.btn_login.configure(state="disabled", text="Authenticating...")
        self.lbl_status.configure(text="Authenticating...", text_color="#FBC02D")

        t = threading.Thread(
            target=self._run_login_process, args=(email, pwd, org, shard)
        )
        t.daemon = True
        t.start()

    def _run_login_process(self, email, pwd, org, shard):
        try:
            logger.info("Initializing connection...")

            self.internal_client = GUIInternalClient(
                email, pwd, org, shard, mfa_callback=self.wait_for_mfa_input
            )
            self.internal_client.login()
            logger.info("Authentication successful.")

            logger.info("Generating API Session...")
            api_key = self.internal_client.create_external_api_key()
            self.external_client = VerkadaExternalAPIClient(api_key, org)

            self.after(0, lambda: self.lbl_status.configure(text="Scanning..."))
            logger.info("Scanning organization assets...")
            self._fetch_inventory()

            logger.info("Scan complete. Found assets.")
            self.after(0, self.show_dashboard_view)

        except Exception as e:
            logger.error(f"Connection Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, self.show_login_view)

    def wait_for_mfa_input(self):
        self.mfa_event.clear()
        self.after(0, self.show_mfa_view)
        self.mfa_event.wait()
        return self.mfa_code

    def submit_mfa_code(self):
        code = self.entry_mfa.get().strip()
        if not code:
            return
        self.mfa_code = code
        self.btn_verify.configure(state="disabled", text="Checking...")
        self.lbl_status.configure(text="Verifying...", text_color="#FBC02D")
        self.mfa_event.set()

    def _fetch_inventory(self):
        ic = self.internal_client
        ec = self.external_client

        intercoms = ic.get_object("intercoms")
        acs = sanitize_list(intercoms, ic.get_object("access_controllers"))
        cams = sanitize_list(intercoms, ec.get_object("cameras"))

        self.inventory = {
            "Sensors": ic.get_object("sensors"),
            "Intercoms": intercoms,
            "Desk Stations": ic.get_object("desk_stations"),
            "Mailroom Sites": ic.get_object("mailroom_sites"),
            "Access Controllers": acs,
            "Cameras": cams,
            "Guest Sites": ec.get_object("guest_sites"),
            "Users": ec.get_users(exclude_user_id=ic.user_id),
            "Alarm Sites": ic.get_object("alarm_sites"),
            "Alarm Devices": ic.get_object("alarm_devices"),
            "Unassigned Devices": ic.get_object("unassigned_devices"),
        }

    def quit_app(self):
        """Cleanly closes the application."""
        self.destroy()

    def confirm_deletion(self):
        count = sum(len(v) for v in self.inventory.values())
        if messagebox.askyesno(
            "CONFIRM DECOMMISSION",
            f"Are you sure you want to delete {count} assets? This cannot be undone. This will wipe the organization data. Proceed?",
            icon="warning",
        ):
            self.start_deletion_thread()

    def start_deletion_thread(self):
        self.btn_nuke.configure(state="disabled", text="Decommissioning in Progress...")
        self.lbl_status.configure(text="Deleting Assets...", text_color=COLOR_DANGER)

        t = threading.Thread(target=self._run_deletion_process)
        t.daemon = True
        t.start()

    def _run_deletion_process(self):
        ic = self.internal_client
        ec = self.external_client
        inv = self.inventory

        logger.info("!!! STARTING BULK DELETION !!!")

        tasks = [
            ("Users", ec.delete_user),
            ("Sensors", lambda x: ic.delete_object("sensors", x)),
            ("Intercoms", lambda x: ic.delete_object("intercoms", x)),
            ("Desk Stations", lambda x: ic.delete_object("desk_stations", x)),
            ("Mailroom Sites", lambda x: ic.delete_object("mailroom_sites", x)),
            ("Access Controllers", lambda x: ic.delete_object("access_controllers", x)),
            ("Cameras", lambda x: ic.delete_object("cameras", x)),
            ("Guest Sites", lambda x: ic.delete_object("guest_sites", x)),
            ("Alarm Devices", lambda x: ic.delete_object("alarm_devices", x)),
        ]

        for cat, func in tasks:
            items = inv.get(cat, [])
            if items:
                logger.info(f"Deleting {len(items)} {cat}...")
                # Use a copy of the list so we can modify the inventory safely
                for item in list(items):
                    try:
                        result = func(item["id"])
                        # Some functions return booleans, others None (void) on success but raise on fail
                        if result is not False:
                            self.after(
                                0,
                                lambda c=cat, i=item["id"]: self.remove_asset_from_ui(
                                    c, i
                                ),
                            )
                    except Exception as e:
                        logger.error(f"Failed to delete {item['id']}: {e}")

        alarm_sites = inv.get("Alarm Sites", [])
        if alarm_sites:
            logger.info(f"Deleting {len(alarm_sites)} Alarm Sites...")
            for site in list(alarm_sites):
                try:
                    if site.get("alarm_system_id"):
                        ic.delete_object("alarm_systems", site["alarm_system_id"])
                    ic.delete_object(
                        "alarm_sites", [site["alarm_site_id"], site["site_id"]]
                    )

                    self.after(
                        0,
                        lambda i=site["id"]: self.remove_asset_from_ui(
                            "Alarm Sites", i
                        ),
                    )
                except Exception as e:
                    logger.error(f"Failed alarm site: {e}")

        logger.info("Decommissioning Run Complete.")
        # We don't need to force show_dashboard_view here because remove_asset_from_ui
        # will trigger the success view automatically when done.


if __name__ == "__main__":
    app = DecommissionApp()
    app.mainloop()

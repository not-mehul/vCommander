import logging
import threading
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_reporting import generate_report
from tools.verkada_utilities import sanitize_list

# Initialize logger for this module
logger = logging.getLogger(__name__)

# =============================================================================
# FLOW STATE CONSTANTS
# =============================================================================
# These constants define the different UI states/screens in the decommission
# workflow. Using constants prevents typos and makes the code more maintainable.

FLOW_SCAN = "scan"  # Initial state - ready to scan for inventory
FLOW_REVIEW = "review"  # Review scanned inventory
FLOW_SELECT = "select"  # Select which assets to delete
FLOW_PROCESSING = "processing"  # Deletion in progress
FLOW_COMPLETE = "complete"  # Deletion finished, show results

# =============================================================================
# STYLING CONSTANTS
# =============================================================================
# Centralized styling values ensure consistent appearance across the UI.

CONTROL_WIDTH = 320  # Fixed width for the right-side control panel
CARD_BG_COLOR = "#333333"  # Dark background for cards
CARD_BG = ("gray95", "gray17")  # Tuple format: (light_mode, dark_mode)
HEADER_FONT = ("Verdana", 22, "bold")  # Large headers
TITLE_FONT = ("Verdana", 18, "bold")  # Section titles
LABEL_FONT = ("Verdana", 12)  # Standard labels and text

# =============================================================================
# DELETION ORDER CONFIGURATION
# =============================================================================
# This list defines the strict order in which assets must be deleted.
# The order is critical because some assets have dependencies on others.
# Format: (category, api_type)
#   - api_type: "external" = use external_client.delete_user
#               "internal" = use internal_client.delete_object

DELETION_ORDER = [
    (
        "Users",
        "external",
    ),  # Delete users first to prevent access during decommissioning
    ("Sensors", "internal"),  # Environmental sensors
    ("Intercoms", "internal"),  # Door intercoms (must be before access controllers)
    ("Desk Stations", "internal"),  # Desk intercom stations
    ("Mailroom Sites", "internal"),  # Package management sites
    ("Guest Sites", "internal"),  # Visitor management sites
    ("Access Controllers", "internal"),  # Door access controllers
    ("Cameras", "internal"),  # Video cameras
    ("Alarm Devices", "internal"),  # Alarm sensors and panels
    ("Alarm Sites", "internal"),  # Alarm sites (last due to complexity)
]


class DecommissionTool(ctk.CTkFrame):
    def __init__(self, parent, controller):
        """
        Initialize the Decommission tool.

        Args:
            parent: The parent widget (usually a container frame).
            controller: The main application controller that manages navigation
                       and provides access to shared resources like API clients.
        """
        super().__init__(parent)
        self.controller = controller

        # API clients
        # internal_client: Uses cookies for internal API access (from controller)
        # external_client: Uses API key for public API (created during scan)
        self.internal_client = controller.client
        self.external_client = None

        # Inventory data storage
        self.inventory = {}  # Raw inventory by category
        self.flattened_assets = []  # Flat list of all assets for display
        self.selected_assets = set()  # Set of selected asset IDs to delete

        # Results tracking
        self.success_count = 0  # Number of successful deletions
        self.fail_count = 0  # Number of failed deletions
        self.deleted_items = []  # List of successfully deleted items
        self.failed_items = []  # List of (item, error) tuples for failures

        # Build the UI layout
        self._setup_layout()

    def _setup_layout(self):
        """
        Sets up the main layout structure with content and control panels.

        The layout uses a two-column grid:
        - Left column (weight=3): Main content area (scrollable lists, etc.)
        - Right column (weight=1): Control panel (buttons, summaries)
        """
        # Configure main grid to expand
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Main container frame with padding
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_columnconfigure(0, weight=3)  # Content takes more space
        container.grid_columnconfigure(1, weight=1)  # Controls take less space
        container.grid_rowconfigure(0, weight=1)

        # Left panel: Main content area (lists, previews, etc.)
        self.content = ctk.CTkFrame(container, corner_radius=15)
        self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        # Right panel: Control panel with fixed width
        self.controls = ctk.CTkFrame(
            container, corner_radius=15, width=CONTROL_WIDTH, fg_color=CARD_BG
        )
        self.controls.grid(row=0, column=1, sticky="nsew")
        self.controls.grid_propagate(False)  # Keep fixed width
        self.controls.grid_columnconfigure(0, weight=1)

        # Start at SCAN flow (ready to scan state)
        self.current_flow = FLOW_SCAN
        self._refresh_ui()

    def _set_flow(self, flow):
        """
        Change the current UI flow/state and refresh the display.

        Args:
            flow: One of the FLOW_* constants defining which screen to show.
        """
        self.current_flow = flow
        self._refresh_ui()

    def _refresh_ui(self):
        """
        Rebuilds the UI based on the current flow state.

        This method:
        1. Clears all existing widgets from content and controls
        2. Determines which builder methods to call based on current_flow
        3. Calls the appropriate content and controls builders
        4. Handles special layout cases (like full-width scan controls)
        """
        # Clear existing widgets
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        # Special handling for SCAN flow - it takes full width
        if self.current_flow == FLOW_SCAN:
            self.content.grid_remove()
            self.controls.grid(
                row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20
            )
            self._build_scan_controls()
            return

        else:
            # Restore normal two-column layout for other flows
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=3)
            self.content.master.grid_columnconfigure(1, weight=1)

        # Always show controls on the right
        self.controls.grid(row=0, column=1, sticky="nsew")

        # Map flows to their respective builder methods
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

        # Get and call the appropriate builders
        content_builder, controls_builder = builders.get(
            self.current_flow, (None, None)
        )
        if content_builder:
            content_builder()
        if controls_builder:
            controls_builder()

    # =========================================================================
    # SCAN FLOW - Initial Scan Interface
    # =========================================================================

    def _build_scan_controls(self):
        """
        Builds the initial scan screen with start button.

        This is the entry point of the decommissioning tool. It provides
        a prominent start button to begin the inventory scanning process.
        """
        # Center container for the content
        center = ctk.CTkFrame(self.controls, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5)
        center.grid_columnconfigure(0, weight=1)

        # Header and description
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

        # Start Scan button
        ctk.CTkButton(
            center,
            text="Start Scan",
            font=("Verdana", 14, "bold"),
            height=50,
            command=self._start_scan,
        ).grid(row=3, column=0, sticky="ew", pady=(20, 0))

    def _start_scan(self):
        """
        Initiate the scanning process.

        Transitions to the scanning state and starts the scan
        in a background thread to avoid blocking the UI.
        """
        self._set_scanning_state()
        threading.Thread(target=self._execute_scan, daemon=True).start()

    def _set_scanning_state(self):
        """
        Show the scanning state with spinner and progress updates.

        This is an intermediate state shown while the scan is running.
        It displays a spinner animation and status messages for each
        category being fetched.
        """
        # Clear existing widgets
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        # Show content area for scanning progress
        self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        self.content.master.grid_columnconfigure(0, weight=3)
        self.content.master.grid_columnconfigure(1, weight=1)
        self.controls.grid(row=0, column=1, sticky="nsew")

        # Scanning content (spinner and status)
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Animated spinner label
        self.scan_spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.scan_spinner.pack(pady=(0, 20))
        ctk.CTkLabel(center, text="Scanning...", font=("Verdana", 20, "bold")).pack()

        # Status label showing current operation
        self.scan_status = ctk.CTkLabel(
            center, text="Initializing...", font=LABEL_FONT, text_color="gray"
        )
        self.scan_status.pack(pady=(10, 0))

        # Start spinner animation
        self._animate_scan_spinner()

        # Scanning controls panel header
        ctk.CTkLabel(self.controls, text="Scanning", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        # Info text in controls panel
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
        """
        Animate the scanning spinner by cycling through Unicode characters.

        Args:
            frame: Current animation frame index (cycles 0-3).
        """
        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "scan_spinner") and self.scan_spinner.winfo_exists():
            self.scan_spinner.configure(text=spinners[frame % 4])
            self.after(500, lambda: self._animate_scan_spinner(frame + 1))

    def _execute_scan(self):
        """
        Execute the inventory scan in a background thread.

        This method performs the following steps:
        1. Sets up admin access (escalates privileges)
        2. Creates an external API key
        3. Fetches all asset types from both internal and external APIs
        4. Sanitizes lists to remove duplicates
        5. Flattens inventory for display
        6. Transitions to review flow
        """
        try:
            # Step 1: Set up admin access for internal APIs
            self.after(
                0, lambda: self.scan_status.configure(text="Setting up admin access...")
            )
            # Grant Access System Admin role (needed for deleting access hardware)
            self.internal_client.set_access_system_admin()
            # Enable Global Site Admin (needed for site-level operations)
            self.internal_client.enable_global_site_admin()

            # Step 2: Create external API client
            if self.external_client is None:
                self.after(
                    0, lambda: self.scan_status.configure(text="Creating API key...")
                )
                # Generate a temporary API key for external API access
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

            # Step 3: Fetch all asset types
            # Intercoms (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching intercoms...")
            )
            intercoms = self.internal_client.get_object("intercoms")

            # Access Controllers (via internal API, sanitized against intercoms)
            self.after(
                0,
                lambda: self.scan_status.configure(
                    text="Fetching access controllers..."
                ),
            )
            access_controllers = sanitize_list(
                intercoms, self.internal_client.get_object("access_controllers")
            )

            # Cameras (via external API, sanitized against intercoms)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching cameras...")
            )
            cameras = sanitize_list(
                intercoms, self.external_client.get_object("cameras")
            )

            # Sensors (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching sensors...")
            )
            sensors = self.internal_client.get_object("sensors")

            # Desk Stations (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching desk stations...")
            )
            desk_stations = self.internal_client.get_object("desk_stations")

            # Mailroom Sites (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching mailroom sites...")
            )
            mailroom_sites = self.internal_client.get_object("mailroom_sites")

            # Guest Sites (via external API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching guest sites...")
            )
            guest_sites = self.external_client.get_object("guest_sites")

            # Users (via external API, excluding current admin)
            self.after(0, lambda: self.scan_status.configure(text="Fetching users..."))
            users = self.external_client.get_users(
                exclude_user_id=self.internal_client.user_id
            )

            # Alarm Sites (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching alarm sites...")
            )
            alarm_sites = self.internal_client.get_object("alarm_sites")

            # Alarm Devices (via internal API)
            self.after(
                0, lambda: self.scan_status.configure(text="Fetching alarm devices...")
            )
            alarm_devices = self.internal_client.get_object("alarm_devices")

            # Step 4: Store inventory
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

            # Step 5: Flatten inventory for display
            self._flatten_inventory()

            # Log completion and transition to review
            total = sum(len(items) for items in self.inventory.values())
            logger.info(f"Scan complete. Found {total} assets.")
            self.after(0, lambda: self._set_flow(FLOW_REVIEW))

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            # Return to scan screen on failure
            self.after(0, lambda: self._set_flow(FLOW_SCAN))

    def _flatten_inventory(self):
        """
        Flatten inventory into a list for display and selection.

        Converts the categorized inventory dictionary into a flat list
        where each item includes its category, name, serial, and full data.
        This format is easier to display in scrollable lists and manage
        for selection.
        """
        self.flattened_assets = []
        for category, items in self.inventory.items():
            for item in items:
                # Extract ID - different asset types use different ID fields
                asset_id = (
                    item.get("id") or item.get("user_id") or item.get("alarm_site_id")
                )

                # Extract name - different asset types use different name fields
                name = (
                    item.get("email")
                    or item.get("name")
                    or item.get("businessName")
                    or item.get("serial_number")
                    or "Unknown"
                )

                # Get serial number (may be N/A for non-hardware assets like users)
                serial = item.get("serial_number", "N/A")

                # Add to flattened list
                self.flattened_assets.append(
                    {
                        "id": asset_id,
                        "category": category,
                        "name": name,
                        "serial": serial,
                        "data": item,
                    }
                )

    # =========================================================================
    # REVIEW FLOW - Inventory Overview
    # =========================================================================

    def _build_review_content(self):
        """
        Builds the review screen showing all discovered assets.

        Displays a scrollable list of all assets found during the scan,
        organized with badges showing item numbers. This is a read-only
        view for verification before selection.
        """
        # Header with total count
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(25, 10))

        total = len(self.flattened_assets)
        ctk.CTkLabel(header, text=f"Inventory ({total} assets)", font=HEADER_FONT).pack(
            side="left"
        )

        # List container
        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(10, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        # Empty state (shouldn't happen in normal use)
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

        # Scrollable frame for asset list
        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Assets found:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        # Create a card for each asset
        for i, asset in enumerate(self.flattened_assets, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=3)

            # Number badge
            badge = ctk.CTkFrame(
                card, fg_color="#1F6AA5", width=30, height=30, corner_radius=15
            )
            badge.pack(side="left", padx=10, pady=10)
            badge.pack_propagate(False)
            ctk.CTkLabel(
                badge, text=str(i), font=("Verdana", 10, "bold"), text_color="white"
            ).place(relx=0.5, rely=0.5, anchor="center")

            # Asset info
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=10)

            # Asset name (truncated if too long)
            name_text = asset["name"]
            if len(name_text) > 40:
                name_text = name_text[:37] + "..."
            ctk.CTkLabel(info, text=name_text, font=("Verdana", 12, "bold")).pack(
                anchor="w"
            )

            # Category and serial info
            detail_text = f"{asset['category']}"
            if asset["serial"] != "N/A":
                detail_text += f" • S/N: {asset['serial']}"
            ctk.CTkLabel(
                info, text=detail_text, font=("Verdana", 10), text_color="gray"
            ).pack(anchor="w")

    def _build_review_controls(self):
        """
        Builds the control panel for the REVIEW flow.

        Shows a summary breakdown by category, total count, and action buttons
        to save a report or proceed to asset selection.
        """
        # Summary card
        summary = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        summary.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

        total = len(self.flattened_assets)
        ctk.CTkLabel(summary, text="Summary", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        # Category counts
        for category, items in self.inventory.items():
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=1)
            ctk.CTkLabel(
                row, text=f"{category}:", font=LABEL_FONT, text_color="gray"
            ).pack(side="left")
            ctk.CTkLabel(row, text=str(len(items)), font=("Verdana", 11, "bold")).pack(
                side="right"
            )

        # Separator line
        ctk.CTkFrame(summary, height=1, fg_color=("gray80", "gray30")).pack(
            fill="x", padx=15, pady=8
        )

        # Total row
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

        # Buttons frame
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(20, 10))
        btn_frame.grid_columnconfigure(0, weight=1)

        # Save CSV Report button
        ctk.CTkButton(
            btn_frame,
            text="Save CSV Report",
            font=LABEL_FONT,
            height=45,
            command=self._save_report,
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        # Navigation button row
        btn_row = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        # Back button (resets to scan)
        ctk.CTkButton(
            btn_row,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=self._reset,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Select Assets button (proceeds to selection)
        ctk.CTkButton(
            btn_row,
            text="Select Assets",
            font=LABEL_FONT,
            height=45,
            command=lambda: self._set_flow(FLOW_SELECT),
        ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def _save_report(self):
        """
        Generate and save a formatted text report.

        Opens a file dialog for the user to choose save location,
        then generates a detailed inventory report using the
        verkada_reporting module.
        """
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

    # =========================================================================
    # SELECT FLOW - Asset Selection
    # =========================================================================

    def _build_select_content(self):
        """
        Builds the asset selection screen with checkboxes.

        Displays all assets with checkboxes, allowing users to select
        which assets they want to delete. Includes a "Select All" option
        and displays the item number for each asset.
        """
        # Configure row weights for proper expansion
        self.content.grid_rowconfigure(1, weight=1)

        # Header with Select All checkbox
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=25, pady=(10, 5))

        total = len(self.flattened_assets)
        ctk.CTkLabel(
            header, text=f"Select Assets ({total} total)", font=HEADER_FONT
        ).pack(side="left")

        # Select All checkbox
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_cb = ctk.CTkCheckBox(
            header,
            text="Select All",
            variable=self.select_all_var,
            font=("Verdana", 11),
            command=self._toggle_select_all,
        )
        self.select_all_cb.pack(side="right")

        # List container
        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(5, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        # Scrollable frame for asset list
        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Select assets:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        # Create checkbox for each asset
        self.asset_vars = {}
        for i, asset in enumerate(self.flattened_assets, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=3)

            # Checkbox variable with trace for tracking selections
            var = ctk.BooleanVar(value=False)
            var.trace_add(
                "write", lambda *args, a=asset["id"], v=var: self._on_asset_toggle(a, v)
            )
            self.asset_vars[asset["id"]] = var

            # Checkbox widget
            cb = ctk.CTkCheckBox(card, text="", variable=var, width=20)
            cb.pack(side="left", padx=10)

            # Asset info
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=8)

            # Asset name with number (truncated if too long)
            name_text = asset["name"]
            if len(name_text) > 35:
                name_text = name_text[:32] + "..."
            ctk.CTkLabel(
                info, text=f"{i}. {name_text}", font=("Verdana", 11, "bold")
            ).pack(anchor="w")

            # Category and serial info
            detail_text = f"{asset['category']}"
            if asset["serial"] != "N/A":
                detail_text += f" • S/N: {asset['serial']}"
            ctk.CTkLabel(
                info, text=detail_text, font=("Verdana", 10), text_color="gray"
            ).pack(anchor="w")

    def _build_select_controls(self):
        """
        Builds the control panel for the SELECT flow.

        Shows the count of selected assets, a warning about deletion
        being permanent, and navigation/action buttons.
        """
        # Selection counter card
        self.selection_frame = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        self.selection_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=20)

        ctk.CTkLabel(
            self.selection_frame, text="Selected", font=("Verdana", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))

        # Large counter showing selected count
        self.selected_count_label = ctk.CTkLabel(
            self.selection_frame,
            text="0",
            font=("Verdana", 36, "bold"),
            text_color="#1F6AA5",
        )
        self.selected_count_label.pack()

        # Total assets denominator
        ctk.CTkLabel(
            self.selection_frame,
            text=f"/ {len(self.flattened_assets)} assets",
            font=LABEL_FONT,
            text_color="gray",
        ).pack(pady=(0, 15))

        # Warning about deletion being permanent
        warning = ctk.CTkFrame(self.controls, fg_color="transparent")
        warning.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))
        ctk.CTkLabel(
            warning,
            text="Warning: This will delete everything.\nThis action cannot be undone!",
            font=("Verdana", 11),
            text_color="#FF5555",
            wraplength=280,
            justify="center",
        ).pack()

        # Button frame
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # Back button (returns to review)
        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_REVIEW),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Decommission button (red, disabled until selections made)
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
        """
        Toggle selection state of all assets.

        When "Select All" is checked/unchecked, updates all asset
        checkboxes to match. The trace callbacks on individual vars
        will update the selected_assets set and counter.
        """
        select_all = self.select_all_var.get()
        for var in self.asset_vars.values():
            var.set(select_all)

    def _on_asset_toggle(self, asset_id, var):
        """
        Handle individual asset checkbox toggle.

        Updates the selected_assets set and UI elements (counter,
        decommission button state, select all checkbox) based on
        the current selection state.

        Args:
            asset_id: The ID of the asset being toggled.
            var: The BooleanVar associated with the checkbox.
        """
        # Add or remove from selected set
        if var.get():
            self.selected_assets.add(asset_id)
        else:
            self.selected_assets.discard(asset_id)

        # Update counter display
        count = len(self.selected_assets)
        self.selected_count_label.configure(text=str(count))

        # Enable/disable decommission button
        if count > 0:
            self.btn_confirm_select.configure(state="normal")
        else:
            self.btn_confirm_select.configure(state="disabled")

        # Update Select All checkbox state based on selection count
        if count == len(self.flattened_assets):
            self.select_all_var.set(True)
        elif count == 0:
            self.select_all_var.set(False)

    # =========================================================================
    # PROCESSING FLOW - Deletion Execution
    # =========================================================================

    def _build_processing_content(self):
        """
        Builds the processing screen with spinner animation.

        Shows a loading indicator and status message while the deletion
        runs in a background thread.
        """
        # Center container
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Animated spinner
        self.process_spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.process_spinner.pack(pady=(0, 20))
        ctk.CTkLabel(
            center, text="Decommissioning...", font=("Verdana", 20, "bold")
        ).pack()

        # Status label
        self.process_status = ctk.CTkLabel(
            center, text="Starting deletion...", font=LABEL_FONT, text_color="gray"
        )
        self.process_status.pack(pady=(10, 0))

        # Start spinner animation
        self._animate_process_spinner()

    def _build_processing_controls(self):
        """
        Builds the control panel for the PROCESSING flow.

        Shows a progress counter (large red number), progress bar,
        and current deletion status. The red color indicates the
        destructive nature of the operation.
        """
        # Header
        ctk.CTkLabel(self.controls, text="Deleting", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        # Progress counter frame
        progress = ctk.CTkFrame(self.controls, fg_color="transparent")
        progress.place(relx=0.5, rely=0.4, anchor="center")

        # Large red counter showing deletions completed
        self.progress_count = ctk.CTkLabel(
            progress,
            text="0",
            font=("Verdana", 48, "bold"),
            text_color="#FF5555",
        )
        self.progress_count.pack(pady=(10, 0))

        # Total denominator
        ctk.CTkLabel(
            progress,
            text=f"/ {len(self.selected_assets)} assets",
            font=LABEL_FONT,
            text_color="gray",
        ).pack()

        # Progress bar (fills as deletion progresses)
        self.progress_bar = ctk.CTkProgressBar(
            self.controls, height=8, corner_radius=4, progress_color="#FF5555"
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=30, pady=(200, 0))
        self.progress_bar.set(0)

        # Current deletion status (shows what's being deleted)
        self.current_deletion = ctk.CTkLabel(
            self.controls,
            text="Preparing...",
            font=("Verdana", 11),
            text_color="gray",
            wraplength=280,
        )
        self.current_deletion.grid(row=2, column=0, pady=(15, 0), padx=20)

    def _animate_process_spinner(self, frame=0):
        """
        Animate the processing spinner by cycling through Unicode characters.

        Args:
            frame: Current animation frame index (cycles 0-3).
        """
        # Only animate if still in processing flow
        if self.current_flow != FLOW_PROCESSING:
            return

        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "process_spinner") and self.process_spinner.winfo_exists():
            self.process_spinner.configure(text=spinners[frame % 4])
            self.after(500, lambda: self._animate_process_spinner(frame + 1))

    def _start_deletion(self):
        """
        Start the deletion process.

        Transitions to the PROCESSING flow and begins deletion
        in a background thread.
        """
        self._set_flow(FLOW_PROCESSING)
        threading.Thread(target=self._execute_deletion, daemon=True).start()

    def _execute_deletion(self):
        """
        Execute the deletion process in a background thread.

        This method follows the DELETION_ORDER to delete assets in the
        correct dependency order. For each asset, it:
        1. Updates the UI with current status
        2. Calls the appropriate delete method
        3. Tracks success/failure
        4. Updates progress
        """
        # Reset counters
        self.success_count = 0
        self.fail_count = 0
        self.deleted_items = []
        self.failed_items = []

        # Create lookup for asset data
        asset_lookup = {a["id"]: a for a in self.flattened_assets}

        # Get list of selected assets
        selected_list = [
            asset_lookup[a_id] for a_id in self.selected_assets if a_id in asset_lookup
        ]
        total = len(selected_list)

        # Process each category in deletion order
        for category, api_type in DELETION_ORDER:
            # Filter selected assets to only those in this category
            items_in_category = [a for a in selected_list if a["category"] == category]

            # Delete each item in the category
            for item in items_in_category:
                try:
                    # Update UI showing current item being deleted
                    self.after(
                        0,
                        lambda c=category, n=item["name"]: (
                            self.current_deletion.configure(
                                text=f"Deleting {category}: {n[:30]}..."
                            )
                        ),
                    )

                    # Perform the deletion
                    self._delete_single_item(item, category, api_type)
                    self.success_count += 1
                    self.deleted_items.append(item)
                    logger.info(f"Deleted {category}: {item['name']}")
                except Exception as e:
                    self.fail_count += 1
                    self.failed_items.append((item, str(e)))
                    logger.error(f"Failed to delete {category} {item['name']}: {e}")

                # Update progress bar
                progress = (self.success_count + self.fail_count) / total
                self.after(
                    0,
                    lambda p=progress, s=self.success_count: self._update_progress(
                        p, s
                    ),
                )

        # Transition to complete screen
        self.after(0, lambda: self._set_flow(FLOW_COMPLETE))

    def _delete_single_item(self, item, category, api_type):
        """
        Delete a single item using the appropriate API.

        Routes deletion to either the external or internal client based
        on the api_type, and handles special cases like Alarm Sites.

        Args:
            item: The asset dictionary containing item data.
            category: The category name (e.g., "Users", "Cameras").
            api_type: Either "external" or "internal".

        Raises:
            RuntimeError: If external client is not initialized for user deletion.
        """
        item_data = item["data"]

        # Route to appropriate client based on api_type
        if category == "Users":
            # Users use the external API
            if self.external_client is None:
                raise RuntimeError("External client not initialized")
            self.external_client.delete_user(item_data["id"])
        elif category == "Alarm Sites":
            # Alarm sites require special handling - delete system first, then site
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
        """
        Update the progress bar and counter.

        Args:
            progress: Float between 0 and 1 representing completion percentage.
            count: Integer count of completed items.
        """
        if hasattr(self, "progress_bar"):
            self.progress_bar.set(progress)
        if hasattr(self, "progress_count"):
            self.progress_count.configure(text=str(count))

    # =========================================================================
    # COMPLETE FLOW - Results Display
    # =========================================================================

    def _build_complete_content(self):
        """
        Builds the completion screen showing deletion results.

        Displays an icon, completion message, and optionally a list
        of failed items. Different icons and colors based on success rate.
        """
        # Center container
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Determine display based on results
        if self.fail_count == 0:
            # All succeeded - green checkmark
            icon, color, msg = (
                "✓",
                "#2CC985",
                f"All {self.success_count} assets deleted successfully!",
            )
        elif self.success_count > 0:
            # Partial success - orange warning
            icon, color, msg = (
                "⚠",
                "orange",
                f"{self.success_count} of {self.success_count + self.fail_count} assets deleted",
            )
        else:
            # All failed - red X
            icon, color, msg = "✗", "#FF5555", "No assets could be deleted"

        # Result display
        ctk.CTkLabel(center, text=icon, font=("Verdana", 80), text_color=color).pack(
            pady=(0, 20)
        )
        ctk.CTkLabel(center, text="Complete!", font=("Verdana", 24, "bold")).pack()
        ctk.CTkLabel(center, text=msg, font=("Verdana", 14), text_color=color).pack(
            pady=(15, 0)
        )

        # Show failed items if any (limit to first 5)
        if self.failed_items:
            failed_frame = ctk.CTkFrame(
                center, fg_color=("gray90", "gray20"), corner_radius=8
            )
            failed_frame.pack(fill="x", padx=40, pady=(20, 0))

            ctk.CTkLabel(
                failed_frame, text="Failed Items:", font=("Verdana", 12, "bold")
            ).pack(anchor="w", padx=15, pady=(10, 5))

            # List first 5 failed items
            for item, error in self.failed_items[:5]:
                ctk.CTkLabel(
                    failed_frame,
                    text=f"• {item['name']}: {error[:40]}...",
                    font=("Verdana", 10),
                    text_color="gray",
                ).pack(anchor="w", padx=15)

            # Indicate if more failures exist
            if len(self.failed_items) > 5:
                ctk.CTkLabel(
                    failed_frame,
                    text=f"... and {len(self.failed_items) - 5} more",
                    font=("Verdana", 10),
                    text_color="gray",
                ).pack(anchor="w", padx=15, pady=(0, 10))

    def _build_complete_controls(self):
        """
        Builds the control panel for the COMPLETE flow.

        Shows final results breakdown and a button to start a new decommission.
        """
        # Header
        ctk.CTkLabel(self.controls, text="Done!", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        # Results card
        results = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        results.place(relx=0.5, rely=0.4, anchor="center", relwidth=0.85)

        ctk.CTkLabel(results, text="Results", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        # Results rows (Successful, Failed, Total)
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

        # Start New Decommission button
        ctk.CTkButton(
            self.controls,
            text="Start New Decommission",
            font=("Arial", 14, "bold"),
            height=50,
            command=self._reset,
        ).grid(row=10, column=0, sticky="ew", padx=20, pady=(0, 20))

    # Helpers

    def _reset(self):
        """
        Reset the tool to initial state.

        Clears all inventory data, selections, and results, then
        returns to the SCAN flow. This allows starting a fresh
        decommissioning process.
        """
        self.inventory = {}
        self.flattened_assets = []
        self.selected_assets = set()
        self.deleted_items = []
        self.failed_items = []
        self.success_count = 0
        self.fail_count = 0
        self._set_flow(FLOW_SCAN)

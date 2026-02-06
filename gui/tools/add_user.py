import logging
import threading
from datetime import datetime, timedelta

import customtkinter as ctk
from tools.verkada_api_clients import VerkadaExternalAPIClient
from tools.verkada_utilities import get_env_var

# Initialize logger for this module
logger = logging.getLogger(__name__)

# =============================================================================
# FLOW STATE CONSTANTS
# =============================================================================
# These constants define the different UI states/screens in the add user workflow.
# Using constants prevents typos and makes the code more maintainable.

FLOW_CONFIGURE = "configure"  # Initial screen to enter API credentials
FLOW_SELECT = "select"  # Site selection and date picker screen
FLOW_PREVIEW = "preview"  # Review visitors before importing
FLOW_CONFIRM = "confirm"  # Confirmation screen (not currently used)
FLOW_PROCESSING = "processing"  # Import progress screen
FLOW_COMPLETE = "complete"  # Success/failure summary screen

# =============================================================================
# STYLING CONSTANTS
# =============================================================================
# Centralized styling values ensure consistent appearance across the UI.
# Using tuples for colors allows light/dark mode compatibility (light, dark).

CONTROL_WIDTH = 320  # Fixed width for the right-side control panel
CARD_BG_COLOR = "#333333"  # Dark background for cards
CARD_BG = ("gray95", "gray17")  # Tuple format: (light_mode, dark_mode)
HEADER_FONT = ("Verdana", 22, "bold")  # Large headers
TITLE_FONT = ("Verdana", 18, "bold")  # Section titles
LABEL_FONT = ("Verdana", 12)  # Standard labels and text


class AddUserTool(ctk.CTkFrame):
    """
    GUI component for importing guest visitors as organization users.

    This tool allows administrators to:
    1. Connect to a different Verkada organization using API credentials
    2. Select a site and date range to retrieve guest visits
    3. Preview the list of visitors
    4. Import those visitors as users in the current organization

    The tool uses a flow-based UI where each screen is a different "flow" state.
    """

    def __init__(self, parent, controller):
        """
        Initialize the Add User tool.

        Args:
            parent: The parent widget (usually a container frame).
            controller: The main application controller that manages navigation
                       and provides access to shared resources like API clients.
        """
        super().__init__(parent)
        self.controller = controller

        # API client for the import organization (different from main org)
        self.import_client = None

        # Selected site information
        self.selected_site_id = None
        self.selected_site_name = None

        # Date selection - default to today
        self.selected_date_str = datetime.now().strftime("%m/%d/%Y")

        # List of pending visitor records to import
        self.pending_visits = []

        # Cache of sites - shared with controller to persist across sessions
        self.sites_cache = getattr(controller, "shared_sites_cache", None)

        # Counter for successful imports
        self.successful_imports = 0

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

        # Determine initial flow based on whether sites are cached
        # If sites are cached, skip configuration and go straight to selection
        self.current_flow = FLOW_SELECT if self.sites_cache else FLOW_CONFIGURE
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
        """
        # Clear existing widgets
        for w in self.content.winfo_children():
            w.destroy()
        for w in self.controls.winfo_children():
            w.destroy()

        # Special handling for CONFIGURE flow - it takes full width
        if self.current_flow == FLOW_CONFIGURE:
            self.content.grid_remove()
            self.controls.grid(
                row=0, column=0, columnspan=2, sticky="nsew", padx=20, pady=20
            )
            self._build_configure_controls()
            return

        # Standard flows - configure grid layout based on flow
        if self.current_flow == FLOW_SELECT:
            # SELECT flow has narrower content for the site list
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=1)
            self.content.master.grid_columnconfigure(1, weight=2)
        else:
            # Other flows have wider content
            self.content.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
            self.content.master.grid_columnconfigure(0, weight=3)
            self.content.master.grid_columnconfigure(1, weight=1)

        # Always show controls on the right
        self.controls.grid(row=0, column=1, sticky="nsew")

        # Map flows to their respective builder methods
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

        # Get and call the appropriate builders
        content_builder, controls_builder = builders.get(
            self.current_flow, (None, None)
        )
        if content_builder:
            content_builder()
        if controls_builder:
            controls_builder()

    # =========================================================================
    # CONFIGURE FLOW - API Credentials Entry
    # =========================================================================

    def _build_configure_controls(self):
        """
        Builds the configuration screen where users enter API credentials.

        This screen appears when the tool first loads (if no cached sites)
        and allows connecting to a different Verkada organization.
        """
        # Center container for the form
        center = ctk.CTkFrame(self.controls, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.5)
        center.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(center, text="Configuration", font=HEADER_FONT).grid(
            row=0, column=0, pady=(0, 10)
        )
        ctk.CTkLabel(
            center,
            text="Enter Import Organization credentials:",
            font=LABEL_FONT,
            text_color="gray",
        ).grid(row=1, column=0, pady=(0, 30))

        # Card container for input fields
        card = ctk.CTkFrame(
            center, corner_radius=15, border_width=2, border_color=CARD_BG_COLOR
        )
        card.grid(row=2, column=0, sticky="ew", pady=20)
        card.grid_columnconfigure(0, weight=1)

        # Organization Short Name input
        ctk.CTkLabel(card, text="Org. Short Name", font=("Verdana", 13, "bold")).grid(
            row=0, column=0, sticky="w", padx=30, pady=(30, 5)
        )
        self.entry_org = ctk.CTkEntry(card, height=45, font=LABEL_FONT)
        self.entry_org.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 15))
        self.entry_org.bind("<Button-1>", lambda e: self.entry_org.focus_set())

        # API Key input with show/hide toggle
        ctk.CTkLabel(card, text="API Key", font=("Verdana", 13, "bold")).grid(
            row=2, column=0, sticky="w", padx=30, pady=(10, 5)
        )

        # Frame to hold API key entry and show/hide button side by side
        key_frame = ctk.CTkFrame(card, fg_color="transparent")
        key_frame.grid(row=3, column=0, sticky="ew", padx=30, pady=(0, 30))
        key_frame.grid_columnconfigure(0, weight=1)  # Entry expands
        key_frame.grid_columnconfigure(1, weight=0)  # Button stays fixed

        # API Key entry (masked by default with "•")
        self.entry_key = ctk.CTkEntry(
            key_frame,
            placeholder_text="Enter API key",
            height=45,
            font=LABEL_FONT,
            show="•",
        )
        self.entry_key.grid(row=0, column=0, sticky="ew")
        self.entry_key.bind("<Button-1>", lambda e: self.entry_key.focus_set())

        # Show/Hide button for API key
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

        # Connect button to load sites
        self.btn_connect = ctk.CTkButton(
            center,
            text="Connect",
            font=("Verdana", 14, "bold"),
            height=50,
            command=self._load_sites,
        )
        self.btn_connect.grid(row=3, column=0, sticky="ew", pady=(20, 0))

        # Auto-fill from environment variables if available
        if key := get_env_var("LEGAL_API_KEY"):
            self.entry_key.insert(0, key)
        if org := get_env_var("LEGAL_ORG_SHORT_NAME"):
            self.entry_org.insert(0, org)

    # =========================================================================
    # SELECT FLOW - Site and Date Selection
    # =========================================================================

    def _build_select_content(self):
        """
        Builds the site selection screen with search and scrollable list.

        This screen displays all available sites from the import organization
        with a search bar to filter them.
        """
        # Configure row weights for proper expansion
        self.content.grid_rowconfigure(2, weight=1)

        # Header with title
        header = ctk.CTkFrame(self.content, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        ctk.CTkLabel(header, text="Select Site:", font=HEADER_FONT).pack(side="left")

        # Search bar for filtering sites
        self.search_bar = ctk.CTkEntry(
            self.content, placeholder_text="Search", height=38, font=LABEL_FONT
        )
        self.search_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(5, 10))
        # Bind key release to filter function for real-time filtering
        # Use after() to debounce rapid keystrokes and prevent UI lag
        self._filter_after_id = None
        self.search_bar.bind("<KeyRelease>", self._on_search_keyrelease)
        self.search_bar.bind("<Button-1>", lambda e: self.search_bar.focus_set())

        # Scrollable frame to hold the site list
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.content,
            label_text="Sites:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))

        # Variable to track selected site
        self.site_var = ctk.StringVar(value="")
        self.site_var.trace_add("write", self._on_site_change)
        self.site_widgets = []  # Store (radio_button, site_name) tuples

        # Populate sites if cache exists
        if self.sites_cache:
            self._populate_sites(self.sites_cache)

    def _build_select_controls(self):
        """
        Builds the control panel for the SELECT flow.

        Includes date picker, week view calendar, selected site display,
        and navigation buttons.
        """
        # Date section header
        ctk.CTkLabel(self.controls, text="Date:", font=("Verdana", 14, "bold")).grid(
            row=0, column=0, pady=(25, 10), padx=20, sticky="w"
        )

        # Date display/entry field
        self.date_display = ctk.CTkEntry(
            self.controls, justify="center", font=("Verdana", 16, "bold"), height=40
        )
        self.date_display.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        self.date_display.insert(0, self.selected_date_str)
        # Bind focus loss and Enter key to validate date entry
        self.date_display.bind("<FocusOut>", self._on_date_manual_entry)
        self.date_display.bind("<Return>", self._on_date_manual_entry)
        self.date_display.bind("<Button-1>", lambda e: self.date_display.focus_set())

        # Week view calendar - shows 7 days with day of week and date
        week_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        week_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=5)
        for i in range(7):
            week_frame.grid_columnconfigure(i, weight=1)

        # Create 7 day buttons (past 6 days + today)
        today = datetime.now()
        for i in range(7):
            # Calculate date for this button (6 days ago to today)
            day = today - timedelta(days=6 - i)
            day_str = day.strftime("%m/%d/%Y")
            # Check if this is the currently selected date
            is_selected = day_str == self.selected_date_str

            # Create day button
            btn = ctk.CTkButton(
                week_frame,
                text=f"{day.strftime('%a')}\n{day.strftime('%d')}",  # e.g., "Mon\n15"
                width=38,
                height=50,
                font=("Verdana", 10),
                # Highlight selected date, otherwise transparent
                fg_color="#1F6AA5" if is_selected else "transparent",
                border_width=0 if is_selected else 1,
                hover_color="#144870" if is_selected else ("gray85", "gray25"),
                command=lambda d=day_str: self._set_date(d),
            )
            btn.grid(row=0, column=i, padx=2, sticky="ew")

        # Separator line
        ctk.CTkFrame(self.controls, height=2, fg_color=("gray80", "gray30")).grid(
            row=3, column=0, sticky="ew", padx=20, pady=20
        )

        # Selected site display
        ctk.CTkLabel(
            self.controls, text="Selected Site:", font=LABEL_FONT, text_color="gray"
        ).grid(row=4, column=0, padx=20, sticky="w")
        self.site_lbl = ctk.CTkLabel(
            self.controls, text="None", font=("Verdana", 14, "bold"), wraplength=270
        )
        self.site_lbl.grid(row=5, column=0, padx=20, sticky="w")

        # Button frame for navigation
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=6, column=0, sticky="ew", padx=20, pady=(20, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # Back button to return to configuration
        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=40,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_CONFIGURE),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Load button to fetch visitors (disabled until site selected)
        self.btn_preview = ctk.CTkButton(
            btn_frame,
            text="Load",
            font=("Verdana", 12, "bold"),
            height=40,
            state="disabled",
            command=self._load_preview,
        )
        self.btn_preview.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # =========================================================================
    # PREVIEW FLOW - Review Visitors
    # =========================================================================

    def _build_preview_content(self):
        """
        Builds the visitor preview screen showing all guests for the selected
        site and date. Displays each visitor in a card format with name and email.
        """
        # Header showing count and context (site + date)
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

        # Container for the scrollable list
        list_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=25, pady=(10, 20))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        # Empty state - no visitors found
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

        # Scrollable frame for visitor cards
        scroll = ctk.CTkScrollableFrame(
            list_frame,
            label_text="Review visitors:",
            label_font=("Verdana", 12, "bold"),
            corner_radius=10,
        )
        scroll.grid(row=0, column=0, sticky="nsew")

        # Create a card for each visitor
        for i, visit in enumerate(self.pending_visits, 1):
            card = ctk.CTkFrame(scroll, fg_color=("gray90", "gray20"), corner_radius=8)
            card.pack(fill="x", padx=5, pady=4)

            # Number badge (blue circle with index)
            badge = ctk.CTkFrame(
                card, fg_color="#1F6AA5", width=35, height=35, corner_radius=17
            )
            badge.pack(side="left", padx=12, pady=12)
            badge.pack_propagate(False)
            ctk.CTkLabel(
                badge, text=str(i), font=("Verdana", 12, "bold"), text_color="white"
            ).place(relx=0.5, rely=0.5, anchor="center")

            # Visitor info container
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, pady=12)

            # Visitor name (first + last)
            name = (
                f"{visit.get('first_name', '')} {visit.get('last_name', '')}".strip()
                or "Unknown"
            )
            ctk.CTkLabel(info, text=name, font=("Verdana", 14, "bold")).pack(anchor="w")
            # Visitor email
            ctk.CTkLabel(
                info,
                text=visit.get("email", "No email"),
                font=("Verdana", 11),
                text_color="gray",
            ).pack(anchor="w")

    def _build_preview_controls(self):
        """
        Builds the control panel for the PREVIEW flow.

        Shows summary information and action buttons to go back or start import.
        """
        # Summary card showing context
        summary = ctk.CTkFrame(
            self.controls, fg_color=("gray90", "gray20"), corner_radius=10
        )
        summary.grid(row=0, column=0, sticky="ew", padx=20, pady=(25, 10))
        ctk.CTkLabel(summary, text="Summary", font=("Verdana", 14, "bold")).pack(
            anchor="w", padx=15, pady=(15, 10)
        )

        # Site and Date info (truncated if too long)
        for label, value in [
            (
                "Site:",
                (self.selected_site_name or "None")[:25] + "..."
                if len(self.selected_site_name or "") > 25
                else self.selected_site_name or "None",
            ),
            ("Date:", self.selected_date_str),
        ][:2]:
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, font=LABEL_FONT, text_color="gray").pack(
                side="left"
            )
            ctk.CTkLabel(row, text=value, font=("Verdana", 12, "bold")).pack(
                side="right"
            )

        # Visitor count with color coding (green if visitors exist)
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

        # Button frame
        btn_frame = ctk.CTkFrame(self.controls, fg_color="transparent")
        btn_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(20, 20))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # Back button to return to site selection
        ctk.CTkButton(
            btn_frame,
            text="Back",
            font=LABEL_FONT,
            height=45,
            fg_color="transparent",
            border_width=1,
            command=lambda: self._set_flow(FLOW_SELECT),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # Conditional action button based on visitor count
        if self.pending_visits:
            # Visitors exist - show Add Users button (green)
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
            # No visitors - show disabled button
            ctk.CTkButton(
                btn_frame,
                text="No Visitors",
                font=("Verdana", 12, "bold"),
                height=45,
                state="disabled",
                fg_color="gray",
            ).grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # =========================================================================
    # PROCESSING FLOW - Import Progress
    # =========================================================================

    def _build_processing_contents(self):
        """
        Builds the processing screen with spinner animation while importing users.

        Shows a loading indicator and status message while the import runs
        in a background thread.
        """
        # Center container
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Animated spinner (updated by _animate_spinner)
        self.spinner = ctk.CTkLabel(center, text="⏳", font=("Verdana", 64))
        self.spinner.pack(pady=(0, 20))
        ctk.CTkLabel(
            center, text="Adding Users to Organization...", font=("Verdana", 20, "bold")
        ).pack()
        ctk.CTkLabel(
            center, text="Please wait...", font=LABEL_FONT, text_color="gray"
        ).pack(pady=(10, 0))

        # Start the spinner animation
        self._animate_spinner()

    def _build_processing_controls(self):
        """
        Builds the control panel for the PROCESSING flow.

        Shows a progress counter, progress bar, and current user being processed.
        """
        # Header
        ctk.CTkLabel(self.controls, text="Processing", font=TITLE_FONT).place(
            relx=0.5, y=40, anchor="center"
        )

        # Progress counter (large number showing current count)
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

        # Progress bar (fills as import progresses)
        self.progress_bar = ctk.CTkProgressBar(self.controls, height=8, corner_radius=4)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=30, pady=(200, 0))
        self.progress_bar.set(0)

        # Current user being processed
        self.current_user = ctk.CTkLabel(
            self.controls,
            text="Starting...",
            font=("Verdana", 11),
            text_color="gray",
            wraplength=280,
        )
        self.current_user.grid(row=2, column=0, pady=(15, 0), padx=20)

    def _animate_spinner(self, frame=0):
        """
        Animate the processing spinner by cycling through Unicode characters.

        Args:
            frame: Current animation frame index (cycles 0-3).
        """
        # Only animate if still in processing flow
        if self.current_flow != FLOW_PROCESSING:
            return

        # Cycle through hourglass characters for animation
        spinners = ["⏳", "⌛", "⏳", "⌛"]
        if hasattr(self, "spinner") and self.spinner.winfo_exists():
            self.spinner.configure(text=spinners[frame % 4])
            # Schedule next frame in 500ms
            self.after(500, lambda: self._animate_spinner(frame + 1))

    # =========================================================================
    # COMPLETE FLOW - Import Results
    # =========================================================================

    def _build_complete_contents(self):
        """
        Builds the completion screen showing import results.

        Displays a success icon, completion message, and summary of results.
        Different icons and colors are used based on success/failure counts.
        """
        # Center container
        center = ctk.CTkFrame(self.content, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Calculate results
        success = self.successful_imports
        total = len(self.pending_visits)

        # Determine icon, color, and message based on results
        if success == total:
            # All succeeded - green checkmark
            icon, color, msg = (
                "✓",
                "#2CC985",
                f"All {total} invitations sent!",
            )
        elif success > 0:
            # Partial success - orange warning
            icon, color, msg = (
                "⚠",
                "orange",
                f"{success} of {total} invitations sent",
            )
        else:
            # All failed - red X
            icon, color, msg = "✗", "#FF5555", "No invitations could be sent"

        # Result display
        ctk.CTkLabel(center, text=icon, font=("Arial", 80), text_color=color).pack(
            pady=(0, 20)
        )
        ctk.CTkLabel(center, text="Complete!", font=("Arial", 24, "bold")).pack()
        ctk.CTkLabel(center, text=msg, font=("Arial", 14), text_color=color).pack(
            pady=(15, 0)
        )

    def _build_complete_controls(self):
        """
        Builds the control panel for the COMPLETE flow.

        Shows final results summary and a button to start a new import.
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

        # Results rows (Successful, Total)
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

        # Start New Import button
        ctk.CTkButton(
            self.controls,
            text="Start New Import",
            font=("Verdana", 14, "bold"),
            height=50,
            command=self._reset,
        ).grid(row=10, column=0, sticky="ew", padx=20, pady=(0, 20))

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _control_header(self, title, subtitle):
        """
        Helper to add a standard header to the control panel.

        Args:
            title: The header title text.
            subtitle: Descriptive subtitle text.
        """
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
        """
        Update the selected date and refresh UI if needed.

        Args:
            date_str: Date string in MM/DD/YYYY format.
        """
        self.selected_date_str = date_str
        if hasattr(self, "date_display"):
            self.date_display.delete(0, "end")
            self.date_display.insert(0, date_str)
        if self.current_flow == FLOW_SELECT:
            self._refresh_ui()

    def _on_date_manual_entry(self, event=None):
        """
        Handle manual date entry with validation.

        Validates that the entered date matches MM/DD/YYYY format.
        If invalid, reverts to the previous valid date.

        Args:
            event: The triggering event (FocusOut or Return key).
        """
        date_str = self.date_display.get().strip()
        try:
            # Validate by parsing
            datetime.strptime(date_str, "%m/%d/%Y")
            self.selected_date_str = date_str
            self._refresh_ui()
        except ValueError:
            # Invalid format - revert to previous valid date
            self.date_display.delete(0, "end")
            self.date_display.insert(0, self.selected_date_str)

    def _on_site_change(self, *args):
        """
        Handle site selection change.

        Updates the selected site info and enables the Load button
        when a valid site is selected.

        Args:
            *args: Arguments passed by the trace callback (unused).
        """
        site_id = self.site_var.get()
        if site_id:
            self.selected_site_id = site_id
            # Find the site name from the stored widgets
            for rb, name in self.site_widgets:
                if rb.cget("value") == site_id:
                    self.selected_site_name = name
                    break
            # Truncate long names for display
            display = (
                (self.selected_site_name or "None")[:30] + "..."
                if len(self.selected_site_name or "") > 30
                else self.selected_site_name
            )
            # Update UI
            if hasattr(self, "site_lbl"):
                self.site_lbl.configure(text=display)
            if hasattr(self, "btn_preview"):
                self.btn_preview.configure(state="normal")

    def _populate_sites(self, sites):
        """
        Populate the scrollable frame with site radio buttons.

        Args:
            sites: List of site dictionaries with 'id' and 'name' keys.
        """
        # Clear existing widgets
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.site_widgets.clear()

        # Empty state
        if not sites:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No sites found",
                font=LABEL_FONT,
                text_color="gray",
            ).pack(pady=20)
            return

        # Create radio button for each site
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
        """
        Filter sites based on search query.

        Shows/hides site radio buttons based on whether the search query
        matches the site name (case-insensitive).

        Args:
            event: The key release event (unused).
        """
        query = self.search_bar.get().lower()
        for rb, name in self.site_widgets:
            # Show if query matches name, hide otherwise
            rb.pack(
                anchor="w", pady=6, padx=10, fill="x"
            ) if query in name.lower() else rb.pack_forget()

    def _toggle_key_visibility(self):
        """
        Toggle the visibility of the API key entry.

        Switches between masked (•) and plain text display.
        Also updates the button text between "Show" and "Hide".
        """
        if self.entry_key.cget("show") == "•":
            # Currently masked - show plain text
            self.entry_key.configure(show="")
            self.btn_show_key.configure(text="Hide")
        else:
            # Currently visible - mask
            self.entry_key.configure(show="•")
            self.btn_show_key.configure(text="Show")

    def _load_sites(self):
        """
        Load sites from the import organization API.

        Validates credentials, connects to the API, fetches the site list,
        and transitions to the SELECT flow on success.
        """
        # Get and validate credentials
        api_key = self.entry_key.get().strip()
        org_name = self.entry_org.get().strip()

        if not api_key or not org_name:
            logger.error("Missing API Key or Organization Short Name")
            return

        # Disable button and show loading state
        self.btn_connect.configure(state="disabled", text="Connecting...")

        def fetch():
            """Background thread function to fetch sites."""
            try:
                # Create API client and fetch sites
                self.import_client = VerkadaExternalAPIClient(api_key, org_name)
                sites = self.import_client.get_object("guest_sites")

                # Cache sites locally and in controller for persistence
                self.sites_cache = sites
                self.controller.shared_sites_cache = sites

                # Update UI on main thread
                self.after(0, lambda: self._set_flow(FLOW_SELECT))
                logger.info(f"Loaded {len(sites)} sites")
            except Exception as e:
                logger.error(f"Error loading sites: {e}")
                # Re-enable button on failure
                self.after(
                    0,
                    lambda: self.btn_connect.configure(
                        state="normal", text="Connect & Load Sites"
                    ),
                )

        # Run in background thread to avoid blocking UI
        threading.Thread(target=fetch, daemon=True).start()

    def _load_preview(self):
        """
        Load visitor preview for the selected site and date.

        Fetches guest visits for the selected site within the selected date
        and transitions to the PREVIEW flow to display them.
        """
        site_id = self.site_var.get()
        if not site_id:
            return

        if not self.import_client:
            logger.error("Import client not initialized")
            return

        # Disable button and show loading state
        self.btn_preview.configure(state="disabled", text="Loading...")

        def fetch():
            """Background thread function to fetch visitors."""
            try:
                # Parse selected date
                start_dt = datetime.strptime(self.selected_date_str, "%m/%d/%Y")
                # Start of day timestamp
                start_ts = int(start_dt.timestamp())
                # End of day timestamp (start of next day - 1 second)
                end_ts = int(
                    (start_dt + timedelta(days=1) - timedelta(seconds=1)).timestamp()
                )

                # Fetch guest visits
                if self.import_client is not None:
                    visits = self.import_client.get_guest_visits(
                        site_id, start_ts, end_ts
                    )
                    self.pending_visits = visits or []

                    # Update UI on main thread
                    self.after(0, lambda: self._set_flow(FLOW_PREVIEW))
                    logger.info(f"Found {len(self.pending_visits)} visitors")
            except Exception as e:
                logger.error(f"Error loading visitors: {e}")
                # Re-enable button on failure
                self.after(
                    0,
                    lambda: self.btn_preview.configure(
                        state="normal", text="Load Visitors →"
                    ),
                )

        # Run in background thread to avoid blocking UI
        threading.Thread(target=fetch, daemon=True).start()

    def _start_import(self):
        """
        Start the user import process.

        Transitions to the PROCESSING flow and begins the import
        in a background thread.
        """
        self._set_flow(FLOW_PROCESSING)
        threading.Thread(target=self._execute_import, daemon=True).start()

    def _execute_import(self):
        """
        Execute the user import in a background thread.

        Iterates through all pending visits and invites each visitor
        as a user in the organization. Updates the progress UI after
        each invitation.
        """
        self.successful_imports = 0
        total = len(self.pending_visits)

        for i, visit in enumerate(self.pending_visits, 1):
            # Check if client session is still available
            if not self.controller.client:
                logger.error("Client session lost")
                break

            try:
                # Update UI showing current user
                name = f"{visit.get('first_name', '')} {visit.get('last_name', '')}".strip()
                self.after(
                    0, lambda n=name: self.current_user.configure(text=f"Inviting: {n}")
                )

                # Send invitation via internal API
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

            # Update progress bar
            progress = i / total
            self.after(0, lambda p=progress, c=i: self._update_progress(p, c))

        # Transition to complete screen
        self.after(0, lambda: self._set_flow(FLOW_COMPLETE))

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

    def _reset(self):
        """
        Reset the tool to initial state.

        Clears all selections and returns to the SELECT flow.
        Sites cache is preserved to avoid re-entering credentials.
        """
        self.pending_visits = []
        self.selected_site_id = None
        self.site_var.set("")
        self.successful_imports = 0
        self._set_flow(FLOW_SELECT)

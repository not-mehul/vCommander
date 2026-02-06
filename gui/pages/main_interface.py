"""
Main Interface Page - Primary Application Workspace

This module provides the main application interface with a sidebar navigation
and content area for tools. It includes a console/log viewer in the sidebar
that displays real-time logging information.
"""

import logging

import customtkinter as ctk
from tools.add_user import AddUserTool
from tools.decommission import DecommissionTool

# =============================================================================
# STYLING CONSTANTS
# =============================================================================

SIDEBAR_WIDTH = 250  # Fixed width of the left sidebar
CONSOLE_FONT = ("Consolas", 10)  # Monospace font for console output
NAV_BUTTON_FONT = ("Verdana", 14)  # Font for navigation buttons
TIMESTAMP_FORMAT = "%H:%M:%S"  # Time format for log messages

# Initialize logger for this module
logger = logging.getLogger(__name__)


class MainInterfacePage(ctk.CTkFrame):
    """
    Main application interface with sidebar navigation.

    Provides:
    - Sidebar with navigation buttons for different tools
    - Console/log viewer showing real-time application logs
    - Main content area for displaying the active tool
    - Tool switching functionality
    """

    def __init__(self, parent, controller):
        """
        Initialize the main interface.

        Args:
            parent: The parent widget (main application window).
            controller: The main application controller (vCommanderApp instance)
                       that provides access to the API client and navigation.
        """
        super().__init__(parent)
        self.controller = controller
        self.current_tool = None  # Track currently displayed tool name

        # Build the UI layout
        self._setup_layout()
        self._create_sidebar()
        self._create_main_area()

        # Configure logging to display in the console textbox
        # Set root logger to capture INFO level and above
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Create custom handler that writes to the console textbox
        handler = TextboxLogHandler(self.console_box)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(message)s", datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        # Show the default tool on startup
        self.show_decommission()

    def _setup_layout(self):
        """
        Set up the main interface layout.

        Creates a two-column grid layout:
        - Column 0: Sidebar with fixed width
        - Column 1: Main content area that expands to fill space
        """
        # Fill the entire parent window
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        # Configure grid columns
        self.grid_columnconfigure(0, weight=0, minsize=SIDEBAR_WIDTH)  # Fixed sidebar
        self.grid_columnconfigure(1, weight=1)  # Expandable main area
        self.grid_rowconfigure(0, weight=1)

    def _create_sidebar(self):
        """
        Create the left sidebar with navigation and console.

        The sidebar contains:
        - Application logo/title
        - Navigation buttons for each tool
        - Console label
        - Scrollable console textbox for logs
        """
        # Sidebar container frame
        self.sidebar_frame = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)  # Maintain fixed width

        # Configure sidebar grid
        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        self.sidebar_frame.grid_rowconfigure(5, weight=1)  # Console expands

        # Application logo
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="vCommander", font=("Verdana", 24, "bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Commission tool button (placeholder)
        self.btn_commission = self._create_nav_button(
            "Commission", self.show_commission
        )
        self.btn_commission.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Users tool button
        self.btn_users = self._create_nav_button("Users", self.show_users)
        self.btn_users.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        # Decommission tool button
        self.btn_decommission = self._create_nav_button(
            "Decommission", self.show_decommission
        )
        self.btn_decommission.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        # Console section label
        self.console_label = ctk.CTkLabel(
            self.sidebar_frame, text="Console:", font=("Verdana", 10)
        )
        self.console_label.grid(row=4, column=0, padx=20, pady=(20, 0), sticky="w")

        # Console textbox (read-only, scrollable)
        self.console_box = ctk.CTkTextbox(
            self.sidebar_frame,
            font=CONSOLE_FONT,
            wrap="word",
            activate_scrollbars=True,
            state="disabled",  # Read-only - user cannot edit
        )
        self.console_box.grid(row=5, column=0, padx=10, pady=(5, 10), sticky="nsew")

    def _create_main_area(self):
        """
        Create the main content area for displaying tools.

        This is an empty container that will be populated with the
        active tool's widgets when a navigation button is clicked.
        """
        self.main_area = ctk.CTkFrame(self, corner_radius=10)
        self.main_area.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(0, weight=1)

    def _create_nav_button(self, text, command):
        """
        Create a styled navigation button.

        Args:
            text: The button label text.
            command: The function to call when clicked.

        Returns:
            The created CTkButton widget.
        """
        return ctk.CTkButton(
            self.sidebar_frame,
            text=text,
            command=command,
            font=NAV_BUTTON_FONT,
            border_width=0,
            anchor="w",  # Left-align text
            height=40,
        )

    def _switch_tool(self, tool_name, tool_factory=None):
        """
        Switch to a different tool in the main content area.

        Clears the current content and either:
        - Creates a new tool instance using the factory function, or
        - Shows a placeholder label if no factory is provided

        Args:
            tool_name: The display name of the tool (for logging).
            tool_factory: Optional callable that creates and returns the tool widget.
        """
        # Avoid unnecessary re-rendering if already showing this tool
        if self.current_tool == tool_name:
            return
        self.current_tool = tool_name

        # Clear existing content
        for widget in self.main_area.winfo_children():
            widget.destroy()

        # Create new content
        if tool_factory:
            # Create the actual tool widget
            tool = tool_factory()
            tool.pack(fill="both", expand=True)
        else:
            # Show placeholder for unimplemented tools
            label = ctk.CTkLabel(
                self.main_area, text=f"{tool_name} Placeholder", font=("Verdana", 24)
            )
            label.place(relx=0.5, rely=0.5, anchor="center")

        logger.info(f"Switched to {tool_name}")

    def show_commission(self):
        """Show the commission tool (placeholder)."""
        self._switch_tool("Coming Soon! Stay Tuned!")

    def show_users(self):
        """Show the user management tool (AddUserTool)."""
        self._switch_tool(
            "User Tool",
            lambda: AddUserTool(parent=self.main_area, controller=self.controller),
        )

    def show_decommission(self):
        """Show the decommission tool."""
        self._switch_tool(
            "Decommission Tool",
            lambda: DecommissionTool(parent=self.main_area, controller=self.controller),
        )


class TextboxLogHandler(logging.Handler):
    """
    Custom logging handler that writes log messages to a CTkTextbox.

    This allows real-time display of application logs in the GUI console.
    The handler formats log records and inserts them into the textbox,
    automatically scrolling to show the most recent messages.
    """

    def __init__(self, text_widget):
        """
        Initialize the handler with a target text widget.

        Args:
            text_widget: The CTkTextbox widget to write log messages to.
        """
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        """
        Process a log record and write it to the textbox.

        Args:
            record: The LogRecord object containing the log message.
        """
        # Format the log record using the handler's formatter
        msg = self.format(record)

        # Enable editing, insert message, then disable editing
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", f"[{record.levelname}] {msg}\n")
        # Scroll to the end to show newest message
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

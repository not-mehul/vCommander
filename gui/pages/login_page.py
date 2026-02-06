"""
Login Page - Authentication Screen for vCommander

This module provides the login interface where users enter their Verkada
credentials (email, password, organization short name, and shard) to
authenticate with the internal Verkada API.
"""

import logging
import re

import customtkinter as ctk
from tools.verkada_api_clients import MFARequiredError, VerkadaInternalAPIClient
from tools.verkada_utilities import get_env_var

# =============================================================================
# STYLING CONSTANTS
# =============================================================================
# Color scheme for the login page UI elements

CARD_BG_COLOR = "#1c1c1c"  # Background color of the login card
CARD_BORDER_COLOR = "#333333"  # Border color of the login card
ENTRY_BG_COLOR = "#2b2b2b"  # Background color of input fields
ENTRY_BORDER_COLOR = "#444444"  # Border color of input fields
BUTTON_FG_COLOR = "#666666"  # Button foreground color
BUTTON_HOVER_COLOR = "#555555"  # Button color on hover
ERROR_COLOR = "#FF5555"  # Error message text color
TITLE_COLOR = "#A0A0A0"  # Title text color
PLACEHOLDER_COLOR = "#888888"  # Placeholder text color

# Initialize logger for this module
logger = logging.getLogger(__name__)


class LoginPage(ctk.CTkFrame):
    """
    Login screen for vCommander application.

    Provides a centered login card with input fields for:
    - Email address
    - Password (with show/hide toggle)
    - Organization short name
    - Shard (backend server identifier)

    Supports auto-filling credentials from environment variables
    and handles both direct login and MFA-required scenarios.
    """

    def __init__(self, parent, controller):
        """
        Initialize the login page.

        Args:
            parent: The parent widget (main application window).
            controller: The main application controller (vCommanderApp instance)
                       that manages screen navigation and stores the API client.
        """
        super().__init__(parent)
        self.controller = controller

        # Build the UI layout and widgets
        self._setup_layout()
        self._create_widgets()

    def _setup_layout(self):
        """
        Set up the page layout structure.

        Creates a centered card container that holds all login form elements.
        The card is positioned in the center of the window with a fixed
        relative width.
        """
        # Make the frame transparent to show parent background
        self.configure(fg_color="transparent")
        # Fill the entire parent window
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        # Create the login card (centered container with border)
        self.login_card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color=CARD_BORDER_COLOR,
            fg_color=CARD_BG_COLOR,
        )
        # Center the card, use 30% of window width
        self.login_card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        # Content frame inside the card for padding
        self.content_frame = ctk.CTkFrame(self.login_card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

    def _create_widgets(self):
        """
        Create and arrange all login form widgets.

        Creates the title, input fields (email, password, org, shard),
        show/hide password button, error label, and login button.
        Also attempts to auto-fill credentials from environment variables.
        """
        # Application title
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="vCommander",
            font=("Verdana", 32, "bold"),
            text_color=TITLE_COLOR,
        )
        self.title_label.pack(pady=(10, 40))

        # Email input field
        self.entry_email = self._create_entry(self.content_frame, "Email")

        # Password input frame (contains entry + show/hide button)
        pass_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        pass_frame.pack(fill="x", pady=5)
        pass_frame.grid_columnconfigure(0, weight=1)

        self.entry_password = self._create_entry(
            pass_frame, "Password", is_password=True, pack=False
        )
        self.entry_password.grid(row=0, column=0, sticky="ew")

        # Show/Hide password button
        self.btn_show_pass = ctk.CTkButton(
            pass_frame,
            text="Show",
            width=50,
            height=40,
            font=("Verdana", 12),
            fg_color="transparent",
            text_color=PLACEHOLDER_COLOR,
            hover_color=CARD_BORDER_COLOR,
            command=self._toggle_password_visibility,
        )
        self.btn_show_pass.grid(row=0, column=1, padx=(4, 0))

        # Row frame for org short name and shard (side by side)
        self.row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.row_frame.pack(fill="x", pady=5)

        # Organization short name input
        self.entry_org = self._create_entry(self.row_frame, "Short Name", pack=False)
        self.entry_org.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Shard input (smaller width)
        self.entry_shard = self._create_entry(self.row_frame, "shard", pack=False)
        self.entry_shard.configure(width=100)
        self.entry_shard.pack(side="right")

        # Attempt to load credentials from environment variables
        # This allows for easier development/testing without manual entry
        try:
            email = get_env_var("ADMIN_EMAIL")
            password = get_env_var("ADMIN_PASSWORD")
            org_name = get_env_var("ORG_SHORT_NAME")
            shard = get_env_var("SHARD")
        except EnvironmentError:
            # If env vars are not set, use empty defaults
            email = password = org_name = shard = ""

        # Auto-fill the form if environment variables are available
        if email:
            self.entry_email.insert(0, email)
        if password:
            self.entry_password.insert(0, password)
        if org_name:
            self.entry_org.insert(0, org_name)
        if shard:
            self.entry_shard.insert(0, shard)
        else:
            # Default to prod1 if no shard specified
            self.entry_shard.insert(0, "prod1")

        # Error message label (initially empty)
        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color=ERROR_COLOR, font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

        # Login button
        self.btn_login = ctk.CTkButton(
            self.content_frame,
            text="Login",
            font=("Verdana", 16, "bold"),
            height=45,
            fg_color=BUTTON_FG_COLOR,
            hover_color=BUTTON_HOVER_COLOR,
            corner_radius=8,
            command=self._handle_login,
        )
        self.btn_login.pack(pady=(20, 10), fill="x")

    def _create_entry(self, parent, placeholder, is_password=False, pack=True):
        """
        Create a styled input field.

        Args:
            parent: The parent widget to contain the entry.
            placeholder: The placeholder text to display when empty.
            is_password: If True, masks input with asterisks.
            pack: If True, automatically packs the widget; otherwise caller must layout.

        Returns:
            The created CTkEntry widget.
        """
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            show="*" if is_password else "",
            height=40,
            font=("Verdana", 14),
            fg_color=ENTRY_BG_COLOR,
            border_color=ENTRY_BORDER_COLOR,
            text_color="white",
            placeholder_text_color=PLACEHOLDER_COLOR,
        )
        # Allow pressing Enter to submit the form
        entry.bind("<Return>", self._handle_login)

        if pack:
            entry.pack(pady=5, fill="x")

        return entry

    def _toggle_password_visibility(self):
        """
        Toggle password field between masked and visible.

        Changes the show attribute of the password entry between "*" and ""
        and updates the button text between "Show" and "Hide".
        """
        if self.entry_password.cget("show") == "*":
            # Currently masked - show plain text
            self.entry_password.configure(show="")
            self.btn_show_pass.configure(text="Hide")
        else:
            # Currently visible - mask
            self.entry_password.configure(show="*")
            self.btn_show_pass.configure(text="Show")

    def _validate_inputs(self, email, password, org, shard):
        """
        Validate login form inputs.

        Args:
            email: The email address entered.
            password: The password entered.
            org: The organization short name entered.
            shard: The shard entered.

        Returns:
            Tuple of (is_valid: bool, error_message: str or None)
        """
        # Check all fields are filled
        if not all([email, password, org, shard]):
            return False, "Please fill in all fields"

        # Validate email format using regex
        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_pattern, email):
            return False, "Invalid email format"

        return True, None

    def _handle_login(self, event=None):
        """
        Process the login attempt.

        Validates inputs, creates the API client, and attempts authentication.
        On success, navigates to the main interface. On MFA requirement,
        navigates to the 2FA screen. On failure, displays an error message.

        Args:
            event: Optional event object (for key binding support).
        """
        # Get values from input fields
        email = self.entry_email.get().strip()
        password = self.entry_password.get().strip()
        org = self.entry_org.get().strip()
        shard = self.entry_shard.get().strip()

        # Validate inputs
        is_valid, error = self._validate_inputs(email, password, org, shard)
        if not is_valid:
            self.error_label.configure(text=error)
            return

        # Show loading state
        self.error_label.configure(text="Logging in...", text_color="white")
        self.btn_login.configure(state="disabled")
        self.update_idletasks()

        try:
            # Create API client with provided credentials
            self.controller.client = VerkadaInternalAPIClient(
                email=email, password=password, org_short_name=org, shard=shard
            )
            # Attempt login
            self.controller.client.login()

            logger.info(f"Login successful for user: {email}")
            # Navigate to main interface on success
            self.controller.setup_main_interface()

        except MFARequiredError:
            # MFA is required - navigate to 2FA screen
            logger.info(f"MFA required for user: {email}")
            self.controller.show_2fa_screen()

        except Exception as e:
            # Login failed - show error
            logger.error(f"Login failed: {e}")
            if self.winfo_exists():
                self.error_label.configure(
                    text=f"Error: {str(e)}", text_color=ERROR_COLOR
                )
            self.controller.client = None

        finally:
            # Re-enable login button if widget still exists
            if self.winfo_exists() and self.btn_login.winfo_exists():
                self.btn_login.configure(state="normal")

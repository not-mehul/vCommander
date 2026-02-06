"""
Two-Factor Authentication (2FA) Page - MFA Verification Screen

This module provides the 2FA/MFA verification interface where users enter
the one-time passcode (OTP) sent to their device after successful
username/password authentication.
"""

import logging

import customtkinter as ctk

# =============================================================================
# STYLING CONSTANTS
# =============================================================================
# Color scheme matching the login page for consistency

CARD_BG_COLOR = "#1c1c1c"  # Background color of the card
CARD_BORDER_COLOR = "#333333"  # Border color of the card
ENTRY_BG_COLOR = "#2b2b2b"  # Background color of input field
ENTRY_BORDER_COLOR = "#444444"  # Border color of input field
BUTTON_FG_COLOR = "#666666"  # Button foreground color
BUTTON_HOVER_COLOR = "#555555"  # Button color on hover
ERROR_COLOR = "#FF5555"  # Error message text color
TITLE_COLOR = "#A0A0A0"  # Title text color
PLACEHOLDER_COLOR = "#888888"  # Placeholder text color

# =============================================================================
# VALIDATION CONSTANTS
# =============================================================================

CODE_LENGTH = 6  # Expected length of 2FA code (6 digits)

# Initialize logger for this module
logger = logging.getLogger(__name__)


class TwoFAPage(ctk.CTkFrame):
    """
    Two-factor authentication verification screen.

    Displays a centered card with an input field for the 6-digit OTP code.
    Validates the code format (digits only, exactly 6 characters) and
    submits it to the API client for verification.
    """

    def __init__(self, parent, controller):
        """
        Initialize the 2FA page.

        Args:
            parent: The parent widget (main application window).
            controller: The main application controller (vCommanderApp instance)
                       that stores the API client and manages navigation.
        """
        super().__init__(parent)
        self.controller = controller

        # Build the UI layout and widgets
        self._setup_layout()
        self._create_widget()

    def _setup_layout(self):
        """
        Set up the page layout structure.

        Creates a centered card container similar to the login page
        for visual consistency.
        """
        # Make the frame transparent to show parent background
        self.configure(fg_color="transparent")
        # Fill the entire parent window
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        # Create the verification card (centered container with border)
        self.card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color=CARD_BORDER_COLOR,
            fg_color=CARD_BG_COLOR,
        )
        # Center the card, use 30% of window width
        self.card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        # Content frame inside the card for padding
        self.content_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

    def _create_widget(self):
        """
        Create and arrange all 2FA verification widgets.

        Creates the title, instruction text, code input field,
        error label, and verify button.
        """
        # Page title
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="Verification Code",
            font=("Verdana", 28, "bold"),
            text_color=TITLE_COLOR,
        )
        self.title_label.pack(pady=(10, 10))

        # Instruction text showing required code length
        self.instr_label = ctk.CTkLabel(
            self.content_frame,
            text=f"Enter the {CODE_LENGTH}-digit code",
            font=("Verdana", 12),
            text_color="gray",
        )
        self.instr_label.pack(pady=(0, 30))

        # Create validation command for input field
        # This restricts input to digits only and max CODE_LENGTH characters
        vcmd = (self.register(self.validate_input), "%P")

        # Code input field (centered, larger font for visibility)
        self.entry_code = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="0" * CODE_LENGTH,  # Shows "000000" as placeholder
            height=50,
            justify="center",  # Center-align text
            font=("Verdana", 24, "bold"),
            fg_color=ENTRY_BG_COLOR,
            border_color=ENTRY_BORDER_COLOR,
            text_color="white",
            placeholder_text_color=PLACEHOLDER_COLOR,
            validate="key",  # Validate on every keystroke
            validatecommand=vcmd,
        )
        self.entry_code.pack(fill="x", pady=10)
        # Allow pressing Enter to submit
        self.entry_code.bind("<Return>", self._handle_verify)

        # Error message label (initially empty)
        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color=ERROR_COLOR, font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

        # Verify button
        self.btn_verify = ctk.CTkButton(
            self.content_frame,
            text="Verify",
            font=("Verdana", 16, "bold"),
            height=45,
            fg_color=BUTTON_FG_COLOR,
            hover_color=BUTTON_HOVER_COLOR,
            corner_radius=8,
            command=self._handle_verify,
        )
        self.btn_verify.pack(pady=(20, 10), fill="x")

    def validate_input(self, new_value):
        """
        Validate input for the code entry field.

        Restricts input to:
        - Empty string (allows deletion)
        - Maximum CODE_LENGTH characters
        - Digits only (0-9)

        Args:
            new_value: The value of the entry field after the proposed change.

        Returns:
            True if the input is valid, False otherwise.
        """
        # Allow empty string (user is deleting)
        if new_value == "":
            return True

        # Check length limit
        if len(new_value) > CODE_LENGTH:
            return False

        # Check content (must be digits only)
        if not new_value.isdigit():
            return False

        return True

    def _handle_verify(self, event=None):
        """
        Process the 2FA verification attempt.

        Validates the code length, submits it to the API client,
        and navigates to the main interface on success or shows
        an error message on failure.

        Args:
            event: Optional event object (for key binding support).
        """
        # Get the entered code
        code = self.entry_code.get().strip()

        # Validate code length
        if len(code) != CODE_LENGTH:
            self.error_label.configure(
                text=f"⚠ Code must be exactly {CODE_LENGTH} digits."
            )
            return

        # Show loading state
        self.error_label.configure(text="Verifying...", text_color="white")
        self.btn_verify.configure(state="disabled")
        self.update_idletasks()

        try:
            # Check if API client is still available
            if not self.controller.client:
                raise ValueError("Session lost. Please restart.")

            # Submit the code for verification
            self.controller.client.verify_mfa(code)

            logger.info("Verification successful!")
            logger.info("Successfully verified 2FA!")
            # Navigate to main interface on success
            self.controller.setup_main_interface()

        except Exception as e:
            # Verification failed - show error
            logger.error(f"2FA verification failed: {e}")
            if self.winfo_exists():
                self.error_label.configure(text=f"⚠ {str(e)}", text_color=ERROR_COLOR)

        finally:
            # Re-enable verify button if widget still exists
            if self.winfo_exists() and self.btn_verify.winfo_exists():
                self.btn_verify.configure(state="normal")

    def clear(self):
        """
        Clear the input field and error message.

        This can be called when navigating away from or returning to
        the 2FA page to ensure a clean state.
        """
        self.entry_code.delete(0, "end")
        self.error_label.configure(text="")

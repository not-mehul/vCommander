import logging

import customtkinter as ctk

# Constants
CARD_BG_COLOR = "#1c1c1c"
CARD_BORDER_COLOR = "#333333"
ENTRY_BG_COLOR = "#2b2b2b"
ENTRY_BORDER_COLOR = "#444444"
BUTTON_FG_COLOR = "#666666"
BUTTON_HOVER_COLOR = "#555555"
ERROR_COLOR = "#FF5555"
TITLE_COLOR = "#A0A0A0"
PLACEHOLDER_COLOR = "#888888"

CODE_LENGTH = 6

logger = logging.getLogger(__name__)


class TwoFAPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self._setup_layout()
        self._create_widget()

    def _setup_layout(self):
        self.configure(fg_color="transparent")
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        self.card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color=CARD_BORDER_COLOR,
            fg_color=CARD_BG_COLOR,
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        self.content_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

    def _create_widget(self):
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="Two-Factor Authentication",
            font=("Verdana", 28, "bold"),
            text_color=TITLE_COLOR,
        )
        self.title_label.pack(pady=(10, 10))

        self.instr_label = ctk.CTkLabel(
            self.content_frame,
            text=f"Enter the {CODE_LENGTH}-digit code",
            font=("Verdana", 12),
            text_color="gray",
        )
        self.instr_label.pack(pady=(0, 30))

        vcmd = (self.register(self.validate_input), "%P")
        self.entry_code = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="0" * CODE_LENGTH,
            height=50,
            justify="center",
            font=("Verdana", 24, "bold"),
            fg_color=ENTRY_BG_COLOR,
            border_color=ENTRY_BORDER_COLOR,
            text_color="white",
            placeholder_text_color=PLACEHOLDER_COLOR,
            validate="key",
            validatecommand=vcmd,
        )
        self.entry_code.pack(fill="x", pady=10)
        self.entry_code.bind("<Return>", self._handle_verify)

        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color=ERROR_COLOR, font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

        # Verify Button
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
        if new_value == "":
            return True

        # 2. Check Length (Must be <= 6)
        if len(new_value) > CODE_LENGTH:
            return False

        # 3. Check Content (Must be digits only)
        if not new_value.isdigit():
            return False

        return True

    def _handle_verify(self, event=None):
        code = self.entry_code.get().strip()

        if len(code) != CODE_LENGTH:
            self.error_label.configure(
                text=f"⚠ Code must be exactly {CODE_LENGTH} digits."
            )
            return

        self.error_label.configure(text="Verifying...", text_color="white")
        self.btn_verify.configure(state="disabled")
        self.update_idletasks()

        try:
            if not self.controller.client:
                raise ValueError("Session lost. Please restart.")

            self.controller.client.verify_mfa(code)

            logger.info("Verification successful!")
            logger.info("Successfully verified 2FA!")
            self.controller.setup_main_interface()

        except Exception as e:
            logger.error(f"2FA verification failed: {e}")
            if self.winfo_exists():
                self.error_label.configure(text=f"⚠ {str(e)}", text_color=ERROR_COLOR)

        finally:
            if self.winfo_exists() and self.btn_verify.winfo_exists():
                self.btn_verify.configure(state="normal")

    def clear(self):
        """Clear the input field and error message."""
        self.entry_code.delete(0, "end")
        self.error_label.configure(text="")

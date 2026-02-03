import logging
import re

import customtkinter as ctk
from tools.verkada_api_clients import MFARequiredError, VerkadaInternalAPIClient
from tools.verkada_utilities import get_env_var

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

logger = logging.getLogger(__name__)


class LoginPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self._setup_layout()
        self._create_widgets()

    def _setup_layout(self):
        self.configure(fg_color="transparent")
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        self.login_card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color=CARD_BORDER_COLOR,
            fg_color=CARD_BG_COLOR,
        )
        self.login_card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        self.content_frame = ctk.CTkFrame(self.login_card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

    def _create_widgets(self):
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="vConduit",
            font=("Verdana", 32, "bold"),
            text_color=TITLE_COLOR,
        )
        self.title_label.pack(pady=(10, 40))

        self.entry_email = self._create_entry(self.content_frame, "Email")

        self.entry_password = self._create_entry(
            self.content_frame, "Password", is_password=True
        )
        self.btn_show_pass = ctk.CTkButton(
            self.content_frame,
            text="Show",
            width=40,
            height=20,
            font=("Verdana", 8),
            fg_color="transparent",
            text_color=PLACEHOLDER_COLOR,
            hover_color=CARD_BORDER_COLOR,
            command=self._toggle_password_visibility,
        )
        self.btn_show_pass.place(
            in_=self.entry_password, relx=1.0, rely=0.5, anchor="e", x=-10
        )
        self.row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.row_frame.pack(fill="x", pady=5)

        self.entry_org = self._create_entry(self.row_frame, "Short Name", pack=False)
        self.entry_org.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.entry_shard = self._create_entry(self.row_frame, "shard", pack=False)
        self.entry_shard.configure(width=100)
        self.entry_shard.pack(side="right")

        email = get_env_var("ADMIN_EMAIL")
        password = get_env_var("ADMIN_PASSWORD")
        org_name = get_env_var("ORG_SHORT_NAME")
        shard = get_env_var("SHARD")

        if email:
            self.entry_email.insert(0, email)
        if password:
            self.entry_password.insert(0, password)
        if org_name:
            self.entry_org.insert(0, org_name)
        if shard:
            self.entry_shard.insert(0, shard)
        else:
            self.entry_shard.insert(0, "prod1")

        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color=ERROR_COLOR, font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

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
        entry.bind("<Return>", self._handle_login)

        if pack:
            entry.pack(pady=5, fill="x")

        return entry

    def _toggle_password_visibility(self):
        if self.entry_password.cget("show") == "*":
            self.entry_password.configure(show="")
            self.btn_show_pass.configure(text="Hide")
        else:
            self.entry_password.configure(show="*")
            self.btn_show_pass.configure(text="Show")

    def _validate_inputs(self, email, password, org, shard):
        if not all([email, password, org, shard]):
            return False, "Please fill in all fields"

        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_pattern, email):
            return False, "Invalid email format"

        return True, None

    def _handle_login(self, event=None):
        email = self.entry_email.get().strip()
        password = self.entry_password.get().strip()
        org = self.entry_org.get().strip()
        shard = self.entry_shard.get().strip()

        is_valid, error = self._validate_inputs(email, password, org, shard)
        if not is_valid:
            self.error_label.configure(text=error)
            return

        self.error_label.configure(text="Logging in...", text_color="white")
        self.btn_login.configure(state="disabled")
        self.update_idletasks()

        try:
            self.controller.client = VerkadaInternalAPIClient(
                email=email, password=password, org_short_name=org, shard=shard
            )
            self.controller.client.login()

            logger.info(f"Login successful for user: {email}")
            self.controller.setup_main_interface()

        except MFARequiredError:
            logger.info(f"MFA required for user: {email}")
            self.controller.show_2fa_screen()

        except Exception as e:
            logger.error(f"Login failed: {e}")
            if self.winfo_exists():
                self.error_label.configure(
                    text=f"Error: {str(e)}", text_color=ERROR_COLOR
                )
            self.controller.client = None

        finally:
            if self.winfo_exists() and self.btn_login.winfo_exists():
                self.btn_login.configure(state="normal")

import re

import customtkinter as ctk
from tools.verkada_api_clients import MFARequiredError, VerkadaInternalAPIClient


class LoginPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # 1. Background Setup
        self.configure(fg_color="transparent")
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        # 2. The Login Card
        self.center_container = ctk.CTkFrame(self, fg_color="transparent")
        self.center_container.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.9)
        self.login_card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color="#333333",
            fg_color="#1c1c1c",
        )
        self.login_card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        # 3. Content Inside the Card
        self.content_frame = ctk.CTkFrame(self.login_card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

        # Title
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="vConduit",
            font=("Verdana", 32, "bold"),
            text_color="#A0A0A0",
        )
        self.title_label.pack(pady=(10, 40))

        # Inputs (fill="x" makes them stretch to the padding limits)
        self.entry_email = self.create_entry(self.content_frame, "Email")
        self.entry_password = self.create_entry(
            self.content_frame, "Password", is_password=True
        )
        self.btn_show_pass = ctk.CTkButton(
            self.content_frame,
            text="Show",
            width=40,
            height=20,
            font=("Verdana", 8),
            fg_color="transparent",  # Transparent background
            text_color="#888888",  # Gray text
            hover_color="#333333",  # Slight hover effect
            command=self.toggle_password_visibility,
        )
        self.btn_show_pass.place(
            in_=self.entry_password, relx=1.0, rely=0.5, anchor="e", x=-10
        )

        # -- Split Row (Org & Shard) --
        self.row_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.row_frame.pack(fill="x", pady=5)  # Fill width

        # Org takes remaining space
        self.entry_org = self.create_entry(self.row_frame, "Short Name", pack_padding=0)
        self.entry_org.pack(
            side="left", fill="x", expand=True, padx=(0, 10)
        )  # expand=True makes it dynamic

        # Shard stays fixed width (better UI for short codes)
        self.entry_shard = self.create_entry(self.row_frame, "shard", pack_padding=0)
        self.entry_shard.configure(width=100)  # Force fixed width for shard
        self.entry_shard.pack(side="right")
        self.entry_shard.insert(0, "prod1")

        # Error Label
        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color="#FF5555", font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

        # Login Button
        self.btn_login = ctk.CTkButton(
            self.content_frame,
            text="Login",
            font=("Verdana", 16, "bold"),
            height=45,
            # No width set, we use fill="x" to stretch it
            fg_color="#666666",
            hover_color="#555555",
            corner_radius=8,
            command=self.event_login_clicked,
        )
        self.btn_login.pack(pady=(20, 10), fill="x")

    def create_entry(self, parent, placeholder, is_password=False, pack_padding=5):
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            show="*" if is_password else "",
            height=40,
            font=("Verdana", 14),
            fg_color="#2b2b2b",
            border_color="#444444",
            text_color="white",
            placeholder_text_color="#888888",
        )
        entry.bind("<Return>", self.event_login_clicked)

        # Only pack if it's not the specialized split-row inputs (we handle those manually)
        if parent == self.content_frame:
            entry.pack(
                pady=pack_padding, fill="x"
            )  # fill="x" is the key for dynamic width

        return entry

    def toggle_password_visibility(self):
        # Check current state
        if self.entry_password.cget("show") == "*":
            # If hidden, make visible
            self.entry_password.configure(show="")
            self.btn_show_pass.configure(text="Hide")
        else:
            # If visible, hide it
            self.entry_password.configure(show="*")
            self.btn_show_pass.configure(text="Show")

    def event_login_clicked(self, event=None):
        email = self.entry_email.get().strip()
        password = self.entry_password.get().strip()
        org = self.entry_org.get().strip()
        shard = self.entry_shard.get().strip()

        if not email or not password or not org or not shard:
            self.error_label.configure(text="Please fill in all fields")
            return

        email_pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(email_pattern, email):
            self.error_label.configure(text="Invalid email format")
            return

        self.error_label.configure(text="Logging in...", text_color="white")
        self.update_idletasks()

        try:
            # Initialize the shared client in the controller
            self.controller.client = VerkadaInternalAPIClient(
                email=email, password=password, org_short_name=org, shard=shard
            )

            # Attempt Login
            self.controller.client.login()

            # If successful (and no error raised), go to Main App
            print("Login Successful!")
            self.controller.setup_main_interface()

        except MFARequiredError as e:
            # Backend says 2FA is needed -> Go to 2FA Screen
            print(f"MFA Required: {e}")
            self.controller.show_2fa_screen()

        except Exception as e:
            # Login Failed (Wrong password, network error, etc.)
            self.error_label.configure(text=f"Error: {str(e)}", text_color="#FF5555")
            # Clear the client so we can try again clean
            self.controller.client = None

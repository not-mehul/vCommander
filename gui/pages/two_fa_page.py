import customtkinter as ctk


class TwoFAPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # 1. Background Setup
        self.configure(fg_color="transparent")
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        # 2. The Card
        self.card = ctk.CTkFrame(
            self,
            corner_radius=15,
            border_width=2,
            border_color="#333333",
            fg_color="#1c1c1c",
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.3)

        # 3. Content Inside
        self.content_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=40, pady=40)

        # Title
        self.title_label = ctk.CTkLabel(
            self.content_frame,
            text="Verification",
            font=("Verdana", 28, "bold"),
            text_color="#A0A0A0",
        )
        self.title_label.pack(pady=(10, 10))

        # Instructions
        self.instr_label = ctk.CTkLabel(
            self.content_frame,
            text="Enter the 6-digit code sent to your email",
            font=("Verdana", 12),
            text_color="gray",
        )
        self.instr_label.pack(pady=(0, 30))

        # --- VALIDATION LOGIC ---
        # We register a function that returns True (allow) or False (reject)
        vcmd = (self.register(self.validate_input), "%P")

        # 2FA Input
        self.entry_code = ctk.CTkEntry(
            self.content_frame,
            placeholder_text="000000",
            height=50,
            justify="center",
            font=("Verdana", 24, "bold"),
            fg_color="#2b2b2b",
            border_color="#444444",
            text_color="white",
            placeholder_text_color="#888888",
            # Hook up the validator
            validate="key",
            validatecommand=vcmd,
        )
        self.entry_code.pack(fill="x", pady=10)
        self.entry_code.bind("<Return>", self.event_verify_clicked)

        # Error Label
        self.error_label = ctk.CTkLabel(
            self.content_frame, text="", text_color="#FF5555", font=("Verdana", 12)
        )
        self.error_label.pack(pady=(10, 0))

        # Verify Button
        self.btn_verify = ctk.CTkButton(
            self.content_frame,
            text="Verify",
            font=("Verdana", 16, "bold"),
            height=45,
            fg_color="#666666",
            hover_color="#555555",
            corner_radius=8,
            command=self.event_verify_clicked,
        )
        self.btn_verify.pack(pady=(20, 10), fill="x")

    def validate_input(self, new_value):
        """
        Checks every keystroke.
        Returns True if the change is allowed, False if rejected.
        """
        # 1. Allow deletion (empty string is okay)
        if new_value == "":
            return True

        # 2. Check Length (Must be <= 6)
        if len(new_value) > 6:
            return False

        # 3. Check Content (Must be digits only)
        if not new_value.isdigit():
            return False

        return True

    def event_verify_clicked(self, event=None):
        code = self.entry_code.get().strip()

        # Final check (e.g. they typed 3 digits and hit enter)
        if len(code) != 6:
            self.error_label.configure(text="⚠ Code must be exactly 6 digits.")
            return

        self.error_label.configure(text="Verifying...", text_color="white")
        self.update_idletasks()

        try:
            # Use the SHARED client from main.py
            if not self.controller.client:
                raise ValueError("Session lost. Please restart.")

            # Call the verify function
            self.controller.client.verify_mfa(code)

            # If we get here, it worked!
            print("2FA Success!")
            self.controller.setup_main_interface()

        except Exception as e:
            self.error_label.configure(text=f"⚠ {str(e)}", text_color="#FF5555")

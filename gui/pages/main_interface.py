import sys
from datetime import datetime

import customtkinter as ctk
from tools.add_user import AddUserTool


class MainInterfacePage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # 1. Setup Grid Layout (1 Row, 2 Columns)
        # relwidth/relheight ensures the frame fills the window
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)

        self.grid_columnconfigure(0, weight=0)  # Sidebar (fixed width)
        self.grid_columnconfigure(1, weight=1)  # Main Content (expands)
        self.grid_rowconfigure(0, weight=1)  # Full height
        self.current_tool = None

        # --- LEFT SIDEBAR ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")

        # KEY CHANGE: Give weight to Row 5 (The Console Box Row)
        # This forces the console box to stretch and fill all remaining vertical space.
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        # Logo / Title
        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="vConduit", font=("Verdana", 24, "bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Navigation Buttons
        self.btn_commission = self.create_nav_button("Commission", self.show_commission)
        self.btn_commission.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.btn_users = self.create_nav_button("Users", self.show_users)
        self.btn_users.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.btn_decommission = self.create_nav_button(
            "Decommission", self.show_decommission
        )
        self.btn_decommission.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        # --- CONSOLE OUTPUT (Bottom Left) ---
        # Label (Row 4) - Fixed height
        self.console_label = ctk.CTkLabel(
            self.sidebar_frame, text="Console:", font=("Verdana", 10)
        )
        self.console_label.grid(row=4, column=0, padx=20, pady=(20, 0), sticky="w")

        # Text Box (Row 5) - Expands
        self.console_box = ctk.CTkTextbox(
            self.sidebar_frame,
            font=("Consolas", 10),
            wrap="word",  # Ensures text wraps to next line instead of horizontal scrolling
            activate_scrollbars=True,  # Explicitly ensures scrollbar is active
        )
        self.console_box.grid(row=5, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.console_box.configure(state="disabled")  # Read-only for user

        # Redirect print statements to this box
        sys.stdout = RedirectText(self.console_box)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] System Ready.")

        # --- RIGHT MAIN AREA ---
        self.main_area = ctk.CTkFrame(self, corner_radius=10)
        self.main_area.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")

        # Show default tool
        self.show_commission()

    def create_nav_button(self, text, command, is_danger=False):
        color = "transparent" if is_danger else None
        hover = "#333333" if is_danger else None
        border = 2 if is_danger else 0

        return ctk.CTkButton(
            self.sidebar_frame,
            text=text,
            command=command,
            font=("Verdana", 14),
            fg_color=color,
            hover_color=hover,
            border_width=border,
            border_color="#DCE4EE" if is_danger else None,
            anchor="w",  # Align text left
            height=40,
        )

    def switch_tool_frame(self, tool_class_name):
        """Destroys current tool and loads new one"""
        # 1. Clear current frame
        for widget in self.main_area.winfo_children():
            widget.destroy()

        # 2. Load new tool (We will implement the actual classes next)
        # For now, just a label placeholder
        label = ctk.CTkLabel(
            self.main_area, text=f"{tool_class_name} Placeholder", font=("Arial", 24)
        )
        label.place(relx=0.5, rely=0.5, anchor="center")

    def show_commission(self):
        if self.current_tool != "Commission":
            self.current_tool = "Commission"
            self.switch_tool_frame("Commission Tool")
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Switched to Commission Tool"
            )

    def show_users(self):
        if self.current_tool != "Users":
            self.current_tool = "Users"
            self.switch_tool_frame("User Tool")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Switched to User Tool")
            # 1. Clear main area
            for widget in self.main_area.winfo_children():
                widget.destroy()

            # 2. Load the tool
            tool = AddUserTool(parent=self.main_area, controller=self.controller)
            tool.pack(fill="both", expand=True)

    def show_decommission(self):
        if self.current_tool != "Decommission":
            self.current_tool = "Decommission"
            self.switch_tool_frame("Decommission Tool")
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Switched to Decommission Tool"
            )


class RedirectText(object):
    """Helper class to redirect print() to a text widget"""

    def __init__(self, text_widget):
        self.output = text_widget

    def write(self, string):
        self.output.configure(state="normal")
        self.output.insert("end", string)
        self.output.see("end")  # Auto-scroll to bottom
        self.output.configure(state="disabled")

    def flush(self):
        pass

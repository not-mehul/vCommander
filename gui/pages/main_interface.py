import logging

import customtkinter as ctk
from tools.add_user import AddUserTool
from tools.decommission import DecommissionTool

# Constants
SIDEBAR_WIDTH = 250
CONSOLE_FONT = ("Consolas", 10)
NAV_BUTTON_FONT = ("Verdana", 14)
TIMESTAMP_FORMAT = "%H:%M:%S"

logger = logging.getLogger(__name__)


class MainInterfacePage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.current_tool = None

        self._setup_layout()
        self._create_sidebar()
        self._create_main_area()

        # Configure logging to show INFO level and above in the console textbox
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        handler = TextboxLogHandler(self.console_box)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(message)s", datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        self.show_commission()

    def _setup_layout(self):
        self.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)
        self.grid_columnconfigure(0, weight=0, minsize=SIDEBAR_WIDTH)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _create_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)

        self.sidebar_frame.grid_columnconfigure(0, weight=1)
        self.sidebar_frame.grid_rowconfigure(5, weight=1)

        self.logo_label = ctk.CTkLabel(
            self.sidebar_frame, text="vCommander", font=("Verdana", 24, "bold")
        )
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.btn_commission = self._create_nav_button(
            "Commission", self.show_commission
        )
        self.btn_commission.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.btn_users = self._create_nav_button("Users", self.show_users)
        self.btn_users.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        self.btn_decommission = self._create_nav_button(
            "Decommission", self.show_decommission
        )
        self.btn_decommission.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        self.console_label = ctk.CTkLabel(
            self.sidebar_frame, text="Console:", font=("Verdana", 10)
        )
        self.console_label.grid(row=4, column=0, padx=20, pady=(20, 0), sticky="w")
        self.console_box = ctk.CTkTextbox(
            self.sidebar_frame,
            font=CONSOLE_FONT,
            wrap="word",
            activate_scrollbars=True,
            state="disabled",
        )
        self.console_box.grid(row=5, column=0, padx=10, pady=(5, 10), sticky="nsew")

    def _create_main_area(self):
        self.main_area = ctk.CTkFrame(self, corner_radius=10)
        self.main_area.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_rowconfigure(0, weight=1)

    def _create_nav_button(self, text, command):
        return ctk.CTkButton(
            self.sidebar_frame,
            text=text,
            command=command,
            font=NAV_BUTTON_FONT,
            border_width=0,
            anchor="w",
            height=40,
        )

        # Show default tool
        self.show_commission()

    def _switch_tool(self, tool_name, tool_factory=None):
        if self.current_tool == tool_name:
            return
        self.current_tool = tool_name

        for widget in self.main_area.winfo_children():
            widget.destroy()

        if tool_factory:
            tool = tool_factory()
            tool.pack(fill="both", expand=True)
        else:
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
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", f"[{record.levelname}] {msg}\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")

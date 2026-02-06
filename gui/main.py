"""
vCommander - Main Application Entry Point

This module initializes the vCommander application, a GUI tool for managing
Verkada organization assets. It sets up the main application window and
handles navigation between different screens (login, 2FA, main interface).
"""

import sys
import customtkinter as ctk
from pages.login_page import LoginPage
from pages.main_interface import MainInterfacePage
from pages.two_fa_page import TwoFAPage

# Configure CustomTkinter appearance settings
# "System" follows the OS light/dark mode preference
ctk.set_appearance_mode("System")
# "dark-blue" is the color theme for widgets
ctk.set_default_color_theme("dark-blue")


class vCommanderApp(ctk.CTk):
    """
    Main application class for vCommander.

    This class represents the root window of the application and manages:
    - Window configuration (title, size)
    - Screen navigation (login → 2FA → main interface)
    - API client storage (shared across screens via controller)
    """

    def __init__(self):
        """
        Initialize the main application window.

        Sets up window properties and shows the initial login screen.
        """
        super().__init__()
        self.title("vCommander")
        self.geometry("1400x800")
        
        # macOS focus fix: Ensure window is properly activated
        # This helps with "click-to-focus" issues on macOS 14+
        self.after(100, self._ensure_focus)

        # Storage for the API client - shared across all screens
        # This is set after successful login and used by all tools
        self.client = None

        # Start with the login screen
        self.show_login_screen()
    
    def _ensure_focus(self):
        """
        Ensure the window has proper focus on macOS.
        
        This helps mitigate the macOS 14+ "click-to-focus" issue where
        the first click only activates the window without triggering widgets.
        """
        try:
            # Lift window to front and force focus
            self.lift()
            self.focus_force()
            # On macOS, also ensure we're the frontmost application
            if sys.platform == 'darwin':
                import os
                os.system('''/usr/bin/osascript -e 'tell app "Finder" to set frontmost of process "Python" to true' 2>/dev/null || true''')
        except Exception:
            pass  # Ignore any errors from focus management

    def clear_screen(self):
        """
        Remove all widgets from the window.

        This is called when switching between screens to ensure
        only one screen's widgets are visible at a time.
        """
        for widget in self.winfo_children():
            widget.destroy()

    def show_login_screen(self):
        """
        Display the login screen.

        Clears the current screen and creates a new LoginPage instance.
        This is the entry point for new users.
        """
        self.clear_screen()
        self.login_page = LoginPage(parent=self, controller=self)

    def show_2fa_screen(self):
        """
        Display the 2FA/MFA verification screen.

        Called when login requires two-factor authentication.
        The user must enter the OTP code sent to their device.
        """
        self.clear_screen()
        self.two_fa_page = TwoFAPage(parent=self, controller=self)

    def setup_main_interface(self):
        """
        Display the main application interface.

        Called after successful authentication. This is the primary
        workspace where users can access all tools (Commission, Users, Decommission).
        """
        self.clear_screen()
        self.main_interface = MainInterfacePage(parent=self, controller=self)


if __name__ == "__main__":
    # Application entry point
    # Creates the app instance and starts the Tkinter main event loop
    app = vCommanderApp()
    app.mainloop()

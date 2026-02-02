import customtkinter as ctk
from pages.login_page import LoginPage
from pages.main_interface import MainInterfacePage
from pages.two_fa_page import TwoFAPage

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("dark-blue")


class vConduitApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("vConduit")
        self.geometry("1400x800")

        self.client = None
        self.show_login_screen()
        # self.setup_main_interface()

    def clear_screen(self):
        for widget in self.winfo_children():
            widget.destroy()

    def show_login_screen(self):
        self.clear_screen()
        self.login_page = LoginPage(parent=self, controller=self)

    def show_2fa_screen(self):
        self.clear_screen()
        self.two_fa_page = TwoFAPage(parent=self, controller=self)

    def setup_main_interface(self):
        self.clear_screen()
        self.main_interface = MainInterfacePage(parent=self, controller=self)


if __name__ == "__main__":
    app = vConduitApp()
    app.mainloop()

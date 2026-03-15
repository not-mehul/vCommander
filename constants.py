import flet as ft

# --- Identity ---
APP_NAME = "vCommander"
APP_VERSION = "2.0"
APP_TAGLINE = "VCE Command Automation Tool"

# --- Pastel Color Palette (Modern/Minimalistic) ---
# Primary: Soft Lavender
PRIMARY_COLOR = "#A78BFA"
# Secondary: Muted Sage
SECONDARY_COLOR = "#A7F3D0"
# Background: Very Light Neutral Grey/Off-White
BG_COLOR = "#F8FAFC"
# Surface: Pure White
SURFACE_COLOR = "#FFFFFF"
# Success: Soft Mint
SUCCESS_COLOR = "#34D399"
# Error: Soft Rose
ERROR_COLOR = "#FB7185"
# Text: Deep Charcoal for readability
TEXT_COLOR = "#1E293B"
# Muted Text: Soft Blue-Grey
MUTED_TEXT_COLOR = "#64748B"

# --- Theme ---
APP_THEME = ft.Theme(
    color_scheme=ft.ColorScheme(
        primary=PRIMARY_COLOR,
        secondary=SECONDARY_COLOR,
        surface=SURFACE_COLOR,
        error=ERROR_COLOR,
        on_primary=SURFACE_COLOR,
        on_secondary=TEXT_COLOR,
        on_surface=TEXT_COLOR,
        # For Material 3, surface usually covers the background role.
    ),
    font_family="Poppins",
)

# --- UI and Window ---
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700

PADDING = 32  # Increased for a more airy, minimal feel
BORDER_RADIUS = 16  # Rounded corners for a softer look
ELEVATION = 0  # Minimalistic look often avoids heavy shadows

# --- Data ---
KITS_CSV_PATH = "assets/kits.csv"

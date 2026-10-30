"""Design system for vCommander.

This module is the single source of truth for the app's visual language:
spacing, radii, type scale, elevation, and a *semantic* color palette that
is deliberately decoupled from the three per-tool brand colors.

Why semantic tokens?
--------------------
The original palette overloaded meaning: the same green meant both
"success" and "the Users tool", and red meant both "danger" and "the
Decommission tool". Here, state colors (`success`, `warning`, `danger`,
`info`) are independent of brand colors (`brand_commission`,
`brand_users`, `brand_decommission`). A success banner is always green
regardless of which tool you're in; a tool's accent is only ever used as
a small icon/tag tint.

Light + dark
------------
Both a `DARK` and a `LIGHT` palette are defined. The module exposes the
active palette as `palette` and mirrors its fields as flat module-level
names (BG, SURFACE, …) so call sites can `from theme import BG`. Call
`set_theme_mode("light")` / `set_theme_mode("dark")` to switch; it rebinds
those flat names in place. The runtime toggle UI (header button + Cmd-K
command in `app_shell`/`main`) drives this at runtime.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import flet as ft

# ----------------------------------------------------------------------
# Spacing — a 4px base scale. Prefer these over magic spacer heights so
# vertical/horizontal rhythm stays consistent across screens.
# ----------------------------------------------------------------------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_2XL = 32


# ----------------------------------------------------------------------
# Radius — standardize on one component radius (RADIUS_MD). The codebase
# previously mixed 8 and 12; everything should round to RADIUS_MD now.
# ----------------------------------------------------------------------
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_PILL = 999

# ----------------------------------------------------------------------
# Type scale — one ladder of sizes used app-wide instead of ad-hoc values.
# Weights are mirrored here so call sites import a single vocabulary.
# ----------------------------------------------------------------------
FONT_DISPLAY = 28
FONT_TITLE = 22
FONT_HEADING = 18
FONT_BODY = 14
FONT_CAPTION = 12
FONT_MICRO = 11

WEIGHT_REGULAR = ft.FontWeight.W_400
WEIGHT_MEDIUM = ft.FontWeight.W_500
WEIGHT_SEMIBOLD = ft.FontWeight.W_600
WEIGHT_BOLD = ft.FontWeight.BOLD

# Monospace family for serials / raw logs. None falls back to the platform
# default monospace; kept as a token so it's swappable in one place.
FONT_MONO = "monospace"


# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Palette:
    """A complete set of semantic color tokens for one theme mode."""

    mode: str  # "dark" | "light"

    # Surfaces
    bg: str            # app background
    surface: str       # card / panel background
    surface_variant: str  # insets, input fields, menus, hover fills
    border: str        # default 1px separators / outlines
    border_subtle: str  # very low-contrast dividers

    # Text
    text_primary: str
    text_secondary: str
    text_muted: str

    # Interactive accent (links, focus rings, primary buttons)
    accent: str
    accent_hover: str
    on_accent: str     # text/icon color on top of `accent`

    # Semantic state (independent of brand)
    success: str
    warning: str
    danger: str
    info: str

    # Per-tool brand tints — used ONLY as small icon/tag accents, never as
    # the dominant surface color.
    brand_commission: str
    brand_users: str
    brand_decommission: str

    # Shadow base color (used by elevation()).
    shadow: str

    # --- derived helpers -------------------------------------------------
    def tint(self, color: str, opacity: float = 0.14) -> str:
        """A translucent version of `color` for banner/tile backgrounds."""
        return ft.Colors.with_opacity(opacity, color)


# Dark palette — preserves the original brand hues (#7eb8da blue,
# #8fd4b0 green, #f0b87e amber, #e8827a red) but reassigns them to
# semantic roles. accent == the blue; success == the green; etc.
DARK = Palette(
    mode="dark",
    bg="#1a1a1a",
    surface="#2a2a2a",
    surface_variant="#323232",
    border="#3a3a3a",
    border_subtle="#2f2f2f",
    text_primary="#e0e0e0",
    text_secondary="#b8b8b8",
    text_muted="#8a8a8a",
    accent="#7eb8da",
    accent_hover="#93c6e4",
    on_accent="#10222e",
    success="#8fd4b0",
    warning="#f0b87e",
    danger="#e8827a",
    info="#7eb8da",
    brand_commission="#7eb8da",
    brand_users="#8fd4b0",
    brand_decommission="#e8827a",
    shadow="#000000",
)

# Light palette — designed to mirror the dark one. Accent/state colors are
# darkened for AA contrast against light surfaces (text-on-color usage).
LIGHT = Palette(
    mode="light",
    bg="#f4f5f7",
    surface="#ffffff",
    surface_variant="#eef0f3",
    border="#d8dbe0",
    border_subtle="#e7e9ed",
    text_primary="#1b1e23",
    text_secondary="#565d66",
    text_muted="#868d96",
    accent="#2f7cad",
    accent_hover="#286992",
    on_accent="#ffffff",
    success="#2e8b57",
    warning="#b9772a",
    danger="#c0392b",
    info="#2f7cad",
    brand_commission="#2f7cad",
    brand_users="#2e8b57",
    brand_decommission="#c0392b",
    shadow="#1b1e23",
)

_PALETTES = {"dark": DARK, "light": LIGHT}

# The active palette. Defaults to dark to match the app's current look.
palette: Palette = DARK


# ----------------------------------------------------------------------
# Elevation — three shadow levels derived from the active palette so they
# read correctly on both light and dark surfaces.
# ----------------------------------------------------------------------
def elevation(level: int = 1) -> ft.BoxShadow:
    """Return a BoxShadow for elevation `level` (1=card, 2=raised, 3=overlay)."""
    specs = {
        1: (12, 0.30, ft.Offset(0, 4)),
        2: (20, 0.35, ft.Offset(0, 6)),
        3: (28, 0.45, ft.Offset(0, 10)),
    }
    blur, opacity, offset = specs.get(level, specs[1])
    # Light mode shadows are subtler.
    if palette.mode == "light":
        opacity *= 0.5
    return ft.BoxShadow(
        spread_radius=0,
        blur_radius=blur,
        color=ft.Colors.with_opacity(opacity, palette.shadow),
        offset=offset,
    )


def set_theme_mode(mode: str) -> None:
    """Switch the active palette and rebind the flat module-level names.

    `mode` is "dark" or "light". Views that imported the flat names by
    reference (e.g. `from theme import BG`) won't see the rebind, so the
    app re-reads `theme.palette` / the flat names on (re)mount, driven by the
    header toggle button and the Cmd-K "Toggle light / dark theme" command.
    """
    global palette
    palette = _PALETTES.get(mode, DARK)
    _bind_flat_names()


def flat_tokens() -> dict:
    """The active palette as a flat {NAME: value} map.

    Includes the semantic names plus the legacy aliases (PRIMARY/SECONDARY/
    ERROR) and the common CARD_SHADOW, so callers that imported any of these
    can be re-pointed at the current palette on a theme switch.
    """
    p = palette
    return {
        "BG": p.bg,
        "SURFACE": p.surface,
        "SURFACE_VARIANT": p.surface_variant,
        "BORDER": p.border,
        "BORDER_SUBTLE": p.border_subtle,
        "TEXT_PRIMARY": p.text_primary,
        "TEXT_SECONDARY": p.text_secondary,
        "TEXT_MUTED": p.text_muted,
        "ACCENT": p.accent,
        "ACCENT_HOVER": p.accent_hover,
        "ON_ACCENT": p.on_accent,
        "SUCCESS": p.success,
        "WARNING": p.warning,
        "DANGER": p.danger,
        "INFO": p.info,
        "BRAND_COMMISSION": p.brand_commission,
        "BRAND_USERS": p.brand_users,
        "BRAND_DECOMMISSION": p.brand_decommission,
        # Legacy aliases kept so the migration is incremental, not big-bang:
        #   PRIMARY -> accent, SECONDARY -> success, ERROR -> danger
        "PRIMARY": p.accent,
        "SECONDARY": p.success,
        "ERROR": p.danger,
        "CARD_SHADOW": elevation(1),
    }


def _bind_flat_names() -> None:
    """Mirror the active palette's fields as flat module-level constants.

    Provides backwards-compatible names (BG, SURFACE, BORDER, PRIMARY, …)
    so existing call sites keep working while views migrate to reading
    `theme.palette.*` directly.
    """
    module = sys.modules[__name__]
    for name, value in flat_tokens().items():
        setattr(module, name, value)


def apply_to(modules) -> None:
    """Re-point the flat color names that `modules` imported at the palette.

    Modules import color tokens by value (`from constants import BG`), so a
    `set_theme_mode` switch doesn't reach them. After switching, call this
    with the affected modules to rebind only the names each one actually
    imported (guarded by hasattr), then rebuild the view tree.
    """
    tokens = flat_tokens()
    for mod in modules:
        for name, value in tokens.items():
            if hasattr(mod, name):
                setattr(mod, name, value)


_bind_flat_names()

# A single shared card shadow alias for the common case (elevation 1).
CARD_SHADOW = elevation(1)

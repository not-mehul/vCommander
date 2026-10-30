"""Reusable UI building blocks for vCommander.

These wrap the styling patterns that were previously re-implemented in each
view (text fields, dropdowns, buttons, cards, banners). Every component
reads its colors/spacing/radius from `theme`, so a token change or a theme
switch propagates everywhere instead of being copy-pasted per screen.

Import from the package root:

    from components import primary_button, text_field, card, section_header
"""

from components.buttons import (
    danger_button,
    ghost_button,
    primary_button,
    secondary_button,
    set_button_loading,
)
from components.command_palette import CommandPalette
from components.inputs import dropdown, text_field
from components.progress import (
    ProgressHeader,
    RawLogPanel,
    StepRow,
    run_step,
    status_row,
)
from components.stepper import Stepper
from components.surfaces import (
    banner,
    card,
    scroll_area,
    section_header,
    stat_row,
)

__all__ = [
    "CommandPalette",
    "ProgressHeader",
    "RawLogPanel",
    "StepRow",
    "Stepper",
    "banner",
    "card",
    "danger_button",
    "dropdown",
    "ghost_button",
    "primary_button",
    "run_step",
    "scroll_area",
    "secondary_button",
    "section_header",
    "set_button_loading",
    "stat_row",
    "status_row",
    "text_field",
]

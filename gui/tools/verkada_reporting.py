# Verkada Reporting
# This module handles the console output and file saving for the inventory report for ProjectDecommission.
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Import our app_path helper to locate save directory relative to executable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_path import get_default_save_dir

# Initialize logger for this module
logger = logging.getLogger(__name__)


def generate_report(
    org_name: str,
    inventory: Dict[str, List[Dict[str, Any]]],
    save_to_file: bool = False,
    file_path: str = "",
):
    """
    Generates a detailed, formatted inventory report.

    This function creates a comprehensive text report of all assets in the inventory.
    The report includes a summary breakdown by category and detailed listings with
    IDs and names for each asset. Output is always printed to console, and optionally
    saved to a file.

    Output:
    - Always prints the report to the console (stdout).
    - If save_to_file is True and file_path is None, saves the output to a text file
      named '{org_name}_report_{timestamp}.txt' in the current directory.
    - If file_path is provided, saves to that specific path.

    Args:
        org_name: Name of the organization (used for header and filename).
        inventory: The dictionary containing lists of assets/users keyed by category.
        save_to_file: Boolean flag to enable file logging.
        file_path: Optional specific file path to save the report to.
    """
    # Create timestamps for display (readable) and filename (safe characters)
    # Display format: "2024-01-15 14:30:00" - human readable
    # File format: "2024-01-15_143000" - safe for filenames (no spaces or colons)
    timestamp_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_file = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Initialize file handling variables
    file_handle = None
    output_filename = ""

    # 1. Setup File Logging if requested
    # If save_to_file is True OR a file_path is provided, open a file for writing
    if save_to_file or file_path:
        # Use provided path, or generate a default filename in the app directory
        if file_path:
            output_filename = file_path
        else:
            # Save to the application directory (where the executable is located)
            save_dir = get_default_save_dir()
            # Sanitize org_name for filename (remove/replace invalid chars)
            safe_org_name = "".join(c for c in org_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            output_filename = os.path.join(save_dir, f"{safe_org_name}_report_{timestamp_file}.txt")
        
        try:
            # Open file in write mode with UTF-8 encoding to support special characters
            file_handle = open(output_filename, "w", encoding="utf-8")
        except IOError as e:
            # Log error but continue with console output
            logger.error(f"Could not open file for writing: {e}")

    # 2. Define Helper to write to both locations
    # This closure allows us to treat console and file output identically
    # Any text sent through output() will go to both console and file (if open)
    def output(text="", end="\n"):
        """Print to console and optionally write to file."""
        print(text, end=end)
        if file_handle:
            file_handle.write(str(text) + end)

    def output_sep(char="=", length=80):
        """Helper to print separator lines using a repeated character."""
        output(char * length)

    # --- REPORT GENERATION START ---

    # Print blank line for visual spacing
    output("\n")

    # Print report header with organization info
    output_sep("=")  # Top border line
    output("   Inventory Report".center(80))  # Centered title
    output(f"  Organization: {org_name}".center(80))  # Centered org name
    output(f"  Generated on: {timestamp_display}".center(80))  # Centered timestamp
    output_sep("=")  # Bottom border line
    output("\n")

    # Dashboard Summary Section
    # Prints a high-level breakdown of counts per category
    output("  Breakdown")
    output_sep("-", 40)

    # Calculate total devices across all categories
    total_devices = 0
    for category, items in inventory.items():
        count = len(items)
        total_devices += count
        # Format: Category Name (left aligned) : Count (right aligned, 5 digits)
        # Replace underscores with spaces for better readability
        output(f"  • {category.replace('_', ' '):<25} : {count:>5}")

    output_sep("-", 40)
    output(f"  • {'TOTAL ASSETS':<25} : {total_devices:>5}")
    output("\n")

    # Detailed Listings Section
    # Iterates through every category to print a detailed table of assets
    for category, items in inventory.items():
        # Convert category name to title case for display
        # e.g., "access_controllers" becomes "Access Controllers"
        title = category.replace("_", " ").title()

        output_sep("=")
        output(f"  CATEGORY: {title} ({len(items)})")
        output_sep("=")

        # Handle empty categories gracefully
        if not items:
            output("  (No items found in this category)")
            output("\n")
            continue

        # Determine column widths dynamically based on content
        # This ensures the table looks good whether names are short or long
        max_name_len = 20  # Minimum width for name column
        max_id_len = 15  # Minimum width for ID column

        # Prepare rows and calculate optimal column widths
        rows = []
        for item in items:
            obj_id = item.get("id")
            # Handle cases where ID might be a list (e.g., Alarm Sites have multiple IDs)
            if isinstance(obj_id, list):
                obj_id = ", ".join(map(str, obj_id))

            obj_id_str = str(obj_id)

            # --- NAME LOGIC ---
            # Try to find a human-readable name from various common keys
            # Priority: email > name > businessName > "(No Name)"
            base_name = (
                item.get("email")
                or item.get("name")
                or item.get("businessName")
                or "(No Name)"
            )

            # Collect extra details to append to the name (Serial, System ID)
            details = []
            if item.get("serial_number"):
                details.append(f"S/N: {item['serial_number']}")
            if item.get("alarm_system_id"):
                details.append(f"Sys ID: {item['alarm_system_id']}")

            # If we have extra details, append them in parentheses
            if details:
                name_str = f"{base_name} ({', '.join(details)})"
            else:
                name_str = base_name
            # ---------------------------

            rows.append((name_str, obj_id_str))

            # Update max widths to fit this row (capped at 80 for name)
            if len(name_str) > max_name_len:
                max_name_len = min(len(name_str), 80)
            if len(obj_id_str) > max_id_len:
                max_id_len = len(obj_id_str)

        # Create dynamic format string based on calculated widths
        # Add 2 characters of padding between columns
        col_name_w = max_name_len + 2
        col_id_w = max_id_len + 2

        # Format strings for header and data rows
        header_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        row_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        divider = f"  {'-' * col_name_w}-+-{'-' * col_id_w}"

        # Print Table Headers
        output(header_fmt.format("Name / Description", "ID"))
        output(divider)

        # Print Data Rows
        for name, obj_id in rows:
            # Truncate name if still too long (rare now with increased max_width)
            if len(name) > max_name_len:
                name = name[: max_name_len - 3] + "..."
            output(row_fmt.format(name, obj_id))

        output("\n")

    # Print report footer
    output_sep("=")
    output("  End of Report".center(80))
    output_sep("=")
    output("\n")

    # --- REPORT GENERATION END ---

    # Close file handle if it was opened
    if file_handle:
        file_handle.close()
        logger.info(f"Report saved to disk: {output_filename}")
        print(f" >> File successfully saved: {output_filename}")

    logger.info("Report printing complete.")


def print_inventory_details(inventory):
    """
    Helper function to print raw details based on device/object type.

    This is used for debugging or detailed verification before deletion.
    Unlike generate_report, this prints a simplified format focused on
    key identifiers for each device type.

    Args:
        inventory: Dictionary containing lists of devices keyed by category.
    """
    # Define formatting rules (lambdas) for different categories
    # Each lambda takes an item dict and returns a formatted string
    format_rules = {
        "Intercoms": lambda x: (
            f"Intercom ID: {x['id']}, Serial Number: {x['serial_number']}"
        ),
        "Sensors": lambda x: (
            f"Sensor ID: {x['id']}, Serial Number: {x['serial_number']}"
        ),
        "Access Controllers": lambda x: (
            f"Access Controller ID: {x['id']}, Serial Number: {x['serial_number']}"
        ),
        "Cameras": lambda x: (
            f"Camera ID: {x['id']}, Serial Number: {x['serial_number']}"
        ),
        "Unassigned Devices": lambda x: (
            f"Unassigned Device ID: {x['id']}, Serial Number: {x.get('name', 'N/A')}"
        ),
        "Guest Sites": lambda x: f"Guest Site ID: {x['id']}, Name: {x['name']}",
        "Mailroom Sites": lambda x: f"Mailroom Site ID: {x['id']}, Name: {x['name']}",
        "Desk Stations": lambda x: f"Desk Station ID: {x['id']}, Name: {x['name']}",
        "Alarm Devices": lambda x: f"Alarm Device ID: {x['id']}, Name: {x['name']}",
        "Users": lambda x: f"User ID: {x['id']}, Email: {x['email']}",
        "Alarm Sites": lambda x: (
            f"Alarm Site:\n\tSite ID: {x['site_id']}\n\t"
            f"Alarm Site ID: {x['alarm_site_id']}\n\t"
            f"Name: {x['name']}\n\t"
            f"Alarm System ID: {x['alarm_system_id']}"
        ),
    }

    # Iterate through each category in the inventory
    for category, items in inventory.items():
        # Only print categories that have items
        if items:
            print(f"\n--- {category} ---")
            # Get the specific formatter for this category, or default to str()
            formatter = format_rules.get(category, lambda x: str(x))
            # Print each item using the category-specific formatter
            for item in items:
                print(formatter(item))

# Verkada Reporting
# This module handles the console output and file saving for the inventory report for ProjectDecommission.
import logging
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def generate_report(
    org_name: str,
    inventory: Dict[str, List[Dict[str, Any]]],
    save_to_file: bool = False,
):
    """
    Generates a detailed inventory report.
    Always prints to console.
    If save_to_file is True, also saves to '{org_name}_report_{timestamp}.txt'.
    """
    timestamp_display = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_file = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    file_handle = None
    output_filename = ""

    # 1. Setup File Logging if requested
    if save_to_file:
        output_filename = f"{org_name}_report_{timestamp_file}.txt"
        try:
            file_handle = open(output_filename, "w", encoding="utf-8")
        except IOError as e:
            logger.error(f"Could not open file for writing: {e}")

    # 2. Define Helper to write to both locations
    def output(text="", end="\n"):
        print(text, end=end)
        if file_handle:
            file_handle.write(str(text) + end)

    def output_sep(char="=", length=80):
        output(char * length)

    # --- REPORT GENERATION START ---

    output("\n")
    output_sep("=")
    output("   Inventory Report".center(80))
    output(f"  Organization: {org_name}".center(80))
    output(f"  Generated on: {timestamp_display}".center(80))
    output_sep("=")
    output("\n")

    # Dashboard Summary
    output("  Breakdown")
    output_sep("-", 40)

    total_devices = 0
    for category, items in inventory.items():
        count = len(items)
        total_devices += count
        output(f"  • {category.replace('_', ' '):<25} : {count:>5}")

    output_sep("-", 40)
    output(f"  • {'TOTAL ASSETS':<25} : {total_devices:>5}")
    output("\n")

    # Detailed Listings
    for category, items in inventory.items():
        title = category.replace("_", " ").title()

        output_sep("=")
        output(f"  CATEGORY: {title} ({len(items)})")
        output_sep("=")

        if not items:
            output("  (No items found in this category)")
            output("\n")
            continue

        # Determine column widths dynamically
        max_name_len = 20
        max_id_len = 15

        rows = []
        for item in items:
            obj_id = item.get("id")
            if isinstance(obj_id, list):
                obj_id = ", ".join(map(str, obj_id))

            obj_id_str = str(obj_id)

            # --- UPDATED NAME LOGIC ---
            base_name = (
                item.get("email")
                or item.get("name")
                or item.get("businessName")
                or "(No Name)"
            )

            # Collect extra details to append to the name
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

            if len(name_str) > max_name_len:
                max_name_len = min(
                    len(name_str), 80
                )  # Increased max width for readability
            if len(obj_id_str) > max_id_len:
                max_id_len = len(obj_id_str)

        # Create format string
        col_name_w = max_name_len + 2
        col_id_w = max_id_len + 2

        header_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        row_fmt = f"  {{:<{col_name_w}}} | {{:<{col_id_w}}}"
        divider = f"  {'-' * col_name_w}-+-{'-' * col_id_w}"

        # Print Table
        output(header_fmt.format("Name / Description", "ID"))
        output(divider)

        for name, obj_id in rows:
            # Truncate if still too long (rare now with increased max_width)
            if len(name) > max_name_len:
                name = name[: max_name_len - 3] + "..."
            output(row_fmt.format(name, obj_id))

        output("\n")

    output_sep("=")
    output("  End of Report".center(80))
    output_sep("=")
    output("\n")

    # --- REPORT GENERATION END ---

    if file_handle:
        file_handle.close()
        logger.info(f"Report saved to disk: {output_filename}")
        print(f" >> File successfully saved: {output_filename}")

    logger.info("Report printing complete.")


def print_inventory_details(inventory):
    """
    Helper function to print details based on device/object type.
    """
    # Define formatting rules for different categories
    format_rules = {
        "Intercoms": lambda x: f"Intercom ID: {x['id']}, Serial Number: {x['serial_number']}",
        "Sensors": lambda x: f"Sensor ID: {x['id']}, Serial Number: {x['serial_number']}",
        "Access Controllers": lambda x: f"Access Controller ID: {x['id']}, Serial Number: {x['serial_number']}",
        "Cameras": lambda x: f"Camera ID: {x['id']}, Serial Number: {x['serial_number']}",
        "Unassigned Devices": lambda x: f"Unassigned Device ID: {x['id']}, Serial Number: {x.get('name', 'N/A')}",
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

    for category, items in inventory.items():
        if items:
            print(f"\n--- {category} ---")
            formatter = format_rules.get(category, lambda x: str(x))
            for item in items:
                print(formatter(item))

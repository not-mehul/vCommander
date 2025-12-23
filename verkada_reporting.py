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
        # User confirmed org_name is safe (contains only safe chars like '-'), so we use it directly.
        output_filename = f"{org_name}_report_{timestamp_file}.txt"
        try:
            file_handle = open(output_filename, "w", encoding="utf-8")
        except IOError as e:
            logger.error(f"Could not open file for writing: {e}")

    # 2. Define Helper to write to both locations
    def output(text="", end="\n"):
        """Internal helper to print to console and optionally write to file."""
        print(text, end=end)
        if file_handle:
            file_handle.write(str(text) + end)

    # 3. Define Helper for separators (using the new output function)
    def output_sep(char="=", length=80):
        output(char * length)

    # --- REPORT GENERATION START ---

    # Header
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
            name_str = (
                item.get("email")
                or item.get("name")
                or item.get("businessName")
                or "(No Name)"
            )

            rows.append((name_str, obj_id_str))

            if len(name_str) > max_name_len:
                max_name_len = min(len(name_str), 60)
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
            if len(name) > max_name_len:
                name = name[: max_name_len - 3] + "..."
            output(row_fmt.format(name, obj_id))

        output("\n")

    output_sep("=")
    output("  End of Report".center(80))
    output_sep("=")
    output("\n")

    # --- REPORT GENERATION END ---

    # 4. Cleanup
    if file_handle:
        file_handle.close()
        logger.info(f"Report saved to disk: {output_filename}")
        print(f" >> File successfully saved: {output_filename}")  # Console feedback

    logger.info("Report printing complete.")


# Example Usage:
# Note: set save_to_file=True to actually generate the .txt file
generate_report(
    "Verkada-Sample-Report",
    {"cameras": [{"id": "123", "name": "Camera 1"}, {"id": "456", "name": "Camera 2"}]},
    save_to_file=True,
)

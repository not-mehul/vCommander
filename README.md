# ProjectDecommission 
Project Decommission is a specialized automation tool designed to inventory and decommission assets within a Verkada organization. It utilizes a hybrid approach, leveraging both Verkada's public API and internal private endpoints to ensure comprehensive coverage of all device types and configurations.

## ⚠️ Critical Warning
**This tool is destructive**. It is designed to **delete** users, devices, sites, and configurations. Once the deletion process begins, it cannot be undone. Always review the generated inventory report carefully before confirming the deletion prompt.

## Key Features

- **Hybrid API Architecture:** Combines an **Internal Client** (mimicking browser behavior) with an **External Client** (Standard Public API) to perform actions not currently possible via public endpoints alone.
- **Dynamic Authentication:** 
  - Handles standard Email/Password login.
  - Supports interactive **Multi-Factor Authentication (MFA/2FA)**.
  - Automatically generates temporary, short-lived Public API keys to ensure secure access without manual dashboard configuration.
- **Smart Inventory Management:**
  - **Deduplication:** Automatically identifies and filters embedded devices (e.g., cameras inside Intercoms) to prevent double-counting or error-prone double-deletion attempts.
  - **Detailed Reporting:** Generates a human-readable ASCII table report to the console and saves a timestamped `.txt` file for audit records.
- **Ordered Decommissioning:** Executes deletion in a strict dependency order (e.g., removing Alarm Systems before Alarm Sites) to prevent API errors.

## Supported Assets

The tool currently supports the inventory and decommissioning of:

- Cameras
- Access Controllers
- Environmental Sensors
- Intercoms
- Desk Stations
- Mailroom Sites
- Guest Sites
- Alarm Sites
- Alarm Devices
- Users (Admins/Members)
- Unassigned Devices

## Prerequisites

- **Python 3.10+**
- **Network Access:** The machine running this script must have access to `*.command.verkada.com` and `api.verkada.com`.

**Dependencies**

The project relies primarily on the `requests` library.

``` pip install requests```

## Configuration

The application is configured entirely via Environment Variables to ensure security. You must set the following variables before running the script:

| Variable         | Required | Description                                                  | Default |
| ---------------- | -------- | ------------------------------------------------------------ | ------- |
| `ADMIN_EMAIL`    | ✅        | The email address of the Organization Admin.                 | -       |
| `ADMIN_PASSWORD` | ✅        | The password for the Admin account.                          | -       |
| `ORG_SHORT_NAME` | ✅        | The short name/subdomain of your organization (e.g., if URL is `myorg.command.verkada.com`, use `myorg`). | -       |
| `SHARD`          | ❌        | The backend shard for your org (check network traffic or support if unknown). | `prod1` |
| `REGION`         | ❌        | The API region.                                              | `api`   |

## Usage

1. **Set Environment Variables** (example for Linux/Mac):

```
export ADMIN_EMAIL="admin@example.com"
export ADMIN_PASSWORD="SuperSecretPassword"
export ORG_SHORT_NAME="my-org-name"
```

2. **Run the Script:**

```
python verkada_decommission.py
```

3. **Authentication:**

- The script will attempt to log in.

- If 2FA is enabled, you will be prompted in the console to enter your SMS/Authenticator code:

```
Enter 2FA code: 123456
```

4. **Review Report:**

- The script will fetch all assets and display a summary table.

- A file named  `{org_name}_report_{timestamp}.txt` will be created.

5. **Confirm Decommissioning:**

- You will be presented with a final warning:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
WARNING: This action cannot be undone.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Delete ALL assets? (y/n):
```

- Type `y`  to proceed with permanent deletion.

## Architecture Overview

The solution is split into four modular files:

1. `verkada_decommission.py` **(Entry Point)**

Orchestrates the entire flow. It initializes clients, triggers the inventory scan, generates the report, and calls the bulk deletion utility.

2. `verkada_api_clients.py` **(Core Logic)**

Contains two distinct classes:

- `VerkadaInternalAPIClient:` Uses `requests.Session` to maintain cookies and CSRF tokens. It handles the "undocumented" internal API calls used by the Command dashboard.

- `VerkadaExternalAPIClient:` Uses a standard API Key (generated dynamically by the Internal Client) to communicate with the public `api.verkada.com` endpoints. Includes automatic retry logic for network stability.

3. `verkada_reporting.py` **(Output)**

Handles the formatting of data. It includes logic to dynamic resize ASCII columns based on the length of device names, ensuring reports are always readable regardless of data size.

4. `verkada_utilities.py` **(Helpers)**

Contains:

- `sanitize_list:` Filters lists to remove dependencies (e.g., removing an Access Controller from the deletion list if it was already identified as part of an Intercom).

- `perform_bulk_deletion:` The execution engine that iterates through asset categories in a specific order to ensure clean removal.

## Decommissioning Order

To avoid dependency errors (e.g., "Cannot delete site because devices are still assigned"), the tool deletes assets in the following specific order:

1. **Users** (Prevents interference during the process)

2. **Sensors**

3. **Intercoms**

4. **Desk Stations**

5. **Mailroom Sites**

6. **Access Controllers**

7. **Cameras**

8. **Guest Sites**

9. **Alarm Devices**

10. **Alarm Systems & Sites**

## Disclaimer

This software is an unofficial tool and is not supported by Verkada. It uses internal APIs which may change without notice. Use at your own risk. Always test in a non-production environment first.

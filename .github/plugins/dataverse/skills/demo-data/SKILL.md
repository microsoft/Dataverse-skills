---
name: dataverse-demo-data
description: Check whether demo/sample data is installed in a Dataverse environment, and load it using the built-in Dataverse sample data feature if desired.
---

# Skill: Demo Data

Check and manage the built-in Dataverse sample data (demo data) for an environment.

Dataverse ships with a set of sample accounts, contacts, opportunities, and related records. The `InstallSampleData` / `UninstallSampleData` Web API actions control this feature, and the `organization` table records whether it has been installed.

> **Confirm the target environment** before checking or loading demo data. Run `pac auth list` + `pac org who` and show the output to the user.

---

## Check Whether Demo Data Is Installed

Query the `organization` table for the `sampledataimported` flag:

```python
"""
check_demo_data.py — Report whether Dataverse sample data is installed.

Run from repo root:
    python scripts/check_demo_data.py
"""
import sys, os, requests

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env

load_env()
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
API = f"{DATAVERSE_URL}/api/data/v9.2"


def main():
    print("Authenticating...")
    token = get_token()

    resp = requests.get(
        f"{API}/organizations?$select=friendlyname,sampledataimported",
        headers={
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Accept": "application/json",
        },
    )
    resp.raise_for_status()
    orgs = resp.json().get("value", [])
    if not orgs:
        print("No organization found in API response.")
        print("Demo data   : Unknown (no organization record)")
        return False
    org = orgs[0]

    installed = org.get("sampledataimported", False)
    name = org.get("friendlyname", "Unknown")
    status = "INSTALLED" if installed else "NOT installed"
    print(f"\nEnvironment : {name}")
    print(f"Demo data   : {status}")
    return installed


if __name__ == "__main__":
    main()
```

```
python scripts/check_demo_data.py
```

---

## Load Demo Data

If demo data is not installed and the user wants to load it, call the `InstallSampleData` unbound action:

```python
"""
load_demo_data.py — Install Dataverse built-in sample data.

This triggers the same process as clicking "Install sample data" in the
Power Platform admin center. The import runs asynchronously; poll
check_demo_data.py to confirm completion (sampledataimported = true).

Run from repo root:
    python scripts/load_demo_data.py
"""
import sys, os, requests

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env

load_env()
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
API = f"{DATAVERSE_URL}/api/data/v9.2"


def main():
    print("Authenticating...")
    token = get_token()

    hdrs = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Check first — avoid re-importing if already installed
    resp = requests.get(
        f"{API}/organizations?$select=sampledataimported",
        headers=hdrs,
    )
    resp.raise_for_status()
    orgs = resp.json().get("value", [])
    if not orgs:
        print("No organizations found in response. Cannot check demo data status.")
        return
    if orgs[0].get("sampledataimported"):
        print("Demo data is already installed. Nothing to do.")
        return

    print("Requesting demo data installation...")
    resp = requests.post(f"{API}/InstallSampleData", headers=hdrs)
    if not resp.ok:
        print(f"ERROR {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    print("Request accepted. The import runs asynchronously.")
    print("Run 'python scripts/check_demo_data.py' to confirm completion.")
    print("Typical import time: 2–10 minutes depending on environment size.")


if __name__ == "__main__":
    main()
```

```
python scripts/load_demo_data.py
```

---

## Remove Demo Data

To remove the sample data:

```python
"""
remove_demo_data.py — Uninstall Dataverse built-in sample data.

Run from repo root:
    python scripts/remove_demo_data.py
"""
import sys, os, requests

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env

load_env()
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
API = f"{DATAVERSE_URL}/api/data/v9.2"


def main():
    print("Authenticating...")
    token = get_token()

    hdrs = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    resp = requests.get(
        f"{API}/organizations?$select=sampledataimported",
        headers=hdrs,
    )
    resp.raise_for_status()
    orgs = resp.json().get("value", [])
    if not orgs:
        print("No organization records found in response. Cannot determine demo data status.")
        return
    if not orgs[0].get("sampledataimported"):
        print("Demo data is not installed. Nothing to remove.")
        return

    print("Requesting demo data removal...")
    resp = requests.post(f"{API}/UninstallSampleData", headers=hdrs)
    if not resp.ok:
        print(f"ERROR {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    print("Request accepted. Removal runs asynchronously.")
    print("Run 'python scripts/check_demo_data.py' to confirm completion.")


if __name__ == "__main__":
    main()
```

```
python scripts/remove_demo_data.py
```

---

## Notes

- **Async operation**: `InstallSampleData` and `UninstallSampleData` return immediately. The actual import/removal runs as a background job. Poll `sampledataimported` on the `organization` record to confirm completion.
- **Idempotent check**: Both load and remove scripts check the current state before acting and exit cleanly if the operation is already in the desired state.
- **Sandbox environments**: Sample data import is supported in Sandbox and Production environments. It is not available in Developer environments provisioned without the full Dataverse service.
- **What's included**: The standard sample dataset includes accounts (Adventure Works, Coho Winery, etc.), contacts, leads, opportunities, cases, and related activity records used by Dynamics 365 Sales and Customer Service demos.
- **This is environment data, not solution data**: Sample data is not exported with `pac solution export`. It lives only in the environment and is not version-controlled.

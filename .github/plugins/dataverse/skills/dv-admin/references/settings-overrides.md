# Settings-Definition Overrides (app/plan security roles)

A small number of allowlisted toggles don't live on the `organization` entity or in `orgdborgsettings`. They're modeled as a join between two entities:

- **`settingdefinition`** — defines the setting (uniquename, datatype, defaultvalue, description). Read-only; one row per known setting; identical across environments in the same build.
- **`organizationsettings`** — holds per-org overrides. If no row exists for a given `settingdefinitionid`, the `defaultvalue` from `settingdefinition` applies.

Allowlisted uniquenames (both `datatype=2` bool, stored as string `"true"`/`"false"`):
- `PowerAppsAppLevelSecurityRolesEnabled` — Enable app level security roles for canvas apps
- `PlanShareSecurityRolesEnabled` — Enable plan level security roles for plan designer

**Read current value:**

```python
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support settingdefinition/organizationsettings entities

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
headers = {
    "Authorization": f"Bearer {get_token()}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
    "Content-Type": "application/json",
}

UNIQUENAME = "PowerAppsAppLevelSecurityRolesEnabled"   # or PlanShareSecurityRolesEnabled

q = urllib.parse.quote(f"uniquename eq '{UNIQUENAME}'")
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/settingdefinitions?$filter={q}"
    f"&$select=settingdefinitionid,uniquename,defaultvalue,datatype",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    defn = json.loads(resp.read())["value"][0]

sd_id = defn["settingdefinitionid"]
default = defn["defaultvalue"]

q2 = urllib.parse.quote(f"_settingdefinitionid_value eq '{sd_id}'")
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/organizationsettings?$filter={q2}&$select=organizationsettingid,value",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    overrides = json.loads(resp.read())["value"]

current = overrides[0]["value"] if overrides else default
print(f"{UNIQUENAME} = {current} (default = {default}, override present: {bool(overrides)})", flush=True)
```

**Write (idempotent CREATE-or-PATCH):**

```python
# Continues from Read script above — reuses UNIQUENAME, sd_id, overrides, headers, env_url.
# SDK does not support settingdefinition/organizationsettings entities.
NEW_VALUE = "true"   # bool-as-string; "true"/"false" (lowercase)

if overrides:
    setting_id = overrides[0]["organizationsettingid"]
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/organizationsettings({setting_id})",
        data=json.dumps({"value": NEW_VALUE}).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
else:
    # No override exists — CREATE a new one
    payload = {
        "settingdefinitionid@odata.bind": f"settingdefinitions({sd_id})",
        "value": NEW_VALUE,
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/organizationsettings",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

with urllib.request.urlopen(req) as resp:
    print(f"SUCCESS: {UNIQUENAME} = {NEW_VALUE} (HTTP {resp.status})", flush=True)
```

**Notes:**
- `datatype=2` means bool; other values exist for string/int but only bool toggles are in our allowlist today.
- `value` is always a **string**, even for bool and int definitions — `"true"` not `True`.
- The two allowlisted uniquenames are gated by ECS feature flags (`enablePowerAppsAppLevelSecurityRolesToggle`, `enablePlanShareSecurityRolesToggle`) in the PPAC UI, but the entities exist regardless — if the flag is off in an env, setting the override still takes effect.
- `DELETE` on the override row reverts to the `settingdefinition.defaultvalue`.

# Settings-Definition Overrides (app/plan security roles)

A small number of allowlisted toggles don't live on the `organization` entity or in `orgdborgsettings`. They're modeled as a join between two entities:

- **`settingdefinition`** — defines the setting (uniquename, datatype, defaultvalue, description). Read-only; one row per known setting; identical across environments in the same build.
- **`organizationsettings`** — holds per-org overrides. If no row exists for a given `settingdefinitionid`, the `defaultvalue` from `settingdefinition` applies.

Allowlisted uniquenames (both `datatype=2` bool, stored as string `"true"`/`"false"`):
- `PowerAppsAppLevelSecurityRolesEnabled` — Enable app level security roles for canvas apps
- `PlanShareSecurityRolesEnabled` — Enable plan level security roles for plan designer

**Read current value:**

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-admin")

UNIQUENAME = "PowerAppsAppLevelSecurityRolesEnabled"   # or PlanShareSecurityRolesEnabled

# settingdefinition + organizationsetting are ordinary entities — plain SDK record reads.
defs = list(client.records.list(
    "settingdefinition",
    select=["settingdefinitionid", "uniquename", "defaultvalue", "datatype"],
    filter=f"uniquename eq '{UNIQUENAME}'",
))
if not defs:
    raise SystemExit(f"Setting '{UNIQUENAME}' is not defined in this environment (ECS-gated -- not available here).")
defn = defs[0]
sd_id = defn["settingdefinitionid"]
default = defn["defaultvalue"]

overrides = list(client.records.list(
    "organizationsetting",
    select=["organizationsettingid", "value"],
    filter=f"_settingdefinitionid_value eq {sd_id}",
))

current = overrides[0]["value"] if overrides else default
print(f"{UNIQUENAME} = {current} (default = {default}, override present: {bool(overrides)})", flush=True)
```

**Write (idempotent CREATE-or-PATCH):**

```python
# Continues from Read script above — reuses UNIQUENAME, sd_id, overrides, client.
NEW_VALUE = "true"   # bool-as-string; "true"/"false" (lowercase)

if overrides:
    client.records.update("organizationsetting", overrides[0]["organizationsettingid"], {"value": NEW_VALUE})
else:
    # No override exists — CREATE a new one (@odata.bind uses the entity-set path).
    client.records.create("organizationsetting", {
        "settingdefinitionid@odata.bind": f"settingdefinitions({sd_id})",
        "value": NEW_VALUE,
    })
print(f"SUCCESS: {UNIQUENAME} = {NEW_VALUE}", flush=True)
```

**Notes:**
- `datatype=2` means bool; other values exist for string/int but only bool toggles are in our allowlist today.
- `value` is always a **string**, even for bool and int definitions — `"true"` not `True`.
- The two allowlisted uniquenames are gated by ECS feature flags (`enablePowerAppsAppLevelSecurityRolesToggle`, `enablePlanShareSecurityRolesToggle`) in the PPAC UI, but the entities exist regardless — if the flag is off in an env, setting the override still takes effect.
- `DELETE` on the override row reverts to the `settingdefinition.defaultvalue`.

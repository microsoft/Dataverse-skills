---
name: dv-admin
description: >
  Environment-level Dataverse administration: bulk delete, data retention/archival,
  organization settings (audit, plugin trace, session timeout), OrgDB settings (MCP, search, copilot, fabric),
  and recycle bin configuration.
  Use when: "bulk delete", "delete all records", "clean up old records", "schedule deletion",
  "data cleanup", "remove old data", "pause bulk delete", "cancel bulk delete", "resume job",
  "bulk delete job status", "list delete jobs", "manage bulk delete", "data management", "pac data",
  "retention", "archive", "archival", "set up retention", "retain old records",
  "long term retain", "data lifecycle", "enable archival", "enable retention",
  "retention policy", "archive records", "retention status",
  "org settings", "organization settings", "enable audit", "disable audit", "audit status",
  "check audit", "audit enabled", "is audit enabled", "audit logs", "turn on auditing",
  "plugin trace", "session timeout", "auto save", "environment settings",
  "list settings", "list-settings", "update settings", "update-settings",
  "enable audit for all environments", "developer environments audit",
  "recycle bin", "enable recycle bin", "disable recycle bin",
  "recycle bin cleanup", "recyclebinconfig", "cleanup interval",
  "orgdb settings", "search settings", "copilot settings", "mcp settings",
  "fabric settings", "enable search", "disable search", "enable mcp", "disable mcp".
  Do not use when: deleting individual records (use dv-data), deleting tables (use dv-metadata),
  exporting/importing data files (use dv-solution), querying records (use dv-query),
  assigning roles or self-elevating (use dv-security), creating sample data (use dv-data),
  tenant governance like DLP or environment lifecycle (use pac admin --help).
---

# Skill: Environment Admin — Bulk Delete, Retention, Org Settings, OrgDB, Recycle Bin

**This skill uses PAC CLI for most operations.** Two exceptions require Python SDK:
- **OrgDB settings** (search, MCP, copilot, fabric) — stored in `orgdborgsettings` XML blob
- **Recycle bin** — stored in `recyclebinconfigs` entity

Do NOT write Python scripts for operations PAC CLI can handle.

## CRITICAL: How to Query Multiple Environments

**When the user asks about settings, audit status, or any read/write across multiple environments, ALWAYS do this:**

```bash
# ONE bash call. ALL environments. Parallel with & and wait.
pac org list-settings --filter isauditenabled --environment https://org1.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org2.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org3.crm.dynamics.com &
wait
```

**Do NOT:**
- Use `pac env select` to switch environments one by one
- Use `pac org who` to check settings
- Make separate bash calls for each environment
- Write Python scripts

---

## Prerequisites

- PAC CLI installed and authenticated (`pac auth create`)
- A Dataverse environment with System Administrator privilege
- Active auth profile: `pac auth list`

---

## Multi-Environment Operations — Always Parallel

When operating across multiple environments, use `--environment` flag and `&` to run **all commands in a single bash call**:

```bash
# READ settings from 5 environments — ONE bash call, all parallel
pac org list-settings --filter isauditenabled --environment https://org1.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org2.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org3.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org4.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org5.crm.dynamics.com &
wait
```

```bash
# UPDATE settings on 5 environments — ONE bash call, all parallel
pac org update-settings --name isauditenabled --value true --environment https://org1.crm.dynamics.com &
pac org update-settings --name isauditenabled --value true --environment https://org2.crm.dynamics.com &
pac org update-settings --name isauditenabled --value true --environment https://org3.crm.dynamics.com &
wait
```

**Rules:**
- Use `--environment <url>` — do NOT use `pac env select` to switch environments
- Run ALL commands in one bash call with `&` and `wait` — do NOT run separate sequential bash calls
- Use `pac org list-settings` to read settings — do NOT use `pac org who`

---

## Common Mistakes — Do NOT Use These

These flags do not exist. Using them will produce errors.

| Wrong | Correct |
|-------|---------|
### Bulk Delete
| Wrong | Correct |
|-------|---------|
| `--filter` | use `--fetchxml` with a FetchXML string |
| `--query` / `--where` / `--condition` | use `--fetchxml` |
| `--date` / `--before` / `--older-than` | encode date in FetchXML `<condition>` |
| `--job-id` | use `--id` |
| `--all` / `--purge` / `--truncate` | omit `--fetchxml` to target all records (warn user first) |

### Retention
| Wrong | Correct |
|-------|---------|
| `--fetchxml` | use `--criteria` (same FetchXML format, different flag name) |
| `--filter` / `--query` / `--policy` | use `--criteria` |
| `--enable` / `--activate` | use `pac data retention enable-entity` |
| `--table` | use `--entity` |
| `--operation-id` / `--job-id` / `--guid` | use `--id` |

### Org Settings
| Wrong | Correct |
|-------|---------|
| `--enable-audit` / `--audit` | use `--name isauditenabled --value true` |
| `--trace` / `--plugin-trace` / `--logging` | use `--name plugintracelogsetting --value 2` |
| `--timeout` / `--session` / `--minutes` | use `--name sessiontimeoutinmins --value <int>` |
| `--setting` / `--key` / `--flag` | use `--name` |
| String values like `"all"` or `"enabled"` for option sets | use integers: `0`, `1`, `2` |

---

## Bulk Delete Commands

### Schedule a Bulk Delete Job

```bash
pac data bulk-delete schedule --entity account
pac data bulk-delete schedule --entity activitypointer \
    --fetchxml "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>"
pac data bulk-delete schedule --entity email \
    --fetchxml "<fetch><entity name='email'><filter><condition attribute='createdon' operator='lt' value='2024-06-01'/></filter></entity></fetch>" \
    --job-name "Cleanup old emails" --recurrence "FREQ=DAILY;INTERVAL=1"
```

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table |
| `--fetchxml` | `-fx` | No | FetchXML filter. If omitted, **all records** targeted |
| `--job-name` | `-jn` | No | Descriptive name for the job |
| `--start-time` | `-st` | No | ISO 8601 start time. Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 pattern (e.g., `FREQ=DAILY;INTERVAL=1`) |
| `--environment` | `-env` | No | Target environment URL |

### Manage Jobs

```bash
pac data bulk-delete list --environment https://myorg.crm.dynamics.com
pac data bulk-delete show --id <job-id>
pac data bulk-delete pause --id <job-id>
pac data bulk-delete resume --id <job-id>
pac data bulk-delete cancel --id <job-id>
```

---

## Retention / Archival Commands

Data retention moves old records to long-term storage without permanently deleting them.

### Agentic Flow

```
Step 1: pac data retention enable-entity --entity activitypointer
Step 2: pac data retention list
Step 3: pac data retention set --entity activitypointer --criteria "<fetchxml>..."
Step 4: pac data retention show --id <config-id>
```

### Commands

```bash
pac data retention enable-entity --entity activitypointer --environment https://myorg.crm.dynamics.com
pac data retention set --entity activitypointer \
    --criteria "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2023-01-01'/></filter></entity></fetch>"
pac data retention list --environment https://myorg.crm.dynamics.com
pac data retention show --id <config-id>
pac data retention status --id <operation-id>
```

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table |
| `--criteria` | `-c` | Yes | FetchXML defining which records to archive |
| `--start-time` | `-st` | No | ISO 8601 start time. Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 recurrence pattern |
| `--environment` | `-env` | No | Target environment URL |

### Retention vs Bulk Delete

| Scenario | Use |
|----------|-----|
| Data no longer needed, permanently delete | **Bulk Delete** |
| Data must be preserved for compliance | **Retention** (archive) |

---

## Organization Settings Commands

### List Settings

```bash
pac org list-settings --environment https://myorg.crm.dynamics.com
pac org list-settings --filter isauditenabled --environment https://myorg.crm.dynamics.com
```

### Update a Setting

```bash
pac org update-settings --name isauditenabled --value true --environment https://myorg.crm.dynamics.com
pac org update-settings --name plugintracelogsetting --value 2 --environment https://myorg.crm.dynamics.com
```

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--name` | `-n` | Yes | Setting name (e.g., `isauditenabled`) |
| `--value` | `-v` | Yes | New value (`true`/`false` for booleans, integer for option sets) |
| `--environment` | `-env` | No | Target environment URL or ID |

#### Available Settings

| Setting Name | Type | Values |
|-------------|------|--------|
| `isauditenabled` | bool | `true` / `false` |
| `isuseraccessauditenabled` | bool | `true` / `false` |
| `isreadauditenabled` | bool | `true` / `false` |
| `plugintracelogsetting` | option | `0` (Off), `1` (Exception), `2` (All) |
| `isautosaveenabled` | bool | `true` / `false` |
| `maxuploadfilesize` | int | Size in KB (e.g., `32768`) |
| `sessiontimeoutenabled` | bool | `true` / `false` |
| `sessiontimeoutinmins` | int | Minutes (e.g., `60`) |
| `inaborttimeoutenabled` | bool | `true` / `false` |
| `inaborttimeoutinmins` | int | Minutes (e.g., `20`) |

### Batch Workflow

```
Step 1: pac admin list                         -> Get all environments
Step 2: Filter by type or name                 -> Identify targets
Step 3: For updates: confirm with user first
Step 4: Run ALL commands in parallel (see Multi-Environment section above)
Step 5: Report summary as a table
```

---

## Advanced Settings (Python SDK — PAC CLI Cannot Handle These)

Some settings can't be managed by `pac org update-settings`. Two patterns exist:

| Setting type | Where it lives | How to update |
|---|---|---|
| Top-level org columns (`isauditenabled`, `plugintracelogsetting`, etc.) | Organization entity columns | **PAC CLI** — `pac org update-settings` |
| OrgDB settings (search, MCP, copilot, fabric, etc.) | XML inside `orgdborgsettings` column | **Python SDK** — fetch XML, parse, modify, PATCH back |
| Recycle bin (org-level and per-table) | `recyclebinconfigs` entity | **Python SDK** — PATCH `recyclebinconfigs(<id>)` |

---

### OrgDB Settings (orgdborgsettings XML)

Settings like search mode, MCP, copilot features, fabric, and retention live inside the `orgdborgsettings` XML blob. The XML uses **direct PascalCase elements** (NOT `<pair>` tags):

```xml
<OrgSettings>
  <SearchAndCopilotIndexMode>0</SearchAndCopilotIndexMode>
  <IsRetentionEnabled>true</IsRetentionEnabled>
  <IsDVCopilotForTextDataEnabled>true</IsDVCopilotForTextDataEnabled>
</OrgSettings>
```

**Read all OrgDB settings:**

```python
import subprocess, json, urllib.request
from xml.etree import ElementTree as ET

ENV_URL = "https://myorg.crm.dynamics.com"  # replace with target

token = subprocess.run(
    ["powershell", "-Command",
     f"az account get-access-token --resource {ENV_URL} --query accessToken -o tsv"],
    capture_output=True, text=True
).stdout.strip()

req = urllib.request.Request(
    f"{ENV_URL}/api/data/v9.2/organizations?$select=organizationid,orgdborgsettings",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    org = json.loads(resp.read())["value"][0]

root = ET.fromstring(org["orgdborgsettings"])
for child in sorted(root, key=lambda c: c.tag):
    print(f"  {child.tag} = {child.text}")
```

**Update or add an OrgDB setting:**

```python
import subprocess, json, urllib.request, urllib.error
from xml.etree import ElementTree as ET

ENV_URL = "https://myorg.crm.dynamics.com"
SETTING_NAME = "SearchAndCopilotIndexMode"  # PascalCase, case-sensitive
SETTING_VALUE = "0"                          # always a string in XML

token = subprocess.run(
    ["powershell", "-Command",
     f"az account get-access-token --resource {ENV_URL} --query accessToken -o tsv"],
    capture_output=True, text=True
).stdout.strip()

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

# Fetch current XML
req = urllib.request.Request(
    f"{ENV_URL}/api/data/v9.2/organizations?$select=organizationid,orgdborgsettings",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    org = json.loads(resp.read())["value"][0]
    org_id = org["organizationid"]

root = ET.fromstring(org.get("orgdborgsettings", "<OrgSettings></OrgSettings>"))

# Update existing or add new
existing = root.find(SETTING_NAME)
if existing is not None:
    print(f"Current {SETTING_NAME} = {existing.text}")
    existing.text = SETTING_VALUE
else:
    print(f"{SETTING_NAME} not set -- adding")
    ET.SubElement(root, SETTING_NAME).text = SETTING_VALUE

# PATCH back
req = urllib.request.Request(
    f"{ENV_URL}/api/data/v9.2/organizations({org_id})",
    data=json.dumps({"orgdborgsettings": ET.tostring(root, encoding="unicode")}).encode("utf-8"),
    headers=headers,
    method="PATCH",
)
try:
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: {SETTING_NAME} = {SETTING_VALUE} (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()}")
```

**Remove an OrgDB setting:**

```python
# After fetching and parsing the XML (same as above):
existing = root.find(SETTING_NAME)
if existing is not None:
    root.remove(existing)
    # PATCH back the XML without the element
```

**Common OrgDB settings (PascalCase, case-sensitive — use these exact names):**

| Setting | Type | Values | What it controls |
|---|---|---|---|
| `IsMCPEnabled` | bool | `true` / `false` | Enable/disable Dataverse MCP server |
| `SearchAndCopilotIndexMode` | int | `0` = default, `1` = on, `2` = off | Dataverse search and Copilot indexing |
| `IsRetentionEnabled` | bool | `true` / `false` | Data retention |
| `IsArchivalEnabled` | bool | `true` / `false` | Data archival |
| `IsDVCopilotForTextDataEnabled` | bool | `true` / `false` | Copilot for text data |
| `IsLinkToFabricEnabled` | bool | `true` / `false` | Link to Fabric |
| `IsFabricVirtualTableEnabled` | bool | `true` / `false` | Fabric virtual tables |
| `IsShadowLakeEnabled` | bool | `true` / `false` | Shadow lake |
| `IsCommandingModifiedOnEnabled` | bool | `true` / `false` | Commanding modified-on tracking |
| `CanCreateApplicationStubUser` | bool | `true` / `false` | Application stub user creation |
| `AllowRoleAssignmentOnDisabledUsers` | bool | `true` / `false` | Role assignment on disabled users |
| `EnableActivitiesFeatures` | int | `0` / `1` | Activities features toggle |
| `EnableActivitiesTimeLinePerfImprovement` | int | `0` / `1` | Timeline performance |
| `TDSListenerInitialized` | int | `0` / `1` | TDS endpoint |
| `AzureSynapseLinkIncrementalUpdateTimeInterval` | int | minutes (e.g., `1440`) | Synapse Link update interval |

**Do NOT search or discover setting names at runtime.** Use the table above. If the user asks for a setting not in this table, read all current settings first (`root.find()` loop) and show the user what's available.

---

### Recycle Bin Configuration

Recycle bin settings live in the `recyclebinconfigs` entity, NOT in `orgdborgsettings` XML. PAC CLI cannot manage these.

### Read Recycle Bin Status

```bash
# Quick check via PAC CLI
pac org fetch --xml "<fetch><entity name='recyclebinconfig'><filter><condition attribute='name' operator='eq' value='organization'/></filter><attribute name='isreadyforrecyclebin'/><attribute name='cleanupintervalindays'/></entity></fetch>" --environment https://myorg.crm.dynamics.com
```

### Enable/Disable Recycle Bin or Change Cleanup Interval

```python
import subprocess, json, urllib.request, urllib.error, urllib.parse

ENV_URL = "https://org470dd288.crm.dynamics.com"  # replace with target

# Get token from az cli (works without .env)
token = subprocess.run(
    ["powershell", "-Command",
     f"az account get-access-token --resource {ENV_URL} --query accessToken -o tsv"],
    capture_output=True, text=True
).stdout.strip()

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

# Step 1: Get the org-level recyclebinconfig ID
filter_q = urllib.parse.quote("name eq 'organization'")
req = urllib.request.Request(
    f"{ENV_URL}/api/data/v9.2/recyclebinconfigs?$filter={filter_q}&$select=recyclebinconfigid,isreadyforrecyclebin,cleanupintervalindays",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    config = json.loads(resp.read())["value"][0]
    config_id = config["recyclebinconfigid"]
    print(f"Current: isreadyforrecyclebin={config['isreadyforrecyclebin']}, cleanupintervalindays={config['cleanupintervalindays']}")

# Step 2: Update — set cleanup interval (30 days) to enable, or -1 to disable auto-cleanup
req = urllib.request.Request(
    f"{ENV_URL}/api/data/v9.2/recyclebinconfigs({config_id})",
    data=json.dumps({"cleanupintervalindays": 30}).encode("utf-8"),
    headers=headers,
    method="PATCH",
)
try:
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: cleanupintervalindays = 30 (HTTP {resp.status})")
except urllib.error.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()}")
```

### Key Fields on `recyclebinconfigs`

| Field | Type | What it does |
|---|---|---|
| `isreadyforrecyclebin` | bool | Whether the entity supports recycle bin (read-only for org level) |
| `cleanupintervalindays` | int | Auto-cleanup interval. `-1` = no auto-cleanup. `30` = delete after 30 days |
| `name` | string | `"organization"` for org-level config, table logical name for per-table configs |
| `statecode` | int | `0` = active, `1` = inactive |

### Per-Table Recycle Bin Config

Each table has its own `recyclebinconfig` record. To check/update a specific table:

```python
# Filter by table name
filter_q = urllib.parse.quote("name eq 'account'")
# ... same pattern as above, just change the filter
```

---

## Safety Rules

- **Always confirm** before scheduling a bulk delete — this is destructive
- If `--fetchxml` is omitted, warn that ALL records in the table will be deleted
- For system tables (`systemuser`, `businessunit`, `organization`), warn that deleting may break the environment
- **Always confirm** before changing org settings that affect all users
- For multi-environment updates, show the list of environments and get confirmation first
- For OrgDB settings, warn that incorrect values can break environment features
- For recycle bin, warn that reducing cleanup interval will permanently delete records sooner

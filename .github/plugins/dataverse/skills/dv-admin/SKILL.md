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

## Skill boundaries

| Need | Use instead |
|---|---|
| Delete or update individual records | **dv-data** |
| Create or delete tables, columns, relationships | **dv-metadata** |
| Query or read records | **dv-query** |
| Export or import solutions / data files | **dv-solution** |
| Assign security roles or self-elevate | **dv-security** |
| Create sample or seed data | **dv-data** |
| Tenant governance (DLP, env lifecycle) | `pac admin --help` |

## CRITICAL: Always Show the Command First

Even when the environment URL, entity name, or other values are missing, **your first response must include the full command(s) you plan to run**, with placeholders (`<ENV_URL>`, `<USER_EMAIL>`) for unknowns. Then ask for confirmation and missing values in the same message.

**Never** ask "which environment?" or "do you want to proceed?" in isolation — the user cannot evaluate a request they can't see. See the Confirmation Protocol section below for examples.

### Canonical bad/good examples — follow these literally

<example operation="pause bulk delete job (all info in prompt)">
<user>Pause the bulk delete job with ID 12345678-1234-1234-1234-123456789012</user>
<bad>The command requires approval. Please confirm to pause the job.</bad>
<good>I'll run:

```bash
pac data bulk-delete pause --id 12345678-1234-1234-1234-123456789012
```

Confirm to proceed.</good>
</example>

<example operation="read recycle bin status (no env URL yet)">
<user>What's the current recycle bin status?</user>
<bad>Please provide your environment URL so I can check.</bad>
<bad>Runs `pac org fetch` against `recyclebinconfig` — PAC CLI does NOT manage recycle bin. Always use the Web API via Python.</bad>
<good>Recycle bin lives in the `recyclebinconfigs` entity — PAC CLI can't read it. Here's the Python I'll run (full script in the Recycle Bin Configuration section below):

```python
ENV_URL = "<YOUR_ENV_URL>"
# GET /api/data/v9.2/recyclebinconfigs?$filter=_extensionofrecordid_value eq '<ORG_ENTITY_ID>'
# prints statecode, statuscode, cleanupintervalindays
```

Provide your environment URL and I'll run this (read-only, no confirmation needed).</good>
</example>

<example operation="audit status across N environments">
<user>Tell me audit status of these 5 environments</user>
<bad>Runs `pac env select` then `pac org fetch --entity organization --attributes isauditenabled` once per environment, sequentially, across N separate bash calls.</bad>
<bad>Falls back to Python / `urllib` / the Web API after `pac org fetch` output is hard to parse.</bad>
<good>Single bash call, one `pac org list-settings` per environment, all backgrounded, single `wait`:

```bash
pac org list-settings --filter isauditenabled --environment https://org1.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org2.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org3.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org4.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org5.crm.dynamics.com &
wait
```

Then render the results as a table. `pac org list-settings` is the ONLY command for reading org settings — never `pac org fetch`, never `pac env select` + anything.</good>
</example>

<example operation="disable MCP (OrgDB setting, no env URL yet)">
<user>Disable MCP for my environment</user>
<bad>Please provide your environment URL so I can disable MCP.</bad>
<good>MCP lives in `orgdborgsettings` XML — PAC CLI can't modify it. Here's the Python I'll run:

```python
# PATCH organizations entity, setting IsMCPEnabled=false in orgdborgsettings XML
# (IsMCPEnabled is PascalCase, case-sensitive — not IsMcpEnabled)
ENV_URL = "<YOUR_ENV_URL>"
# ... (full script from OrgDB section below)
```

Confirm to proceed and provide your environment URL.</good>
</example>

## CRITICAL: How to Read or Update Org Settings (Single or Multi-Environment)

**To check any org setting (audit, plugin trace, etc.):** `pac org list-settings`
**To update any org setting:** `pac org update-settings`

These are the ONLY commands for org settings. Do NOT use `pac org fetch`, `pac org who`, `curl`, `urllib`, PowerShell Invoke-RestMethod, or any Web API call. The PAC CLI commands handle authentication automatically.

**Single environment:**

```bash
pac org list-settings --filter isauditenabled --environment https://org1.crm.dynamics.com
```

**Multiple environments — ALWAYS parallel in ONE bash call:**

```bash
pac org list-settings --filter isauditenabled --environment https://org1.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org2.crm.dynamics.com &
pac org list-settings --filter isauditenabled --environment https://org3.crm.dynamics.com &
wait
```

**NEVER do any of these for org settings:**
- `pac env select` then `pac org fetch` — WRONG, use `pac org list-settings --environment <url>`
- `pac org who` — shows connection info, NOT settings
- `curl` / `urllib` / `requests` to the Web API — WRONG, use `pac org list-settings`
- `pac auth token` — WRONG, PAC CLI handles auth internally
- PowerShell `Invoke-RestMethod` — WRONG, use PAC CLI directly
- Separate bash calls per environment — WRONG, use `&` and `wait` in ONE call
- Python scripts for org settings — WRONG, use PAC CLI

---

## Prerequisites

- PAC CLI **latest version (.NET Framework build)** — `pac data bulk-delete` and `pac data retention` commands are only in the .NET Framework build (not the `dotnet tool` cross-platform version). Check your version:
  ```bash
  pac help   # look for "Version: x.x.x (.NET Framework ...)"
  ```
  If it shows `.NET 10` or `.NET 8` instead of `.NET Framework`, the `pac data` commands will not be available. To update to the latest .NET Framework build:
  ```bash
  pac install latest   # downloads latest NuGet package
  pac use latest       # switches to the latest installed version
  ```
- Authenticated (`pac auth create`)
- A Dataverse environment with System Administrator privilege
- Active auth profile: `pac auth list`

---

## Multi-Environment Operations — Always Parallel

The pattern above applies to ALL multi-environment operations, not just org settings. For updates:

```bash
# UPDATE settings on multiple environments — ONE bash call, all parallel
pac org update-settings --name isauditenabled --value true --environment https://org1.crm.dynamics.com &
pac org update-settings --name isauditenabled --value true --environment https://org2.crm.dynamics.com &
pac org update-settings --name isauditenabled --value true --environment https://org3.crm.dynamics.com &
wait
```

---

## Common Mistakes — Do NOT Use These

These flags do not exist. Using them will produce errors.

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
pac data bulk-delete schedule --entity activitypointer \
    --fetchxml "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>"
pac data bulk-delete schedule --entity email \
    --fetchxml "<fetch><entity name='email'><filter><condition attribute='createdon' operator='lt' value='2024-06-01'/></filter></entity></fetch>" \
    --job-name "Cleanup old emails" --recurrence "FREQ=DAILY;INTERVAL=1"
```

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table |
| `--fetchxml` | `-fx` | No | FetchXML filter. **See the hard-stop rule below — if omitted, ALL records in the table are deleted.** |
| `--job-name` | `-jn` | No | Descriptive name for the job |
| `--start-time` | `-st` | No | ISO 8601 start time. Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 pattern (e.g., `FREQ=DAILY;INTERVAL=1`) |
| `--environment` | `-env` | No | Target environment URL |

### Hard stop: no `--fetchxml` means ALL records

A `pac data bulk-delete schedule` without `--fetchxml` targets every record in the table and is irreversible. Bulk delete does not go through the recycle bin. Apply this gate before running:

1. **Refuse to run until the user explicitly acknowledges.** The acknowledgement must include both the word ALL (or ALL RECORDS) **and** the entity logical name. Example accepted: `"yes, delete ALL records in contact"`. Example rejected: a bare `"yes"` or `"proceed"`.
2. **Disambiguate first.** If the user's ask is vague ("clean up old emails", "remove stale accounts"), ask clarifying questions (date cutoff? statecode filter? owner?) and draft a FetchXML before showing any `bulk-delete schedule` command.
3. **Do not synthesize empty-filter FetchXML to bypass the gate.** An empty `<filter/>` or `<filter><condition ...><value/></condition></filter>` still targets every record — that counts as "no `--fetchxml`" for this rule.
4. **Scope.** This gate applies to `pac data bulk-delete schedule` only. `cancel`, `pause`, `resume`, `show`, and `list` don't need it.

For system tables (`systemuser`, `businessunit`, `organization`, `role`), warn additionally that an unfiltered bulk delete will break the environment.

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
import os, sys, json, urllib.request
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support orgdborgsettings XML blob

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/organizations?$select=organizationid,orgdborgsettings",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    org = json.loads(resp.read())["value"][0]

root = ET.fromstring(org["orgdborgsettings"])
for child in sorted(root, key=lambda c: c.tag):
    print(f"  {child.tag} = {child.text}", flush=True)
```

**Update or add an OrgDB setting:**

```python
import os, sys, json, urllib.request, urllib.error
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support orgdborgsettings XML blob

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

SETTING_NAME = "SearchAndCopilotIndexMode"  # PascalCase, case-sensitive
SETTING_VALUE = "0"                          # always a string in XML

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

# Fetch current XML
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/organizations?$select=organizationid,orgdborgsettings",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    org = json.loads(resp.read())["value"][0]
    org_id = org["organizationid"]

root = ET.fromstring(org.get("orgdborgsettings", "<OrgSettings></OrgSettings>"))

# Update existing or add new
existing = root.find(SETTING_NAME)
if existing is not None:
    print(f"Current {SETTING_NAME} = {existing.text}", flush=True)
    existing.text = SETTING_VALUE
else:
    print(f"{SETTING_NAME} not set -- adding", flush=True)
    ET.SubElement(root, SETTING_NAME).text = SETTING_VALUE

# PATCH back
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/organizations({org_id})",
    data=json.dumps({"orgdborgsettings": ET.tostring(root, encoding="unicode")}).encode("utf-8"),
    headers=headers,
    method="PATCH",
)
try:
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: {SETTING_NAME} = {SETTING_VALUE} (HTTP {resp.status})", flush=True)
except urllib.error.HTTPError as e:
    print(f"ERROR {e.code}: {e.read().decode()}", flush=True)
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

**Well-known constant:** The organization entity metadata ID is `e1bd1119-6e9d-45a4-bc15-12051e65a0bd`. This is the `MetadataId` of the `organization` entity's *schema record* in `EntityDefinitions` (a product-level system constant baked into every Dataverse installation), not a tenant-level GUID — so it is identical across all environments and all tenants. Verified empirically across 5 environments. Do not re-query it per environment.

### Read Recycle Bin Status

```python
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support recyclebinconfigs entity

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

ORGANIZATION_ENTITY_ID = "e1bd1119-6e9d-45a4-bc15-12051e65a0bd"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

# Fetch org-level config by extensionofrecordid (NOT by name)
filter_q = urllib.parse.quote(f"_extensionofrecordid_value eq '{ORGANIZATION_ENTITY_ID}'")
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/recyclebinconfigs?$filter={filter_q}&$select=recyclebinconfigid,statecode,statuscode,cleanupintervalindays",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    records = json.loads(resp.read()).get("value", [])

if records:
    config = records[0]
    enabled = config["statecode"] == 0
    cleanup = config["cleanupintervalindays"]
    print(f"Recycle bin: {'enabled' if enabled else 'disabled'}", flush=True)
    print(f"Cleanup interval: {cleanup} days ({'-1 means no auto-cleanup' if cleanup == -1 else ''})", flush=True)
    print(f"Config ID: {config['recyclebinconfigid']}", flush=True)
else:
    print("Recycle bin: not configured (no org-level record)", flush=True)
```

### Enable Recycle Bin

Three cases depending on whether a config record already exists:

```python
# ... (same imports, headers, ORGANIZATION_ENTITY_ID, and fetch as above)
# SDK does not support recyclebinconfigs entity

CLEANUP_DAYS = 30  # default; -1 means records in recycle bin are never auto-purged

if not records:
    # Case 1: No config exists -- CREATE a new one
    # extensionofrecordid binds to the entities() metadata endpoint, NOT organizations()
    payload = {
        "extensionofrecordid@odata.bind": f"entities({ORGANIZATION_ENTITY_ID})",
        "extensionofrecordid@OData.Community.Display.V1.FormattedValue": "OrganizationId",
        "cleanupintervalindays": CLEANUP_DAYS,
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup (HTTP {resp.status})", flush=True)
else:
    # Case 2: Config exists -- UPDATE statecode/statuscode and cleanup interval
    config_id = records[0]["recyclebinconfigid"]
    payload = {
        "cleanupintervalindays": CLEANUP_DAYS,
        "statecode": 0,
        "statuscode": 1,
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup (HTTP {resp.status})", flush=True)
```

### Disable Recycle Bin

**Disable = DELETE the recyclebinconfig record.** No payload, no statecode change.

```python
# ... (same fetch as above to get config_id)
# SDK does not support recyclebinconfigs entity

if records:
    config_id = records[0]["recyclebinconfigid"]
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        headers=headers,
        method="DELETE",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin disabled (HTTP {resp.status})", flush=True)
else:
    print("Recycle bin is already disabled (no config record)", flush=True)
```

### Key Fields on `recyclebinconfigs`

| Field | Type | What it does |
|---|---|---|
| `statecode` | int | `0` = enabled (active), `1` = disabled (inactive) |
| `statuscode` | int | `1` = enabled, `2` = disabled |
| `cleanupintervalindays` | int | Auto-cleanup interval. `-1` = no auto-cleanup (default). `30` = purge after 30 days (max). Min: `1` |
| `_extensionofrecordid_value` | guid | Entity metadata ID this config applies to. Org-level = `e1bd1119-6e9d-45a4-bc15-12051e65a0bd` |

### Important Notes

- **Fetch by `_extensionofrecordid_value`**, not by `name`. The `name` field is unreliable for filtering.
- **Create uses `entities()` binding** -- `extensionofrecordid@odata.bind: entities({id})`, NOT `organizations()`.
- **Disable = DELETE**, not a statecode PATCH. This is how the Power Platform Admin Center does it.
- **Cleanup days**: default is `-1` (no auto-cleanup). Max is `30`. When the UI shows "30 days", the API stores `-1` internally (the platform applies a 30-day default).
- Solution-managed configs (e.g., `msdyn_recurringsalesaction`) cannot be enabled/disabled via API.

### Per-Table Recycle Bin Config

Each table can have its own `recyclebinconfig` record. Filter by the table's entity metadata ID:

```python
# Get entity metadata ID for a specific table
# SDK does not support recyclebinconfigs entity
params = urllib.parse.urlencode({"$select": "MetadataId", "$filter": "LogicalName eq 'account'"})
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/EntityDefinitions?{params}",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    entity_id = json.loads(resp.read())["value"][0]["MetadataId"]

# Then filter recyclebinconfigs by that entity ID
filter_q = urllib.parse.quote(f"_extensionofrecordid_value eq '{entity_id}'")
# ... same enable/disable pattern as org-level
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

## Confirmation Protocol — Show the Plan First, Then Ask

When the user hasn't provided the environment URL, user email, or other required values, **still show the complete command(s) or Python code you will run**, using placeholders (`<ENV_URL>`, `<USER_EMAIL>`, etc.). Then ask the user to confirm and fill in the missing values in a single follow-up turn.

Do NOT ask "which environment?" or "should I proceed?" in isolation — the user cannot approve a command they haven't seen yet.

Example — user asks "Enable auditing for all developer environments":

> Here's the plan:
>
> ```bash
> pac admin list                                          # step 1: list environments
> pac org update-settings --name isauditenabled --value true --environment <DEV_ENV_1> &
> pac org update-settings --name isauditenabled --value true --environment <DEV_ENV_2> &
> wait                                                    # step 2: parallel update
> ```
>
> Confirm to proceed, or tell me which environments qualify as "developer".

**OrgDB setting names are case-sensitive.** Use PascalCase with acronyms UPPER: `IsMCPEnabled` (not `IsMcpEnabled`), `IsDVCopilotForTextDataEnabled` (not `IsDvCopilot...`). Getting this wrong silently fails to update.

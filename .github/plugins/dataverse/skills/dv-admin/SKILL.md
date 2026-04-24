---
name: dv-admin
description: >
  Environment-level Dataverse administration: bulk delete, data retention/archival,
  organization settings, OrgDB settings, recycle bin, and settings-definition overrides.
  Covers 37 allowlisted PPAC toggles — audit, plugin trace, typeahead/quick find, canvas/flow solutions,
  audit retention, MCP, search, Fabric, Work IQ, M365 Copilot, TDS endpoint, attachment security,
  ownership across BUs, address records, delete users, Excel AI import, block unmanaged, app/plan security roles.
  Use when: "bulk delete", "clean up old records", "schedule deletion", "pause/cancel/resume bulk delete", "pac data",
  "retention", "archive", "data lifecycle", "audit retention", "audit log retention",
  "org settings", "organization settings", "environment settings", "list-settings", "update-settings",
  "enable audit", "audit status", "read auditing", "user access audit", "plugin trace",
  "typeahead", "lookup delay", "quick find", "single table search", "leading wildcard",
  "canvas apps in solutions", "cloud flows in solutions", "email validation",
  "recycle bin", "cleanup interval", "recyclebinconfig",
  "orgdb settings", "search settings", "mcp settings", "mcp advanced",
  "fabric settings", "link to fabric", "fabric virtual tables",
  "work iq", "dataverse intelligence", "m365 copilot data",
  "tds endpoint", "attachment security", "record ownership", "ownership across business units",
  "address records", "block unmanaged customizations", "delete disabled users", "excel import ai",
  "app level security roles", "plan level security roles".
  Do not use when: deleting individual records (use dv-data), deleting tables (use dv-metadata),
  exporting/importing data files (use dv-solution), querying records (use dv-query),
  assigning roles or self-elevating (use dv-security), creating sample data (use dv-data),
  tenant governance like DLP or environment lifecycle (use pac admin --help).
---

# Skill: Environment Admin — Bulk Delete, Retention, Org Settings, OrgDB, Recycle Bin

**Four mechanisms — pick based on where the setting lives:**

| Mechanism | Use for | How |
|---|---|---|
| **PAC CLI** (`pac org update-settings` / `list-settings`) | Columns on the `organization` entity (audit, plugin trace, typeahead, quick find, canvas/flow solutions, email validation, audit retention) | `--name <column> --value <value>` — accepts any org column, not just the legacy audit ones |
| **Python SDK — OrgDB XML** | Keys inside the `orgdborgsettings` XML blob (MCP, search, Fabric, Work IQ, TDS endpoint, attachment security, ownership, address records, block unmanaged, delete users, Excel AI) | Read XML → parse → modify → PATCH whole blob back on `organizations({id})` |
| **Python SDK — recyclebinconfigs** | Recycle bin on/off + retention days | CREATE/PATCH `recyclebinconfigs` entity record |
| **Python SDK — settingdefinition + organizationsettings** | App-level / plan-level security role toggles | Look up `settingdefinition` by `uniquename` → CREATE or PATCH `organizationsettings` row with `value` |

Do NOT write Python scripts for operations PAC CLI can handle. Do NOT mix mechanisms (e.g., don't hand-PATCH an org column that PAC CLI already covers).

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

## Allowed settings — hard allowlist

This skill is only permitted to **read or update** the 37 PPAC toggles listed below (mapped to 35 unique backend keys — `SearchAndCopilotIndexMode` covers two toggles, `auditretentionperiodv2` covers two). Any request to change any other setting (session timeout, autosave, upload size, abort timeout, archival, shadow lake, activities features, synapse, or any org column / OrgDB key / `organizationsettings` override not in this table) **must be refused** with: *"That setting is out of scope for dv-admin. Use the Power Platform admin center."*

Reading other settings is also out of scope — do not generate `pac org list-settings` without `--filter`, and do not dump the whole `orgdborgsettings` XML when the user's question is about a specific non-allowlisted setting.

### Organization entity columns — use PAC CLI (14)

Use `pac org list-settings --filter <column>` to read, `pac org update-settings --name <column> --value <value>` to write. PAC CLI accepts any column on the organization entity — not just the legacy audit ones.

| # | PPAC label | Column | Type |
|---|---|---|---|
| 1 | Start Auditing | `isauditenabled` | bool |
| 2 | Audit user access (Log access) | `isuseraccessauditenabled` | bool |
| 3 | Start Read Auditing (Read logs to Purview) | `isreadauditenabled` | bool |
| 4 | Plugin trace log setting | `plugintracelogsetting` | int: `0` Off, `1` Exception, `2` All |
| 5 | Single table search option | `tablescopeddvsearchinapps` | bool |
| 6 | Prevent slow keyword filter for quick find terms | `allowleadingwildcardsinquickfind` | int: `0` prevent, `1` allow (UI "prevent=On" flips to `0`) |
| 7 | Quick Find record limits | `quickfindrecordlimitenabled` | bool |
| 8 | Use quick find view for searching on grids/subgrids | `usequickfindviewforgridsearch` | bool |
| 9 | Canvas apps in Dataverse solutions by default | `enablecanvasappsinsolutionsbydefault` | bool |
| 10 | Cloud flows in Dataverse solutions by default | `enableflowsinsolutionbydefault` | bool (note: `solution` singular) |
| 11 | Enable email address validation (preview) | `isemailaddressvalidationenabled` | bool |
| 12 | Minimum number of characters to trigger typeahead | `lookupcharactercountbeforeresolve` | int (0–MAX_INT, null = feature off) |
| 13 | Delay between character inputs that trigger a search | `lookupresolvedelayms` | int ms (default 250) |
| 14 | Audit log retention policy / Custom retention period (days) | `auditretentionperiodv2` | int days (`-1` = Forever; presets 30/90/180/365/730/2555; max 365000) |

### OrgDB XML keys — use Python SDK on `orgdborgsettings` blob (17)

Read/modify/PATCH the XML blob on `organizations({id})`. PascalCase is significant — `IsMCPEnabled`, not `IsMcpEnabled`.

| # | PPAC label | XML key | Type |
|---|---|---|---|
| 15 | Allow MCP clients to interact with Dataverse MCP server | `IsMCPEnabled` | bool |
| 16 | Advanced Settings (non-Copilot Studio MCP clients) | `IsMCPPreviewEnabled` | bool |
| 17 | Dataverse search / Search for records in Microsoft 365 apps | `SearchAndCopilotIndexMode` | int 0–3 (see truth table below — one key, two UI toggles) |
| 18 | Link Dataverse tables with Microsoft Fabric workspace | `IsLinkToFabricEnabled` | bool |
| 19 | Define Dataverse virtual tables using Fabric OneLake data | `IsFabricVirtualTableEnabled` | bool |
| 20 | Allow data availability in Microsoft 365 Copilot | `ShowDataInM365Copilot` | bool |
| 21 | Turn on Dataverse intelligence (Work IQ) for agents | `EnableWorkIQ` | bool |
| 22 | Block unmanaged customizations in environment | `IsLockdownOfUnmanagedCustomizationEnabled` | bool |
| 23 | Enable security on Attachment entity | `EnableSecurityOnAttachment` | bool |
| 24 | Enable TDS endpoint | `EnableTDSEndpoint` | bool |
| 25 | Enable user level access control for TDS endpoint | `AllowAccessToTDSEndpoint` | bool |
| 26 | Record ownership across business units | `EnableOwnershipAcrossBusinessUnits` | bool |
| 27 | Disable empty address record creation | `CreateOnlyNonEmptyAddressRecordsForEligibleEntities` | bool |
| 28 | Enable deletion of address records | `EnableDeleteAddressRecords` | bool |
| 29 | Block deletion of OOB attribute maps | `BlockDeleteManagedAttributeMap` | bool |
| 30 | Enable delete disabled users | `EnableSystemUserDelete` | bool |
| 31 | Import Excel to existing table with AI-assisted mapping | `IsExcelToExistingTableWithAssistedMappingEnabled` | bool |

**`SearchAndCopilotIndexMode` truth table** (one int encodes two UI toggles):

| Value | "Dataverse search" | "Search for records in M365 apps" (Copilot) |
|---|---|---|
| `0` | Off | On |
| `1` | On | On |
| `2` | Off | Off |
| `3` | On | Off |

### recyclebinconfigs entity — use Python SDK (2, **org-level only**)

These two toggles operate on the **organization-level** `recyclebinconfigs` row (filtered by the organization entity's MetadataId). Per-table recycle bin enable/disable is **out of scope** — PPAC only exposes the org-level on/off + cleanup days. Refuse requests like "enable recycle bin for `contact` only".

| # | PPAC label | Field | Notes |
|---|---|---|---|
| 32 | Keep deleted Dataverse records (on/off) | `statecode` + `statuscode` + `isreadyforrecyclebin` | Org-level row only. See "Recycle Bin Configuration" section — always send `isreadyforrecyclebin: true` on enable |
| 33 | Keep deleted records (days) | `cleanupintervalindays` | Org-level row only. int days; `-1` = never auto-purge; max 30 (when UI shows "30 days" with retention, stored as `-1`) |

### settingdefinition + organizationsettings — use Python SDK (2)

These live in a join: `settingdefinition` holds the definition (default value, datatype), `organizationsettings` holds the org-level override. No override row means the defaultvalue applies.

| # | PPAC label | `settingdefinition.uniquename` | Type |
|---|---|---|---|
| 34 | Enable app level security roles for canvas apps | `PowerAppsAppLevelSecurityRolesEnabled` | bool (string `"true"`/`"false"`) |
| 35 | Enable plan level security roles for plan designer | `PlanShareSecurityRolesEnabled` | bool (string `"true"`/`"false"`) |

Bulk delete, retention/archival jobs, and role assignment are covered elsewhere in this skill and remain in scope — this allowlist is about **environment/org/orgdb settings** only.

## Preview Before Running — Scope by Operation Type

Two rules, different strictness:

- **Destructive / stateful operations** (bulk delete schedule/cancel/pause/resume, org-settings update, OrgDB-settings update, recycle bin toggle or interval change, role assignment, self-elevate, retention set/enable-entity) — preview the action in plain prose: what's changing, new value, and which environment(s), using placeholders (`<ENV_URL>`, `<USER_EMAIL>`) for anything unknown. Ask for confirmation and missing values in the same turn. Skip the raw command block; the user shouldn't need to read CLI syntax to approve a change.
- **Read-only operations** (list-settings, list jobs, show job, read recycle bin status, read OrgDB settings) — a one-sentence prose preview is enough.

**Key principle:** the user should be able to evaluate what's about to happen from your first response. A bare *"which environment?"* fails that test; a one-line prose preview passes it.

### Examples

<example operation="pause bulk delete job (destructive — all info given)">
<user>Pause the bulk delete job with ID 12345678-1234-1234-1234-123456789012</user>
<bad>The command requires approval. Please confirm to pause the job.</bad>
<good>I'll pause bulk delete job `12345678-1234-1234-1234-123456789012` on the active environment. Confirm to proceed.</good>
</example>

<example operation="read recycle bin status (read-only — prose is enough)">
<user>What's the current recycle bin status?</user>
<bad>Please provide your environment URL so I can check.</bad>
<bad>Runs `pac org fetch` against `recyclebinconfig` — PAC CLI does NOT manage recycle bin. Always use the Web API via Python.</bad>
<good>Recycle bin lives in the `recyclebinconfigs` entity — PAC CLI can't read it. I'll run the "Read Recycle Bin Status" snippet in the Recycle Bin Configuration section below (read-only, no confirmation needed). Provide your environment URL.</good>
</example>

<example operation="audit status across N environments (read-only but multi-call — teach the pattern)">
<user>Tell me audit status of these 5 environments</user>
<bad>Runs `pac env select` then `pac org fetch --entity organization --attributes isauditenabled` once per environment, sequentially, across N separate bash calls.</bad>
<bad>Falls back to Python / `urllib` / the Web API after `pac org fetch` output is hard to parse.</bad>
<good>I'll read `isauditenabled` across all 5 environments in parallel (one batch, single `wait`), then render the results as a table. `pac org list-settings` is the only command for reading org settings — never `pac org fetch` or `pac env select` + anything.</good>
</example>

<example operation="disable MCP (destructive OrgDB write — prose + snippet reference)">
<user>Disable MCP for my environment</user>
<bad>Please provide your environment URL so I can disable MCP.</bad>
<good>MCP is the `IsMCPEnabled` key in the `orgdborgsettings` XML blob — PAC CLI can't modify it. I'll run the "Update or add an OrgDB setting" snippet in the OrgDB Settings section with `SETTING_NAME="IsMCPEnabled"`, `SETTING_VALUE="false"`. Provide your environment URL and confirm to proceed.</good>
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

#### Allowed Settings (14 org columns)

`pac org update-settings --name <column>` accepts any column on the `organization` entity, not just the legacy audit ones — verified against real orgs.

| Setting Name | Type | Values | PPAC label |
|-------------|------|--------|------------|
| `isauditenabled` | bool | `true` / `false` | Start Auditing |
| `isuseraccessauditenabled` | bool | `true` / `false` | Audit user access (Log access) |
| `isreadauditenabled` | bool | `true` / `false` | Start Read Auditing (Read logs to Purview) |
| `plugintracelogsetting` | option | `0` Off, `1` Exception, `2` All | Plugin trace log setting |
| `tablescopeddvsearchinapps` | bool | `true` / `false` | Single table search option |
| `allowleadingwildcardsinquickfind` | int | `0` = prevent slow filter (UI "Prevent" ON), `1` = allow | Prevent slow keyword filter for quick find terms |
| `quickfindrecordlimitenabled` | bool | `true` / `false` | Quick Find record limits |
| `usequickfindviewforgridsearch` | bool | `true` / `false` | Use quick find view for searching on grids/subgrids |
| `enablecanvasappsinsolutionsbydefault` | bool | `true` / `false` | Canvas apps in Dataverse solutions by default |
| `enableflowsinsolutionbydefault` | bool | `true` / `false` | Cloud flows in Dataverse solutions by default (note: `solution` singular, no `s`) |
| `isemailaddressvalidationenabled` | bool | `true` / `false` | Enable email address validation (preview) |
| `lookupcharactercountbeforeresolve` | int | `0`–MAX_INT (null = feature off) | Minimum number of characters to trigger typeahead search |
| `lookupresolvedelayms` | int | milliseconds (default `250`) | Delay between character inputs that trigger a search |
| `auditretentionperiodv2` | int | `-1` = Forever; presets `30`, `90`, `180`, `365`, `730`, `2555`; custom integer `30`–`365000` (PPAC validates this range; `< 30` or `> 365000` fails) | Audit log retention policy / Custom retention period (days) |

Any other org column (`isautosaveenabled`, `maxuploadfilesize`, `sessiontimeoutenabled`, `sessiontimeoutinmins`, `inaborttimeoutenabled`, `inaborttimeoutinmins`, etc.) is **out of scope** — refuse and direct the user to the Power Platform admin center.

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

Three patterns require Python SDK:

| Setting type | Where it lives | How to update |
|---|---|---|
| Top-level org columns (14 allowlisted — audit, typeahead, quick find, canvas/flow solutions, email validation, audit retention, etc.) | Organization entity columns | **PAC CLI** — `pac org update-settings --name <column>` (accepts any org column) |
| OrgDB settings (17 allowlisted — MCP, search, Fabric, Work IQ, TDS, attachment security, ownership, address records, block unmanaged, delete users, Excel AI) | XML inside `orgdborgsettings` column | **Python SDK** — fetch XML, parse, modify, PATCH back |
| Recycle bin (**org-level only**) | `recyclebinconfigs` entity, row filtered by the organization entity's MetadataId | **Python SDK** — CREATE/PATCH `recyclebinconfigs(<id>)`. Per-table toggles are out of scope — PPAC only exposes the org-level on/off + cleanup days |
| Settings-definition overrides (2 allowlisted — app/plan security roles) | `settingdefinition` + `organizationsettings` join | **Python SDK** — look up `settingdefinitionid` by `uniquename`, then CREATE/PATCH `organizationsettings` row |

---

### OrgDB Settings (orgdborgsettings XML)

Settings like search mode, MCP, copilot features, fabric, and retention live inside the `orgdborgsettings` XML blob. The XML uses **direct PascalCase elements** (NOT `<pair>` tags):

```xml
<OrgSettings>
  <IsMCPEnabled>true</IsMCPEnabled>
  <SearchAndCopilotIndexMode>0</SearchAndCopilotIndexMode>
  <IsLinkToFabricEnabled>true</IsLinkToFabricEnabled>
  <IsFabricVirtualTableEnabled>false</IsFabricVirtualTableEnabled>
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

**Allowed OrgDB settings (17 keys — PascalCase, case-sensitive):**

| Setting | Type | Values | PPAC label |
|---|---|---|---|
| `IsMCPEnabled` | bool | `true` / `false` | Allow MCP clients to interact with Dataverse MCP server |
| `IsMCPPreviewEnabled` | bool | `true` / `false` | Advanced Settings (enable non-Copilot Studio MCP clients) |
| `SearchAndCopilotIndexMode` | int | `0` Search Off / Copilot On; `1` Both On; `2` Both Off; `3` Search On / Copilot Off | Dataverse search + Search for records in Microsoft 365 apps (one key, two UI toggles — see truth table above) |
| `IsLinkToFabricEnabled` | bool | `true` / `false` | Link Dataverse tables with Microsoft Fabric workspace |
| `IsFabricVirtualTableEnabled` | bool | `true` / `false` | Define Dataverse virtual tables using Fabric OneLake data |
| `ShowDataInM365Copilot` | bool | `true` / `false` | Allow data availability in Microsoft 365 Copilot |
| `EnableWorkIQ` | bool | `true` / `false` | Turn on Dataverse intelligence (Work IQ) for agents |
| `IsLockdownOfUnmanagedCustomizationEnabled` | bool | `true` / `false` | Block unmanaged customizations in environment |
| `EnableSecurityOnAttachment` | bool | `true` / `false` | Enable security on Attachment entity |
| `EnableTDSEndpoint` | bool | `true` / `false` | Enable TDS endpoint |
| `AllowAccessToTDSEndpoint` | bool | `true` / `false` | Enable user level access control for TDS endpoint (requires TDS endpoint enabled first) |
| `EnableOwnershipAcrossBusinessUnits` | bool | `true` / `false` | Record ownership across business units |
| `CreateOnlyNonEmptyAddressRecordsForEligibleEntities` | bool | `true` / `false` | Disable empty address record creation (affects Account, Contact, Lead) |
| `EnableDeleteAddressRecords` | bool | `true` / `false` | Enable deletion of address records |
| `BlockDeleteManagedAttributeMap` | bool | `true` / `false` | Block deletion of OOB attribute maps |
| `EnableSystemUserDelete` | bool | `true` / `false` | Enable delete disabled users |
| `IsExcelToExistingTableWithAssistedMappingEnabled` | bool | `true` / `false` | Import Excel to existing table with AI-assisted mapping |

Every other OrgDB key (`IsRetentionEnabled`, `IsArchivalEnabled`, `IsDVCopilotForTextDataEnabled`, `IsShadowLakeEnabled`, `IsCommandingModifiedOnEnabled`, `CanCreateApplicationStubUser`, `AllowRoleAssignmentOnDisabledUsers`, `EnableActivitiesFeatures`, `TDSListenerInitialized`, `AzureSynapseLinkIncrementalUpdateTimeInterval`, etc.) is **out of scope** — refuse and direct the user to the Power Platform admin center. Do NOT dump the whole `orgdborgsettings` XML to "discover" other settings for the user.

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

### Critical: Always Send `isreadyforrecyclebin: true` on Enable

**Every enable payload (POST or PATCH) must set `isreadyforrecyclebin: true`.**

Without it, the platform defaults `isreadyforrecyclebin` to `false` (CREATE) or leaves it null (PATCH), which forces the platform into the **asynchronous** opt-in path — a `ProcessRecycleBin` background job is queued and your HTTP call returns success before any entity-level work happens. In that window, platform metadata operations (solution imports, attribute publish, async handlers) can race against the partial state and throw `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin`. Sending `isreadyforrecyclebin: true` forces the synchronous, globally-locked opt-in path, which fans out to every entity inside one transaction.

### Critical: Disable via PATCH, Not DELETE

**Disable with `PATCH statecode=1, statuscode=2, isreadyforrecyclebin=false`. Do not DELETE the org config record.**

DELETE enqueues an async opt-out (when `RecycleBinOptOutOrgAsynchronously` is on) while leaving the org row marked Inactive and child entity rows still flagged `IsReadyForRecycleBin=true, IsDisabled=false`. Any platform operation that runs between your DELETE and your next enable will see "org is enabled" from the config cache, proceed to `RecycleBinConfigService.Update(<entity-config>)` synchronously, and throw when the DB-backed `IsRecycleBinEnabledForEntity` check disagrees. A PATCH-based disable takes the synchronous `OptOutOrganization` path under the customization lock, cleanly cascading to every entity.

### Wait for in-flight `ProcessRecycleBin` Jobs Between Toggles

Every enable/disable queues a `ProcessRecycleBin` async operation (OperationType = `50`). Do NOT enable-then-disable-then-enable rapidly; the jobs share a dependency token and can interleave in ways that corrupt state. Before any second toggle, poll `AsyncOperation` until no `ProcessRecycleBin` row is `Queued` or `InProgress` for this org.

### Enable Recycle Bin

Two cases depending on whether a config record already exists. Both send `isreadyforrecyclebin: true`.

```python
# ... (same imports, headers, ORGANIZATION_ENTITY_ID, and fetch as above)
# SDK does not support recyclebinconfigs entity

CLEANUP_DAYS = 30  # default; -1 means records in recycle bin are never auto-purged

# Pre-flight: wait for any in-flight ProcessRecycleBin async jobs to finish
import time
def wait_for_recyclebin_async_jobs(env_url, headers, timeout_s=120):
    # OperationType 50 = ProcessRecycleBin; StateCode 0=Ready/1=Suspended/2=Locked are all "not done"
    filter_q = urllib.parse.quote("operationtype eq 50 and statecode ne 3")
    url = f"{env_url}/api/data/v9.2/asyncoperations?$filter={filter_q}&$select=asyncoperationid,statecode,statuscode,name"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            pending = json.loads(resp.read()).get("value", [])
        if not pending:
            return
        print(f"  waiting on {len(pending)} ProcessRecycleBin job(s)...", flush=True)
        time.sleep(5)
    raise RuntimeError("Timed out waiting for pending ProcessRecycleBin async jobs")

wait_for_recyclebin_async_jobs(env_url, headers)

if not records:
    # Case 1: No config exists -- CREATE a new one
    # extensionofrecordid binds to the entities() metadata endpoint, NOT organizations()
    payload = {
        "extensionofrecordid@odata.bind": f"entities({ORGANIZATION_ENTITY_ID})",
        "extensionofrecordid@OData.Community.Display.V1.FormattedValue": "OrganizationId",
        "isreadyforrecyclebin": True,   # MUST be true -- forces sync opt-in under the global lock
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
    # Case 2: Config exists -- PATCH statecode/statuscode, cleanup interval, and isreadyforrecyclebin
    config_id = records[0]["recyclebinconfigid"]
    payload = {
        "cleanupintervalindays": CLEANUP_DAYS,
        "statecode": 0,
        "statuscode": 1,
        "isreadyforrecyclebin": True,   # MUST be true -- without this, UpdateInternal routes through updateAsync
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup (HTTP {resp.status})", flush=True)

# Post-flight: drain the sync opt-in fan-out before returning control
wait_for_recyclebin_async_jobs(env_url, headers)
```

### Disable Recycle Bin

**Disable = PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`.** This triggers the synchronous `OptOutOrganization` path which cascades cleanly to every entity config.

```python
# ... (same fetch as above to get config_id)
# SDK does not support recyclebinconfigs entity

wait_for_recyclebin_async_jobs(env_url, headers)   # drain first

if records:
    config_id = records[0]["recyclebinconfigid"]
    payload = {
        "statecode": 1,                 # Inactive
        "statuscode": 2,                # Inactive
        "isreadyforrecyclebin": False,  # required to take the isOptOut branch in UpdateInternal
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin disabled (HTTP {resp.status})", flush=True)
else:
    print("Recycle bin is already disabled (no config record)", flush=True)

wait_for_recyclebin_async_jobs(env_url, headers)   # drain the opt-out fan-out
```

**Do NOT use DELETE to disable.** Legacy guidance (including older Admin Center behavior) suggested DELETE, but DELETE enqueues an async opt-out and can leave per-entity configs orphaned — any platform metadata operation that runs before cleanup finishes will throw `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin` on an unrelated entity.

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
- **Enable payloads MUST include `isreadyforrecyclebin: true`.** Without it, CREATE defaults to false and PATCH sends null — both force the async opt-in path and expose the org to cache-vs-DB races during platform metadata operations.
- **Disable = PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`**, not DELETE. DELETE enqueues an async opt-out and can leave per-entity configs orphaned.
- **Drain `ProcessRecycleBin` async jobs between toggles.** Query `asyncoperations` for `operationtype eq 50 and statecode ne 3` before and after each enable/disable.
- **Cleanup days**: default is `-1` (no auto-cleanup). Max is `30`. When the UI shows "30 days", the API stores `-1` internally (the platform applies a 30-day default).
- Solution-managed configs (e.g., `msdyn_recurringsalesaction`) cannot be enabled/disabled via API.
- **Per-table recycle bin toggles are out of scope.** PPAC only exposes the org-level on/off + cleanup days — if a user asks to enable/disable recycle bin for a specific table (e.g., "turn on recycle bin for `contact` only"), refuse with: *"Per-table recycle bin is out of scope for dv-admin. Use the Power Platform admin center."* The `recyclebinconfigs` entity does hold per-entity rows, but this skill only reads/writes the org-level row (filtered by the organization entity's MetadataId).

---

### Settings-Definition Overrides (app/plan security roles)

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

---

## Safety Rules

- **Always confirm** before scheduling a bulk delete — this is destructive
- If `--fetchxml` is omitted, warn that ALL records in the table will be deleted
- For system tables (`systemuser`, `businessunit`, `organization`), warn that deleting may break the environment
- **Always confirm** before changing org settings that affect all users
- For multi-environment updates, show the list of environments and get confirmation first
- For OrgDB settings, warn that incorrect values can break environment features
- For recycle bin, warn that reducing cleanup interval will permanently delete records sooner
- For recycle bin enable/disable: always set `isreadyforrecyclebin` explicitly (true on enable, false on disable), use PATCH for disable (not DELETE), and drain any in-flight `ProcessRecycleBin` async jobs before toggling. Omitting these can produce `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin` on unrelated platform operations.


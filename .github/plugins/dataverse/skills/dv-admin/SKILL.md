---
name: dv-admin
description: Environment-level Dataverse administration — bulk delete, retention/archival, organization settings, OrgDB settings, recycle bin, audit, and the 37 allowlisted PPAC toggles. Use when the user wants to clean up data at scale, configure audit, change environment settings, or manage retention policies.
---

# Skill: Environment Admin — Bulk Delete, Retention, Org Settings, OrgDB, Recycle Bin

> ## ⚠️ Critical safety rules — read first
>
> 1. **Bulk delete is irreversible and bypasses the recycle bin.** `pac data bulk-delete schedule` without `--fetchxml` deletes every record in the table. Refuse to run until the user explicitly says ALL (or ALL RECORDS) **and** the entity logical name — e.g., `"yes, delete ALL records in contact"`. Bare `"yes"` rejected. Empty-filter FetchXML does NOT bypass this gate. See [Bulk Delete Commands](#bulk-delete-commands) for the full rule and disambiguation flow.
> 2. **Settings allowlist is hard.** Only the 37 PPAC toggles in [Allowed settings](#allowed-settings--hard-allowlist) may be read or updated. Any other setting **must be refused**: *"That setting is out of scope for dv-admin. Use the Power Platform admin center."*
> 3. **Recycle bin disable is PATCH, never DELETE.** `PATCH statecode=1, statuscode=2, isreadyforrecyclebin=false`. DELETE enqueues async opt-out and orphans per-entity configs — see [`references/recycle-bin.md`](references/recycle-bin.md).
> 4. **System tables warning.** Unfiltered bulk delete on `systemuser`, `businessunit`, `organization`, or `role` breaks the environment. Warn additionally before running.

**Four mechanisms — pick based on where the setting lives:**

| Mechanism | Use for | How |
|---|---|---|
| **PAC CLI** (`pac org update-settings` / `list-settings`) | Columns on the `organization` entity (audit, plugin trace, typeahead, quick find, canvas/flow solutions, email validation, audit retention) | `--name <column> --value <value>` — accepts any org column, not just the legacy audit ones |
| **Python SDK — OrgDB XML** | Keys inside the `orgdborgsettings` XML blob (MCP, search, Fabric, Work IQ, TDS endpoint, attachment security, ownership, address records, block unmanaged, delete users, Excel AI) | Read XML → parse → modify → PATCH whole blob back on `organizations({id})` |
| **Python SDK — recyclebinconfigs** | Recycle bin on/off + retention days | CREATE/PATCH `recyclebinconfigs` entity record |
| **Python SDK — settingdefinition + organizationsettings** | App-level / plan-level security role toggles | Look up `settingdefinition` by `uniquename` → CREATE or PATCH `organizationsettings` row with `value` |

Do NOT write Python scripts for operations PAC CLI can handle. Do NOT mix mechanisms (e.g., don't hand-PATCH an org column that PAC CLI already covers).

## Skill boundaries

Use **dv-data** for record CRUD and sample data, **dv-metadata** for tables / columns / relationships, **dv-query** for reading records, **dv-solution** for solution export/import, **dv-security** for roles and self-elevate, `pac admin --help` for tenant governance (DLP, env lifecycle).

## Allowed settings — hard allowlist

The 37 PPAC toggles below are the only ones this skill may read or update (35 unique backend keys — `SearchAndCopilotIndexMode` and `auditretentionperiodv2` each cover two toggles). Examples that are **out of scope and must be refused** per the safety rule above: `sessiontimeoutinmins`, `isautosaveenabled`, `maxuploadfilesize`, `inaborttimeoutinmins`, `IsArchivalEnabled`, `IsShadowLakeEnabled`, `EnableActivitiesFeatures`. Do not run `pac org list-settings` without `--filter`, and do not dump the whole `orgdborgsettings` XML for a non-allowlisted setting.

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

PascalCase is significant (`IsMCPEnabled`, not `IsMcpEnabled`). Full key list with PPAC labels and types lives in [`references/orgdb-settings.md`](references/orgdb-settings.md). Notable keys: `IsMCPEnabled`, `IsMCPPreviewEnabled`, `SearchAndCopilotIndexMode`, `IsLinkToFabricEnabled`, `IsFabricVirtualTableEnabled`, `ShowDataInM365Copilot`, `EnableWorkIQ`, `IsLockdownOfUnmanagedCustomizationEnabled`, `EnableSecurityOnAttachment`, `EnableTDSEndpoint`, `AllowAccessToTDSEndpoint`, `EnableOwnershipAcrossBusinessUnits`, `CreateOnlyNonEmptyAddressRecordsForEligibleEntities`, `EnableDeleteAddressRecords`, `BlockDeleteManagedAttributeMap`, `EnableSystemUserDelete`, `IsExcelToExistingTableWithAssistedMappingEnabled`.

**`SearchAndCopilotIndexMode`** is one int (0–3) that encodes two UI toggles — Dataverse search × M365 Copilot search:

| Value | Dataverse search | M365 Copilot search |
|---|---|---|
| `0` | Off | On |
| `1` | On | On |
| `2` | Off | Off |
| `3` | On | Off |

### recyclebinconfigs entity — use Python SDK (2, org-level only)

Two toggles operate on the org-level `recyclebinconfigs` row (filtered by the organization entity's MetadataId): on/off (`statecode` + `statuscode` + `isreadyforrecyclebin`) and cleanup days (`cleanupintervalindays`). Per-table toggles are **out of scope** — refuse requests like "enable recycle bin for `contact` only". Full lifecycle in [`references/recycle-bin.md`](references/recycle-bin.md).

### settingdefinition + organizationsettings — use Python SDK (2)

Two allowlisted toggles, both bool stored as string: `PowerAppsAppLevelSecurityRolesEnabled` (canvas apps), `PlanShareSecurityRolesEnabled` (plan designer). Read default from `settingdefinition`, CREATE/PATCH `organizationsettings` for the override. Full Python in [`references/settings-overrides.md`](references/settings-overrides.md).

## Preview Before Running

- **Destructive / stateful** (bulk delete schedule/cancel/pause/resume, settings updates, recycle bin toggle, role assignment, self-elevate, retention set) — preview in prose: what's changing, new value, target environment(s). Use placeholders (`<ENV_URL>`) for unknowns and ask for missing values in the same turn. Skip the raw CLI block.
- **Read-only** (list-settings, show job, read OrgDB / recycle bin status) — one-sentence prose preview is enough.

The user must be able to evaluate the action from your first response. A bare *"which environment?"* fails; a one-line prose preview passes.

### Examples

**Pause bulk delete (destructive, ID supplied):**
- ❌ "The command requires approval. Please confirm to pause the job."
- ✅ "I'll pause bulk delete job `<job-id>` on the active environment. Confirm to proceed."

**Audit status across N environments (read-only, multi-call):**
- ❌ Sequential `pac org fetch` per env, or starting with Python/SDK because it "feels like a query."
- ✅ "I'll run `pac org list-settings --filter audit` in parallel across all N environments (one `&`-batch, single `wait`)."

## How to Read or Update Org Settings

**Org settings always go through `pac org list-settings` / `pac org update-settings`** — never raw Web API, FetchXML, PowerShell, or Python for org columns. Use `--filter <substring>` for category reads in one call. Multi-environment work runs in parallel via `&` + `wait` in ONE bash call.

**Single setting:**
```bash
pac org list-settings --filter isauditenabled --environment <url>
```

**Category read** (returns every match, e.g. all audit settings in one call):
```bash
pac org list-settings --filter audit --environment <url>
```

**Multi-environment — parallel in ONE bash call:**
```bash
pac org list-settings --filter audit --environment <url1> &
pac org list-settings --filter audit --environment <url2> &
pac org list-settings --filter audit --environment <url3> &
wait
```

If `pac org list-settings` fails for a setting, that setting is NOT an org column — check the mechanism routing in the four-mechanism table at the top, then use the appropriate Python pattern. Do NOT fall back to Web API, PowerShell, FetchXML, or `pac org fetch` for org columns.

---

## Prerequisites

- PAC CLI **latest .NET Framework build** — `pac data bulk-delete` and `pac data retention` are only in the .NET Framework build, not the `dotnet tool` cross-platform version. Check with `pac help` (look for "Version: x.x.x (.NET Framework ...)"); if it shows `.NET 10` or `.NET 8`, run `pac install latest && pac use latest` to switch.
- Authenticated (`pac auth create`), active profile (`pac auth list`), and System Administrator privilege on the target environment.

## Multi-Environment Operations — Always Parallel

The same `&` + `wait` pattern from `list-settings` applies to every multi-env operation (`update-settings`, `bulk-delete`, etc.) — N backgrounded calls in ONE bash call, never sequential or `for` loops.

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

`pac data bulk-delete schedule` without `--fetchxml` targets every record in the table and is irreversible (does not go through recycle bin). Required gate:

1. **Refuse until the user explicitly acknowledges** with the word ALL (or ALL RECORDS) **and** the entity logical name — e.g., `"yes, delete ALL records in contact"`. Bare `"yes"` rejected.
2. **Disambiguate vague asks** ("clean up old emails") — propose a FetchXML filter with date / statecode / owner conditions before showing any command.
3. **Empty-filter FetchXML doesn't bypass the gate** — `<filter/>` or `<filter><condition><value/></condition></filter>` still targets every record.
4. **Scope:** applies to `bulk-delete schedule` only. `cancel`, `pause`, `resume`, `show`, `list` don't need it.

For system tables (`systemuser`, `businessunit`, `organization`, `role`), additionally warn that unfiltered bulk delete breaks the environment.

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

**Args:** `--name <column>` (required), `--value <value>` (required; `true`/`false` for bool, int for option sets), `--environment <url>` (optional). Allowed columns are the 14 listed in [Allowed settings](#allowed-settings--hard-allowlist) — anything else is out of scope.

**Batch workflow:** `pac admin list` → filter targets → confirm → run all `update-settings` calls in parallel (`&` + `wait`) → render summary table.

---

## Advanced Settings (Python SDK — PAC CLI Cannot Handle These)

OrgDB, recycle bin, and settings-definition overrides each need raw Web API or the Python SDK — PAC CLI does not cover them. The four-mechanism routing table at the top of this skill ([§ Skill](#skill-environment-admin--bulk-delete-retention-org-settings-orgdb-recycle-bin)) maps each setting to its mechanism. Sub-sections below summarise the patterns and link to the references for full Python.

### OrgDB Settings (orgdborgsettings XML)

OrgDB settings live as PascalCase XML elements inside the `orgdborgsettings` column of the `organizations` entity. PAC CLI cannot read or write these — use raw Web API.

**Quick reference:** `GET /organizations?$select=organizationid,orgdborgsettings` → parse XML with `xml.etree.ElementTree` → modify or `SubElement` → `PATCH /organizations({id})` with the serialized XML.

For the read / update / remove Python patterns and the 17-key allowlist, see [`references/orgdb-settings.md`](references/orgdb-settings.md). Keys are case-sensitive (`IsMCPEnabled`, not `IsMcpEnabled`).

### Recycle Bin Configuration

Recycle bin settings live in the `recyclebinconfigs` entity (NOT `orgdborgsettings`). PAC CLI cannot manage them — use raw Web API.

**Quick reference:** filter `recyclebinconfigs` by `_extensionofrecordid_value eq <ORG_ENTITY_METADATA_ID>` (the org-level metadata ID is a system constant: `e1bd1119-6e9d-45a4-bc15-12051e65a0bd`).

- **Enable:** PATCH `statecode=0, statuscode=1, isreadyforrecyclebin=true` (or POST a new config). `isreadyforrecyclebin: true` is required to force the synchronous opt-in path.
- **Disable:** PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`. **Do NOT DELETE** — it enqueues async opt-out and orphans per-entity configs.
- **Drain in-flight `ProcessRecycleBin` async jobs** (`operationtype eq 50, statecode ne 3`) before any second toggle.

For the full Python lifecycle (read / enable / disable / async-drain helper), the cache-vs-DB race explanation, and the per-table out-of-scope rule, see [`references/recycle-bin.md`](references/recycle-bin.md).

### Settings-Definition Overrides (app/plan security roles)

Two allowlisted toggles (`PowerAppsAppLevelSecurityRolesEnabled`, `PlanShareSecurityRolesEnabled`) live in a join: `settingdefinition` (defaults) + `organizationsettings` (overrides). PAC CLI doesn't manage these.

**Quick reference:** look up the `settingdefinitionid` by `uniquename`, then either CREATE an `organizationsettings` row with `value` (string `"true"`/`"false"`) or PATCH the existing row. DELETE on the override row reverts to the default.

For the read + idempotent CREATE/PATCH Python and the gating notes, see [`references/settings-overrides.md`](references/settings-overrides.md).

## Operational confirmation rules

The four rules in the safety callout at the top of this file cover the irreversible / destructive cases. The rules below cover the non-destructive but still impactful operations:

- Confirm before changing org settings that affect all users.
- For multi-environment updates, show the list of target environments and get confirmation first.
- For OrgDB settings, warn that incorrect values can break environment features.
- For recycle bin cleanup interval changes, warn that reducing the interval permanently deletes recycled records sooner.
- For recycle bin enable/disable specifically: always set `isreadyforrecyclebin` explicitly (true on enable, false on disable), and drain any in-flight `ProcessRecycleBin` async jobs before any second toggle. Omitting these can produce `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin` on unrelated platform operations.


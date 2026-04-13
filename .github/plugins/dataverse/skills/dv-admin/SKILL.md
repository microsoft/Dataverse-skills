---
name: dv-admin
description: >
  Environment-level Dataverse administration: bulk delete, data retention/archival,
  and organization settings (audit, plugin trace, session timeout).
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
  "enable audit for all environments", "developer environments audit".
  Do not use when: deleting individual records (use dv-data), deleting tables (use dv-metadata),
  exporting/importing data files (use dv-solution), querying records (use dv-query),
  assigning roles or self-elevating (use dv-security), creating sample data (use dv-data),
  tenant governance like DLP or environment lifecycle (use pac admin --help).
---

# Skill: Environment Admin — Bulk Delete, Retention, Org Settings

**This skill uses PAC CLI exclusively.** Do NOT write Python scripts, PowerShell scripts, or use `az account get-access-token`. Just run `pac` commands directly.

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
- A Dataverse environment with System Administrator or Bulk Delete privilege
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
# Delete all records in a table
pac data bulk-delete schedule --entity account

# Delete with a filter (FetchXML)
pac data bulk-delete schedule --entity activitypointer \
    --fetchxml "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>"

# With a custom job name and scheduled start time
pac data bulk-delete schedule --entity email \
    --fetchxml "<fetch><entity name='email'><filter><condition attribute='createdon' operator='lt' value='2024-06-01'/></filter></entity></fetch>" \
    --job-name "Cleanup old emails before 2024" \
    --start-time 2025-07-01T02:00:00Z

# Recurring daily cleanup
pac data bulk-delete schedule --entity activitypointer \
    --fetchxml "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>" \
    --job-name "Daily activity cleanup" \
    --recurrence "FREQ=DAILY;INTERVAL=1"

# Target a specific environment
pac data bulk-delete schedule --entity account \
    --environment https://myorg.crm.dynamics.com
```

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table (e.g., `account`, `activitypointer`, `email`) |
| `--fetchxml` | `-fx` | No | FetchXML query to filter records. If omitted, **all records** in the table are targeted |
| `--job-name` | `-jn` | No | Descriptive name for the job. Defaults to `Bulk Delete - <entity> - <timestamp>` |
| `--start-time` | `-st` | No | ISO 8601 start time (e.g., `2025-07-01T02:00:00Z`). Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 recurrence pattern (e.g., `FREQ=DAILY;INTERVAL=1`) |
| `--environment` | `-env` | No | Target environment URL or ID |

### List Bulk Delete Jobs

```bash
pac data bulk-delete list
pac data bulk-delete list --environment https://myorg.crm.dynamics.com
```

### Show Bulk Delete Job Details

```bash
pac data bulk-delete show --id <job-id>
```

### Pause / Resume / Cancel

```bash
pac data bulk-delete pause --id <job-id> --environment https://myorg.crm.dynamics.com
pac data bulk-delete resume --id <job-id> --environment https://myorg.crm.dynamics.com
pac data bulk-delete cancel --id <job-id> --environment https://myorg.crm.dynamics.com
```

**Cancel cannot be undone.** Records already deleted will not be restored.

---

## Common FetchXML Patterns

### Delete records older than a date

```xml
<fetch>
  <entity name="activitypointer">
    <filter>
      <condition attribute="createdon" operator="lt" value="2024-01-01"/>
    </filter>
  </entity>
</fetch>
```

### Delete records by status

```xml
<fetch>
  <entity name="email">
    <filter>
      <condition attribute="statecode" operator="eq" value="1"/>
      <condition attribute="createdon" operator="lt" value="2024-06-01"/>
    </filter>
  </entity>
</fetch>
```

### Delete records with null field

```xml
<fetch>
  <entity name="contact">
    <filter>
      <condition attribute="emailaddress1" operator="null"/>
    </filter>
  </entity>
</fetch>
```

---

## Retention / Archival Commands

Data retention moves old records to long-term storage (archive) without permanently deleting them.

### Agentic Flow

```
Step 1: pac data retention enable-entity --entity activitypointer
Step 2: pac data retention list
Step 3: pac data retention set --entity activitypointer --criteria "<fetchxml>..."
Step 4: pac data retention show --id <config-id>
```

### Commands

```bash
pac data retention list --environment https://myorg.crm.dynamics.com
pac data retention show --id <config-id> --environment https://myorg.crm.dynamics.com

pac data retention set --entity activitypointer \
    --criteria "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2023-01-01'/></filter></entity></fetch>" \
    --environment https://myorg.crm.dynamics.com

pac data retention enable-entity --entity activitypointer --environment https://myorg.crm.dynamics.com
pac data retention status --id <operation-id> --environment https://myorg.crm.dynamics.com
```

#### Arguments for `retention set`

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table |
| `--criteria` | `-c` | Yes | FetchXML defining which records to archive |
| `--start-time` | `-st` | No | ISO 8601 start time. Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 recurrence pattern |
| `--environment` | `-env` | No | Target environment URL or ID |

### When to Use Retention vs Bulk Delete

| Scenario | Use |
|----------|-----|
| Data no longer needed, can be permanently deleted | **Bulk Delete** |
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

## Safety Rules

- **Always confirm** before scheduling a bulk delete
- If `--fetchxml` is omitted, warn that ALL records will be deleted
- For system tables (`systemuser`, `businessunit`, `organization`), warn that deleting may break the environment
- Prefer `--start-time` for off-peak scheduling
- For large deletions, suggest a test run with a narrow filter first

---

## Quick Reference

### Bulk Delete

| Command | Key Arguments |
|---------|---------------|
| `pac data bulk-delete schedule` | `--entity`, `--fetchxml`, `--job-name`, `--start-time`, `--recurrence` |
| `pac data bulk-delete list` | `--environment` |
| `pac data bulk-delete show/pause/resume/cancel` | `--id` |

### Retention

| Command | Key Arguments |
|---------|---------------|
| `pac data retention enable-entity` | `--entity` |
| `pac data retention set` | `--entity`, `--criteria`, `--start-time`, `--recurrence` |
| `pac data retention list/show/status` | `--id` or `--environment` |

### JSON Output

```bash
pac data bulk-delete list --output json
pac data retention list --output json
```

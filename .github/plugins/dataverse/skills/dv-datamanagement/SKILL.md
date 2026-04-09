---
name: dv-datamanagement
description: >
  Schedule and manage data management operations: bulk delete, data retention/archival,
  organization settings, role assignment, and sample data generation.
  Use when: "bulk delete", "delete all records", "clean up old records", "schedule deletion",
  "data cleanup", "remove old data", "pause bulk delete", "cancel bulk delete", "resume job",
  "bulk delete job status", "list delete jobs", "manage bulk delete", "data management", "pac data",
  "retention", "archive", "archival", "set up retention", "retain old records",
  "long term retain", "data lifecycle", "enable archival", "enable retention",
  "retention policy", "archive records", "retention status",
  "org settings", "organization settings", "enable audit", "audit logs", "turn on auditing",
  "plugin trace", "session timeout", "auto save", "environment settings",
  "enable audit for all environments", "developer environments audit",
  "assign role", "system admin", "security role", "give me admin role",
  "assign system administrator", "role assignment", "make me admin",
  "create sample data", "seed data", "generate test records", "populate entity",
  "add sample records", "create dummy data", "generate sample accounts",
  "seed the account table", "create test data for".
  Do not use when: deleting individual records (use dv-data), deleting tables (use dv-metadata),
  exporting/importing data files (use dv-solution), querying records (use dv-query).
---

# Skill: Data Management

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. If you are about to run `npm install` or write a `.js` file, STOP -- you are going off-rails. See the overview skill's Hard Rules.

Manage Dataverse data lifecycle via PAC CLI: schedule bulk delete jobs, configure data retention/archival policies, manage organization settings, and generate sample data. Designed for IT admin agentic workflows.

## Skill Boundaries

| Need | Use instead |
|---|---|
| Delete a single record | **dv-data** (`client.records.delete()`) |
| Create/modify tables, columns, relationships | **dv-metadata** |
| Export or deploy solutions | **dv-solution** |
| Query or read records | **dv-query** |
| Bulk import from CSV | **dv-data** (multi-table import) |

---

## Prerequisites

- PAC CLI installed and authenticated (`pac auth create`)
- A Dataverse environment with System Administrator or Bulk Delete privilege
- Active auth profile: `pac auth list`
- Workspace initialized (`.env` and `scripts/auth.py` exist -- if not, run the `dv-connect` flow first)

---

## End-to-End Agentic Flow

This is the primary workflow. When a user asks about data cleanup, follow these steps in order.

**Before the first operation, confirm the target environment with the user.** See the Multi-Environment Rule in the overview skill.

### Step 1: Schedule bulk delete for cleanup targets

Based on the user's request, suggest bulk delete jobs for the tables they identify. **Always confirm with the user first.**

```bash
# Example: clean up old activity records (often the #1 consumer)
pac data bulk-delete schedule --entity activitypointer \
    --fetchxml "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>" \
    --job-name "Cleanup activities before 2024" \
    --environment https://myorg.crm.dynamics.com
```

### Step 2: Verify the job was scheduled

```bash
pac data bulk-delete show --id <job-id-from-step-1> --environment https://myorg.crm.dynamics.com
```

### Step 3: Monitor and manage the job

```bash
# List all jobs to see status
pac data bulk-delete list --environment https://myorg.crm.dynamics.com

# Pause a running job if needed
pac data bulk-delete pause --id <job-id> --environment https://myorg.crm.dynamics.com

# Resume a paused job
pac data bulk-delete resume --id <job-id> --environment https://myorg.crm.dynamics.com

# Cancel a job if necessary
pac data bulk-delete cancel --id <job-id> --environment https://myorg.crm.dynamics.com
```

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

Shows detailed information including:
- Job name and status (Waiting, In Progress, Completed, Paused, Failed, Cancelled)
- Target entity and FetchXML criteria
- Records processed, succeeded, failed
- Start/end times
- Created by and recurrence pattern

### Pause a Bulk Delete Job

```bash
pac data bulk-delete pause --id <job-id> --environment https://myorg.crm.dynamics.com
```

Pauses a currently running bulk delete job. The job can be resumed later with `resume`.

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--id` | `-id` | Yes | The bulk delete job ID (GUID) |
| `--environment` | `-env` | No | Target environment URL or ID |

### Resume a Bulk Delete Job

```bash
pac data bulk-delete resume --id <job-id> --environment https://myorg.crm.dynamics.com
```

Resumes a previously paused bulk delete job.

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--id` | `-id` | Yes | The bulk delete job ID (GUID) |
| `--environment` | `-env` | No | Target environment URL or ID |

### Cancel a Bulk Delete Job

```bash
pac data bulk-delete cancel --id <job-id> --environment https://myorg.crm.dynamics.com
```

Cancels a bulk delete job. **This action cannot be undone.** The job will be marked as cancelled and any records already deleted will not be restored.

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--id` | `-id` | Yes | The bulk delete job ID (GUID) |
| `--environment` | `-env` | No | Target environment URL or ID |

---

## Common FetchXML Patterns for Bulk Delete

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

### Delete records owned by a specific user

```xml
<fetch>
  <entity name="account">
    <filter>
      <condition attribute="ownerid" operator="eq" value="00000000-0000-0000-0000-000000000001"/>
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

Data retention moves old records to long-term storage (archive), reducing active database size without permanently deleting data. Archived records can later be purged if no longer needed.

### Extended Agentic Flow (Bulk Delete to Retention)

When bulk delete is not appropriate (data needs to be preserved for compliance), use retention instead:

```
Step 1: pac data retention enable-entity --entity activitypointer (ensure table supports archival)
Step 2: pac data retention list (check any existing policies)
Step 3: pac data retention set --entity activitypointer --criteria "<fetchxml>..." (create/update policy)
Step 4: Monitor execution via pac data retention show --id <config-id>
```

**Note**: Retention policies run automatically based on their schedule. There is no manual "run" command - policies execute on their configured schedule.

### List Retention Policies

```bash
pac data retention list --environment https://myorg.crm.dynamics.com
```

### Show Retention Policy Details

```bash
pac data retention show --id <config-id> --environment https://myorg.crm.dynamics.com
```

### Create or Update a Retention Policy

```bash
# Basic retention policy
pac data retention set --entity activitypointer \
    --criteria "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2023-01-01'/></filter></entity></fetch>" \
    --environment https://myorg.crm.dynamics.com

# With scheduled start time
pac data retention set --entity account \
    --criteria "<fetch><entity name='account'><filter><condition attribute='name' operator='like' value='test%'/></filter></entity></fetch>" \
    --start-time 2025-07-01T02:00:00Z

# Recurring daily retention
pac data retention set --entity email \
    --criteria "<fetch><entity name='email'><filter><condition attribute='createdon' operator='lt' value='2024-01-01'/></filter></entity></fetch>" \
    --recurrence "FREQ=DAILY;INTERVAL=1"
```

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table to configure retention for |
| `--criteria` | `-c` | Yes | FetchXML defining which records to retain/archive |
| `--start-time` | `-st` | No | ISO 8601 start time (e.g., `2025-07-01T02:00:00Z`). Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 recurrence pattern (e.g., `FREQ=DAILY;INTERVAL=1`) |
| `--environment` | `-env` | No | Target environment URL or ID |

### Enable Archival for a Table

Before creating retention policies, ensure the table supports archival:

```bash
pac data retention enable-entity --entity activitypointer --environment https://myorg.crm.dynamics.com
```

This command:
- Enables long-term retention (archival) capability for the specified table
- Uses the metadata API when available, falls back to `EnableArchivalRequest` if needed
- Required before creating retention policies for tables that don't have archival enabled

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table to enable archival for |
| `--environment` | `-env` | No | Target environment URL or ID |

### Check Retention Operation Status

```bash
pac data retention status --id <operation-id> --environment https://myorg.crm.dynamics.com
```

Shows the current status of a retention operation. Status values include: Waiting, In Progress, Completed, Failed, Cancelled.

### When to Use Retention vs Bulk Delete

| Scenario | Use |
|----------|-----|
| Data no longer needed, can be permanently deleted | **Bulk Delete** |
| Data must be preserved for compliance but is not actively used | **Retention** (archive) |

---

## Organization Settings Commands

View and update per-environment organization settings like audit, plugin trace logging, session timeouts, etc.

### List Organization Settings

```bash
# List all org settings
pac org list-settings --environment https://myorg.crm.dynamics.com

# Filter for specific settings
pac org list-settings --filter isauditenabled --environment https://myorg.crm.dynamics.com
```

Returns a structured view of key settings grouped by category:
- **Audit**: audit enabled, user access audit, read audit
- **General**: plugin trace log, auto save, max upload size, search index, SharePoint type
- **Session**: session timeout, inactivity timeout

### Update an Organization Setting

```bash
# Enable auditing
pac org update-settings --name isauditenabled --value true --environment https://myorg.crm.dynamics.com

# Enable user access audit
pac org update-settings --name isuseraccessauditenabled --value true --environment https://myorg.crm.dynamics.com

# Set plugin trace to capture all (option sets require integer values)
pac org update-settings --name plugintracelogsetting --value 2 --environment https://myorg.crm.dynamics.com
```

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--name` | `-n` | Yes | Setting name (e.g., `isauditenabled`, `plugintracelogsetting`) |
| `--value` | `-v` | Yes | New value (`true`/`false` for booleans, integer for option sets -- see Available Settings table) |
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
| `sharepointdeploymenttype` | option | `0` (Online), `1` (OnPremises) |
| `isexternalsearchindexenabled` | bool | `true` / `false` |

### Batch Workflow: Enable Audit for All Developer Environments

This is the primary agentic workflow for org-settings. When a user asks to enable audit (or any setting) across multiple environments:

```
Step 1: pac admin list                                    -> Get all environments
Step 2: Filter output for Type = Developer                -> Identify target environments
Step 3: For each environment URL:
        pac org list-settings --filter isauditenabled --environment <url>   -> Check current state
        pac org update-settings --name isauditenabled --value true --environment <url>
Step 4: Report summary ("Enabled audit on 5/5 developer environments")
```

**Important**: Always show the user which environments will be affected and confirm before updating. Present a table of environments with their current audit state before making changes.

---

## Role Assignment Commands

Assign security roles to users across environments. Uses the existing `pac admin assign-user` command.

### Assign a Security Role to a User

```bash
pac admin assign-user --user <email-or-object-id> --role "System Administrator" --environment <url>
```

#### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--user` | `-u` | Yes | User email (UPN) or Azure AD object ID |
| `--role` | `-r` | Yes | Security role name (e.g., `System Administrator`, `Basic User`) |
| `--environment` | `-env` | Yes | Target environment URL or ID |
| `--application-user` | `-au` | No | Flag: treat user as an application user (service principal) |
| `--business-unit` | `-bu` | No | Business unit ID. Defaults to the caller's business unit |

### Batch Workflow: Assign System Admin Role Across All Environments

When a user asks to get system admin role on all (or filtered) environments:

```
Step 1: pac admin list                                              -> Get all environments
Step 2: Filter by type if needed (e.g., Developer, Sandbox)        -> Identify targets
Step 3: For each environment:
        pac admin assign-user --user <email> --role "System Administrator" --environment <url>
Step 4: Report summary ("Assigned System Administrator on 5/5 environments")
```

**Important**: Always confirm with the user which environments will be affected before assigning roles. Show the list of target environments first.

### Tenant Admin Self-Elevation (Fallback)

If `pac admin assign-user` fails with "user has not been assigned any roles", use the self-elevate command:

```bash
# Self-elevate to System Administrator (requires Global admin, PP admin, or D365 admin)
pac admin self-elevate --environment https://myorg.crm.dynamics.com
```

Uses the active auth profile if `--environment` is omitted. All elevations are logged to Microsoft Purview.

**Flow**: Always try `pac admin assign-user` first. Only use `admin self-elevate` as fallback when the chicken-and-egg error occurs.

---

## Safety Rules

- **Always confirm with the user** before scheduling a bulk delete -- this is a destructive operation
- If `--fetchxml` is omitted, warn the user that ALL records in the table will be deleted
- For system tables (`systemuser`, `businessunit`, `organization`), warn that deleting records may break the environment
- Prefer scheduling during off-peak hours using `--start-time`
- For large deletions, suggest a test run with a narrow filter first

---

## Sample Data Generation

Generate and insert realistic sample records into any Dataverse table. Useful for development, demos, and testing.

**Use the Python SDK** (`client.records.create()`) for sample data creation -- not raw `urllib` or `requests`. The SDK handles auth, error handling, and bulk operations. See the `dv-data` skill for the full SDK reference.

### Agentic Flow for Sample Data

#### Step 1: Confirm environment and count

Before creating anything, confirm:
- **Target environment** -- run `pac auth list` to show the active environment and ask the user to confirm
- **Record count** -- default is **5 records** unless the user specifies otherwise
- **Table name** -- get the logical name (e.g., `account`, `contact`, `cr123_customtable`)

#### Step 2: Inspect the table schema

Use `describe_table` via MCP if available. Otherwise, use the reusable schema inspection script:

```bash
python scripts/inspect_schema.py              # defaults to 'account'
python scripts/inspect_schema.py contact      # any table
```

This script (`scripts/inspect_schema.py`) fetches all columns via the Web API and reports:
- **Required columns** (`RequiredLevel = "ApplicationRequired"`)
- **Column types** (`AttributeType`) -- determines what fake data to generate

#### Step 3: Create sample records

Use the reusable sample data script:

```bash
python scripts/create_sample_data.py                       # 5 sample accounts (default)
python scripts/create_sample_data.py --table account --count 10
python scripts/create_sample_data.py --table contact --count 20
```

This script (`scripts/create_sample_data.py`):
- Uses the Python SDK (`client.records.create()`) -- not raw HTTP
- Creates records individually (with progress) for <= 10, bulk `CreateMultiple` for 10+
- Shows a summary table with record IDs and a link to view in the environment UI

For tables not yet in the script's `SAMPLE_DATA` templates, add a new entry or create a custom script following the same pattern. See the `dv-data` skill for adaptive chunking patterns when creating large datasets.

#### Step 4: Generate realistic sample data

Follow type mapping guidelines:

| AttributeType | Generate |
|---|---|
| `String` / `Memo` | Realistic text based on column name (e.g., `name` -> company names, `emailaddress1` -> emails) |
| `Integer` / `Decimal` / `Money` | Random values within `MinValue`/`MaxValue`, or sensible defaults |
| `Boolean` | Alternate `true`/`false` across records |
| `DateTime` | Recent dates in ISO 8601 format (e.g., `2024-01-15T10:30:00Z`) |
| `Picklist` / `Status` | Use integer option values (e.g., `industrycode: 1`) |
| `Lookup` | **Skip by default** -- only set if user explicitly requests and provides valid record IDs |
| `Uniqueidentifier` (non-PK) | Skip -- let Dataverse auto-generate |

#### Step 5: Run and verify

Show the user:
- Progress for each record created
- Summary table with record IDs and primary names
- Direct link to view records in the environment UI
- Reminder to use bulk delete to clean up later

---

### Safety Rules for Sample Data

- **Always confirm** the target environment and record count before creating anything
- Use `.example.com` domains for generated email addresses -- never real domains
- Use obviously fake phone numbers (`555-01xx`) to avoid accidental contact
- Do not set lookup fields unless the user explicitly asks -- missing lookups cause fewer errors than wrong ones
- If the entity has a required lookup, warn the user and ask them to provide a valid record ID or skip that field
- Skip system fields: `createdon`, `modifiedon`, `ownerid`, `statecode`, `statuscode`, `versionnumber`, etc.

---

## Quick Reference: All Data Management Commands

### Bulk Delete Commands

| Command | Description | Key Arguments |
|---------|-------------|---------------|
| `pac data bulk-delete schedule` | Schedule a new bulk delete job | `--entity`, `--fetchxml`, `--job-name`, `--start-time`, `--recurrence` |
| `pac data bulk-delete list` | List all bulk delete jobs | `--environment` |
| `pac data bulk-delete show` | Show details of a specific job | `--id` |
| `pac data bulk-delete pause` | Pause a running job | `--id` |
| `pac data bulk-delete resume` | Resume a paused job | `--id` |
| `pac data bulk-delete cancel` | Cancel a job | `--id` |

### Retention Commands

| Command | Description | Key Arguments |
|---------|-------------|---------------|
| `pac data retention enable-entity` | Enable archival for a table | `--entity` |
| `pac data retention set` | Create or update a retention policy | `--entity`, `--criteria`, `--start-time`, `--recurrence` |
| `pac data retention list` | List all retention policies | `--environment` |
| `pac data retention show` | Show details of a retention policy | `--id` |
| `pac data retention status` | Check status of a retention operation | `--id` |

---

## JSON Output

All PAC CLI commands support `--output json` for programmatic consumption:

```bash
pac data bulk-delete list --output json
pac data bulk-delete show --id <job-id> --output json
pac data retention list --output json
pac data retention show --id <config-id> --output json
```

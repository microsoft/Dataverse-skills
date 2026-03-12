---
name: dataverse-solution
description: >
  Create, export, unpack, pack, import, and validate Dataverse solutions.
  USE WHEN: "export solution", "import solution", "pack solution", "unpack solution", "create solution",
  "pull from environment", "push to environment", "validate import", "check import errors",
  "check if table exists", "check if form is published", "verify deployment".
  DO NOT USE WHEN: creating tables/columns/forms/views (use dataverse-metadata).
---

# Skill: Solution

Create, export, unpack, pack, import, and validate Dataverse solutions via PAC CLI. Includes post-import validation using the Python SDK.

## Create a New Solution

**Use the Python SDK for publisher and solution record creation — not raw HTTP.** Publishers and solutions are standard Dataverse tables. `client.records.create()` and `client.records.get()` handle auth, pagination, and error handling automatically, avoiding the URL encoding, header boilerplate, and GUID-parsing bugs that raw `urllib` calls introduce.

### Step 1: Find or Create the Publisher

Every solution belongs to a publisher. The publisher's `customizationprefix` (e.g., `contoso`, `sa`, `lit`) is prepended to every custom table, column, and relationship schema name. **This prefix is effectively permanent** — existing components keep their prefix forever, even if you change the publisher later.

**Never use the default `new` prefix.** It provides no organizational identity, risks naming collisions, and signals the developer did not follow best practices.

**Discovery flow — always run this before creating a publisher:**

```python
# 1. Query for existing non-Microsoft publishers
pages = client.records.get(
    "publisher",
    filter="customizationprefix ne 'none' and uniquename ne 'MicrosoftCorporation' and uniquename ne 'Microsoftdynamic'",
    select=["publisherid", "uniquename", "friendlyname", "customizationprefix"],
    top=10,
)
publishers = [p for page in pages for p in page]

if publishers:
    # Show existing publishers and ask user which to use
    print("Existing publishers in this environment:")
    for p in publishers:
        print(f"  {p['uniquename']} (prefix: {p['customizationprefix']}_)")
    # ASK THE USER: "Which publisher should this solution use?"
    # Or: "Should I reuse '<name>' (prefix: <prefix>_)?"
    publisher_id = publishers[0]["publisherid"]  # after user confirms
else:
    # No custom publisher exists — ASK THE USER for prefix
    # "What publisher prefix should I use? (e.g., 'contoso', 'sa', 'lit' — 2-8 lowercase chars)"
    publisher_id = client.records.create("publisher", {
        "uniquename": "<publisheruniquename>",
        "friendlyname": "<Publisher Display Name>",
        "customizationprefix": "<prefix>",   # from user input, NOT 'new'
        "description": "<description>",
    })
```

**Rules:**
- **Always ask the user** before creating a new publisher or choosing a prefix. Never hardcode a prefix.
- The prefix must match any tables already created in the solution — you cannot mix prefixes.
- One publisher can own many solutions. Reuse an existing publisher when possible.

### Step 2: Create the Solution Record

Use the SDK to create the solution record (preferred over raw Web API):

```python
from PowerPlatform.Dataverse.client import DataverseClient
from scripts.auth import get_credential, load_env
import os

load_env()
client = DataverseClient(os.environ["DATAVERSE_URL"], get_credential())

# Create the solution record
solution_id = client.records.create("solution", {
    "uniquename": "<UniqueName>",
    "friendlyname": "<Display Name>",
    "version": "1.0.0.0",
    "publisherid@odata.bind": "/publishers(<publisher_guid>)",
})
print(f"Created solution: {solution_id}")
```

The required fields:
```
Table:  solution
Fields: uniquename    = "<UniqueName>"
        friendlyname  = "<Display Name>"
        version       = "1.0.0.0"
        publisherid   = <publisher GUID from step 1>
```

> **Note:** There is no `pac solution create` command. PAC CLI handles export/import/pack/unpack, not solution record creation. Use the SDK or Web API to create the record.

### Step 3: Add Components

Use `pac solution add-solution-component` to add tables, forms, views, and other components:
```
pac solution add-solution-component \
  --solutionUniqueName <UniqueName> \
  --component <ComponentSchemaName> \
  --componentType <TypeCode> \
  --environment <url>
```

> **Note:** PAC CLI uses camelCase args here (`--solutionUniqueName`, `--componentType`), not kebab-case.

Common component type codes:
| Type Code | Component |
|---|---|
| 1 | Entity (Table) |
| 2 | Attribute (Column) |
| 26 | View |
| 60 | Form |
| 61 | Web Resource |
| 300 | Canvas App |
| 371 | Connector |

Repeat the command for each component you need to add.

### Alternative: Auto-add via MSCRM.SolutionName Header

When creating metadata via the Web API, include the `MSCRM.SolutionName` header to auto-add components to the solution:
```python
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "MSCRM.SolutionName": "<UniqueName>"
}
```

**Important:** After using this approach, verify components were added by listing them:
```bash
pac solution list-components --solutionUniqueName <UniqueName> --environment <url>
```

If the header was misspelled or the solution doesn't exist, components will be created in the default solution instead — silently. Always verify.

## Find the Solution Name

Before exporting, confirm the exact unique name:
```
pac solution list --environment <url>
```
The `UniqueName` column is what you pass to other commands. Display names have spaces; unique names do not.

## Pull: Export + Unpack

> **Confirm the target environment before exporting or importing.** Run `pac auth list` + `pac org who`, show the output to the user, and confirm it matches the intended environment. Developers work across multiple environments — do not assume.

Export the solution as unmanaged (source of truth):
```
pac solution export \
  --name <UniqueName> \
  --path ./solutions/<UniqueName>.zip \
  --managed false \
  --environment <url>
```

Unpack into editable source files:
```
pac solution unpack \
  --zipfile ./solutions/<UniqueName>.zip \
  --folder ./solutions/<UniqueName> \
  --packagetype Unmanaged
```

Delete the zip — the unpacked folder is the source:
```
rm ./solutions/<UniqueName>.zip
```

Commit:
```
git add ./solutions/<UniqueName>
git commit -m "chore: pull <UniqueName> baseline"
git push
```

## Push: Pack + Import

Pack the source files back into a zip:
```
pac solution pack \
  --zipfile ./solutions/<UniqueName>.zip \
  --folder ./solutions/<UniqueName> \
  --packagetype Unmanaged
```

Import (async recommended for large solutions):
```
pac solution import \
  --path ./solutions/<UniqueName>.zip \
  --environment <url> \
  --async \
  --activate-plugins
```

## Poll Import Status

After async import, check the job:
```
pac solution list --environment <url>
```

## Post-Import Validation

After importing a solution, verify that components are live. Use the Python SDK to check directly — no external scripts needed.

### Check a table exists

```python
info = client.tables.get("<logical_name>")
if info:
    print(f"[PASS] Table '{info['LogicalName']}' exists")
else:
    print(f"[FAIL] Table '<logical_name>' not found")
```

### Check a form is published

```python
pages = client.records.get(
    "systemform",
    filter="objecttypecode eq '<entity>' and type eq <form_type_code>",
    select=["name", "formid"],
    top=5,
)
forms = [f for page in pages for f in page]
# Form type codes: 2 = main, 7 = quick create
```

### Check a view exists

```python
pages = client.records.get(
    "savedquery",
    filter="returnedtypecode eq '<entity>'",
    select=["name", "savedqueryid", "statuscode"],
    top=10,
)
views = [v for page in pages for v in page]
```

### Check a user's role assignment

N:N `$expand` (like `systemuserroles_association`) is not supported by the SDK. Use the Web API:

```python
# Web API fallback for N:N expand
import urllib.request, json
from auth import get_token

token = get_token()
url = f"{env}/api/data/v9.2/systemusers?$filter=internalemailaddress eq '<email>'&$select=fullname&$expand=systemuserroles_association($select=name)&$top=1"
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    users = json.loads(resp.read()).get("value", [])
if users:
    roles = [r["name"] for r in users[0].get("systemuserroles_association", [])]
    print(f"Roles: {', '.join(roles)}")
```

### Check import errors

```python
pages = client.records.get(
    "importjob",
    select=["importjobid", "solutionname", "startedon", "completedon", "progress"],
    orderby=["startedon desc"],
    top=5,
)
jobs = [j for page in pages for j in page]
```

For detailed error history, also query `msdyn_solutionhistory`:

```python
pages = client.records.get(
    "msdyn_solutionhistory",
    filter="msdyn_status eq 1",  # 1 = failed
    select=["msdyn_name", "msdyn_starttime", "msdyn_exceptionmessage"],
    orderby=["msdyn_starttime desc"],
    top=5,
)
```

### Validation error reference

| Error | Cause | Fix |
| --- | --- | --- |
| Table not found after import | Component not in solution | Add via `pac solution add-solution-component` |
| Form check fails immediately | Publishing is async | Wait 30 seconds and retry |
| Role not assigned | User not provisioned | Assign the role via `pac admin assign-user` or the Power Platform Admin Center |
| Import job at 0% | Import still running | Poll again in 60 seconds |

## Notes

- Always use `--managed false` / `--packagetype Unmanaged` for the development solution. Managed packages are for deployment to downstream environments (test, prod).
- `--activate-plugins` ensures any registered plugins in the solution are activated on import.
- If you see "solution already exists" errors, use `--import-mode ForceUpgrade` to overwrite.
- Large solutions (Sales, Customer Service) can take 10–20 minutes to import. Be patient and poll rather than re-importing.
- All validation queries above require auth. Use `scripts/auth.py` for credential/token acquisition. See `/dataverse:python-sdk` for SDK setup patterns.

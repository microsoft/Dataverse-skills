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

Creating a solution is a two-step process: create the solution record in Dataverse, then add components to it.

### Step 1: Find the Publisher

Every solution belongs to a publisher. Look up the publisher that matches your table prefix:
```sql
SELECT publisherid, uniquename, customizationprefix FROM publisher
WHERE customizationprefix = '<prefix>'
```

If the publisher doesn't exist yet, create it first in make.powerapps.com or via Web API. The publisher prefix must match the prefix already used by your tables — you cannot mix prefixes within a solution.

### Step 2: Create the Solution Record

Create a record in the `solution` table via MCP, SDK, or Web API:
```
Table:  solution
Fields: uniquename    = "<UniqueName>"
        friendlyname  = "<Display Name>"
        version       = "1.0.0.0"
        publisherid   = <publisher GUID from step 1>
```

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

```python
pages = client.records.get(
    "systemuser",
    filter="internalemailaddress eq '<email>'",
    expand=["systemuserroles_association"],
    select=["fullname", "internalemailaddress"],
    top=1,
)
users = [u for page in pages for u in page]
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

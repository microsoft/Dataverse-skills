---
name: dv-solution
description: Dataverse solution lifecycle — create, export, import, promote across environments, and validate deployments. Use when the user wants to package customizations, deploy to another environment, or move work between dev / test / prod.
---

# Skill: Solution

Create, export, unpack, pack, import, and validate Dataverse solutions via PAC CLI. Includes post-import validation using the Python SDK.

> **Headless / restricted-egress hosts**: solution export/import workflows require PAC CLI. Raw `ExportSolution` / `ImportSolution` Web API calls do not satisfy this workflow because they bypass PAC's package contract and local pack/unpack validation. Run the workflow on a capable machine or CI runner that can execute PAC. Verify egress with `python scripts/auth.py --check`. See `dv-connect/references/headless-hosts.md`.

> **Execution proof**: run each `pac solution export`, `pack`, `unpack`, or `import` as a standalone command and inspect its exit status before continuing. Do not pipe PAC output through `tail`, `head`, `grep`, or another command, and do not place PAC after `&&`; those wrappers can report the other process's status and make a failed PAC command look successful. If PAC authentication is unavailable, stop and report that blocker. Never substitute raw `ExportSolution` / `ImportSolution` calls or a hand-built ZIP.

## Skill boundaries

| Need | Use instead |
|---|---|
| Create tables, columns, relationships, forms, views | **dv-metadata** |
| Create, update, or delete data records | **dv-data** |
| Query or read records | **dv-query** |
| Connect to Dataverse / set up MCP | **dv-connect** |

---

## Create a New Solution

**Use the Python SDK for publisher and solution record creation — not raw HTTP.** Publishers and solutions are standard Dataverse tables. `client.records.create()` and `client.records.list()` handle auth, pagination, and error handling automatically, avoiding the URL encoding, header boilerplate, and GUID-parsing bugs that raw `urllib` calls introduce.

### Step 1: Find or Create the Publisher

Every solution belongs to a publisher. The publisher's `customizationprefix` (e.g., `contoso`, `sa`, `lit`) is prepended to every custom table, column, and relationship schema name. **This prefix is effectively permanent** — existing components keep their prefix forever, even if you change the publisher later.

**Never use the default `new` prefix.** It provides no organizational identity, risks naming collisions, and signals the developer did not follow best practices.

**Discovery flow — always run this before creating a publisher:**

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

# get_client sets a plugin attribution context on the User-Agent header.
# Do not modify the context value — it is a closed schema for server-side
# telemetry (app/skill/agent). Never include secrets or PII.
client = get_client("dv-solution")

# Query the exact requested unique name before creating. A broad top-N list is
# not an idempotency check because the target may exist outside that page.
publishers = client.records.list(
    "publisher",
    filter="uniquename eq '<publisheruniquename>'",
    select=["publisherid", "uniquename", "friendlyname", "customizationprefix"],
    top=1,
)
publisher = publishers.first()

if publisher is not None:
    if publisher["customizationprefix"] != "<prefix>":
        raise ValueError("Existing publisher has a different permanent prefix")
    publisher_id = publisher["publisherid"]
    print(f"Reusing publisher: {publisher_id}")
else:
    # The user must confirm the permanent prefix before this branch runs.
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
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

# get_client sets a plugin attribution context on the User-Agent header.
# Do not modify the context value — it is a closed schema for server-side
# telemetry (app/skill/agent). Never include secrets or PII.
client = get_client("dv-solution")

# Query the exact unique name first so retries reuse the same unmanaged solution.
solutions = client.records.list(
    "solution",
    filter="uniquename eq '<UniqueName>'",
    select=["solutionid", "version", "ismanaged", "_publisherid_value"],
    top=1,
)
solution = solutions.first()

if solution is not None:
    if (
        solution["ismanaged"]
        or solution["_publisherid_value"] != "<publisher_guid>"
        or solution["version"] != "<requested_version>"
    ):
        raise ValueError("Existing solution does not match the requested publisher/type/version")
    solution_id = solution["solutionid"]
    print(f"Reusing solution: {solution_id}")
else:
    solution_id = client.records.create("solution", {
        "uniquename": "<UniqueName>",
        "friendlyname": "<Display Name>",
        "version": "<requested_version>",
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

**Important:** After using this approach, verify components were added by querying the `solutioncomponent` table with the SDK (`pac solution list-components` is not available in current PAC):
```python
sol = client.records.list("solution",
    filter="uniquename eq '<UniqueName>'", select=["solutionid"], top=1).first()
if sol is not None:
    components = client.records.list("solutioncomponent",
        filter=f"_solutionid_value eq {sol['solutionid']}",
        select=["componenttype", "objectid"])
    print(f"{len(components)} components in the solution")
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
rm -f ./solutions/<UniqueName>.zip
pac solution export \
  --name <UniqueName> \
  --path ./solutions/<UniqueName>.zip \
  --managed false \
  --environment <url>
```

When both package modes are requested, run two standalone exports with distinct paths:
```
rm -f ./solutions/<UniqueName>_unmanaged.zip
pac solution export \
    --name <UniqueName> \
    --path ./solutions/<UniqueName>_unmanaged.zip \
    --managed false \
    --environment <url>

rm -f ./solutions/<UniqueName>_managed.zip
pac solution export \
    --name <UniqueName> \
    --path ./solutions/<UniqueName>_managed.zip \
    --managed true \
    --environment <url>
```

After each export, run `test -s <exact-zip-path>` as a separate command. After unpacking, run `test -f <exact-folder>/Other/Solution.xml` separately. These checks prove that PAC produced non-empty packages and real unpacked solution files without masking PAC's exit status.

Unpack into editable source files:
```
rm -rf ./solutions/<UniqueName>
pac solution unpack \
  --zipfile ./solutions/<UniqueName>.zip \
  --folder ./solutions/<UniqueName> \
  --packagetype Unmanaged
```

> **Windows file-lock race.** Run export and unpack as **separate** commands (as above); chaining them immediately can hit a transient ZIP file-lock right after export. If `unpack` fails with a lock / "in use" error, retry after a moment, and verify the unpacked folder has the expected components before deleting the zip.

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

For development environments, pack the unmanaged source files back into a zip:
```
rm -f ./solutions/<UniqueName>.zip
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

For downstream test or production environments, deploy a managed package. A managed pack requires source previously unpacked with `--packagetype Both`; do not relabel an unmanaged-only unpack. The simplest safe path is a fresh managed export from the confirmed source environment, followed by import to the separately confirmed downstream environment:
```
rm -f ./solutions/<UniqueName>_managed.zip
pac solution export \
    --name <UniqueName> \
    --path ./solutions/<UniqueName>_managed.zip \
    --managed true \
    --environment <source-url>

test -s ./solutions/<UniqueName>_managed.zip

pac solution import \
    --path ./solutions/<UniqueName>_managed.zip \
    --environment <test-or-production-url> \
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
if not info:
    raise RuntimeError("Table '<logical_name>' not found after import")
print(f"[PASS] Table '{info.logical_name}' exists")
```

### Check a form is published

```python
forms = list(client.records.list(
    "systemform",
    filter="objecttypecode eq '<entity>' and type eq <form_type_code>",
    select=["name", "formid"],
    top=5,
))
if not forms:
    raise RuntimeError("Expected published form was not found after import")
# Form type codes: 2 = main, 7 = quick create
```

### Check a view exists

```python
views = list(client.records.list(
    "savedquery",
    filter="returnedtypecode eq '<entity>'",
    select=["name", "savedqueryid", "statuscode"],
    top=10,
))
if not views:
    raise RuntimeError("Expected view was not found after import")
```

### Check a user's role assignment (N:N `$expand`)

`records.list` passes `$expand` straight through, so read the N:N navigation property directly with the SDK:

```python
users = list(client.records.list(
    "systemuser",
    filter="internalemailaddress eq '<email>'",   # fallback: domainname eq '<upn>'
    select=["fullname"],
    expand=["systemuserroles_association($select=name)"],
    top=1,
))
roles = [r["name"] for r in users[0].get("systemuserroles_association", [])] if users else []
if not roles:
    raise RuntimeError("Expected user role assignment was not found after import")
```

Alternatively, the managed **Dataverse CLI** escape hatch (`dataverse api request` — not `urllib`), or FetchXML with a link-entity:

```bash
dataverse api request --target dataverse --method GET \
  --path "/api/data/v9.2/systemusers?%24filter=internalemailaddress eq '<email>'&%24select=fullname&%24expand=systemuserroles_association(%24select=name)&%24top=1" \
  --environment <DATAVERSE_URL> \
  --context "app=dataverse-skills/<ver>;skill=dv-solution;agent=<agent>"
```

The response `value[0].systemuserroles_association` is the list of assigned roles (each with `name`).

### Check import errors

```python
jobs = client.records.list(
    "importjob",
    select=["importjobid", "solutionname", "startedon", "completedon", "progress"],
    orderby=["startedon desc"],
    top=5,
)
```

For detailed error history, also query `msdyn_solutionhistory`:

```python
history = client.records.list(
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
- All validation queries above require auth. Use `scripts/auth.py` for credential/token acquisition. See `dv-query` for SDK query patterns and `dv-data` for write patterns.

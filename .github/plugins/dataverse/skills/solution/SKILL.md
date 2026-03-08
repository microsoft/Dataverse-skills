---
name: dataverse-solution
description: Create, export, unpack, pack, and import Dataverse solutions. Use this for creating new solutions, pulling changes from an environment to the repo, or pushing repo changes to an environment.
---

# Skill: Solution

Create, export, unpack, pack, and import Dataverse solutions via PAC CLI.

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
Or query the import job directly via Web API (see `dataverse-validation/SKILL.md`).

If the import fails, the error details are in the import job record. Run `validate.py --import-errors` to retrieve them in readable form.

## Notes

- Always use `--managed false` / `--packagetype Unmanaged` for the development solution. Managed packages are for deployment to downstream environments (test, prod).
- `--activate-plugins` ensures any registered plugins in the solution are activated on import.
- If you see "solution already exists" errors, use `--import-mode ForceUpgrade` to overwrite.
- Large solutions (Sales, Customer Service) can take 10–20 minutes to import. Be patient and poll rather than re-importing.

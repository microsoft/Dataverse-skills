# X++ workflow recipes

Every online workflow begins with explicit environment confirmation and:

```bash
pac org who --environment <dataverse-url>
```

Require the output to match the confirmed Dataverse URL and show ERP linkage.

## Compile/build only

Use when the user wants artifacts but no environment mutation:

```bash
pac tool xpp list
pac package compile --solution-root <root> --package-type erp \
  --app-version <x.y.z.w> --language en-US
```

If the matching SDK is absent:

```bash
pac tool xpp install --environment <dataverse-url>
```

Success criteria:

- PAC exits zero.
- Compile summary reports every requested model succeeded.
- Best-practice checks have no errors; address warnings unless accepted.
- A current `<Model>_<version>_managed.zip` exists under `<root>/bin` or the explicit output directory.

Do not deploy or DB-sync.

## Deploy one prebuilt package only

Inspect the exact ZIP path and state the selected modes before asking for confirmation:

```bash
pac package deploy --environment <dataverse-url> --package-type erp \
  --package <managed-zip> \
  --build-type Full --release-type Dev --db-sync None \
  --logConsole --logFile <deployment-log-path>
```

Success means PAC exits zero and reports `Deploy completed successfully.` after polling. Capture the async operation ID and log path, then apply the validation guidance linked from the skill body. Do not compile, redeploy other models, or DB-sync.

## Deploy a multi-model solution

Compile all configured models:

```bash
pac package compile --solution-root <root> --package-type erp \
  --app-version <x.y.z.w> --language en-US
```

Then omit `--package` so PAC reads `.erp/xpp.json`, orders dependencies, and deploys every current ZIP:

```bash
pac package deploy --environment <dataverse-url> --package-type erp \
  --solution-root <root> \
  --build-type Full --release-type Dev --db-sync None \
  --logConsole --logFile <deployment-log-path>
```

Do not manually loop deployments. PAC deliberately waits between packages for ERP orchestration to settle. Validate every planned model and the final deployed-model count using the validation guidance linked from the skill body.

## DB-sync only

Do not compile or deploy.

Full:

```bash
pac package db-sync --environment <dataverse-url> --db-sync Full
```

Module:

```bash
pac package db-sync --environment <dataverse-url> \
  --db-sync Module --modules <ModelA,ModelB>
```

Incremental:

```bash
pac package db-sync --environment <dataverse-url> \
  --db-sync Incremental --argument-file <incremental-sync.json>
```

Require the user to choose the mode. Show modules or argument-file path in the confirmation. PAC waits for the asynchronous operation; capture its ID and require `Database synchronization completed successfully.` Apply the DB-sync failure guidance linked from the skill body.

## Deploy and synchronize in one operation

One package:

```bash
pac package deploy --environment <dataverse-url> --package-type erp \
  --package <managed-zip> \
  --build-type Full --release-type Dev \
  --db-sync Module --modules <ModelName> \
  --logConsole --logFile <deployment-log-path>
```

All configured models, followed by one sync:

```bash
pac package deploy --environment <dataverse-url> --package-type erp \
  --solution-root <root> \
  --build-type Full --release-type Dev \
  --db-sync Full \
  --logConsole --logFile <deployment-log-path>
```

Use integrated sync only when the user requests deployment plus synchronization. Otherwise keep deploy and DB sync independent.

## End-to-end code change

1. Inspect `.erp/xpp.json`, descriptors, metadata paths, current branch, and working tree.
2. Scaffold only missing models with `pac package init --package-type erp`.
3. Create/edit the requested metadata. Add label resources for user-facing strings.
4. Validate XML files before invoking the compiler.
5. Confirm the target Dataverse URL and verify `pac org who`.
6. Run `pac tool xpp list`; install the environment-matching SDK only if missing.
7. Use incremental compile while fixing errors.
8. Run one final non-incremental compile with best-practice checks.
9. Identify the ZIP created by that final run.
10. Deploy with explicit `Full|Incremental|Delete`, `Dev|Release`, and DB-sync choices.
11. Require PAC's successful terminal result and apply every applicable success gate from the validation guidance linked from the skill body.
12. Verify each deployed artifact through its runtime surface:
    - Runnable class: open `https://<erp-host>/?mi=SysClassRunner&cls=<ClassName>` and observe the infolog.
    - Custom service: when names are known from source, use `dataverse api invoke 'erp:<ServiceGroup>/<Service>/<Operation>' --target erp --param '<name>=<value>' --json --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`; reserve `list`/`describe` for unknown deployed names and obtain parameter contracts from the X++ source.
    - `ICustomAPI` action: use ERP MCP `api_find_actions` to validate its action menu-item name and input/output contract, then call `api_invoke_action` with a JSON-encoded `parameters` string. Require `isError: false` and validate representative positive, zero, negative, and boundary results.
    - Public OData data entity: use `dataverse data describe --target erp --table <EntitySet> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`, then `dataverse data query --target erp --table <EntitySet> --top <n> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`.
13. Persist source changes in the repository; do not commit generated `bin/`, compiler caches, or logs unless repository policy explicitly tracks them.

## Failure handling

Use the validation guidance linked from the skill body for compile diagnostics, async-operation inspection, deployment and DB-sync success criteria, the validation error reference, and the required failure report.

# X++ workflow recipes

Every online workflow begins with explicit environment confirmation and:

```bash
pac org who --environment <dataverse-url>
```

Require PAC to match the confirmed Dataverse URL and show ERP linkage. PAC-only deployment and DB-sync workflows do not require Dataverse CLI or MCP setup.

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

Capture PAC's exit code, async operation ID, terminal state, and log path. Then ask whether the user wants any additional validation of this ERP X++ package deployment and run only the selected checks. Do not compile, redeploy other models, or DB-sync.

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

Do not manually loop deployments. PAC deliberately waits between packages for ERP orchestration to settle. Capture every reported model result and final deployed-model count. Ask before performing any additional post-deployment validation.

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

## Runtime verification target

Before a workflow invokes or queries the deployed ERP artifact through the Dataverse CLI or ERP MCP:

```bash
dataverse auth who
dataverse org who --json \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
```

Require the selected CLI profile to match the confirmed Dataverse URL and linked ERP URL. If it differs, run `dataverse auth select --name <profile-name>`, then repeat both checks. Pass `--environment <dataverse-url>` where supported, but do not rely on it instead of selecting the correct profile.

For ERP MCP, inspect the active server configuration according to its transport. Direct HTTP must target the confirmed `<erp-url>/mcp`; an stdio proxy must receive the confirmed base `<erp-url>` and route effectively to `/mcp`. Reconnect or reinitialize a mismatched connection.

Before every MCP runtime invocation, establish fresh transport-specific authentication and prove the caller through an MCP-originated identity/current-session check. `dataverse auth who` alone is not evidence of the MCP caller. If MCP cannot expose its caller, do not invoke through that session. For security acceptance, the proven caller must be the intended non-administrator test user.

## End-to-end code change

1. Inspect `.erp/xpp.json`, descriptors, metadata paths, current branch, and working tree.
2. Scaffold only missing models with `pac package init --package-type erp`.
3. Create/edit the requested metadata. Add label resources for user-facing strings.
4. Validate XML files before invoking the compiler.
5. Confirm the target Dataverse URL; verify `pac org who`, `dataverse auth who`, and `dataverse org who --json` resolve to the same Dataverse and linked ERP environment.
6. Run `pac tool xpp list`; install the environment-matching SDK only if missing.
7. Use incremental compile while fixing errors.
8. Run one final non-incremental compile with best-practice checks.
9. Identify the ZIP created by that final run.
10. Deploy with explicit `Full|Incremental|Delete`, `Dev|Release`, and DB-sync choices.
11. Capture PAC's terminal deployment result without performing any additional validation.
12. Ask whether the user wants post-deployment validation and which checks they select: async-operation re-query, API/action discovery, runtime behavior, data-entity query, multiple-case testing, and/or security acceptance. Deployment approval and selection of one check do not authorize another.
13. If all validation is declined, report the PAC result and mark additional validation as not performed. If runtime validation is selected, inspect only the deployed custom artifact and its contract, ask for every required input plus explicit success and failure criteria, and repeat exact values or criteria from the prompt for confirmation. Never invent or broaden them; failure criteria do not authorize an unapproved negative test.
14. Inspect the approved custom X++ logic for side effects, classify it, disclose expected mutations, and obtain any additional confirmation. Use non-production isolated data by default; run only one minimal approved case for non-idempotent operations.
15. Verify only the approved deployed artifact through its runtime surface:
    - Runnable class: open `https://<erp-host>/?mi=SysClassRunner&cls=<ClassName>` and observe the infolog.
    - Custom service: when names are known from source, use `dataverse api invoke 'erp:<ServiceGroup>/<Service>/<Operation>' --target erp --param '<name>=<value>' --json --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`; reserve `list`/`describe` for unknown deployed names, obtain parameter contracts from X++ source, and verify the approved response and expected mutations.
    - `ICustomAPI` action: if discovery was selected, use ERP MCP `api_find_actions` to validate its action menu-item name and contract. If execution was selected, call `api_invoke_action` with user-confirmed JSON inputs from the source contract or approved discovery result. Require `isError: false` and verify only approved results and mutations.
    - Public OData data entity: if discovery was selected, use `dataverse data describe --target erp --table <EntitySet> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`. If query execution was separately selected, use `dataverse data query --target erp --table <EntitySet> --top <confirmed-limit> --filter "<confirmed-filter>" --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`.
16. Only when runtime execution and `ICustomAPI` security acceptance were both selected, authenticate a fresh transport-specific MCP session as a non-administrator test user assigned the intended custom role, prove its caller through MCP, and invoke the approved case. Administrator execution is diagnostic only. Any optional negative role test must use a disposable user, guarantee restoration independently, and verify that restoration completed.
17. Persist source changes in the repository; do not commit generated `bin/`, compiler caches, or logs unless repository policy explicitly tracks them.

## Failure handling

Use the validation guidance linked from the skill body for compile diagnostics, async-operation inspection, deployment and DB-sync success criteria, the validation error reference, and the required failure report.

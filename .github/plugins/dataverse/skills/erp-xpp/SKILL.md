---
name: erp-xpp
description: Finance and Operations X++ development lifecycle — scaffold models, author classes, custom services/APIs, and data entities, install matching SDKs, compile deployable packages, deploy packages, synchronize databases, and verify deployed artifacts. Use when the user wants to create, build, compile, package, deploy, DB-sync, or verify X++ customizations, or complete an end-to-end ERP code change.
---

# Skill: Finance and Operations X++ Development

> ## Critical safety rules — read first
>
> 1. **Windows only.** `pac tool xpp install` and `pac package compile --package-type erp` require Windows. Do not invent a Linux/macOS or SDK-based fallback.
> 2. **Confirm the target before any deploy or DB sync.** Show the Dataverse environment URL, obtain explicit confirmation, then run `pac org who --environment <url>` and verify both the Dataverse URL and linked ERP URL/version.
> 3. **Never assume Full DB sync.** Although standalone `pac package db-sync` defaults to `Full`, require the user to choose `Full`, `Module`, or `Incremental` when the request is ambiguous.
> 4. **Do not call deployment successful until PAC reaches a successful terminal state.** Preserve and report the async operation ID on failure.
> 5. **Do not overwrite existing models or source files.** Inspect `.erp/xpp.json`, descriptors, and target metadata paths before scaffolding or editing.
> 6. **Pin every runtime surface before ERP verification.** PAC and the Dataverse CLI have separate active profiles. Before any `dataverse ... --target erp` check, require `dataverse auth who` and `dataverse org who --json` to match the confirmed Dataverse and linked ERP URLs. Validate ERP MCP according to its transport: direct HTTP must target `<erp-url>/mcp`; an stdio proxy must receive the base `<erp-url>` and route effectively to `/mcp`. Profile selection does not retarget an existing MCP connection.
> 7. **Treat service and action verification as possible data mutation.** Inspect the X++ implementation first, disclose exact test inputs and expected mutations, and obtain confirmation when runtime execution was not already approved. Do not apply a generic test matrix to non-idempotent operations.

PAC CLI is the managed surface for the X++ lifecycle. Do not replace these commands with raw Dataverse APIs, direct calls to the ERP sidecar, LCS upload automation, or hand-written compiler invocations.

## Intent routing

| User intent | Action |
|---|---|
| Create an ERP package/model | `pac package init --package-type erp` |
| Install compiler metadata for an environment | `pac tool xpp install` |
| Check/remove local SDKs | `pac tool xpp list` / `pac tool xpp uninstall` |
| Compile or build X++ | `pac package compile --package-type erp` |
| Deploy one prebuilt ZIP | `pac package deploy --package-type erp --package <zip>` |
| Deploy all models in a repo | `pac package deploy --package-type erp --solution-root <root>` |
| Run DB sync only | `pac package db-sync` |
| Create an ERP custom service | Author its X++ class/contracts plus `AxService` and `AxServiceGroup` metadata, then compile and deploy |
| Create an ERP `ICustomAPI` action | Author an `ICustomAPI` class, action menu item, and privilege/duty/role security, then compile, deploy, DB-sync when required, and verify through ERP MCP |
| Author, compile, deploy, and verify | Follow [End-to-end workflow](#end-to-end-workflow) |

**There is no `pac package build` or top-level `pac xpp` command.** For ERP, `pac package compile --package-type erp` compiles labels and X++, runs best-practice checks, and builds deployable managed ZIPs.

## Skill boundaries

| Need | Use instead |
|---|---|
| Connect/authenticate, install or update PAC CLI | **dv-connect** |
| Read or analyze ERP business data | **dv-query** |
| Create/update/delete ERP business records or import DMF data | **dv-data** |
| List/cancel ERP batch jobs | **dv-admin** |
| Dataverse solution ALM | **dv-solution** |
| ERP UI personalization, workflow editing, or environment lifecycle | Finance and Operations UI / Power Platform admin tooling; not covered |

## Preflight

1. Confirm Windows.
2. Run `pac` and inspect its banner; `pac --version` is invalid. These commands require the PAC CLI .NET tool version 2.11.1 or later.
3. Run `pac package help` and `pac tool xpp help`. If `compile`, `db-sync`, or `tool xpp` is absent, load **dv-connect** and update to the latest .NET tool installation before continuing.
4. For environment operations, run:

```bash
pac auth list
pac org who --environment <dataverse-url>
```

The output must identify the confirmed Dataverse environment and include a linked ERP URL/version. Do not substitute the ERP URL for `--environment`; PAC accepts the Dataverse URL and resolves ERP linkage.

5. Before runtime verification through the Dataverse CLI or ERP MCP, run:

```bash
dataverse auth who
dataverse org who --json \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
```

Require the selected CLI profile's environment URL and returned `erpUrl` to match the PAC target confirmed above. If they do not, run `dataverse auth select --name <profile-name>`, then repeat both checks. Pass `--environment <dataverse-url>` on commands that support it, but never treat that option as a substitute for selecting the correct profile; some ERP data commands have no environment override.

For ERP MCP verification, inspect the active server configuration. Require direct HTTP to use the confirmed `<erp-url>/mcp`, or require an stdio proxy such as `dataverse mcp` to receive the confirmed base `<erp-url>` and use its effective `/mcp` endpoint. If it differs, stop and reconnect or reinitialize the matching ERP MCP server before discovery or invocation.

For security acceptance, establish a fresh transport-specific MCP session as the intended test user and verify the caller through an MCP-originated identity/current-session check before invoking the custom action. `dataverse auth who` proves only the CLI identity. If the MCP surface cannot prove its caller, do not claim security acceptance through that session; use a verification surface that can.

6. Before a first SDK install, explain that it downloads roughly 4 GB and expands to roughly 16 GB under `%LOCALAPPDATA%\Microsoft\Dynamics365\<version>\PackagesLocalDirectory`.

## Command quick reference

```bash
# Scaffold one or more models
pac package init --outputDirectory <root> --package-type erp \
  --model <ModelA,ModelB> --publisher <publisher> --layer ISV

# SDK lifecycle
pac tool xpp install --environment <dataverse-url>
pac tool xpp list
pac tool xpp uninstall --version <four-part-version>

# Compile/build all configured models
pac package compile --solution-root <root> --package-type erp \
  --app-version <four-part-version> --language en-US

# Compile one model during the edit loop
pac package compile --solution-root <root> --package-type erp \
  --model <ModelName> --app-version <four-part-version> \
  --language en-US --incremental

# Deploy one compiled package, without DB sync
pac package deploy --environment <dataverse-url> --package-type erp \
  --package <root>/bin/<Model>_<version>_managed.zip \
  --build-type Full --release-type Dev --db-sync None \
  --logConsole --logFile <deployment-log-path>

# Deploy every model in .erp/xpp.json in dependency order
pac package deploy --environment <dataverse-url> --package-type erp \
  --solution-root <root> --build-type Full --release-type Dev \
  --db-sync None --logConsole --logFile <deployment-log-path>
```

Use explicit values rather than relying on defaults in automation. Full argument tables and DB-sync rules are in [`references/commands.md`](references/commands.md).

## Authoring X++ source

The repo root contains `.erp/xpp.json`; source defaults to `src/`. Each model has a descriptor and metadata under:

```text
<root>/
  .erp/xpp.json
  src/<Model>/Descriptor/<Model>.xml
  src/<Model>/<Model>/AxClass/<Class>.xml
```

Run `pac package init` instead of hand-writing the descriptor/config. Add metadata files surgically after inspecting existing paths. PAC compiles and packages authored metadata; it does not scaffold custom services, `ICustomAPI` actions, or data entities. For runnable classes, labels, custom services, `ICustomAPI` actions, public OData data entities, and artifact-specific verification, use [`references/authoring.md`](references/authoring.md).

## Compile/build rules

- A normal compile runs labels -> X++ -> best-practice checks -> deployable ZIP.
- Use `--incremental` only for the edit loop. Run a non-incremental compile before a final deployment.
- Do not use `--skip-bp` unless the user explicitly requests it and understands the reduced validation.
- If multiple SDKs are installed, pass `--app-version`; otherwise PAC may reject ambiguous selection.
- Treat `Compile summary: ... failed` or any nonzero exit as failure even if a ZIP already exists from an earlier run.
- Verify the output ZIP was produced by the current run under `<root>/bin/`.
- If label compilation reports `XPPLC2010` and PAC fails despite exit code 0 from LabelC, add a valid label resource; do not delete logs or bypass the stage.

## Deploy and DB-sync rules

- **Deploy-only** means `--db-sync None`.
- `--build-type` controls how the server applies the package: `Full`, `Incremental`, or `Delete`; it is not a local build command.
- `--release-type Dev` is the normal test/development choice. `Release` forces Full DB sync server-side when a sync is requested.
- `Delete` ignores DB-sync settings.
- Single-package deployment uses `--package <zip>`. Solution-mode deployment omits `--package`, reads `.erp/xpp.json`, topologically orders models, deploys them, then runs one requested DB sync.
- PAC injects `fnomoduledefinition.json` into the ZIP at deploy time. Copy the artifact first if an immutable checksum must be retained.
- Standalone DB sync and deploy-with-sync are separate supported workflows; never redeploy merely to satisfy a DB-sync-only request.

See [`references/workflows.md`](references/workflows.md) for compile-only, deploy-only, DB-sync-only, multi-model, and full lifecycle sequences. Apply the success gates, diagnostics flow, and error mappings in [`references/validation.md`](references/validation.md) to every compile, deployment, DB sync, and runtime verification.

## End-to-end workflow

For “make this X++ change and deploy it”:

1. Inspect the repo and preserve existing work.
2. Confirm model/class names, publisher, and layer before scaffolding a new model.
3. Run `pac package init --package-type erp` only when the model does not exist.
4. Add or edit the requested X++ metadata, such as classes, contracts, custom services, service groups, `ICustomAPI` actions and security, public data entities, and required labels.
5. Confirm/authenticate the target environment and verify ERP linkage/version.
6. Install or reuse the matching SDK.
7. Compile non-incrementally and require zero compile errors. Address best-practice warnings unless the user accepts them.
8. Deploy with explicit build/release/DB-sync modes.
9. Apply the deployment success criteria in [`references/validation.md`](references/validation.md), pin the Dataverse CLI profile and transport-specific ERP MCP target to the confirmed environment, then verify the deployed artifact through its actual surface:
   - Runnable class: open `https://<erp-host>/?mi=SysClassRunner&cls=<ClassName>`.
   - Custom service: inspect the X++ implementation for side effects before invoking `erp:<ServiceGroup>/<Service>/<Operation>` with `dataverse api invoke --target erp --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"`; use `list`/`describe` only for discovery.
   - `ICustomAPI` action: use ERP MCP `api_find_actions` to validate its action menu item and contract, then invoke only approved inputs and compare every returned property and expected mutation with the observed result.
   - Public OData data entity: inspect and query it with `dataverse data describe|query --target erp`, adding `--context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"` to each command.
   - Security acceptance: invoke an `ICustomAPI` as a non-administrator test user assigned the intended custom role. Administrator execution is diagnostic only and does not validate the privilege/duty/role chain.
10. Report the package path, environment, async operation ID, terminal status, DB-sync mode, and artifact-specific verification result. Never claim runtime behavior that was not actually observed.

## Common mistakes — do not use these

| Wrong | Correct |
|---|---|
| `pac xpp install` | `pac tool xpp install` |
| `pac xpp compile` | `pac package compile --package-type erp` |
| `pac package build` | `pac package compile --package-type erp` |
| `pac package deploy --package-type xpp` | `--package-type erp` |
| Passing the ERP URL to `--environment` | Pass the linked Dataverse URL |
| Omitting `--package` for one ZIP | Add `--package <zip>` |
| Adding `--package` for repo-wide deployment | Omit it and use `--solution-root` |
| `pac package db-sync --db-sync None` | `None` is deploy-only; standalone modes are `Full`, `Module`, `Incremental` |
| Module sync without `--modules` | Add `--modules ModelA,ModelB` |
| Incremental sync without `--argument-file` | Add a valid `IncrementalSyncParameters` JSON file |

# ERP (Finance and Operations) target routing

**ERP intent:** Load `dv-overview` first for Finance and Operations requests, then `dv-connect` for setup or existing-linkage diagnostics, `dv-query` for business-data reads, or `dv-data` for record writes and DMF imports. For write previews and import planning, load `dv-data` even when execution is prohibited; this overview does not replace the specialist's operation-specific guidance. Do not load `erp-xpp` for record reads; reserve it for X++ code development and deployment.

On Unified Operations environments, ERP is provisioned on top of the same Dataverse environment — it's an app running on Dataverse, not a separate product. Same auth profile, same tenant, same `pac auth list`. The Dataverse CLI surfaces the ERP linkage automatically (`dataverse org who --json` includes `erpUrl`, version, deployment type, env state when ERP is linked; `dataverse env list` adds an ERP URL column).

The same skills (`dv-connect`, `dv-query`, `dv-data`) cover both targets — the routing differs by which tool the agent reaches for, not which skill. Batch administration uses `dv-admin`, and X++ development uses `erp-xpp`.

## Detecting ERP context

The user's request involves ERP when any of the following is true:

- They explicitly mention ERP, Finance and Operations, F&O, or Dynamics 365 Finance and Operations, or pass `--target erp`.
- The entity name is an ERP public entity — examples: `SalesOrderHeaders`, `PurchaseOrderHeaders`, `CustomerGroupsV3`, `BatchJobs`, `ExpMobileMasterData`, `DataManagementDefinitionGroups`, `Currencies`.
- The topic is ERP-specific: batch jobs, financial dimensions, data management framework, `dataAreaId`, cross-company, legal entity, X++.

If unsure whether the env has ERP, run `dataverse org who --json --context "app=dataverse-skills/<ver>;skill=dv-overview;agent=<agent>"` — a non-null `erpUrl` field confirms linkage.

## Tool priority for ERP target

Same shape as Dataverse — MCP first, CLI for medium volume, dedicated commands for service-style endpoints:

1. **ERP MCP** for simple, interactive reads/writes. The Dataverse CLI ships an ERP MCP proxy — `dataverse mcp <erpUrl>` auto-routes to the ERP MCP endpoint when the URL host is an ERP host. One-time client allow-list via `dataverse mcp allow <appId> --erp --context "app=dataverse-skills/<ver>;skill=dv-connect;agent=<agent>"`. Setup is in `dv-connect`.

2. **Dataverse CLI `data` commands with `--target erp`** for medium volume, composite keys, cross-company, and ad-hoc CRUD. Reads, counts and runtime schema discovery (`data query|get|count|describe`) belong to **dv-query**, whose `references/erp-reads.md` holds the templates. Writes (`data create|update|delete`), including previews of a write the user will run themselves, belong to **dv-data**, whose `references/erp-writes.md` holds the templates. Load the specialist: the command templates, composite-key format and attribution are deliberately not repeated here. The ERP URL is auto-discovered from the active auth profile -- no separate connection step.

3. **`dataverse api invoke --target erp`** for ERP Custom Services (`/api/services/<group>/<service>/<operation>`) — these are the "unbound action" surface (ERP OData has no truly unbound actions; global ops live under `/api/services/`). Discovery uses `dataverse api list --target erp --context "app=dataverse-skills/<ver>;skill=dv-query;agent=<agent>"` and `dataverse api describe --target erp --context "app=dataverse-skills/<ver>;skill=dv-query;agent=<agent>"`. Add the same context to `invoke`. Use `erp:ServiceGroup/Service/Operation` syntax or pass `--service-group`/`--service` separately.

4. **ERP batch jobs** (`dataverse erp batch list|cancel`) on the linked ERP instance: load **dv-admin**, which owns the options, ordering and attribution.

5. **PAC CLI X++ lifecycle** for source models and deployable packages: `pac package init --package-type erp`, `pac tool xpp install`, `pac package compile --package-type erp`, `pac package deploy --package-type erp`, and `pac package db-sync`. Use **erp-xpp**.

6. **DMF data packages** for write volume above what `data create/update` covers reasonably (~hundreds+) — there is no `CreateMultiple` analog on ERP OData. For planning or execution, load **dv-data** and follow [`erp-writes.md`](../../dv-data/references/erp-writes.md); this overview does not replace the specialist's DMF workflow.

## Reads for ERP

Load **dv-query** for ERP reads -- small and interactive (ERP MCP if available, else CLI), cross-company, single records by composite key, and counts. Its `references/erp-reads.md` holds the `data query|get|count --target erp` templates.

What's different from Dataverse OData:

- **No FetchXML, no SQL, no `$apply`.** ERP exposes OData only. Use `--select` / `--filter` / `--top` / `--orderby` / `--expand`. For aggregation, pull and aggregate locally (pandas).
- **Composite keys are common** — `dataAreaId='usmf',OrderNumber='SO-001'`. Pass the whole expression as `--key "<expr>"`.
- **`--cross-company`** is the equivalent of "query across all legal entities." Without it, queries are scoped to the user's default company.
- **Entity sets are PascalCase plurals** (`SalesOrderHeaders`, not `salesorderheader`).
- **`data associate` / `data disassociate`** are not supported on ERP. Set or clear the linking property on the entity via `data update --target erp`.

## Writes for ERP

Load **dv-data** for ERP writes and write previews. For single-record CRUD prefer ERP MCP (10 records or fewer); for programmatic or scripted writes use the CLI, whose `data create|update|delete --target erp` templates (including `--no-confirm` for scripted deletes) are in dv-data's `references/erp-writes.md`.

For bulk writes, go to DMF (tier 6 above). There is no efficient Python SDK path for ERP today.

## Discover what's on an entity

Before writing a query or action call against an unfamiliar ERP entity, load **dv-query** and use `data describe --target erp` from its `references/erp-reads.md` -- it returns the entity's schema, key fields, properties, navigations, and **bound actions** in one small JSON response (no expensive `$metadata` download).

The output reflects what is **actually routable at runtime** — empty `Actions[]` means the entity exposes no bound actions on this env (even if X++ declares some). This avoids the "try the action, get a 404, try a different name" exploration loop.

## X++ development

ERP X++ authoring, SDK installation, package compilation/build, deployment, database synchronization, and verification of deployed X++ artifacts are covered by **erp-xpp**. Verification can include ERP custom services/APIs, runnable classes, and public OData data entities. Use ERP API or data commands only for post-deployment verification; do not use ERP OData, MCP, DMF, or Dataverse solution ALM to author, compile, package, or deploy X++ customizations.

## What's out of scope for skills

- **ERP UI customization** (form personalizations, workflow editor) — out of skill scope.
- **LCS / Power Platform admin tasks specific to ERP** (LCS uploads, environment lifecycle) — out of skill scope.

For supported data and administration operations, `dv-connect`, `dv-query`, `dv-data`, and `dv-admin` route to the appropriate Dataverse or ERP target. `erp-xpp` is exclusively for Finance and Operations X++ development and deployment; it does not handle Dataverse customizations.

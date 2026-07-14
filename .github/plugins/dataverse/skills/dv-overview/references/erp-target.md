# ERP (Finance and Operations) target routing

On Unified Operations environments, ERP is provisioned on top of the same Dataverse environment — it's an app running on Dataverse, not a separate product. Same auth profile, same tenant, same `pac auth list`. The Dataverse CLI surfaces the ERP linkage automatically (`dataverse org who --json` includes `erpUrl`, version, deployment type, env state when ERP is linked; `dataverse env list` adds an ERP URL column).

The same skills (dv-connect, dv-query, dv-data) cover both targets — the routing differs by **which tool** the agent reaches for, not which skill.

## Detecting ERP context

The user's request involves ERP when any of the following is true:

- They explicitly mention ERP, Finance and Operations, F&O, or Dynamics 365 Finance and Operations, or pass `--target erp`.
- The entity name is an ERP public entity — examples: `SalesOrderHeaders`, `PurchaseOrderHeaders`, `CustomerGroupsV3`, `BatchJobs`, `ExpMobileMasterData`, `DataManagementDefinitionGroups`, `Currencies`.
- The topic is ERP-specific: batch jobs, financial dimensions, data management framework, `dataAreaId`, cross-company, legal entity, X++.

If unsure whether the env has ERP, run `dataverse org who --json` — a non-null `erpUrl` field confirms linkage.

## Tool priority for ERP target

Same shape as Dataverse — MCP first, CLI for medium volume, dedicated commands for service-style endpoints:

1. **ERP MCP** for simple, interactive reads/writes. The Dataverse CLI ships an ERP MCP proxy — `dataverse mcp <erpUrl>` auto-routes to the ERP MCP endpoint when the URL host is an ERP host. One-time client allow-list via `dataverse mcp allow <appId> --erp`. Setup is in `dv-connect`.

2. **Dataverse CLI `data` commands with `--target erp`** for medium volume, composite keys, cross-company, and ad-hoc CRUD:
   ```bash
   dataverse data query  --target erp --table <EntitySet> --select "..." [--cross-company] [--top 100]
   dataverse data get    --target erp --table <EntitySet> --key "<composite>"
   dataverse data count  --target erp --table <EntitySet> [--filter "..."]
   dataverse data create --target erp --table <EntitySet> --data '{...}'
   dataverse data update --target erp --table <EntitySet> --key "<composite>" --data '{...}'
   dataverse data delete --target erp --table <EntitySet> --key "<composite>" [--no-confirm]
   dataverse data describe --target erp --table <EntitySet>
   ```
   ERP URL is auto-discovered from the active auth profile — no separate connection step. `--json` is supported on read commands for script consumption.

3. **`dataverse api invoke --target erp`** for ERP Custom Services (`/api/services/<group>/<service>/<operation>`) — these are the "unbound action" surface (ERP OData has no truly unbound actions; global ops live under `/api/services/`). Discovery via `dataverse api list --target erp` and `dataverse api describe --target erp`. Use `erp:ServiceGroup/Service/Operation` syntax or pass `--service-group`/`--service` separately.

4. **`dataverse erp batch list|cancel`** for ERP batch jobs on the linked ERP instance.

5. **DMF data packages** for write volume above what `data create/update` covers reasonably (~hundreds+) — there is no `CreateMultiple` analog on ERP OData; DMF is the platform's bulk path. The flow uses bound-to-collection actions on `DataManagementDefinitionGroups`:
   ```
   GetAzureWriteUrl     → returns blob SAS URL
   (upload package.zip to that URL)
   ImportFromPackage    → returns executionId
   GetExecutionSummaryStatus  → poll until terminal
   GetExecutionErrors   → on Failed / PartiallySucceeded
   ```
   DMF is reachable via `dataverse api invoke --target erp` against the bound actions.

## Reads for ERP

```bash
# Small / interactive — ERP MCP if available, else CLI
dataverse data query --target erp --table SalesOrderHeaders --top 10 \
  --select "SalesOrderNumber,CustomerAccount,SalesOrderStatus"

# Cross-company — all legal entities the user can read
dataverse data query --target erp --table CustomerGroups --cross-company \
  --select "CustomerGroupId,Description,dataAreaId" --top 50

# Single record by composite key
dataverse data get --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='10'"

# Count
dataverse data count --target erp --table Currencies --filter "CurrencyCode eq 'AED'"
```

What's different from Dataverse OData:

- **No FetchXML, no SQL, no `$apply`.** ERP exposes OData only. Use `--select` / `--filter` / `--top` / `--orderby` / `--expand`. For aggregation, pull and aggregate locally (pandas).
- **Composite keys are common** — `dataAreaId='usmf',OrderNumber='SO-001'`. Pass the whole expression as `--key "<expr>"`.
- **`--cross-company`** is the equivalent of "query across all legal entities." Without it, queries are scoped to the user's default company.
- **Entity sets are PascalCase plurals** (`SalesOrderHeaders`, not `salesorderheader`).
- **`data associate` / `data disassociate`** are not supported on ERP. Set or clear the linking property on the entity via `data update --target erp`.

## Writes for ERP

For single-record CRUD, prefer ERP MCP (≤10 records). For programmatic / scripted writes, use the CLI:

```bash
dataverse data create --target erp --table CustomerGroups \
  --data '{"dataAreaId":"usmf","CustomerGroupId":"demo","Description":"demo group"}'

dataverse data update --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='demo'" \
  --data '{"Description":"demo group (updated)"}'

dataverse data delete --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='demo'" --no-confirm
```

`--no-confirm` suppresses the interactive prompt on `delete` for scripted use.

For bulk writes, go to DMF (tier 5 above). There is no efficient Python SDK path for ERP today.

## Discover what's on an entity

Before writing a query or action call against an unfamiliar ERP entity, use `data describe` — it returns the entity's schema, key fields, properties, navigations, and **bound actions** in one small JSON response (no expensive `$metadata` download):

```bash
dataverse data describe --target erp --table ExpMobileMasterData
dataverse data describe --target erp --table SalesOrderHeaders --json
```

The output reflects what is **actually routable at runtime** — empty `Actions[]` means the entity exposes no bound actions on this env (even if X++ declares some). This avoids the "try the action, get a 404, try a different name" exploration loop.

## What's out of scope for skills

- **ERP X++ authoring and package builds** — these go through `pac package init/compile/db-sync/deploy`; not a runtime data-plane operation.
- **ERP UI customization** (form personalizations, workflow editor) — out of skill scope.
- **LCS / Power Platform admin tasks specific to ERP** (LCS uploads, environment lifecycle) — out of skill scope.

For anything in scope, the skills (dv-connect, dv-query, dv-data) handle Dataverse and ERP through the same routing — pick the target and the right tool follows.

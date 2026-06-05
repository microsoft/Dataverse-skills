# ERP (Finance & Operations) target routing

On Unified Operations environments, F&O is provisioned on top of the same Dataverse environment — it's an app running on Dataverse, not a separate product. Same auth profile, same `pac org who` output (the `erpUrl` field surfaces F&O when linked). The same skills (dv-connect, dv-query, dv-data) cover both Dataverse and ERP work; target selection drives the routing.

## Detecting ERP context

The user's request involves ERP when any of the following is true:

- They explicitly pass `--target erp` or mention ERP / Finance & Operations / F&O / Dynamics 365 Finance & Operations
- The entity name is an F&O public entity — examples: `SalesOrderHeaders`, `PurchaseOrderHeaders`, `CustomerGroupsV3`, `BatchJobs`, `ExpMobileMasterData`, `DataManagementDefinitionGroups`, `Currencies`
- The topic is F&O-specific: batch jobs, financial dimensions, data management framework, dataAreaId, cross-company, legal entity, X++

If unsure whether the env has ERP, run `dataverse org who --json` — a non-null `erpUrl` field confirms linkage.

## Tool priority for ERP target

The MCP / SDK / Web API priority is the Dataverse path — those tools reach Dataverse entities, not F&O. For ERP, the priority is:

1. **Dataverse CLI single-record CRUD** for 1-10 records:
   ```bash
   dataverse data create --target erp --table <EntitySet> --data '{...}'
   dataverse data update --target erp --table <EntitySet> --key "<composite>" --data '{...}'
   dataverse data get    --target erp --table <EntitySet> --key "<composite>"
   dataverse data delete --target erp --table <EntitySet> --key "<composite>"
   ```

2. **DMF data packages** for any volume above ~10 records — there is no `CreateMultiple` analog on F&O OData; DMF is the platform's bulk path. The flow uses bound-to-collection actions on `DataManagementDefinitionGroups`:
   ```
   GetAzureWriteUrl     → returns blob SAS URL
   (upload package.zip to that URL)
   ImportFromPackage    → returns executionId
   GetExecutionSummaryStatus  → poll until terminal
   GetExecutionErrors   → on Failed / PartiallySucceeded
   ```
   See `dv-data` for the full DMF pipeline.

3. **`dataverse api invoke --target erp`** for `/api/services/<group>/<service>/<operation>` Custom Services — these are F&O's "unbound action" surface (F&O OData has no truly unbound actions; global ops live under `/api/services/`).

## Reads for ERP

All reads go through `dataverse data query --target erp`:

```bash
# Single company (the user's default)
dataverse data query --target erp --table SalesOrderHeaders --top 10 \
  --select "SalesOrderNumber,CustomerAccount,SalesOrderStatus"

# Cross-company (all companies the user has access to)
dataverse data query --target erp --table CustomerGroups --cross-company \
  --select "CustomerGroupId,Description,dataAreaId" --top 50

# Get a single record by composite key
dataverse data get --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='10'"
```

What's different from Dataverse OData:

- **No FetchXML, no SQL, no `$apply`.** ERP exposes OData only. Use `--select` / `--filter` / `--top` / `--orderby` / `--expand`.
- **Composite keys are common** — `dataAreaId='usmf',OrderNumber='SO-001'`. Pass the whole thing as `--key "<expr>"`.
- **`--cross-company`** is the equivalent of "query across all legal entities." Without it, queries are scoped to the user's default company.
- **Entity sets are PascalCase plurals** (`SalesOrderHeaders`, not `salesorderheader`).

## Discover what's on an entity

Before writing a query or action call against an unfamiliar ERP entity, use `data describe` — it returns the entity's schema, key fields, and bound actions in one small JSON response (no expensive `$metadata` download):

```bash
# Human-readable
dataverse data describe --target erp --table ExpMobileMasterData

# Raw JSON for programmatic use
dataverse data describe --target erp --table SalesOrderHeaders --json
```

The output reflects what is **actually routable at runtime** — empty `Actions[]` means the entity exposes no bound actions on this env (even if X++ declares some). This avoids the "try the action, get a 404, try a different name" exploration loop.

## What's out of scope for skills

- **F&O X++ authoring and package builds** — these go through `pac package init/compile/db-sync/deploy`; not a runtime data-plane operation.
- **F&O UI customization** (form personalizations, workflow editor) — out of skill scope.
- **LCS / Power Platform admin tasks specific to F&O** (LCS uploads, environment lifecycle) — out of skill scope.

For anything in scope, the skills (dv-connect, dv-query, dv-data) handle Dataverse and ERP through the same routing — pick the target and the right tool follows.

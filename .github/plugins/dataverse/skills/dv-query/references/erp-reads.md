# Querying ERP data

When the env is ERP-linked (ERP provisioned on the same Dataverse env), ERP reads do not go through `DataverseClient`. Use one of:

1. **ERP MCP** for simple, interactive reads — if `dataverse mcp <erpUrl>` is wired up as an MCP server in your client. Same `read_query` / `read_metadata` shape as Dataverse MCP.
2. **Dataverse CLI `--target erp`** for everything else — composite keys, cross-company, `--top` paging, multi-record reads.

```bash
# Multi-record read
dataverse data query --target erp --table SalesOrderHeaders --top 200 \
  --select "SalesOrderNumber,CustomerAccount,SalesOrderStatus" \
  --filter "SalesOrderStatus eq Microsoft.Dynamics.DataEntities.SalesStatus'Backorder'" \
  --orderby "SalesOrderNumber"

# Single record by composite key (ERP keys are dataAreaId + business key)
dataverse data get --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='10'"

# Cross-company — all legal entities the user can read
dataverse data query --target erp --table CustomerGroups --cross-company \
  --select "CustomerGroupId,Description,dataAreaId" --top 50

# Count
dataverse data count --target erp --table Currencies --filter "CurrencyCode eq 'AED'"
```

Add `--json` on read commands for script consumption. The ERP URL is auto-discovered from the active auth profile.

For ERP Custom Services (`/api/services/...`), use `dataverse api invoke --target erp`. See [`erp-target.md`](../../dv-overview/references/erp-target.md).

## What's different from Dataverse OData

| Concept | Dataverse | ERP |
|---|---|---|
| Entity set casing | lowercase plural (`accounts`) | PascalCase plural (`SalesOrderHeaders`) |
| Primary key | single GUID | composite, often includes `dataAreaId` (e.g. `dataAreaId='usmf',CustomerGroupId='10'`) |
| Cross-org query | n/a — one org per env | `--cross-company` flag |
| Aggregation | `$apply` (Web API) | **Not supported** — pull and aggregate locally |
| FetchXML / SQL | supported | **Not supported** — OData only |
| Bound actions | per-entity | per-entity; discover via `dataverse data describe --target erp --table <T>` |
| Tooling | MCP / Python SDK / Web API / PAC CLI | ERP MCP / Dataverse CLI `--target erp` / `api invoke --target erp` |

## Discovering an unfamiliar ERP entity

```bash
dataverse data describe --target erp --table ExpMobileMasterData
dataverse data describe --target erp --table SalesOrderHeaders --json
```

Returns schema, key fields, properties, navigations, and runtime-routable bound actions in one call. Use before guessing entity-set names or action names.

For the broader ERP routing model (when to use which tool, DMF for bulk writes, ERP MCP setup), see [`erp-target.md`](../../dv-overview/references/erp-target.md) in `dv-overview`.

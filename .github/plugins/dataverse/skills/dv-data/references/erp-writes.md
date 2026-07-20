# Writing ERP data

When the env is ERP-linked — ERP (Finance and Operations) provisioned on the same Dataverse env — ERP writes do not go through the Python SDK. Use:

1. **ERP MCP** for simple, interactive writes — if `dataverse mcp <erpUrl>` is wired up as an MCP server. Same `create_record` / `update_record` / `delete_record` shape as Dataverse MCP.
2. **Dataverse CLI `--target erp`** for scripted single-record writes:

```bash
# Create
dataverse data create --target erp --table CustomerGroups \
  --data '{"dataAreaId":"usmf","CustomerGroupId":"demo","Description":"demo group"}'

# Update (composite key)
dataverse data update --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='demo'" \
  --data '{"Description":"demo group (updated)"}'

# Delete (suppress interactive confirm in scripts)
dataverse data delete --target erp --table CustomerGroups \
  --key "dataAreaId='usmf',CustomerGroupId='demo'" --no-confirm
```

3. **DMF (Data Management Framework) data packages** for bulk writes. ERP OData has **no `CreateMultiple` equivalent** — looping `data create` is the wrong tool at higher volume. DMF dispatch via `dataverse api invoke --target erp` against the `DataManagementDefinitionGroups` bound actions (`GetAzureWriteUrl` → upload zip → `ImportFromPackage` → `GetExecutionSummaryStatus`). See [`erp-target.md`](../../dv-overview/references/erp-target.md) for the full flow.

4. **`data associate` / `data disassociate` are not supported on ERP.** Set or clear the linking property on the entity directly via `dataverse data update --target erp`.

## Key differences from Dataverse writes

| Concept | Dataverse | ERP |
|---|---|---|
| Entity set casing | lowercase plural (`accounts`) | PascalCase plural (`CustomerGroups`) |
| Primary key | single GUID | composite, usually includes `dataAreaId` |
| Lookup binding | `@odata.bind` to navigation property | Set the FK property directly on the body |
| Bulk write | `CreateMultiple` via SDK | **No bulk API** — DMF is the platform path |
| Custom actions | bound/unbound via Web API | bound and unbound via `dataverse api invoke --target erp` |

For the broader ERP routing model (when to use which tool, ERP MCP setup), see [`erp-target.md`](../../dv-overview/references/erp-target.md) in `dv-overview`.

# Metadata troubleshooting

Detail for `dv-metadata`.

## Common Web API Error Codes

| Error Code | Meaning | Recovery |
|---|---|---|
| `0x80040216` | Transient metadata cache error. Column or table metadata not yet propagated. | Wait 3-5 seconds and retry. Usually succeeds on second attempt. |
| `0x80048d19` | Invalid property in payload. A field name doesn't match any column on the table. | Check logical column names — use `EntityDefinitions(LogicalName='...')/Attributes` to verify. |
| `0x80040237` | Schema name already exists. | Verify the column/table exists before creating a new one — it may have been created by a previous timed-out call. |
| `0x8004431a` | Publisher prefix mismatch. | Ensure all schema names use the solution's publisher prefix. |
| `0x80060891` | Metadata cache not ready after table creation. | Call `GET EntityDefinitions(LogicalName='...')` first to force cache refresh, then retry. |

Always translate error codes to plain English before presenting them to the user.

## EntityDefinitions Filter Limitation

**`startswith()` is NOT supported as a filter on `EntityDefinitions`.** This query will return a 400 error:

```
GET /api/data/v9.2/EntityDefinitions?$filter=startswith(LogicalName,'new_')  # BROKEN
```

To retrieve metadata for multiple custom tables, query each table individually:
```python
GET /api/data/v9.2/EntityDefinitions(LogicalName='new_projectbudget')?$select=LogicalName,EntitySetName
```

Or query all and filter client-side:
```python
GET /api/data/v9.2/EntityDefinitions?$select=LogicalName,EntitySetName
```

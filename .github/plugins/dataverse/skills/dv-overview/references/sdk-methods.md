# Dataverse SDK method cheat-sheet

These are Dataverse SDK operations, not direct Finance and Operations database
access. Ordinary ERP business-data reads use ERP MCP/OData through **dv-query**.

**SDK method cheat-sheet** (anti-hallucination, *not* a preference signal): SDK method names are the least discoverable surface, so agents invent them. This maps common ops to the exact call. Each op is equally reachable via MCP/CLI per Hard Rule 2; see the noted skill for the full pattern.

| Operation | SDK call | Skill |
| --- | --- | --- |
| Create / update / delete records | `client.records.create()` / `.update()` / `.delete()` (pass a list for bulk) | `dv-data` |
| Upsert on an alternate key | `client.records.upsert()` | `dv-data` |
| Query / filter records | `client.records.list(...)` (flat) or `.list_pages(...)` (streaming) | `dv-query` |
| One record by GUID | `client.records.retrieve(table, guid)` (`None` if missing) | `dv-query` |
| Aggregation / server-side joins | `client.query.fetchxml(xml)` (aggregates + link-entity) | `dv-query` |
| Fluent query build (chainable) | `client.query.builder(Table).where(...).execute()` | `dv-query` |
| Limited SQL read | `client.query.sql("SELECT ...")` | `dv-query` |
| Load into pandas | `client.query.builder(table).select(...).execute().to_dataframe()` | `dv-query` |
| Upload to a file column | `client.files.upload(...)` | `dv-data` |
| Create tables / columns / lookups / N:N | `client.tables.create()` / `.add_columns()` / `.create_lookup_field()` / `.create_many_to_many_relationship()` | `dv-metadata` |
| Create an alternate key (enables upsert) | `client.tables.create_alternate_key(...)` | `dv-metadata` |
| Inspect existing schema | `client.tables.list_columns(table)` / `.list_table_relationships(table)` | `dv-metadata` |
| Create publisher / solution | `client.records.create("publisher" / "solution", {...})` | `dv-solution` |

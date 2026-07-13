# Data Retention / Archival — `pac data retention` command reference

Data retention moves old records to long-term storage without permanently deleting them. This is the full command syntax and argument reference for the `dv-admin` retention flow.

## Commands

```bash
pac data retention enable-entity --entity activitypointer --environment https://myorg.crm.dynamics.com
pac data retention set --entity activitypointer \
    --criteria "<fetch><entity name='activitypointer'><filter><condition attribute='createdon' operator='lt' value='2023-01-01'/></filter></entity></fetch>"
pac data retention list --environment https://myorg.crm.dynamics.com
pac data retention show --id <config-id>
pac data retention status --id <operation-id>
```

## Argument reference (`pac data retention set`)

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--entity` | `-e` | Yes | Logical name of the table |
| `--criteria` | `-c` | Yes | FetchXML defining which records to archive |
| `--start-time` | `-st` | No | ISO 8601 start time. Defaults to now |
| `--recurrence` | `-r` | No | RFC 5545 recurrence pattern |
| `--environment` | `-env` | No | Target environment URL |

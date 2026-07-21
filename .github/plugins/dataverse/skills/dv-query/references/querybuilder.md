# QueryBuilder — Fluent Query API

> **Version check:** QueryBuilder is available on the GA SDK (`>=1.0.0`). `client.records.list()` / `.list_pages()` cover the same reads without the fluent chain if you prefer. The skills document the supported API — if a method isn't documented here, don't assume it exists; check the skill's version notes.

QueryBuilder offers composable filters and OR/AND logic, executed via `.execute()` (then `.to_dataframe()` on the result). It is a convenience layer over the same flat-read path as `client.records.list()` — not a replacement.

```python
from PowerPlatform.Dataverse.models.filters import eq

# Basic — flat record iteration
for record in client.query.builder("opportunity") \
        .select("name", "estimatedvalue", "statuscode") \
        .where(eq("statuscode", 1)) \
        .order_by("estimatedvalue", descending=True) \
        .top(100) \
        .execute():
    print(record["name"], record["estimatedvalue"])
```

**DataFrame result** — call `.execute()`, then `.to_dataframe()` on the result:

```python
df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue", "statuscode") \
    .where(eq("statuscode", 1)) \
    .execute() \
    .to_dataframe()
```

**Composable filter expressions** — for OR/AND logic:

```python
from PowerPlatform.Dataverse.models.filters import eq, gt

active_or_pending = (eq("statecode", 0) | eq("statecode", 1)) & gt("estimatedvalue", 10000)

df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue") \
    .where(active_or_pending) \
    .execute() \
    .to_dataframe()
```

**Paged execution** — when you need per-page control:

```python
for page in client.query.builder("opportunity").select("name").execute_pages():
    for record in page:
        print(record["name"])
```

---

## Pandas DataFrame Handoff

**Prefer `client.query.builder(t).select(...).execute().to_dataframe()` for any read that involves analysis, verification, comparison, or export.** Use `client.records.list_pages()` (streaming, one page at a time) only when you need per-page processing (e.g., streaming to a file) or when the table is too large to fit in memory.

| Task | Use | Why |
|---|---|---|
| Aggregate, group, pivot | `client.query.builder(t).execute().to_dataframe()` | pandas does this natively |
| Compare counts after import | `client.records.list_pages()` with single-column select | Page-count is memory-efficient; no need to load full DataFrame for a count |
| Build a lookup map (small table) | `client.query.builder(t).execute().to_dataframe()` | `dict(zip(df["src_id"], df["guid"]))` — 1 line |
| Build a lookup map (100K+ rows) | `client.records.list_pages()` | Streaming pages use less memory |
| Export to CSV/Excel | `client.query.builder(t).execute().to_dataframe()` | `df.to_csv("out.csv")` |
| Stream large result to file | `client.records.list_pages()` | Page-at-a-time avoids loading all into memory |
| Cross-table join/aggregation | `client.query.sql()`/`fetchxml()` (server-side), else builder->DataFrame per table + `pd.merge()` | `sql()` does INNER/LEFT JOIN; pandas merge for the rest |

**Always pass `select=` when calling `client.query.builder(...).select(...)`, `client.records.list()`, or `client.records.list_pages()`.** Omitting `select` returns every column — on a 100K-row table with 20 columns, this transfers 10-20x more data than needed and turns a 15-second query into a 90-second query. Only request the columns you need.

Use the builder's `.execute().to_dataframe()` to pull Dataverse records directly into a pandas DataFrame — no manual page iteration needed:

```python
import pandas as pd

# Returns a fully consolidated DataFrame (all pages)
df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue", "statuscode", "_parentaccountid_value") \
    .execute() \
    .to_dataframe()
print(df.groupby("statuscode")["estimatedvalue"].agg(["count", "sum", "mean"]))
```

**DataFrame write-back** — update or create records from a DataFrame. These are write operations — agents consulting **dv-data** for writes should also check here for the DataFrame variant. **Note:** DataFrame write-back supports `create` and `update` only — not upsert. For idempotent imports with alternate keys, use `client.records.upsert()` with `UpsertItem` (see **dv-data**).

```python
# Update records — DataFrame must include the primary key column
client.dataframe.update("opportunity", df_updates, id_column="opportunityid")

# Create records — returns a Series of new GUIDs
guids = client.dataframe.create("opportunity", df_new_records)
```

**Fallback (manual page iteration)** — use only when you need per-page processing. Prefer the builder's `.execute().to_dataframe()` above for the common case:

```python
all_records = []
for page in client.records.list_pages("opportunity",
    select=["name", "estimatedvalue", "statuscode"],
):
    all_records.extend([dict(r) for r in page])  # convert Record objects to dicts
df = pd.DataFrame(all_records)
```

# QueryBuilder — Fluent Query API (SDK b8+)

> **Version check:** QueryBuilder requires SDK version b8 or later (`pip show PowerPlatform-Dataverse-Client` → Version ≥ 0.1.0b8). If you're on b7 or earlier, `client.query.builder()` does not exist — use `client.records.get()` instead (documented above). Do NOT introspect the SDK with `dir()` or `inspect` to discover APIs — if a method isn't documented here, it doesn't exist in the installed version.

QueryBuilder offers composable filters, OR/AND logic, and `.to_dataframe()` in one chain. It calls `client.records.get()` internally — it is a convenience layer, not a replacement.

```python
# Basic — flat record iteration
for record in client.query.builder("opportunity") \
        .select("name", "estimatedvalue", "statuscode") \
        .filter_eq("statuscode", 1) \
        .order_by("estimatedvalue", descending=True) \
        .top(100) \
        .execute():
    print(record["name"], record["estimatedvalue"])
```

**Direct DataFrame result** — combines query + pandas handoff in one call:

```python
df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue", "statuscode") \
    .filter_eq("statuscode", 1) \
    .to_dataframe()
```

**Composable filter expressions** — for OR/AND logic:

```python
from PowerPlatform.Dataverse.models.filters import eq, gt

active_or_pending = (eq("statecode", 0) | eq("statecode", 1)) & gt("estimatedvalue", 10000)

df = client.query.builder("opportunity") \
    .select("name", "estimatedvalue") \
    .where(active_or_pending) \
    .to_dataframe()
```

**Paged execution** — when you need per-page control:

```python
for page in client.query.builder("opportunity").select("name").execute(by_page=True):
    for record in page:
        print(record["name"])
```

---

## Pandas DataFrame Handoff

**Prefer `client.dataframe.get()` for any read that involves analysis, verification, comparison, or export.** Use `client.records.get()` with page iteration only when you need per-page processing (e.g., streaming to a file) or when the table is too large to fit in memory.

| Task | Use | Why |
|---|---|---|
| Aggregate, group, pivot | `client.dataframe.get()` | pandas does this natively |
| Compare counts after import | `client.records.get()` with single-column select | Page-count is memory-efficient; no need to load full DataFrame for a count |
| Build a lookup map (small table) | `client.dataframe.get()` | `dict(zip(df["src_id"], df["guid"]))` — 1 line |
| Build a lookup map (100K+ rows) | `client.records.get()` | Page iterator uses less memory |
| Export to CSV/Excel | `client.dataframe.get()` | `df.to_csv("out.csv")` |
| Stream large result to file | `client.records.get()` | Page-at-a-time avoids loading all into memory |
| Cross-table join/aggregation | `client.dataframe.get()` both tables with `$select` + `pd.merge()` | pandas merge is sub-second; use `$select` to minimize network transfer |

**Always pass `select=` when calling `client.dataframe.get()` or `client.records.get()`.** Omitting `select` returns every column — on a 100K-row table with 20 columns, this transfers 10-20x more data than needed and turns a 15-second query into a 90-second query. Only request the columns you need.

Use `client.dataframe.get()` to pull Dataverse records directly into a pandas DataFrame — no manual page iteration needed:

```python
import pandas as pd

# Returns a fully consolidated DataFrame (all pages)
df = client.dataframe.get("opportunity",
    select=["name", "estimatedvalue", "statuscode", "_parentaccountid_value"],
)
print(df.groupby("statuscode")["estimatedvalue"].agg(["count", "sum", "mean"]))
```

**DataFrame write-back** — update or create records from a DataFrame. These are write operations — agents consulting **dv-data** for writes should also check here for the DataFrame variant. **Note:** DataFrame write-back supports `create` and `update` only — not upsert. For idempotent imports with alternate keys, use `client.records.upsert()` with `UpsertItem` (see **dv-data**).

```python
# Update records — DataFrame must include the primary key column
client.dataframe.update("opportunity", df_updates, id_column="opportunityid")

# Create records — returns a Series of new GUIDs
guids = client.dataframe.create("opportunity", df_new_records)
```

**Fallback (manual page iteration)** — use only when you need per-page processing. Prefer `client.dataframe.get()` above for the common case:

```python
all_records = []
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "statuscode"],
):
    all_records.extend([dict(r) for r in page])  # convert Record objects to dicts
df = pd.DataFrame(all_records)
```

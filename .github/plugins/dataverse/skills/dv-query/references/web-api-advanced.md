# Web API advanced — `$expand` on N:N and `$apply` aggregation


> **Note:** These raw Web API examples fetch a single page only. If results exceed one page (~5000 records), you must follow `@odata.nextLink` in a loop to get all records. For most N:N and aggregation queries, a single page is sufficient.

```python
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # get_token() is correct here — SDK cannot do this

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

# Tickets with their linked KB articles (N:N)
url = (f"{env}/api/data/v9.2/new_tickets"
       f"?$select=new_name"
       f"&$expand=new_ticket_kbarticle($select=new_title)")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req, timeout=150) as resp:
    data = json.loads(resp.read())
    for ticket in data["value"]:
        articles = [a["new_title"] for a in ticket.get("new_ticket_kbarticle", [])]
        print(f"{ticket['new_name']}: {', '.join(articles)}")
```

---

## $apply Aggregation (Web API — SDK does not support)

**Use `$apply` for any single-table aggregation** — "which X has the most Y", "total by group", "top N", "average per category". This runs server-side and returns only the grouped results. One HTTP call, no client-side processing. Limit: 50,000 source records per aggregation.

**Common $apply patterns:**

| User question | $apply expression |
|---|---|
| "total sales by status" | `groupby((statuscode),aggregate(amount with sum as total))` |
| "which account has the most revenue" | `groupby((_parentaccountid_value),aggregate(estimatedvalue with sum as total))` then sort client-side |
| "how many records per category" | `groupby((category),aggregate($count as count))` |
| "average deal size by region" | `groupby((region),aggregate(amount with average as avg))` |

```python
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # get_token() is correct here — SDK does not support $apply

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

def apply_query(entity_set, apply_expr):
    """Run a $apply aggregation query. Returns list of result dicts."""
    url = f"{env}/api/data/v9.2/{entity_set}?$apply={apply_expr}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=150) as resp:
        return json.loads(resp.read()).get("value", [])

# Example 1: Count and sum by status
results = apply_query("opportunities",
    "groupby((statuscode),aggregate($count as count,estimatedvalue with sum as total_value))")
for row in results:
    print(f"Status {row['statuscode']}: {row['count']} records, ${row['total_value']:,.0f}")

# Example 2: Top accounts by total deal value
results = apply_query("opportunities",
    "groupby((_parentaccountid_value),aggregate(estimatedvalue with sum as total))")
top = sorted(results, key=lambda r: r.get("total", 0), reverse=True)[:10]
for r in top:
    print(f"Account {r['_parentaccountid_value']}: ${r['total']:,.0f}")
```

**When `$apply` won't work** (cross-table questions, complex transforms):

`$apply` only works within a single entity set. For cross-table aggregation, use `client.dataframe.get()` with minimal `$select` on each table, then `pd.merge()`. The merge itself is sub-second; the bottleneck is network transfer, which `$select` minimizes:

```python
import pandas as pd

# Only the columns needed — always pass select= on large tables
df_a = client.dataframe.get("prefix_tablea",
    select=["prefix_keycolumn", "prefix_metric"])
df_b = client.dataframe.get("prefix_tableb",
    select=["prefix_keycolumn", "prefix_dimension"])

merged = pd.merge(df_a, df_b, on="prefix_keycolumn")
top = merged.groupby("prefix_dimension")["prefix_metric"].sum().nlargest(10)
print(top)
```

**Performance rules for client-side processing:**
- Always use `$select` — fetching all columns on 100K rows transfers 10-20x more data than needed
- Use `client.dataframe.get()`, not raw HTTP page iteration
- pandas `merge` + `groupby` on 100K-300K rows takes seconds — the bottleneck is network transfer, not Python processing

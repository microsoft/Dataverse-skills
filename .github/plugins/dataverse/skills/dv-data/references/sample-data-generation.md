# Sample Data Generation

Generate and insert realistic sample records into any Dataverse table. Useful for development, demos, and testing.

**Use the Python SDK** (`client.records.create()`) — not raw `urllib` or `requests`.

## Agentic Flow

### Step 1: Confirm environment and count

Before creating anything, confirm:
- **Target environment** — run `pac auth list` to show the active environment
- **Record count** — default is **5 records** unless the user specifies otherwise
- **Table name** — get the logical name (e.g., `account`, `contact`, `cr123_customtable`)

### Step 2: Inspect the table schema

Use the EntityDefinitions metadata API to discover required columns and their types. Two non-obvious bits:

- **`$filter=AttributeOf eq null`** — without this, each lookup column returns a duplicated sub-attribute row (e.g. a `primarycontactid` Lookup plus a `_primarycontactid_value` pair), which makes the list twice as long and confuses downstream code.
- **`UserLocalizedLabel` is null on unlocalized columns** — dereference safely before reading `.Label`, otherwise custom tables without display names crash the loop.

```python
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support EntityDefinitions metadata

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
TABLE = "account"   # or any other table logical name

params = urllib.parse.urlencode({
    "$select": "LogicalName,AttributeType,RequiredLevel,DisplayName",
    "$filter": "AttributeOf eq null",
})
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/EntityDefinitions(LogicalName='{TABLE}')/Attributes?{params}",
    headers={"Authorization": f"Bearer {get_token()}", "Accept": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    attrs = json.loads(resp.read())["value"]

for a in attrs:
    dn = (a.get("DisplayName") or {}).get("UserLocalizedLabel")
    label = dn["Label"] if dn else a["LogicalName"]
    if a["RequiredLevel"]["Value"] == "ApplicationRequired":
        print(f"REQUIRED  {a['LogicalName']:30s} {a['AttributeType']:15s} {label}", flush=True)
```

Filter or group the raw `attrs` list however the task needs — don't assume the printed shape above; inline code downstream should consume `attrs` directly.

### Step 3: Generate realistic data (by AttributeType)

Use the schema from Step 2 to pick a generator per column. No separate script — the agent writes this inline per request so it matches the actual table.

| AttributeType | Generate |
|---|---|
| `String` / `Memo` | Realistic text based on column name (e.g., `name` -> company names) |
| `Integer` / `Decimal` / `Money` | Random values within `MinValue`/`MaxValue` |
| `Boolean` | Alternate `true`/`false` |
| `DateTime` | Recent dates in ISO 8601 format |
| `Picklist` / `Status` | Integer option values (e.g., `industrycode: 1`) |
| `Lookup` | **Skip by default** — only set if user provides valid record IDs |
| `Uniqueidentifier` (non-PK) | Skip — let Dataverse auto-generate |

### Step 4: Create the records inline via the SDK — schema-driven

This template is **table-agnostic by design**. It reads the `attrs` list from Step 2 and dispatches by `AttributeType` — no table-specific field names or hardcoded sample values baked in. Use it as a starting point; override/extend `fake()` when the table has domain-specific needs (e.g., look up real picklist option values, generate industry-appropriate company names for `account`, etc.).

```python
import os, sys, random, datetime
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
client = DataverseClient(base_url=env_url, credential=get_credential())

TABLE = "account"   # any table logical name from Step 1
COUNT = 5           # confirmed with user
# `attrs` = the list returned by Step 2's EntityDefinitions query (re-run Step 2 if needed)

SKIP_TYPES = {"Lookup", "Uniqueidentifier", "EntityName", "State", "Status", "Owner", "Customer"}

def fake(attr, i):
    """Context-based value by AttributeType + PII-safe heuristics on column name."""
    name, t = attr["LogicalName"], attr["AttributeType"]
    if t in ("String", "Memo"):
        if "email" in name: return f"user{i}@example.com"
        if any(s in name for s in ("phone", "telephone", "fax")): return f"555-01{i:02d}"
        if "url" in name or "website" in name: return f"https://example.com/{name}/{i}"
        return f"Sample {name} {i}"
    if t in ("Integer", "BigInt"):          return random.randint(1, 1000)
    if t in ("Decimal", "Double", "Money"): return round(random.uniform(1, 10_000), 2)
    if t == "Boolean":                       return bool(i % 2)
    if t == "DateTime":
        d = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=i)
        return d.isoformat(timespec="seconds").replace("+00:00", "Z")
    if t in ("Picklist", "Status"):
        return 1   # placeholder — for real picklists, look up valid OptionSet values first
    return None    # skip Lookup, Uniqueidentifier, and anything unhandled

required = [a for a in attrs
            if a["RequiredLevel"]["Value"] == "ApplicationRequired"
            and a["AttributeType"] not in SKIP_TYPES]

records = []
for i in range(COUNT):
    rec = {}
    for a in required:
        v = fake(a, i)
        if v is not None:
            rec[a["LogicalName"]] = v
    records.append(rec)

# CreateMultiple for count >= 10, individual creates otherwise.
if COUNT >= 10:
    ids = client.records.create(TABLE, records)
    print(f"Created {len(ids)} records via CreateMultiple", flush=True)
else:
    ids = [client.records.create(TABLE, r) for r in records]
    print(f"Created {len(ids)} records individually", flush=True)

print(f"View: {env_url}/main.aspx?pagetype=entitylist&etn={TABLE}", flush=True)
```

**Why schema-driven and not a hardcoded 5-account template:** a template that bakes in `account`-shaped columns (`name`, `telephone1`, `revenue`, `numberofemployees`) biases the agent toward copy-paste-then-hack whenever the user asks for `contact` or `cr123_project` records. The `fake()` function above dispatches per-attribute so the same snippet produces correct fields for any table. Override `fake()` when you need domain-specific values — e.g. real company names for `account.name`, valid status-reason integers for a custom picklist.

## Safety Rules for Sample Data

- **Always confirm** the target environment and record count
- Use `.example.com` domains for emails — never real domains
- Use `555-01xx` phone numbers — obviously fake
- Skip lookup fields unless user explicitly asks
- Skip system fields: `createdon`, `modifiedon`, `ownerid`, `statecode`, `statuscode`

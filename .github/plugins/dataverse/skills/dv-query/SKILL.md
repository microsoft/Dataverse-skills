---
name: dv-query
description: >
  Query, filter, and analyze Dataverse records using the Python SDK and Web API. Includes
  aggregation, GUID-free display, fuzzy lookup, cross-table joins, and Jupyter notebook handoff.
  Use when: "query records", "filter records", "find records", "show me", "how many",
  "list records", "read data", "fetch data", "search records", "OData filter",
  "aggregate", "group by", "average", "sum", "count", "analyze data",
  "data profiling", "data quality", "Jupyter notebook", "pandas", "notebook",
  "cross-table", "join tables", "expand lookup", "GUID-free", "display names".
  Do not use when: creating or modifying records (use dv-data),
  creating forms/views (use dv-metadata), exporting solutions (use dv-solution).
---

# Skill: Query — Filter, Analyze, and Read Dataverse Records

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. If you are about to run `npm install` or write a `.js` file, STOP — you are going off-rails. See the overview skill's Hard Rules.

Use the official Microsoft Power Platform Dataverse Client Python SDK for all query and read operations. Use the Web API directly only for `$apply` aggregation and N:N `$expand` (SDK does not support these).

---

## Before Writing ANY Script — Check MCP First

**If MCP tools are available** (`read_query`, `list_tables`, `describe_table`) and the task is a simple read or filter query, **use MCP directly — no script needed.**

Examples that need no script: "how many accounts have 'Contoso' in the name?", "show me open tickets", "describe the contact table".

Only write a Python script when the task requires: multi-page iteration, `$expand`, aggregation, analytics, change tracking, or notebook handoff.

---

## Setup

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env
from PowerPlatform.Dataverse.client import DataverseClient

load_env()
client = DataverseClient(
    base_url=os.environ["DATAVERSE_URL"],
    credential=get_credential(),
)
```

---

## Basic Query

```python
for page in client.records.get(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    filter="new_status eq 100000000",   # Open
    orderby=["new_name asc"],
    top=50,
):
    for r in page:
        print(r["new_name"], r["new_priority"])
```

`client.records.get()` returns a page iterator — always iterate pages and records within each page.

---

## Fetch a Single Record by ID

```python
record = client.records.get("new_ticket", "<record-guid>",
    select=["new_name", "new_priority", "new_status"])
print(record["new_name"])
```

---

## GUID-Free Display — Resolving Lookup Fields

Dataverse lookup columns return a GUID by default. To show display names instead:

### Option 1 — `$select` the formatted value (fastest)

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "_parentaccountid_value"],
):
    for r in page:
        # Raw GUID
        account_id = r.get("_parentaccountid_value")
        # Display name (no extra query)
        account_name = r.get("_parentaccountid_value@OData.Community.Display.V1.FormattedValue")
        print(f"{r['name']} — {account_name}")
```

Formatted values are available for lookup, choice, status, and owner fields using the `@OData.Community.Display.V1.FormattedValue` annotation.

### Option 2 — `$expand` to get full related record

```python
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue"],
    expand=["parentaccountid"],      # system nav props are lowercase
):
    for r in page:
        account = r.get("parentaccountid") or {}
        print(f"{r['name']} — {account.get('name', 'Unknown')}")
```

**Nav property casing:**
- System table lookups (e.g., `parentaccountid`, `ownerid`): lowercase
- Custom lookups: case-sensitive, matches `$metadata` SchemaName (e.g., `new_AccountId`)

### $expand with multiple custom lookups

```python
for page in client.records.get(
    "new_ticket",
    select=["new_name", "new_priority", "new_status"],
    expand=["new_CustomerId", "new_AgentId"],   # Navigation Property Names, case-sensitive
):
    for r in page:
        customer = r.get("new_CustomerId") or {}
        agent    = r.get("new_AgentId") or {}
        print(f"{r['new_name']} | {customer.get('new_name','')} | {agent.get('new_name','')}")
```

> `expand` uses the Navigation Property Name (e.g., `new_CustomerId`), not the lowercase logical name (`new_customerid`). Using lowercase causes a 400 error.

---

## $expand on N:N Relationships (Web API Required)

The SDK does **not** support `$expand` on N:N collection-valued navigation properties. Use Web API directly:

```python
import json, urllib.request
from auth import get_token, load_env  # get_token() is correct here — SDK cannot do this

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

# Tickets with their linked KB articles (N:N relationship)
url = (f"{env}/api/data/v9.2/new_tickets"
       f"?$select=new_name"
       f"&$expand=new_ticket_kbarticle($select=new_title)")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())
    for ticket in data["value"]:
        articles = [a["new_title"] for a in ticket.get("new_ticket_kbarticle", [])]
        print(f"{ticket['new_name']}: {', '.join(articles)}")
```

---

## Fuzzy Record Lookup

When a user says "the Contoso opportunity" without a GUID, search by name and handle ambiguity:

```python
def find_record(client, table, name_field, search_term, select=None):
    results = []
    for page in client.records.get(table,
        select=[name_field] + (select or []),
        filter=f"contains({name_field}, '{search_term}')",
        top=10,
    ):
        results.extend(page)

    if len(results) == 0:
        print(f"No records found matching '{search_term}'")
        return None
    if len(results) == 1:
        return results[0]
    # Multiple matches — show options
    print(f"Multiple matches for '{search_term}':")
    for i, r in enumerate(results):
        print(f"  {i+1}. {r[name_field]}")
    choice = int(input("Enter number: ")) - 1
    return results[choice]

ticket = find_record(client, "opportunity", "name", "Contoso",
    select=["estimatedvalue", "estimatedclosedate"])
```

---

## "My" Scoping — Filter to Current User's Records

"Show me my open opportunities" requires resolving the current user's `systemuserid`:

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
token = get_token()
env = os.environ["DATAVERSE_URL"].rstrip("/")

# Get current user's systemuserid
req = urllib.request.Request(
    f"{env}/api/data/v9.2/WhoAmI",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
             "OData-MaxVersion": "4.0", "OData-Version": "4.0"},
)
with urllib.request.urlopen(req) as resp:
    me = json.loads(resp.read())
    my_user_id = me["UserId"]

# Now filter records owned by current user
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "estimatedclosedate", "stagename"],
    filter=(f"statecode eq 0 "                           # Open
            f"and estimatedvalue gt 100000 "
            f"and _ownerid_value eq {my_user_id}"),
    orderby=["estimatedclosedate asc"],
):
    for r in page:
        name  = r["name"]
        value = r["estimatedvalue"]
        close = r.get("estimatedclosedate", "")[:10]
        stage = r.get("stagename", "")
        print(f"{name} | ${value:,.0f} | {close} | {stage}")
```

---

## Aggregation

### Simple — pull data + pandas (preferred for analytics)

```python
import pandas as pd

all_records = []
for page in client.records.get("opportunity",
    select=["name", "estimatedvalue", "statuscode", "_parentaccountid_value"],
):
    all_records.extend(page)

df = pd.DataFrame(all_records)
print(df.groupby("statuscode")["estimatedvalue"].agg(["count", "sum", "mean"]))
```

### Server-side `$apply` aggregation (Web API required — SDK does not support)

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
token = get_token()
env = os.environ["DATAVERSE_URL"].rstrip("/")

# Count and sum opportunities by status
url = (f"{env}/api/data/v9.2/opportunities"
       f"?$apply=groupby((statuscode),"
       f"aggregate($count as count,estimatedvalue with sum as total_value))")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    for row in json.loads(resp.read())["value"]:
        print(f"Status {row['statuscode']}: {row['count']} records, ${row['total_value']:,.0f}")
```

---

## Data Quality Queries

Common patterns for profiling an unfamiliar org.

### Null rate — contacts missing email

```python
total = 0
missing = 0
for page in client.records.get("contact", select=["contactid", "emailaddress1"]):
    for r in page:
        total += 1
        if not r.get("emailaddress1"):
            missing += 1
print(f"Missing email: {missing}/{total} ({100*missing/total:.1f}%)")
```

### Duplicate detection — emails appearing on more than one contact

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
token = get_token()
env = os.environ["DATAVERSE_URL"].rstrip("/")

url = (f"{env}/api/data/v9.2/contacts"
       f"?$apply=groupby((emailaddress1),aggregate($count as cnt))"
       f"&$filter=cnt gt 1&$orderby=cnt desc")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    dupes = json.loads(resp.read())["value"]
    for d in dupes:
        print(f"{d['emailaddress1']}: {d['cnt']} records")
```

### Orphan detection — accounts with zero contacts

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
token = get_token()
env = os.environ["DATAVERSE_URL"].rstrip("/")

# Left anti-join: accounts with no related contact records
url = (f"{env}/api/data/v9.2/accounts"
       f"?$select=name,accountid"
       f"&$filter=not contact_customer_accounts/any()")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    orphans = json.loads(resp.read())["value"]
    print(f"Accounts with no contacts: {len(orphans)}")
    for a in orphans[:20]:
        print(f"  {a['name']}")
```

---

## Change Tracking / Delta Queries

For efficient incremental sync — only retrieve records changed since the last run.

```python
import json, urllib.request
from auth import get_token, load_env

load_env()
token = get_token()
env = os.environ["DATAVERSE_URL"].rstrip("/")

def get_changes(table, select_fields, delta_token=None):
    if delta_token:
        url = f"{env}/api/data/v9.2/{table}?$deltatoken={delta_token}"
    else:
        url = f"{env}/api/data/v9.2/{table}?$select={','.join(select_fields)}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
        "Prefer": "odata.track-changes",
    })
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    records = data.get("value", [])
    next_token = None
    # Extract delta token from @odata.deltaLink
    delta_link = data.get("@odata.deltaLink", "")
    if "$deltatoken=" in delta_link:
        next_token = delta_link.split("$deltatoken=")[-1]

    return records, next_token

# Initial full sync
records, token_val = get_changes("new_customers", ["new_name", "new_email", "new_tier"])
print(f"Initial sync: {len(records)} records. Save delta token: {token_val}")

# Subsequent delta sync (only changed records)
changed, token_val = get_changes("new_customers", [], delta_token=token_val)
print(f"Delta sync: {len(changed)} changed records")
```

> Change tracking must be enabled on the table first — see `dv-metadata`.
> Store `token_val` between runs. An expired or reused token produces an error — request a fresh full sync if that happens.

---

## Jupyter Notebook Handoff

Generate a working snippet the user can paste into a notebook. Uses the same credentials the CLI already has.

```python
# Cell 1: Setup — paste into Jupyter, update DATAVERSE_URL
import os
from azure.identity import InteractiveBrowserCredential
from PowerPlatform.Dataverse.client import DataverseClient

credential = InteractiveBrowserCredential()
client = DataverseClient(
    base_url="https://<org>.crm.dynamics.com",   # replace with your org URL
    credential=credential,
)

# Cell 2: Load data into pandas
import pandas as pd

records = []
for page in client.records.get("account",
    select=["name", "industrycode", "revenue", "numberofemployees"],
):
    records.extend(page)

df = pd.DataFrame(records)
df.head()

# Cell 3+: Analysis
print(df.groupby("industrycode")["revenue"].agg(["count", "mean"]))
```

### Prerequisites for notebook

```bash
pip install --upgrade PowerPlatform-Dataverse-Client pandas matplotlib seaborn azure-identity
```

---

## Windows Scripting Notes

- **ASCII only** in `.py` files — curly quotes and em dashes cause `SyntaxError` on Windows.
- **No `python -c` for multiline code** — write a `.py` file instead.
- **Generate GUIDs in scripts**: `str(uuid.uuid4())`, not shell backtick substitution.

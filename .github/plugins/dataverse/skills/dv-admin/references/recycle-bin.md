# Recycle Bin Configuration

Recycle bin settings live in the `recyclebinconfigs` entity, NOT in `orgdborgsettings` XML. PAC CLI cannot manage these.

**Well-known constant:** The organization entity metadata ID is `e1bd1119-6e9d-45a4-bc15-12051e65a0bd`. This is the `MetadataId` of the `organization` entity's *schema record* in `EntityDefinitions` (a product-level system constant baked into every Dataverse installation), not a tenant-level GUID — so it is identical across all environments and all tenants. Verified empirically across 5 environments. Do not re-query it per environment.

### Read Recycle Bin Status

```python
import os, sys, json, urllib.request, urllib.parse
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # SDK does not support recyclebinconfigs entity

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

ORGANIZATION_ENTITY_ID = "e1bd1119-6e9d-45a4-bc15-12051e65a0bd"

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0",
}

# Fetch org-level config by extensionofrecordid (NOT by name)
filter_q = urllib.parse.quote(f"_extensionofrecordid_value eq '{ORGANIZATION_ENTITY_ID}'")
req = urllib.request.Request(
    f"{env_url}/api/data/v9.2/recyclebinconfigs?$filter={filter_q}&$select=recyclebinconfigid,statecode,statuscode,cleanupintervalindays",
    headers=headers,
)
with urllib.request.urlopen(req) as resp:
    records = json.loads(resp.read()).get("value", [])

if records:
    config = records[0]
    enabled = config["statecode"] == 0
    cleanup = config["cleanupintervalindays"]
    print(f"Recycle bin: {'enabled' if enabled else 'disabled'}", flush=True)
    print(f"Cleanup interval: {cleanup} days ({'-1 means no auto-cleanup' if cleanup == -1 else ''})", flush=True)
    print(f"Config ID: {config['recyclebinconfigid']}", flush=True)
else:
    print("Recycle bin: not configured (no org-level record)", flush=True)
```

### Critical: Always Send `isreadyforrecyclebin: true` on Enable

**Every enable payload (POST or PATCH) must set `isreadyforrecyclebin: true`.**

Without it, the platform defaults `isreadyforrecyclebin` to `false` (CREATE) or leaves it null (PATCH), which forces the platform into the **asynchronous** opt-in path — a `ProcessRecycleBin` background job is queued and your HTTP call returns success before any entity-level work happens. In that window, platform metadata operations (solution imports, attribute publish, async handlers) can race against the partial state and throw `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin`. Sending `isreadyforrecyclebin: true` forces the synchronous, globally-locked opt-in path, which fans out to every entity inside one transaction.

### Critical: Disable via PATCH, Not DELETE

**Disable with `PATCH statecode=1, statuscode=2, isreadyforrecyclebin=false`. Do not DELETE the org config record.**

DELETE enqueues an async opt-out (when `RecycleBinOptOutOrgAsynchronously` is on) while leaving the org row marked Inactive and child entity rows still flagged `IsReadyForRecycleBin=true, IsDisabled=false`. Any platform operation that runs between your DELETE and your next enable will see "org is enabled" from the config cache, proceed to `RecycleBinConfigService.Update(<entity-config>)` synchronously, and throw when the DB-backed `IsRecycleBinEnabledForEntity` check disagrees. A PATCH-based disable takes the synchronous `OptOutOrganization` path under the customization lock, cleanly cascading to every entity.

### Wait for in-flight `ProcessRecycleBin` Jobs Between Toggles

Every enable/disable queues a `ProcessRecycleBin` async operation (OperationType = `50`). Do NOT enable-then-disable-then-enable rapidly; the jobs share a dependency token and can interleave in ways that corrupt state. Before any second toggle, poll `AsyncOperation` until no `ProcessRecycleBin` row is `Queued` or `InProgress` for this org.

### Enable Recycle Bin

Two cases depending on whether a config record already exists. Both send `isreadyforrecyclebin: true`.

```python
# ... (same imports, headers, ORGANIZATION_ENTITY_ID, and fetch as above)
# SDK does not support recyclebinconfigs entity

CLEANUP_DAYS = 30  # default; -1 means records in recycle bin are never auto-purged

# Pre-flight: wait for any in-flight ProcessRecycleBin async jobs to finish
import time
def wait_for_recyclebin_async_jobs(env_url, headers, timeout_s=120):
    # OperationType 50 = ProcessRecycleBin; StateCode 0=Ready/1=Suspended/2=Locked are all "not done"
    filter_q = urllib.parse.quote("operationtype eq 50 and statecode ne 3")
    url = f"{env_url}/api/data/v9.2/asyncoperations?$filter={filter_q}&$select=asyncoperationid,statecode,statuscode,name"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            pending = json.loads(resp.read()).get("value", [])
        if not pending:
            return
        print(f"  waiting on {len(pending)} ProcessRecycleBin job(s)...", flush=True)
        time.sleep(5)
    raise RuntimeError("Timed out waiting for pending ProcessRecycleBin async jobs")

wait_for_recyclebin_async_jobs(env_url, headers)

if not records:
    # Case 1: No config exists -- CREATE a new one
    # extensionofrecordid binds to the entities() metadata endpoint, NOT organizations()
    payload = {
        "extensionofrecordid@odata.bind": f"entities({ORGANIZATION_ENTITY_ID})",
        "extensionofrecordid@OData.Community.Display.V1.FormattedValue": "OrganizationId",
        "isreadyforrecyclebin": True,   # MUST be true -- forces sync opt-in under the global lock
        "cleanupintervalindays": CLEANUP_DAYS,
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup (HTTP {resp.status})", flush=True)
else:
    # Case 2: Config exists -- PATCH statecode/statuscode, cleanup interval, and isreadyforrecyclebin
    config_id = records[0]["recyclebinconfigid"]
    payload = {
        "cleanupintervalindays": CLEANUP_DAYS,
        "statecode": 0,
        "statuscode": 1,
        "isreadyforrecyclebin": True,   # MUST be true -- without this, UpdateInternal routes through updateAsync
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup (HTTP {resp.status})", flush=True)

# Post-flight: drain the sync opt-in fan-out before returning control
wait_for_recyclebin_async_jobs(env_url, headers)
```

### Disable Recycle Bin

**Disable = PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`.** This triggers the synchronous `OptOutOrganization` path which cascades cleanly to every entity config.

```python
# ... (same fetch as above to get config_id)
# SDK does not support recyclebinconfigs entity

wait_for_recyclebin_async_jobs(env_url, headers)   # drain first

if records:
    config_id = records[0]["recyclebinconfigid"]
    payload = {
        "statecode": 1,                 # Inactive
        "statuscode": 2,                # Inactive
        "isreadyforrecyclebin": False,  # required to take the isOptOut branch in UpdateInternal
    }
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/recyclebinconfigs({config_id})",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        print(f"SUCCESS: recycle bin disabled (HTTP {resp.status})", flush=True)
else:
    print("Recycle bin is already disabled (no config record)", flush=True)

wait_for_recyclebin_async_jobs(env_url, headers)   # drain the opt-out fan-out
```

**Do NOT use DELETE to disable.** Legacy guidance (including older Admin Center behavior) suggested DELETE, but DELETE enqueues an async opt-out and can leave per-entity configs orphaned — any platform metadata operation that runs before cleanup finishes will throw `EntityBinUpdateAction called for entity <x> which is not enabled for RecycleBin` on an unrelated entity.

### Key Fields on `recyclebinconfigs`

| Field | Type | What it does |
|---|---|---|
| `statecode` | int | `0` = enabled (active), `1` = disabled (inactive) |
| `statuscode` | int | `1` = enabled, `2` = disabled |
| `cleanupintervalindays` | int | Auto-cleanup interval. `-1` = no auto-cleanup (default). `30` = purge after 30 days (max). Min: `1` |
| `_extensionofrecordid_value` | guid | Entity metadata ID this config applies to. Org-level = `e1bd1119-6e9d-45a4-bc15-12051e65a0bd` |

### Important Notes

- **Fetch by `_extensionofrecordid_value`**, not by `name`. The `name` field is unreliable for filtering.
- **Create uses `entities()` binding** -- `extensionofrecordid@odata.bind: entities({id})`, NOT `organizations()`.
- **Enable payloads MUST include `isreadyforrecyclebin: true`.** Without it, CREATE defaults to false and PATCH sends null — both force the async opt-in path and expose the org to cache-vs-DB races during platform metadata operations.
- **Disable = PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`**, not DELETE. DELETE enqueues an async opt-out and can leave per-entity configs orphaned.
- **Drain `ProcessRecycleBin` async jobs between toggles.** Query `asyncoperations` for `operationtype eq 50 and statecode ne 3` before and after each enable/disable.
- **Cleanup days**: default is `-1` (no auto-cleanup). Max is `30`. When the UI shows "30 days", the API stores `-1` internally (the platform applies a 30-day default).
- Solution-managed configs (e.g., `msdyn_recurringsalesaction`) cannot be enabled/disabled via API.
- **Per-table recycle bin toggles are out of scope.** PPAC only exposes the org-level on/off + cleanup days — if a user asks to enable/disable recycle bin for a specific table (e.g., "turn on recycle bin for `contact` only"), refuse with: *"Per-table recycle bin is out of scope for dv-admin. Use the Power Platform admin center."* The `recyclebinconfigs` entity does hold per-entity rows, but this skill only reads/writes the org-level row (filtered by the organization entity's MetadataId).

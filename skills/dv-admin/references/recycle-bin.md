# Recycle Bin Configuration

Recycle bin settings live in the `recyclebinconfigs` entity, NOT in `orgdborgsettings` XML. PAC CLI cannot manage these.

**Well-known constant:** The organization entity metadata ID is `e1bd1119-6e9d-45a4-bc15-12051e65a0bd`. This is the `MetadataId` of the `organization` entity's *schema record* in `EntityDefinitions` (a product-level system constant baked into every Dataverse installation), not a tenant-level GUID — so it is identical across all environments and all tenants. Verified empirically across 5 environments. Do not re-query it per environment.

### Read Recycle Bin Status

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-admin")

ORGANIZATION_ENTITY_ID = "e1bd1119-6e9d-45a4-bc15-12051e65a0bd"

# recyclebinconfig is an ordinary entity — SDK record read (filter by extensionofrecordid).
records = list(client.records.list(
    "recyclebinconfig",
    select=["recyclebinconfigid", "statecode", "statuscode", "cleanupintervalindays"],
    filter=f"_extensionofrecordid_value eq {ORGANIZATION_ENTITY_ID}",
))

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
# ... (same imports, client, ORGANIZATION_ENTITY_ID, and fetch as above; recyclebinconfig is an entity)
CLEANUP_DAYS = 30  # default; -1 means records in recycle bin are never auto-purged

# Pre-flight: wait for any in-flight ProcessRecycleBin async jobs to finish
import time
def wait_for_recyclebin_async_jobs(client, timeout_s=120):
    # OperationType 50 = ProcessRecycleBin; statecode 3 = Completed (done).
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pending = list(client.records.list(
            "asyncoperation",
            select=["asyncoperationid", "statecode", "statuscode", "name"],
            filter="operationtype eq 50 and statecode ne 3",
        ))
        if not pending:
            return
        print(f"  waiting on {len(pending)} ProcessRecycleBin job(s)...", flush=True)
        time.sleep(5)
    raise RuntimeError("Timed out waiting for pending ProcessRecycleBin async jobs")

wait_for_recyclebin_async_jobs(client)

if not records:
    # Case 1: No config exists -- CREATE a new one.
    # extensionofrecordid binds to the entities() metadata endpoint, NOT organizations().
    client.records.create("recyclebinconfig", {
        "extensionofrecordid@odata.bind": f"entities({ORGANIZATION_ENTITY_ID})",
        "isreadyforrecyclebin": True,   # MUST be true -- forces sync opt-in under the global lock
        "cleanupintervalindays": CLEANUP_DAYS,
    })
else:
    # Case 2: Config exists -- update statecode/statuscode, cleanup interval, isreadyforrecyclebin.
    config_id = records[0]["recyclebinconfigid"]
    client.records.update("recyclebinconfig", config_id, {
        "cleanupintervalindays": CLEANUP_DAYS,
        "statecode": 0,
        "statuscode": 1,
        "isreadyforrecyclebin": True,   # MUST be true -- without this, UpdateInternal routes through updateAsync
    })
print(f"SUCCESS: recycle bin enabled with {CLEANUP_DAYS} day cleanup", flush=True)

# Post-flight: drain the sync opt-in fan-out before returning control
wait_for_recyclebin_async_jobs(client)
```

### Disable Recycle Bin

**Disable = PATCH `statecode=1, statuscode=2, isreadyforrecyclebin=false`.** This triggers the synchronous `OptOutOrganization` path which cascades cleanly to every entity config.

```python
# ... (same imports/client and the records fetch from the Read block above,
# AND the wait_for_recyclebin_async_jobs helper defined in the Enable block above)
wait_for_recyclebin_async_jobs(client)   # drain first

if records:
    config_id = records[0]["recyclebinconfigid"]
    client.records.update("recyclebinconfig", config_id, {
        "statecode": 1,                 # Inactive
        "statuscode": 2,                # Inactive
        "isreadyforrecyclebin": False,  # required to take the isOptOut branch in UpdateInternal
    })
    print("SUCCESS: recycle bin disabled", flush=True)
else:
    print("Recycle bin is already disabled (no config record)", flush=True)

wait_for_recyclebin_async_jobs(client)   # drain the opt-out fan-out
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

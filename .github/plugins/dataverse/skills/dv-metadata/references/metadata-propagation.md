# Metadata Propagation Delays and Lock Contention

After creating tables, columns, or alternate keys, Dataverse runs internal metadata operations (index building, cache propagation) that can take 3-30 seconds. Submitting another metadata operation while these are still running causes lock contention errors ("another operation is running").

**Common symptoms:**
- Picklist columns fail with `0x80040216` immediately after table creation
- Lookup `@odata.bind` operations fail with "Invalid property" shortly after column creation
- `update_table` (MCP) fails with "EntityId not found in MetadataCache"
- Alternate key creation fails with lock contention after table creation
- Lookup creation fails with "another customization operation is running"

**Mitigation — use phased creation, not interleaved:**

When creating many tables with alternate keys and lookups (e.g., multi-table import schema), create them in phases rather than interleaving operations on the same table:

1. **Phase 1: Create ALL tables** (5-8s delay between each)
2. **Wait 15-30s** for metadata propagation
3. **Phase 2: Create ALL alternate keys** (3s delay between each)
4. **Wait 15-30s** for index building
5. **Phase 3: Create ALL lookups** (3s delay between each)

Do NOT interleave: `create table A → create key A → create table B → create key B`. This causes lock contention because key A's index build blocks table B's creation.

**Retry pattern:** Wrap all metadata operations with retry for transient lock errors:

```python
import time

def retry_metadata(fn, description, max_attempts=5):
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "already exists" in err.lower() or "0x80040237" in err:
                print(f"  {description}: already exists, skipping")
                return None
            if "another" in err.lower() and "running" in err.lower():
                wait = 10 * (attempt + 1)
                print(f"  {description}: lock contention, waiting {wait}s (attempt {attempt+1}/{max_attempts})...")
                time.sleep(wait)
                continue
            raise
    print(f"  WARNING: {description} failed after {max_attempts} attempts")
    return None
```

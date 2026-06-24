# Business Skills — consuming org-specific guidance

**Business Skills** are records in the `skill` entity that hold **org-specific domain
instructions** — playbooks like refund handling, lead qualification, or case escalation. They
are *environment-specific*: authored and curated per Dataverse environment, so they differ
across orgs (unlike the bundled `dv-*` skills, which are the same everywhere). **Most
environments have none.**

This reference covers **consuming existing** Business Skills. Authoring and managing them
(create/update/delete, file resources) is out of scope here.

## The model: load the catalog once, pull bodies on demand

A skill's `body` is the full instruction content and can be large, so don't load bodies
wholesale, and don't query the `skill` entity on every operation. Instead:

1. **Once per session** (at `dv-connect`, after the connection is verified), check whether the
   org has any skills. If it does, load the lightweight **catalog** — `skillid`, `name`,
   `description` only — into context and keep it for the session. If none, stop here.
2. **On demand:** when a user request matches a catalog entry's `description`, fetch just that
   skill's `body` and follow its instructions.

The catalog is cheap: name + description is ~40–60 tokens per skill, so even a few dozen skills
is ~1k tokens loaded once — negligible. Matching is done by the agent reading the descriptions,
not by keyword search, so natural-language requests ("qualify this lead") resolve to the right
skill (e.g. `Lead-Qualifier`) even when the names don't share words.

### Setup

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-connect")
```

### Load the catalog (once per session)

```python
# Lightweight index — names + descriptions, no bodies.
catalog = client.records.get("skill", select="skillid,name,description")
# If empty, the org has no Business Skills — skip consultation for the rest of the session.
```

### Consult a skill (on demand, when a request matches)

```python
# The agent picks the matching skill from the catalog by description, then pulls its body:
skill = client.records.get("skill", select="name,body",
                           filter="skillid eq '<id-from-catalog>'")
# Incorporate skill[0]["body"] as domain context before generating the operation.
```

Finding no relevant skill is fine — the org may only have skills for unrelated domains. Proceed
with standard SDK/MCP work.

## When the org has many skills

Loading the full catalog stays comfortable into the low hundreds of skills. Past that, the
catalog itself gets heavy and discovery should move to a server-side retrieval channel (e.g. the
MCP server's per-org `instructions`) rather than preloading every description. That's a future
enhancement — not needed for the common single- to double-digit case.

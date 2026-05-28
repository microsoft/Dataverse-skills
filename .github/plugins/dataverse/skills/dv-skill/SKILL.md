---
name: dv-skill
description: Manage the Dataverse skill entity — list, create, update, delete, and attach resource files to skill records that provide domain-specific instructions. Use when the user wants to create, view, edit, remove, or organize skill or skillresource records in their Dataverse environment.
---

# Skill: Dataverse Business Skills — CRUD and Resource Management

> **This skill uses Python exclusively.** Do not use Node.js, JavaScript, or any other language for Dataverse scripting. See the overview skill's Hard Rules.

## What Are Dataverse Business Skills?

Business Skills are records in the `skill` entity that provide domain-specific guidance for handling tasks. They are **environment-specific** — authored and curated within each Dataverse environment, and will differ across environments. This distinguishes them from static skills (like this `dv-skill` file) which are bundled with the plugin and are the same everywhere.

Each skill record has:

- **Name** — display name (e.g., `Sales-Call-Logging`)
- **Unique name** — prefixed identifier (e.g., `new_salescalllogging`); auto-generated if omitted
- **Description** — short summary of what the skill does
- **Body** — the full instruction/prompt content
- **Scope** — JSON array of app scope names the skill is associated with
- **Resources** — attached files (markdown, templates) stored on the `skillresource` table's `filecontent` column

## Skill boundaries

| Need | Use instead |
|---|---|
| Query or read data records | **dv-query** |
| Create/update/delete data records | **dv-data** |
| Create tables, columns, relationships | **dv-metadata** |
| Export or deploy solutions | **dv-solution** |
| Environment settings, bulk delete | **dv-admin** |
| Security roles, user access | **dv-security** |

---

### Scope Management

When updating a skill's scope:
- **Merge** (default): omit `unlinkScope` or set `false` — new scopes are added to existing
- **Replace**: set `unlinkScope: true` — existing scopes are replaced with the provided list

---

## Python SDK — CRUD Examples

### Setup

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-skill")
```

### List All Skills

```python
skills = client.records.get("skill", select="name,uniquename,description,body")
for skill in skills:
    print(f"{skill['name']} ({skill['uniquename']})")
```

### Create a Skill

```python
client.records.create("skill", {
    "name": "My-Skill-Name",
    "uniquename": "new_myskillname",
    "description": "Short description of what this skill does",
    "body": "Full instruction content..."
})
```

### Update a Skill by ID

```python
skill_id = "00000000-0000-0000-0000-000000000000"  # replace with actual GUID
client.records.update("skill", skill_id, {
    "description": "Updated description",
    "body": "Updated instruction content..."
})
```

### Delete a Skill by ID

```python
skill_id = "00000000-0000-0000-0000-000000000000"  # replace with actual GUID
client.records.delete("skill", skill_id)
```

### Bulk Upsert Skills from a List

```python
skills_to_load = [
    {"name": "Skill-A", "uniquename": "new_skilla", "description": "Desc A", "body": "Instructions A"},
    {"name": "Skill-B", "uniquename": "new_skillb", "description": "Desc B", "body": "Instructions B"},
]

for skill in skills_to_load:
    existing = client.records.get("skill", filter=f"uniquename eq '{skill['uniquename']}'")
    if existing:
        client.records.update("skill", existing[0]["skillid"], skill)
        print(f"{skill['name']}: updated")
    else:
        client.records.create("skill", skill)
        print(f"{skill['name']}: created")
```

---

## Skill Resources — File Attachments

Skills can have attached resource files (markdown docs, templates, reference material) stored on the `skillresource` table.

### List Resources for a Skill

```python
resources = client.records.get(
    "skillresource",
    filter=f"_skillid_value eq '{skill_id}'",
    select="name,filecontent"
)
for r in resources:
    print(r["name"])
```

### Upload a Resource File

Use the SDK file column upload for the `filecontent` attribute on `skillresource`:

```python
# Create the resource record first
resource_id = client.records.create("skillresource", {
    "name": "myfile.md",
    "skillid@odata.bind": f"skills({skill_id})"
})

# Upload file content to the file column
client.records.upload_file("skillresource", resource_id, "filecontent", "myfile.md")
```

### Download a Resource File

```python
client.records.download_file("skillresource", resource_id, "filecontent", "downloaded.md")
```

---

## Consult Helper — Mandatory Skill Consumption for Python SDK

The Python SDK path **must** consult Business Skills before executing any operation. This ensures domain awareness regardless of which surface handles the request.

### Rule: Always Consult Before Executing

**Before generating or running any Python SDK code, query Dataverse for relevant Business Skills.** Extract keywords from the user's request (table names, domain terms, action verbs) and search for matching skills. If matching skills are found, incorporate their `body` as domain context. If no skills match, proceed normally.

Finding no matching skills is fine — skipping the check is not.

| Step | Action |
|---|---|
| 1 | Extract keywords from the user's request |
| 2 | Query skill table via `client.records.get('skill', ...)` |
| 3 | If results found → read `body` and incorporate as context |
| 4 | If no results → proceed with standard SDK code |
| 5 | Generate/run the Python operation guided by any retrieved instructions |

### Consult via Python

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-skill")

def consult_skills(client, keywords):
    """Fetch Business Skills matching any of the given keywords.
    Returns a list of {name, body} dicts with domain instructions."""
    filter_clauses = " or ".join(
        f"contains(name,'{kw}')" for kw in keywords
    )
    results = client.records.get("skill", select="name,body", filter=filter_clauses)
    return [{"name": s["name"], "body": s["body"]} for s in results]
```

### End-to-End Example — SDK with Skill Consultation

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-skill")

# Step 1: Consult — fetch domain instructions
skills = client.records.get("skill", select="name,body", filter="contains(name,'Refund')")

# Step 2: Display retrieved skill instructions for agent context
for skill in skills:
    print(f"--- Skill: {skill['name']} ---")
    print(skill["body"])
```

After retrieving the skill instructions, the agent incorporates them as context before generating the SDK code for the actual operation (e.g., creating records, running queries).

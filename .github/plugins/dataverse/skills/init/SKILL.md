---
name: dataverse-init
description: >
  Initialize a Dataverse workspace on a new machine or new repo.
  USE WHEN: ".env is missing", "setting up on a new machine", "starting a new project",
  "initialize workspace", "new repo", "first time setup", "configure MCP server",
  "MCP not connected", "load demo data", "sample data".
  DO NOT USE WHEN: installing tools (use dataverse-setup).
---

# Skill: Init

> **Environment-First Rule** — All metadata (solutions, columns, tables, forms, views) and plugin registrations are created **in the Dynamics environment** via API or scripts, then pulled into the repo. Never write or edit solution XML by hand to create new components. This rule applies to every step in both scenarios below.

**Execute every numbered step in order.** Do not skip ahead to a later step, even if it appears more relevant to the user's immediate goal. Steps that seem unrelated to the current task (e.g., MCP setup when the user asked about tables) are still required — they enable the user's workflow in future sessions.

Two scenarios — handle both.

---

## Scenario A: New Machine (repo already exists)

The repo is already cloned. Scripts and CLAUDE.md are present. Only machine-local config is missing.

### 1. Check what's already there

```
ls .env 2>/dev/null && echo "found" || echo "missing"
ls .vscode/settings.json 2>/dev/null && echo "found" || echo "missing"
ls .mcp.json 2>/dev/null && echo "found" || echo "missing"
```

### 2. Discover TENANT_ID automatically

If the user does not know their TENANT_ID, derive it from the Dataverse environment URL — no portal login required:

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

The output is the tenant GUID. Use it directly in `.env`.

### 3. Create .env if missing

Ask the user for each value, then write the file:

```
DATAVERSE_URL=https://<org>.crm.dynamics.com
TENANT_ID=<guid>
SOLUTION_NAME=<UniqueName>
PAC_AUTH_PROFILE=nonprod
CLIENT_ID=<app-registration-client-id>
CLIENT_SECRET=<app-registration-secret>
```

How to prompt the user:
- `DATAVERSE_URL`: "What is your Dataverse environment URL?"
- `TENANT_ID`: Auto-discover from the URL above before asking. Only ask if discovery fails.
- `SOLUTION_NAME`: "What is the unique name of your solution?"
- `CLIENT_ID` / `CLIENT_SECRET`: Only needed for service principal auth. If the user authenticates via browser (interactive login), skip these. When omitted, auth.py uses interactive device code flow with AuthenticationRecord persistence (no browser re-prompt on subsequent runs).

Write the file directly — do not instruct the user to create it:

```python
# Write .env
with open(".env", "w") as f:
    f.write(f"DATAVERSE_URL={dataverse_url}\n")
    f.write(f"TENANT_ID={tenant_id}\n")
    f.write(f"SOLUTION_NAME={solution_name}\n")
    f.write(f"PAC_AUTH_PROFILE=nonprod\n")
    if client_id:
        f.write(f"CLIENT_ID={client_id}\n")
    if client_secret:
        f.write(f"CLIENT_SECRET={client_secret}\n")
```

### 4. Ensure sensitive files are gitignored

Write a comprehensive `.gitignore` that covers all credential and generated files:

```python
GITIGNORE_ENTRIES = [
    ".env",
    ".vscode/settings.json",
    ".claude/mcp_settings.json",
    ".token_cache.bin",
    "*.snk",
    "__pycache__/",
    "*.pyc",
    "solutions/*.zip",
    "plugins/**/bin/",
    "plugins/**/obj/",
]

gitignore = open(".gitignore").read() if os.path.exists(".gitignore") else ""
missing = [e for e in GITIGNORE_ENTRIES if e not in gitignore]
if missing:
    with open(".gitignore", "a") as f:
        f.write("\n" + "\n".join(missing) + "\n")
```

### 5. Configure MCP server

Use the `dataverse-mcp-configure` skill to set up the MCP server for GitHub Copilot or Claude Code.

### 6. Ensure PAC CLI is on PATH

Find the path (this may be slow, wait for it to finish):

```bash
find /c/Users/$USER/AppData/Local/Microsoft/PowerAppsCLI -name "pac.exe" 2>/dev/null
find /c/Users/$USER/.dotnet/tools -name "pac" 2>/dev/null
```

Add to `~/.bashrc` (for Git Bash / Claude Code):

```bash
echo 'export PATH="$PATH:/c/Users/$USER/.dotnet/tools"' >> ~/.bashrc
source ~/.bashrc
```

### 7. Connect to the environment

Ask the user which environment they are setting up for. Do not assume.

Check whether a connection already exists for that environment:

```
pac auth list
pac org who
```

If a matching profile already exists, select it:

```
pac auth select --name <profile-name>
```

If no connection exists yet, create one. Name the profile after the environment it targets (e.g., `dev`, `staging`, `prod`) — not a generic name. **A browser window will open — sign in with your Microsoft account when prompted:**

```
pac auth create --name <profile-name>
```

For service principal auth (non-interactive, used in CI):

```
pac auth create --name <profile-name> \
  --applicationId <CLIENT_ID> \
  --clientSecret <CLIENT_SECRET> \
  --tenant <TENANT_ID>
```

> **Multi-environment repos:** If the team deploys to multiple environments from the same repo, each developer's `.env` represents their current target. Consider `.env.dev`, `.env.staging`, etc., with a pattern like `cp .env.dev .env` to switch targets. Each developer manages their own local `.env`.

### 8. Verify the connection

```
pac org who
python scripts/auth.py
```

Both should succeed without error. Confirm the environment URL in the output matches the intended target. New machine setup is complete.

---

## Scenario B: First Time (new project, empty repo)

All commands below can be run directly by Claude — the user does not need to copy-paste or execute anything manually unless they want to.

### 1. Confirm the repo

Verify you are at the repo root.

### 2. Discover TENANT_ID

Always ask the user to confirm the Dataverse environment URL and pause to let the user respond even if you can derive it from `pac auth list` or other sources.

Do not perform any subsequent or parallel operations until the user answers. Do not assume.

Before writing `.env`, auto-discover `TENANT_ID` from the Dataverse URL confirmed by the user:

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

Use the resulting GUID as `TENANT_ID` in `.env`. Only ask the user if this command fails.

### 3. Create .env, MCP config, and .gitignore

Follow steps 3–4 from Scenario A above. Ask the user for SOLUTION_NAME if not already known (but use the DATAVERSE_URL you obtained and confirmed in step 2).

Set up MCP following step 5 from Scenario A.

### 4. Create the directory structure

```
mkdir -p solutions plugins scripts
```

Copy plugin scripts into the repo so they're committed and available to teammates:

```
cp .dataverse/scripts/auth.py scripts/
cp .dataverse/scripts/enable-mcp-client.py scripts/
```

### 5. Write CLAUDE.md

Copy `templates/CLAUDE.md` from the plugin to the repo root. Replace placeholders:
- `{{DATAVERSE_URL}}` → environment URL
- `{{SOLUTION_NAME}}` → solution unique name
- `{{PAC_AUTH_PROFILE}}` → `nonprod`

### 6. Connect to the environment

Ask the user which environment this new project targets. Do not assume.

Check whether a connection already exists:

```
pac auth list
pac org who
```

If a matching profile appears, select it:

```
pac auth select --name <profile-name>
```

If not, connect now. Name the profile after the environment (e.g., `dev`, `staging`, `prod`). **A browser window will open — sign in with your Microsoft account when prompted:**

```
pac auth create --name <profile-name>
```

Continue to the next steps.

### 7. Create the solution and metadata in the environment

**This is where changes go into Dynamics first — never into the repo directly.**

Write and run `scripts/create_solution.py` to create the publisher and solution in the environment via Web API. Follow the pattern in the `dataverse-solution` skill. Run it:

```
python scripts/create_solution.py
```

Then write and run any scripts needed to create columns, tables, or other metadata in the environment. Each script should POST to the Dataverse MetadataService API with `MSCRM.SolutionUniqueName` header so the changes are automatically included in the solution. Run them:

```
python scripts/add_<whatever>_column.py
```

### 8. Pull the environment state to the repo

**After all changes are live in the environment, pull them into the repo:**

```
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
```

### 9. Load demo data (optional)

If the user wants sample data for testing (accounts, contacts, opportunities), use the built-in Dataverse sample data feature:

```python
from PowerPlatform.Dataverse.client import DataverseClient
from auth import get_credential, load_env
import requests, os

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")

# Check if already installed
client = DataverseClient(base_url=env_url, credential=get_credential())
pages = client.records.get(
    "organization",
    select=["friendlyname", "sampledataimported"],
    top=1,
)
orgs = [o for page in pages for o in page]
if orgs and orgs[0].get("sampledataimported"):
    print("Demo data is already installed.")
else:
    # Install via Web API action (SDK doesn't support unbound actions)
    from auth import get_token
    token = get_token()
    resp = requests.post(
        f"{env_url}/api/data/v9.2/InstallSampleData",
        headers={
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    print("Demo data installation started. Takes 2-10 minutes.")
```

To remove demo data later, call `UninstallSampleData` the same way.

### 10. Commit

```
git add .gitignore CLAUDE.md solutions/ plugins/ scripts/
git commit -m "chore: initialize Dataverse workspace"
```

---

## MCP Server Verification

After configuring the MCP server, verify it works by asking the agent: *"List the tables in my Dataverse environment."*

If the agent calls `list_tables` directly, MCP is connected. If it falls back to PAC CLI or Web API, the MCP server is not connected — check:

1. `.mcp.json` (Claude Code) or `.vscode/settings.json` (Copilot) exists and has correct values
2. `CLIENT_ID`/`CLIENT_SECRET`/`TENANT_ID` in the config match a valid service principal
3. The service principal has been granted access to the environment

### MCP Server Capabilities

| Task | Use |
| --- | --- |
| Create/read/update/delete data records | MCP server |
| Create a new table | MCP server |
| Explore what tables/columns exist | MCP server (`list_tables`, `describe_table`) |
| Add a column to an existing table | Web API (see `dataverse-metadata`) |
| Create a relationship / lookup | Web API (see `dataverse-metadata`) |
| Create or modify a form | Web API (see `dataverse-metadata`) |
| Create or modify a view | Web API (see `dataverse-metadata`) |

For anything beyond data CRUD and basic table operations, use the Web API directly.

---
name: dataverse-init
description: >
  Initialize a Dataverse workspace on a new machine or new repo.
  USE WHEN: ".env is missing", "setting up on a new machine", "starting a new project",
  "initialize workspace", "new repo", "first time setup", "configure MCP server",
  "MCP not connected", "load demo data", "sample data",
  "create a new environment", "select environment", "which environment".
  DO NOT USE WHEN: installing tools (use dataverse-setup).
---

# Skill: Init

> **Environment-First Rule** — All metadata (solutions, columns, tables, forms, views) and plugin registrations are created **in the Dynamics environment** via API or scripts, then pulled into the repo. Never write or edit solution XML by hand to create new components. This rule applies to every step in both scenarios below.

**Execute every numbered step in order.** Do not skip ahead to a later step, even if it appears more relevant to the user's immediate goal.

Do not skip MCP configuration (step 9 in Scenario A, step 12 in Scenario B) unless an MCP server is already configured (`.mcp.json` exists with a Dataverse server entry, or `claude mcp list` shows one).

Two scenarios — handle both. But first, both scenarios share an environment discovery flow.

---

## Environment Discovery

Before asking the user for a Dataverse environment URL, **check what is already available**. This avoids unnecessary questions and handles the common cases: the user is already connected, wants to pick from a list, or wants to create a new environment.

### Step 1: Check existing auth

```
pac auth list
pac org who
```

If PAC CLI is not authenticated at all (no profiles), ask the user:
- "Do you want to connect to an existing environment or create a new one?"
Then skip to Step 3 based on their answer.

If PAC CLI has auth profiles, note the currently active environment and continue to Step 2.

### Step 2: List available environments

```
pac env list
```

This shows all environments the user has access to (name, URL, type, state). Collect this list for the next step.

### Step 3: Present options

Show the user what you found and offer a choice:

- **Use the currently active environment**: `<name>` (`<url>`) — if `pac org who` returned one
- **Select a different existing environment** — show the list from `pac env list`
- **Create a new environment**

Wait for the user to choose. Do not assume.

### Step 4a: If the user selects an existing environment

If it is already the active auth profile, proceed — no connection changes needed.

If it is a different environment, check whether an auth profile already exists for it (`pac auth list`). If so, select it:

```
pac auth select --name <profile-name>
```

If no profile exists, create one. **A browser window will open — sign in when prompted:**

```
pac auth create --name <profile-name> --environment <url>
```

Verify with `pac org who`.

### Step 4b: If the user wants to create a new environment

Ask for:
- **Environment name** (required)
- **Type**: `Developer` (default, free, single-user), `Sandbox`, or `Production`
- **Region**: e.g., `unitedstates`, `europe`, `asia`, `australia`, `canada`, `japan`, `uk` (default: `unitedstates`)

Run:

```
pac admin create --name "<name>" --type "<type>" --region "<region>"
```

Wait for completion (can take 1–3 minutes). The output contains the new environment URL. Connect to it:

```
pac auth create --name "<profile-name>" --environment "<new-url>"
```

Verify with `pac org who`.

> **Note:** `pac admin create` requires tenant admin or Power Platform admin permissions. If it fails with a permissions error, guide the user to create the environment in the [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/) instead, then return to Step 4a to connect to it.

### Step 5: Confirm and capture details

Run `pac org who` one final time and **parse the output** to extract:
- **Environment URL** → used as `DATAVERSE_URL` in `.env`
- **Tenant ID** → used as `TENANT_ID` in `.env` (no separate HTTP call needed)

Show the user the confirmed environment:

> "Connected to `<name>` at `<url>`. I'll use this for all subsequent operations."

If `pac org who` does not show a tenant ID (rare), fall back to the HTTP discovery method:

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

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

The `pac org who` output (from step 6's Environment Discovery) includes the tenant ID. Parse it directly — no separate HTTP call needed.

If `pac org who` has not been run yet or does not contain a tenant ID, fall back to the HTTP method:

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
PUBLISHER_PREFIX=<prefix>
PAC_AUTH_PROFILE=nonprod
CLIENT_ID=<app-registration-client-id>
CLIENT_SECRET=<app-registration-secret>
```

How to prompt the user:
- `DATAVERSE_URL`: "What is your Dataverse environment URL?" (e.g., `https://myorg.crm10.dynamics.com`). If the Environment Discovery flow already determined this, use it directly — do not re-ask.
- `TENANT_ID`: Auto-discover from the `DATAVERSE_URL` using the curl method (see Scenario A step 2). This is preferred over `pac org who` because it derives the tenant directly from the URL — no PAC CLI setup needed, and no risk of returning the wrong tenant when multiple auth profiles exist. Only ask the user if the curl method fails.
- `SOLUTION_NAME`: "What is the unique name of your solution?" (allow skipping for now)
- `PUBLISHER_PREFIX`: Do **not** ask yet — this is discovered in the solution creation step (step 7 in Scenario B). Leave it blank in `.env` for now; the `create_solution.py` script will query existing publishers and ask the user. Once confirmed, update `.env` with the chosen prefix.

**Present authentication options — always ask this explicitly with clear descriptions:**

> How would you like to authenticate with Dataverse?
>
> 1. **Interactive login (recommended for personal use)** — Sign in via your browser. No app registration needed. You'll authenticate once and the token stays cached across sessions.
> 2. **Service principal (for CI/CD or shared environments)** — Uses a CLIENT_ID and CLIENT_SECRET from an Azure app registration. Required for unattended/automated scenarios.

- If **Interactive**: skip `CLIENT_ID` and `CLIENT_SECRET`. `auth.py` uses device code flow with persistent OS-level token caching — no re-prompt on subsequent runs.
- If **Service principal**: ask for `CLIENT_ID` and `CLIENT_SECRET`.

Write the file directly — do not instruct the user to create it:

```python
# Write .env
with open(".env", "w") as f:
    f.write(f"DATAVERSE_URL={dataverse_url}\n")
    f.write(f"TENANT_ID={tenant_id}\n")
    f.write(f"SOLUTION_NAME={solution_name}\n")
    f.write(f"PUBLISHER_PREFIX=\n")  # filled in during solution creation step
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

### 5. Ensure PAC CLI is on PATH

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

### 6. Connect to the environment

Run the **Environment Discovery** flow (see section above) to determine the target environment. The user may want to use the currently active environment, pick a different one, or create a new one — the discovery flow handles all three cases.

For service principal auth (non-interactive, used in CI), use this variant instead:

```
pac auth create --name <profile-name> \
  --applicationId <CLIENT_ID> \
  --clientSecret <CLIENT_SECRET> \
  --tenant <TENANT_ID>
```

> **Multi-environment repos:** If the team deploys to multiple environments from the same repo, each developer's `.env` represents their current target. Consider `.env.dev`, `.env.staging`, etc., with a pattern like `cp .env.dev .env` to switch targets. Each developer manages their own local `.env`.

### 7. Install / upgrade Python dependencies

```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client
```

### 8. Verify the connection

```
pac org who
python scripts/auth.py
```

Both should succeed without error. Confirm the environment URL in the output matches the intended target.

### 9. Configure MCP server (if not already configured)

**Skip this step** if MCP is already configured:
- `.mcp.json` already exists and contains a Dataverse server entry
- `claude mcp list` shows a `dataverse-*` server already registered

**Defer (but don't skip)** if the user's immediate task can proceed without MCP (e.g., schema creation via SDK, solution import via PAC CLI). Complete the task first, then offer to configure MCP — it makes future conversational queries (reads, simple CRUD) much faster.

If MCP is needed and not yet configured, use the `dataverse-mcp-configure` skill. **This is always the last step** because `claude mcp add` requires a Claude Code restart, which ends the current session.

Before triggering the MCP install command, inform the user:

> MCP setup requires restarting Claude Code. All other setup steps are complete.
> Remember to **use `claude --continue` to resume the session** without losing context.
> After restart, you can verify MCP works by asking: "List the tables in my Dataverse environment."

New machine setup is complete.

---

## Scenario B: First Time (new project, empty repo)

All commands below can be run directly by Claude — the user does not need to copy-paste or execute anything manually unless they want to.

### 1. Confirm the repo

Verify you are at the repo root.

### 2. Select or create the target environment

Run the **Environment Discovery** flow (see section above) to determine which environment this project targets. The user may want to use an existing environment or create a new one — the discovery flow handles both.

The discovery flow's final `pac org who` output includes the **tenant ID**. Parse it directly — no separate HTTP call needed. If the tenant ID is not in the output, fall back to:

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

Use the resulting GUID as `TENANT_ID` in `.env`. Only ask the user if both methods fail.

### 3. Create .env and .gitignore

Follow steps 3–4 from Scenario A above. Ask the user for SOLUTION_NAME if not already known (but use the DATAVERSE_URL you obtained and confirmed in step 2).

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
- `{{PUBLISHER_PREFIX}}` → leave as `TBD` for now (filled in after step 7 when the publisher is confirmed)
- `{{PAC_AUTH_PROFILE}}` → `nonprod`

### 6. Install / upgrade Python dependencies

```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client
```

### 7. Verify the environment connection

The environment connection was established during step 2 (Environment Discovery). Verify it is still active:

```
pac org who
```

If the output does not match the target environment from step 2, re-run `pac auth select` or `pac auth create` to reconnect.

Continue to the next steps.

### 8. Create the solution and metadata in the environment

**This is where changes go into Dynamics first — never into the repo directly.**

Write and run `scripts/create_solution.py` to create the publisher and solution in the environment using the Python SDK. The script **must** follow the publisher discovery flow from the `dataverse-solution` skill:

1. **Query existing publishers** in the environment (excluding Microsoft system publishers)
2. **If a custom publisher exists**, show it to the user and ask: "Should I reuse this publisher (prefix: `<prefix>_`)?"
3. **If no custom publisher exists**, ask the user: "What publisher prefix should I use? (e.g., `contoso`, `sa`, `lit` — 2-8 lowercase chars, not `new`)"
4. **Never hardcode a prefix.** Never default to `new`. Always get user confirmation.
5. After the publisher is confirmed/created, **update `.env`** with `PUBLISHER_PREFIX=<chosen_prefix>`

Run it:

```
python scripts/create_solution.py
```

Then write and run any scripts needed to create tables, columns, or other metadata. **All custom schema names must use the confirmed publisher prefix** (from `PUBLISHER_PREFIX` in `.env`). Each script should use the SDK with `solution=SOLUTION` so changes are automatically included in the solution. Run them:

```
python scripts/create_tables.py
```

### 9. Pull the environment state to the repo

**After all changes are live in the environment, pull them into the repo:**

```
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
```

### 10. Load demo data (optional)

If the user wants sample data for testing (accounts, contacts, opportunities), use the built-in Dataverse sample data feature:

```python
import os, urllib.request
from PowerPlatform.Dataverse.client import DataverseClient
from auth import get_credential, load_env

load_env()
env_url = os.environ["DATAVERSE_URL"].rstrip("/")

# Check if already installed (SDK)
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
    # Web API required — SDK does not support unbound actions
    from auth import get_token
    token = get_token()
    req = urllib.request.Request(
        f"{env_url}/api/data/v9.2/InstallSampleData",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urllib.request.urlopen(req)
    print("Demo data installation started. Takes 2-10 minutes.")
```

To remove demo data later, call `UninstallSampleData` the same way.

### 11. Commit

```
git add .gitignore CLAUDE.md solutions/ plugins/ scripts/
git commit -m "chore: initialize Dataverse workspace"
```

### 12. Configure MCP server (if not already configured)

**Skip this step entirely** if any of the following are true:

- `.mcp.json` already exists and contains a Dataverse server entry
- `claude mcp list` shows a `dataverse-*` server already registered
- The user's immediate task does not require MCP (e.g., they asked to create tables, import data, or build a solution — all of which use the SDK or PAC CLI, not MCP) **and** the user has not explicitly mentioned MCP or asked to connect via MCP

If MCP is needed and not yet configured, use the `dataverse-mcp-configure` skill.

Before triggering the MCP install command, inform the user:

> MCP setup requires restarting Claude Code. All other setup steps are complete — your solution, tables, and scripts are committed.
> Remember to **use `claude --continue` to resume the session** without losing context.
> After restart, you can verify MCP works by asking: "List the tables in my Dataverse environment."

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

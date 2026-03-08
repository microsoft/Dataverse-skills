---
name: dataverse-init
description: Initialize a Dataverse workspace on a new machine or new repo. Use this when .env is missing, setting up on a new machine, or starting a new project.
---

# Skill: Init

> **Environment-First Rule** — All metadata (solutions, columns, tables, forms, views) and plugin registrations are created **in the Dynamics environment** via API or scripts, then pulled into the repo. Never write or edit solution XML by hand to create new components. This rule applies to every step in both scenarios below.

Two scenarios — handle both.

---

## Scenario A: New Machine (repo already exists)

The repo is already cloned. Scripts and CLAUDE.md are present. Only machine-local config is missing.

### 1. Check what's already there

```
ls .env 2>/dev/null && echo "found" || echo "missing"
ls .vscode/settings.json 2>/dev/null && echo "found" || echo "missing"
```

### 2. Discover TENANT_ID automatically

If the user does not know their TENANT_ID, derive it from the Dataverse environment URL — no portal login required:

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | grep -oP 'login\.microsoftonline\.com/\K[^/]+'
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
- `CLIENT_ID` / `CLIENT_SECRET`: Only needed for service principal auth. If the user authenticates via browser (interactive login), skip these. When omitted, auth.py uses interactive device code flow with automatic OS-level token caching (no browser re-prompt on subsequent runs).

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

### 5. Create .vscode/settings.json if missing

Only create this if the user has CLIENT_ID/CLIENT_SECRET (service principal). Do not ask the user to do this:

```python
import os, json
os.makedirs(".vscode", exist_ok=True)

settings = {
    "github.copilot.chat.mcp.servers": {
        "dataverse": {
            "command": "npx",
            "args": ["@microsoft/dataverse-mcp"],
            "env": {
                "DATAVERSE_URL": dataverse_url,
                "TENANT_ID": tenant_id,
                "CLIENT_ID": client_id,
                "CLIENT_SECRET": client_secret
            }
        }
    }
}
with open(".vscode/settings.json", "w") as f:
    json.dump(settings, f, indent=2)
```

### 6. Ensure PAC CLI is on PATH

Find the path:

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

Before writing `.env`, auto-discover `TENANT_ID` from the Dataverse URL (the user must provide the URL first):

```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | grep -oP 'login\.microsoftonline\.com/\K[^/]+'
```

Use the resulting GUID as `TENANT_ID` in `.env`. Only ask the user if this command fails.

### 3. Create .env and .vscode/settings.json

Follow steps 3–5 from Scenario A above. Ask the user for DATAVERSE_URL and SOLUTION_NAME if not already known. Skip CLIENT_ID/CLIENT_SECRET if the user authenticates interactively. Device code tokens are cached automatically in the OS credential store.

### 4. Create the directory structure

```
mkdir -p solutions plugins scripts
```

Copy plugin scripts into the repo so they're committed and available to teammates:
```
cp .dataverse/scripts/auth.py scripts/
cp .dataverse/scripts/validate.py scripts/
cp .dataverse/scripts/assign-user.py scripts/
cp .dataverse/scripts/mcp_proxy.py scripts/
cp .dataverse/scripts/sdk_check.py scripts/
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

Write and run `scripts/create_solution.py` to create the publisher and solution in the environment via Web API. Follow the pattern in `dataverse-solution/SKILL.md`. Run it:

```
python scripts/create_solution.py
```

Then write and run any scripts needed to create columns, tables, or other metadata in the environment. Each script should POST to the Dataverse MetadataService API with `MSCRM.SolutionUniqueName` header so the changes are automatically included in the solution. Run them:

```
python scripts/add_<whatever>_column.py
```

### 8. Build and deploy plugins

If the project includes C# plugins, build and deploy them now. Follow `dataverse-csharp-plugins/SKILL.md` for the full sequence: generate strong-name key, build, register assembly and step via script. All of this goes into the environment. Do not commit the plugin DLL to git.

### 9. Pull the environment state to the repo

**After all changes are live in the environment, pull them into the repo:**

```
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
```

### 10. Commit

```
git add .gitignore CLAUDE.md solutions/ plugins/ scripts/
git commit -m "chore: initialize Dataverse workspace"
```

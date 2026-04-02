---
name: dv-connect
description: >
  Connect to a Dataverse environment in one step — installs tools, authenticates, configures MCP, and verifies the connection.
  Use when: "connect to Dataverse", "configure MCP", "set up MCP server", "MCP not working",
  ".env is missing", "setting up on a new machine", "starting a new project",
  "initialize workspace", "new repo", "first time setup", "install tools",
  "command not found", "missing tools", "new machine setup", "authenticate",
  "MCP not connected", "create a new environment", "select environment",
  "connect via MCP", "add Dataverse to Copilot", "add Dataverse to Claude",
  "load demo data", "sample data".
---

# Skill: Connect

One-step connection to Dataverse. Handles tool installation, authentication, environment selection, workspace initialization, MCP configuration, and verification — all idempotently. Each step checks if it's already done and skips if so.

> **Environment-First Rule** — All metadata (solutions, columns, tables, forms, views) and plugin registrations are created **in the Dynamics environment** via API or scripts, then pulled into the repo. Never write or edit solution XML by hand to create new components.

**Execute every step in order.** Do not skip ahead, even if a later step appears more relevant to the user's immediate goal.

---

## Step 1: Ensure tools are installed

Check each tool independently — **do not use fail-fast parallel execution.** If one tool check fails, continue checking the others so you can report all missing tools at once. See [tools-setup.md](references/tools-setup.md) for installation commands and platform-specific notes.

| Tool | Check |
|---|---|
| Python 3 | `python --version` |
| Git | `git --version` |
| PAC CLI | `pac` (prints version banner; note: `pac --version` is not a valid command and returns a non-zero exit code) (see [tools-setup.md](references/tools-setup.md) for Windows path discovery if not in PATH) |
| .NET SDK | `dotnet --version` |
| Azure CLI | `az --version` |

.NET SDK is needed for PAC CLI but NOT for the MCP proxy (the npm package bundles its own runtime). Azure CLI is used as a fallback for environment discovery when PAC CLI isn't available (see [mcp-configuration.md](references/mcp-configuration.md) Step 3b). GitHub CLI is not needed for connecting — it's used later for ALM/CI/CD scenarios (see `dv-solution`).

If any tool is missing, install it (see [tools-setup.md](references/tools-setup.md)), then verify. If `winget` installs a tool but it's not in PATH, ask the user to restart the terminal.

After Python is confirmed:
```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client
```

**Skip condition:** All tools present and Python SDK installed.

---

## Step 2: Discover and select the environment

Before asking the user for a URL, check what's already available:

```
pac auth list
pac org who
```

**If PAC CLI is authenticated:**
- Show the currently active environment
- Offer to use it, switch to another (`pac env list`), or create a new one

**If PAC CLI is not authenticated:**
- Ask: "Do you want to connect to an existing environment or create a new one?"

**Before selecting, check for tenant/region mismatch.** If the target environment URL uses a different region (e.g., `crm10.dynamics.com` = APAC) than the currently authenticated account's environments, the current auth profile likely belongs to a different tenant. In that case, create a new auth profile for the correct tenant rather than trying `pac org select` (which will fail with "no organization found"):

```
pac auth create --name <profile-name> --environment <url>
```

**To select from existing profiles:**
```
pac auth select --name <profile-name>
```

**To create a new environment** (requires admin permissions):
```
pac admin create --name "<name>" --type "<type>" --region "<region>"
```
If this fails with permissions error, guide the user to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/) to create it, then connect.

**Confirm connection:**
```
pac org who
```
Parse the output to extract `DATAVERSE_URL` and `TENANT_ID`.

If `pac org who` does not show a tenant ID, fall back to:
```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

**Skip condition:** `.env` exists with valid `DATAVERSE_URL` and `TENANT_ID`, and `pac org who` confirms the connection.

---

## Step 3: Create .env

Present authentication options:

> How would you like to authenticate with Dataverse?
> 1. **Interactive login (recommended)** — Sign in via browser. No app registration needed. Token stays cached across sessions.
> 2. **Service principal (for CI/CD)** — Uses CLIENT_ID and CLIENT_SECRET from an Azure app registration.

Write `.env` directly — do not instruct the user to create it:

Detect the current tool (Claude or Copilot) from context and set `MCP_CLIENT_ID` automatically:
- Claude (CLI or VSCode extension): `0c412cc3-0dd6-449b-987f-05b053db9457`
- GitHub Copilot: `aebc6443-996d-45c2-90f0-388ff96faa56`

```python
with open(".env", "w") as f:
    f.write(f"DATAVERSE_URL={dataverse_url}\n")
    f.write(f"TENANT_ID={tenant_id}\n")
    f.write(f"MCP_CLIENT_ID={mcp_client_id}\n")
    f.write(f"SOLUTION_NAME={solution_name}\n")
    f.write(f"PUBLISHER_PREFIX=\n")  # filled in when solution is created
    f.write(f"PAC_AUTH_PROFILE=nonprod\n")
    if client_id:
        f.write(f"CLIENT_ID={client_id}\n")
    if client_secret:
        f.write(f"CLIENT_SECRET={client_secret}\n")
```

> **Multi-environment repos:** If the team deploys to multiple environments from the same repo, each developer's `.env` represents their current target. Consider `.env.dev`, `.env.staging`, etc., with a pattern like `cp .env.dev .env` to switch targets. Each developer manages their own local `.env`.

Ensure `.env` is in `.gitignore`:

```python
GITIGNORE_ENTRIES = [
    ".env", ".vscode/settings.json", ".claude/mcp_settings.json",
    ".token_cache.bin", "*.snk", "__pycache__/", "*.pyc",
    "solutions/*.zip", "plugins/**/bin/", "plugins/**/obj/",
]
gitignore = open(".gitignore").read() if os.path.exists(".gitignore") else ""
missing = [e for e in GITIGNORE_ENTRIES if e not in gitignore]
if missing:
    with open(".gitignore", "a") as f:
        f.write("\n" + "\n".join(missing) + "\n")
```

**Skip condition:** `.env` already exists with all required values.

---

## Step 4: Set up project structure (new projects only)

If this is a new project (no `scripts/` directory):

```
mkdir -p solutions plugins scripts
```

Copy plugin scripts:
```
cp .dataverse/scripts/auth.py scripts/
cp .dataverse/scripts/enable-mcp-client.py scripts/
```

Copy `templates/CLAUDE.md` to the repo root if it doesn't exist. Replace placeholders (`{{DATAVERSE_URL}}`, `{{SOLUTION_NAME}}`, `{{PUBLISHER_PREFIX}}`) with values from `.env`.

**Skip condition:** `scripts/auth.py` exists.

---

## Step 5: Verify the connection

```
pac org who
python scripts/auth.py
```

Both must succeed. Confirm the environment URL matches the intended target.

**If either fails:**
- `pac org who` fails → re-run Step 2
- `python scripts/auth.py` fails → check Python SDK install, check `.env` values

---

## Step 6: Configure MCP server

**Skip this step** if MCP is already configured:
- `.mcp.json` or `~/.copilot/mcp-config.json` or `.mcp/copilot/mcp.json` contains a Dataverse server entry
- `claude mcp list` shows a `dataverse-*` server registered

If MCP is not configured, follow [mcp-configuration.md](references/mcp-configuration.md):

1. Detect which tool the user is running (Copilot or Claude) from context
2. Set `MCP_CLIENT_ID` based on tool choice
3. Get environment URL from `.env`
4. Default to GA endpoint (`/api/mcp`)
5. Register the MCP server (Copilot: write JSON config; Claude: run `claude mcp add` command)
6. Handle admin consent and environment allowlist (one-time per tenant/environment)

**Important:** MCP configuration requires an editor/CLI restart.

**For Copilot:** Write the JSON config, then:
> ✅ Dataverse MCP server configured. **Restart your editor** for changes to take effect.

**For Claude:** Run the `claude mcp add` command, then warn the user about the auth popup that will appear on next launch:
> ✅ Dataverse MCP server registered. Restart Claude Code to enable MCP tools.
> Remember to **use `claude --continue` to resume the session** without losing context.
>
> **On restart, a browser window will open** asking you to sign in to your Dataverse environment. This is the MCP proxy authenticating on your behalf — sign in with the same account you used for PAC CLI (e.g., `{username}`). This only happens once; the token is cached for future sessions.

---

## Step 7: Final verification

After the editor/CLI restarts, verify MCP works.

**Programmatic check (preferred):**
```
npx @microsoft/dataverse mcp {DATAVERSE_URL} --validate
```
This tests both GA and Preview endpoints, verifies authentication, and reports detailed errors without starting the server. If it passes, MCP is correctly configured.

**Agent check (alternative):**
> "Try asking: 'List the tables in my Dataverse environment.'"

If `list_tables` is called directly → MCP is connected. If the agent falls back to PAC CLI or Web API → see [mcp-configuration.md](references/mcp-configuration.md) troubleshooting section.

### MCP Server Capabilities

| Task | Use |
|---|---|
| Create/read/update/delete data records | MCP server |
| Create a new table | MCP server |
| Explore what tables/columns exist | MCP server (`list_tables`, `describe_table`) |
| Add a column to an existing table | Web API (see `dv-metadata`) |
| Create a relationship / lookup | Web API (see `dv-metadata`) |
| Create or modify a form | Web API (see `dv-metadata`) |
| Create or modify a view | Web API (see `dv-metadata`) |

After verifying MCP works, tell the user:

> ✅ Connected to Dataverse at `{DATAVERSE_URL}`. Tools installed, authenticated, MCP live.
>
> You can now:
> - Create tables, columns, and relationships (`dv-metadata`)
> - Query and manage data (`dv-python-sdk`)
> - Export and promote solutions (`dv-solution`)
>
> To create your first solution, see the `dv-solution` skill.
> To load sample data (accounts, contacts, opportunities), ask: "Load demo data into my Dataverse environment."

---

## Supported Agents

This plugin's skill files are natively loaded by both **GitHub Copilot CLI** and **Claude Code CLI** when installed as a plugin. No manual context-loading is needed — both agents discover and invoke skills automatically.

The PAC CLI commands, Python scripts, and XML templates work identically in both environments.

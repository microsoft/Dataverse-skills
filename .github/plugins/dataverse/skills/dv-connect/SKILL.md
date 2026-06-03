---
name: dv-connect
description: One-step setup for a Dataverse environment — installs tools, authenticates, registers the MCP server, and writes `.env`. Use when starting a new project, switching environments, fixing authentication, or troubleshooting an MCP connection that won't come up.
---

# Skill: Connect

One-step connection to Dataverse. Handles tool installation, authentication, environment selection, workspace initialization, MCP configuration, and verification — all idempotently. Each step checks if it's already done and skips if so.

> **Environment-First Rule** — All metadata (solutions, columns, tables, forms, views) and plugin registrations are created **in the Dynamics environment** via API or scripts, then pulled into the repo. Never write or edit solution XML by hand to create new components.

**Execute every step in order.** Do not skip ahead, even if a later step appears more relevant to the user's immediate goal. **Exception:** Step 0 below can short-circuit the entire flow if the workspace is already set up.

---

## Step 0: Detect existing setup (run this first)

Before touching anything, check whether this workspace is already connected to a Dataverse environment. This matters a lot on `claude --continue` or any re-run — the whole flow takes several minutes, and repeating it on an already-configured workspace overwrites `.env`, re-registers MCP, and wastes time.

Run these checks in order. If **all four pass**, skip straight to Step 7 (final verification) and stop there.

1. **`.env` is present and complete** — file exists at the workspace root and contains non-empty values for `DATAVERSE_URL`, `TENANT_ID`, and `MCP_CLIENT_ID`
2. **MCP is registered** — `.mcp.json` (Claude Code) or the equivalent Copilot / Cursor config file has a `dataverse-*` server entry pointing at the `DATAVERSE_URL` from `.env`
3. **Shared auth cache matches `.env`** — `dataverse auth who` shows a profile whose `Environment Url` matches `DATAVERSE_URL`, and `dataverse org who` against that profile succeeds. (PAC CLI is no longer the auth gate; `pac auth list` is optional.)
4. **Python SDK is importable and current** — `python -c "from PowerPlatform.Dataverse.client import DataverseClient; import pandas; from importlib.metadata import version; v=version('PowerPlatform-Dataverse-Client'); assert v>='0.1.0b9', f'SDK {v} is outdated, need >=0.1.0b9'"` exits 0

**If all pass:** Tell the user you detected an existing setup, list what you found (URL, profile name, MCP server name), then jump to Step 7. Do not rewrite `.env`, do not re-register MCP, do not re-run `pip install`.

> Example: "Detected existing Dataverse setup at `{DATAVERSE_URL}` (auth profile: `{PROFILE}`, MCP server: `dataverse-{orgid}`). Running verification only."

**If any check fails:** Proceed through the normal flow (Steps 1–7), but still use each step's own skip condition. A partially-configured workspace doesn't need a full redo — e.g., if only `.env` and MCP are missing but tools and auth are fine, start at Step 2 or Step 3.

---

## Step 1: Ensure tools are installed

Check each tool independently — **do not use fail-fast parallel execution.** If one tool check fails, continue checking the others so you can report all missing tools at once. See [tools-setup.md](references/tools-setup.md) for installation commands and platform-specific notes.

| Tool | Check |
|---|---|
| Python 3 | `python --version` |
| Git | `git --version` |
| Node.js | `node --version` |
| PAC CLI | `pac` (prints version banner; note: `pac --version` is not a valid command and returns a non-zero exit code) (see [tools-setup.md](references/tools-setup.md) for Windows path discovery if not in PATH) |
| Dataverse CLI | `npm list -g @microsoft/dataverse` (prints `@microsoft/dataverse@<version>` if installed globally; prints `(empty)` if not) |
| .NET SDK | `dotnet --version` |
| Azure CLI | `az --version` |

.NET SDK is needed for PAC CLI but NOT for the Dataverse CLI (the npm package bundles its own runtime). Node.js powers the Dataverse CLI npm package (`@microsoft/dataverse`), which is used as the MCP proxy and for scripted data plane actions. Azure CLI is used as a fallback for environment discovery when PAC CLI isn't available (see [mcp-configuration.md](references/mcp-configuration.md) Step 3b). GitHub CLI is not needed for connecting — it's used later for ALM/CI/CD scenarios (see `dv-solution`).

If any tool is missing, install it (see [tools-setup.md](references/tools-setup.md)), then verify. If `winget` installs a tool but it's not in PATH, ask the user to restart the terminal.

After Python is confirmed:
```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client pandas msal msal-extensions
```

`msal` and `msal-extensions` let `scripts/auth.py` reuse the token cache populated by `dataverse auth create`, so a single sign-in covers the CLI, the MCP stdio proxy, and every Python script in the plugin — no second device-code prompt.

After Node.js is confirmed, install or upgrade the Dataverse CLI to the latest version. This mirrors the `pip install --upgrade` pattern used for the Python SDK — running it on each connect ensures the CLI stays current:
```
npm install -g @microsoft/dataverse@latest
```

**Skip condition:** All tools present, Python SDK installed, and `pandas` importable (`python -c "import pandas"`).

---

## Step 2: Discover and select the environment

Before asking the user for a URL, check what's already available.

> **Auth tool choice.** `dataverse auth create` (from the `@microsoft/dataverse` npm package installed in Step 1) is the preferred login surface for this plugin. It uses the Dataverse CLI app registration (`0c412cc3-…`) and writes its MSAL cache to a location that the MCP stdio proxy AND `scripts/auth.py` both read — so one login serves all three. PAC CLI stays installed for solution / admin verbs in `dv-solution` and `dv-admin` but is no longer the auth gate.

Check for an existing DV CLI profile first, then fall back to PAC for environment discovery if needed:

```
dataverse auth list
dataverse auth who
pac auth list   # PAC profiles are still useful for env discovery / pac org list
```

**If `dataverse auth who` shows a profile and its environment matches the user's target:**
- Reuse it. Set `DATAVERSE_URL` and `TENANT_ID` from the profile.

**If no DV CLI profile exists (or it points at the wrong environment):**
- Ask: "Do you want to connect to an existing environment or create a new one?"

**Before selecting, check for tenant/region mismatch.** If the target environment URL uses a different region (e.g., `crm10.dynamics.com` = APAC) than the currently authenticated account's environments, create a new profile for the correct tenant rather than trying to reuse the old one:

```
dataverse auth create --environment <url>          # interactive (WAM broker on Windows → no browser tab)
dataverse auth create --environment <url> --deviceCode   # headless / remote / SSH
```

On first run in a tenant, AAD may prompt for admin consent for app `0c412cc3-0dd6-449b-987f-05b053db9457`. If the user lacks consent rights, ask an admin to visit:

```
https://login.microsoftonline.com/<tenant-id>/adminconsent?client_id=0c412cc3-0dd6-449b-987f-05b053db9457
```

**To switch between existing DV CLI profiles:**
```
dataverse auth select --name <profile-name>
```

**To create a new environment** (requires admin permissions):
```
pac admin create --name "<name>" --type "<type>" --region "<region>"
```
If this fails with permissions error, guide the user to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/) to create it, then connect.

**Confirm connection:**
```
dataverse auth who
dataverse org who      # or: pac org who
```
Parse the output to extract `DATAVERSE_URL` and `TENANT_ID`.

If neither command shows a tenant ID, fall back to:
```bash
curl -sI https://<org>.crm.dynamics.com/api/data/v9.2/ \
  | grep -i "WWW-Authenticate" \
  | sed -n 's|.*login\.microsoftonline\.com/\([^/]*\).*|\1|p'
```

**Skip condition:** `.env` exists with valid `DATAVERSE_URL` and `TENANT_ID`, and `dataverse auth who` confirms the connection.

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

Also set plugin attribution variables for User-Agent tagging. **Fill in the two literals below from your own context** — you (the agent) loaded this plugin, so you already know both values:

- `PLUGIN_VERSION` — the `version` field of your loaded plugin manifest (e.g. `"1.5.0"`). At runtime, `auth.py` re-reads this from the live manifest via host env vars; this `.env` entry is a fallback for offline cases.
- `AGENT` — your host identity, one of: `claude-code`, `copilot`, `cursor`, `codex`, or `unknown`. Must match an entry in `_ALLOWED_AGENTS` in `auth.py` — if you don't recognize your host, use `unknown`.

```python
# Substitute these two literals from your loaded plugin context.
# Do NOT leave the angle-bracket placeholders — replace with real values.
plugin_version = "<plugin manifest version, e.g. 1.5.0>"
agent_host = "<your host name: claude-code | copilot | cursor | codex | unknown>"

with open(".env", "w") as f:
    f.write(f"DATAVERSE_URL={dataverse_url}\n")
    f.write(f"TENANT_ID={tenant_id}\n")
    f.write(f"MCP_CLIENT_ID={mcp_client_id}\n")
    f.write(f"DATAVERSE_PLUGIN_VERSION={plugin_version}\n")
    f.write(f"DATAVERSE_PLUGIN_AGENT={agent_host}\n")
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
import os

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
cp .github/plugins/dataverse/scripts/auth.py scripts/
```

Copy `templates/CLAUDE.md` to the repo root if it doesn't exist. Replace placeholders (`{{DATAVERSE_URL}}`, `{{SOLUTION_NAME}}`, `{{PUBLISHER_PREFIX}}`) with values from `.env`.

**Skip condition:** `scripts/auth.py` exists.

---

## Step 5: Verify the connection

```
dataverse auth who
python scripts/auth.py
```

Both must succeed and resolve the same user/environment. `dataverse auth who` proves the shared MSAL cache is populated; `python scripts/auth.py` proves Python can silently read that same cache (no device-code prompt).

If the user is doing solution / admin work, optionally also confirm `pac org who` matches.

**If either fails:**
- `dataverse auth who` fails → re-run Step 2 (`dataverse auth create --environment <url>`)
- `python scripts/auth.py` prints a device-code URL → the shared cache is missing or the wrong tenant. Re-run `dataverse auth create --environment <url>` and try again. Confirm `msal` and `msal-extensions` are installed (`pip show msal msal-extensions`) — without them Python falls back to its own device-code flow.
- `python scripts/auth.py` fails with a different error → check Python SDK install and `.env` values.

---

## Step 6: Configure MCP server

**Skip this step** if MCP is already configured:
- `.mcp.json` or `~/.copilot/mcp-config.json` or `~/.cursor/mcp.json` contains a Dataverse server entry
- `claude mcp list` shows a `dataverse-*` server registered

If MCP is not configured, follow [mcp-configuration.md](references/mcp-configuration.md):

1. Detect which tool the user is running (Copilot, Claude, or Cursor) from context
2. Set `MCP_CLIENT_ID` based on tool choice
3. Get environment URL from `.env`
4. Default to GA endpoint (`/api/mcp`)
5. Register the MCP server (Copilot: write JSON config; Claude: run `claude mcp add` command; Cursor: write JSON config to `~/.cursor/mcp.json` or workspace `.cursor/mcp.json`)
6. Handle admin consent and environment allowlist (one-time per tenant/environment)

**Plugin attribution for MCP:** This plugin uses the **stdio proxy** transport (`npx @microsoft/dataverse mcp <url>`) — the CLI runs as a local subprocess and proxies requests to the Dataverse MCP HTTP endpoint. When registering the stdio proxy, include `DATAVERSE_OPERATION_CONTEXT` in the env block so the CLI reads it at startup and appends it to its User-Agent on all outbound HTTP requests to `/api/mcp`. Build the value from `.env`:

```
DATAVERSE_OPERATION_CONTEXT=app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=unknown;agent={DATAVERSE_PLUGIN_AGENT}
```

For Claude Code (`claude mcp add -t stdio`), pass it via `-e DATAVERSE_OPERATION_CONTEXT=...`. For Copilot/Cursor JSON configs, add it to the `"env"` object in the stdio server entry.

**Important:** MCP configuration requires an editor/CLI restart.

**For Copilot:** Write the JSON config, then:
> ✅ Dataverse MCP server configured. **Restart your editor** for changes to take effect.

**For Claude:** Run the `claude mcp add` command, then warn the user about the auth popup that will appear on next launch:
> ✅ Dataverse MCP server registered. Restart Claude Code to enable MCP tools.
> Remember to **use `claude --continue` to resume the session** without losing context.
>
> **On restart, a browser window will open** asking you to sign in to your Dataverse environment. This is the MCP proxy authenticating on your behalf — sign in with the same account you used for PAC CLI (e.g., `{username}`). This only happens once; the token is cached for future sessions.

**For Cursor:** Write the JSON config, then:
> ✅ Dataverse MCP server `dataverse-{orgid}` configured in `~/.cursor/mcp.json`. **Reload the Cursor window** (Ctrl+Shift+P → "Developer: Reload Window") for the new MCP server to appear under Settings → Tools & MCPs.
>
> On first use, the `npx @microsoft/dataverse` proxy starts a device-code sign-in in your browser. Sign in with the same account you used for PAC CLI; the token is cached in your OS credential store for future sessions.

---

## Step 7: Final verification

After the editor/CLI restarts, **both** of these must succeed before declaring the setup complete:

**Check 1: `claude mcp list` (or Copilot equivalent) shows ✓ Connected**
```
claude mcp list
```
This proves the MCP server process starts and speaks the MCP protocol. It does NOT by itself prove that data operations work — authentication, environment allowlisting, and endpoint reachability are only exercised on the first real tool call.

**Check 2: Agent successfully calls `list_tables` and returns data**
> "List the tables in my Dataverse environment."

This proves end-to-end wiring: auth, tenant consent, environment allowlist, and endpoint reachability are all correct. If the agent falls back to PAC CLI or Web API, see [mcp-configuration.md](references/mcp-configuration.md) troubleshooting.

Only when **both** checks pass is the setup verified.

**Interpreting failures:**

- If Check 1 fails (server not ✓ Connected): the MCP server itself cannot start. Re-run Step 6 and check that `npx`/Node.js are installed and the MCP registration succeeded.
- If Check 1 passes but Check 2 fails (server starts but `list_tables` errors): the server can speak MCP but cannot reach or read Dataverse. Run `--validate` below to diagnose.

**Diagnostic — `--validate` (for failure investigation only):**
```
npx @microsoft/dataverse mcp {DATAVERSE_URL} --validate
```
This exercises two Dataverse MCP endpoints with a fresh authentication handshake and reports detailed errors (auth, allowlist, consent, endpoint reachability):

- **GA / Production endpoint** — `{DATAVERSE_URL}/api/mcp`. This is the one the plugin actually uses at runtime.
- **Preview endpoint** — `{DATAVERSE_URL}/api/mcp_preview`. Opt-in per environment; not used by the plugin.

**Do not use `--validate` as a success gate on first-time setup.** On a freshly configured workspace, the token cache hasn't warmed up, so `--validate` can fail with `MsalClientException` or `403` while MCP is actually working fine on subsequent real calls. Reserve `--validate` for diagnosing a confirmed failure in Check 1 or Check 2.

**How to read `--validate` output:**

- **Look at the GA / Production endpoint (`/api/mcp`) result first.** If this passes, MCP will work for normal plugin usage regardless of what the Preview endpoint reports.
- **A `403 Forbidden` on the Preview endpoint (`/api/mcp_preview`) is expected for most environments.** Preview is opt-in per environment; if your environment hasn't enabled it, the Preview check will always fail. This does not indicate a broken setup.
- **Ignore the overall exit code and the `⚠ Partial success` warning in this case.** The validator returns exit code `1` (failure) unless BOTH `/api/mcp` and `/api/mcp_preview` pass. Because most environments don't enable the Preview endpoint, `--validate` will exit `1` even when MCP is fully functional via the GA endpoint. Focus on per-endpoint results, not the aggregate status.
- **If the GA endpoint (`/api/mcp`) fails:** that's the real signal to investigate — auth, tenant consent, environment allowlist, or endpoint reachability.

### MCP Server Capabilities

| Task | Use |
|---|---|
| Create/read/update/delete data records | MCP server |
| Create a new table | MCP server |
| Explore what tables/columns exist | MCP server (`list_tables`, `describe_table`) |
| Add a column to an existing table | MCP server (`update_table`) for basic columns; SDK or Web API (see `dv-metadata`) for advanced options (choice columns, lookups, relationships) |
| Create a relationship / lookup | SDK (see `dv-metadata`) |
| Create or modify a form | Web API (see `dv-metadata`) |
| Create or modify a view | Web API (see `dv-metadata`) |

After verifying MCP works, tell the user:

> ✅ Connected to Dataverse at `{DATAVERSE_URL}`. Tools installed, authenticated, MCP live.
>
> You can now:
> - Create tables, columns, and relationships (`dv-metadata`)
> - Write and import data (`dv-data`)
> - Query and analyze data (`dv-query`)
> - Export and promote solutions (`dv-solution`)
>
> To create your first solution, see the `dv-solution` skill.
> To load sample data (accounts, contacts, opportunities), ask: "Load demo data into my Dataverse environment."

---

## Supported Agents

This plugin's skill files are natively loaded by both **GitHub Copilot CLI** and **Claude Code CLI** when installed as a plugin. No manual context-loading is needed — both agents discover and invoke skills automatically.

The PAC CLI commands, Python scripts, and XML templates work identically in both environments.

# MCP Server Configuration Reference

Detailed instructions for configuring the Dataverse MCP server for GitHub Copilot, Claude Code, Cursor, or Codex.

The environment URL should already be known from the `dv-connect` flow (stored in `DATAVERSE_URL` in `.env`). If it's not set, go back to Step 2 of the `dv-connect` skill to discover and select the environment first.

The parameters for the MCP server should be determined from context or environment variables where possible, and interactive prompts should only be used when it cannot be done.

---

## 0. Determine which tool to configure

Determine whether to configure MCP for GitHub Copilot, Claude Code, Cursor, or Codex:
- If explicitly mentioned in prompt, use that.
- Otherwise, determine which tool the user is running from the context.
- Only if choosing based on the context is impossible, ask the user:

> Which tool would you like to configure the Dataverse MCP server for?
> 1. **GitHub Copilot**
> 2. **Claude**
> 3. **Cursor**
> 4. **Codex**

Based on the result, set the `TOOL_TYPE` variable to `copilot`, `claude`, `cursor`, or `codex`. Store this for use in all subsequent steps.

Set the `MCP_CLIENT_ID` variable in `.env` based on the tool choice:
- If `copilot`: `MCP_CLIENT_ID` = `aebc6443-996d-45c2-90f0-388ff96faa56`
- If `claude`, `cursor`, or `codex`: `MCP_CLIENT_ID` = `0c412cc3-0dd6-449b-987f-05b053db9457` (all use the `@microsoft/dataverse` npx stdio proxy, which authenticates as the Dataverse CLI app)
- If `claude` and the VSCode extension is used: set it to the same value as `CLIENT_ID` if already set, otherwise offer to create a new app registration following the auth setup in the `dv-connect` skill.

---

## 1. Determine the MCP scope

Choose the configuration scope based on the tool. Use the scope explicitly mentioned by the user, or choose the default without asking to confirm it.

**If TOOL_TYPE is `copilot`:**

The options are:
1. **Globally** (default, available in all projects)
2. **Project-only** (available only in this project)

Based on the scope, set the `CONFIG_PATH` variable:
- **Global**: `~/.copilot/mcp-config.json` (use the user's home directory)
- **Project**: `.mcp.json` (relative to the current working directory)

Store this path for use in steps 2 and 5.

**If TOOL_TYPE is `claude`:**

The options are:
1. **User** (available in all projects for this user)
2. **Project** (default, available only in this project)
3. **Local** (scoped to current project directory)

Based on the scope, set the `CLAUDE_SCOPE` variable:
- **User**: `CLAUDE_SCOPE` = `user`
- **Project**: `CLAUDE_SCOPE` = `project`
- **Local**: `CLAUDE_SCOPE` = `local`

Store this value for use in step 5.

**If TOOL_TYPE is `cursor`:**

The options are:
1. **Globally** (default, available in all projects)
2. **Project-only** (available only in this project)

Based on the scope, set the `CONFIG_PATH` variable:
- **Global**: `~/.cursor/mcp.json` (use the user's home directory)
- **Project**: `.cursor/mcp.json` (relative to the current working directory)

Store this path for use in steps 2 and 5.

**If TOOL_TYPE is `codex`:**

Codex stores MCP servers in a `config.toml` file. The options are:
1. **Globally** (default, available in all projects)
2. **Project-only** (trusted projects only)

Based on the scope, set the `CONFIG_PATH` variable:
- **Global**: `~/.codex/config.toml` (use the user's home directory)
- **Project**: `.codex/config.toml` (relative to the current working directory)

Store this path for use in steps 2 and 5.

---

## 2. Check already-configured MCP servers

**If TOOL_TYPE is `copilot`:**

Read the MCP configuration file at `CONFIG_PATH` (determined in step 1) to check for already-configured servers.

The configuration file is a JSON file with the following structure:

```json
{
  "mcpServers": {
    "ServerName1": {
      "type": "http",
      "url": "https://example.com/api/mcp"
    }
  }
}
```

Or it may use `"servers"` instead of `"mcpServers"` as the top-level key.

Extract all `url` values from the configured servers and store them as `CONFIGURED_URLS`. For example:

```json
["https://orgfbb52bb7.crm.dynamics.com/api/mcp"]
```

If the file doesn't exist or is empty, treat `CONFIGURED_URLS` as empty (`[]`). This step must never block the skill.

If the environment URL from `.env` is already in `CONFIGURED_URLS`, the MCP server is **already configured**. Confirm with the user whether they want to re-register it (e.g. to change the endpoint type) before proceeding. If not, skip to the end.

**If TOOL_TYPE is `claude`:**

Skip this step — Claude uses CLI commands to manage MCP servers, so we don't need to check existing configuration.

**If TOOL_TYPE is `cursor`:**

Read the MCP configuration file at `CONFIG_PATH` (determined in step 1) to check for already-configured servers. Same logic as Copilot: parse `mcpServers` (or `servers`) keys, extract URLs, store as `CONFIGURED_URLS`. If the file doesn't exist or is empty, treat `CONFIGURED_URLS` as empty (`[]`).

If the environment URL from `.env` is already in `CONFIGURED_URLS`, the MCP server is **already configured**. Confirm with the user whether they want to re-register it before proceeding. If not, skip to the end.

**If TOOL_TYPE is `codex`:**

Read the `config.toml` file at `CONFIG_PATH` (determined in step 1) to check for already-configured servers. The file is TOML — look for `[mcp_servers.<name>]` tables and extract the environment URL from each table's `args` array (the URL is the argument that follows `"mcp"`). Store the URLs as `CONFIGURED_URLS`. If the file doesn't exist or has no `[mcp_servers.*]` tables, treat `CONFIGURED_URLS` as empty (`[]`).

If the environment URL from `.env` is already in `CONFIGURED_URLS`, the MCP server is **already configured**. Confirm with the user whether they want to re-register it before proceeding. If not, skip to the end.

---

## 3. Determine the environment URL

If the user provided a URL via command parameters it is: '$ARGUMENTS'. If the user mentioned the URL in the prompt, use it. Otherwise, take the URL from the `DATAVERSE_URL` variable in `.env`. If you have the URL, skip to step 4.

If the file or the variable doesn't exist, the environment URL must be discovered. Try the `dv-connect` skill's Step 2 first. If that's not possible (e.g., this reference is being used standalone), use the auto-discovery priority order below — try each method in order, stop at the first that succeeds:

1. **PAC CLI** (preferred) → step 3a
2. **Azure CLI** (fallback) → step 3b
3. **Manual entry** (last resort) → step 3c

### 3a. Auto-discover via PAC CLI (preferred)

Check if PAC CLI is available:

```
pac --version
```

If available, check auth and list environments:

```
pac auth list
pac org who
pac env list
```

If PAC CLI is authenticated and `pac env list` returns results, present the environments to the user:

> I found the following Dataverse environments via PAC CLI. Which one would you like to configure MCP for?
>
> 1. My Dev Org — `https://orgfbb52bb7.crm.dynamics.com`
> 2. Another Env — `https://orgabc123.crm.dynamics.com`
>
> Or type a URL manually.

If PAC CLI is not installed or not authenticated, fall back to step 3b.

### 3b. Auto-discover via Azure CLI (fallback)

**Check prerequisites:**
- Verify Azure CLI (`az`) is installed (check with `which az` or `where az` on Windows)
- If not installed, inform the user and fall back to step 3c

**Make the API call:**

1. Check if the user is logged into Azure CLI:
   ```bash
   az account show
   ```
   If this fails, prompt the user to log in:
   ```bash
   az login
   ```

2. Get an access token for the Power Apps API:
   ```bash
   az account get-access-token --resource https://service.powerapps.com/ --query accessToken --output tsv
   ```

3. Call the Power Apps API to list environments:
   ```
   GET https://api.powerapps.com/providers/Microsoft.PowerApps/environments?api-version=2016-11-01
   Authorization: Bearer {token}
   Accept: application/json
   ```

4. Parse the JSON response and filter for environments where `properties?.linkedEnvironmentMetadata?.instanceUrl` is not null.

5. For each matching environment, extract:
   - `properties.displayName` as `displayName`
   - `properties.linkedEnvironmentMetadata.instanceUrl` (remove trailing slash) as `instanceUrl`

6. Create a list of environments in this format:
   ```json
   [
     { "displayName": "My Org (default)", "instanceUrl": "https://orgfbb52bb7.crm.dynamics.com" },
     { "displayName": "Another Env", "instanceUrl": "https://orgabc123.crm.dynamics.com" }
   ]
   ```

**If the API call succeeds**, present the environments as a numbered list. For each environment, check whether any URL in `CONFIGURED_URLS` starts with that environment's `instanceUrl` — if so, append **(already configured)** to the line.

> I found the following Dataverse environments on your account. Which one would you like to configure?
>
> 1. My Org (default) — `https://orgfbb52bb7.crm.dynamics.com` **(already configured)**
> 2. Another Env — `https://orgabc123.crm.dynamics.com`
>
> Enter the number of your choice, or type "manual" to enter a URL yourself.

If the user selects an already-configured environment, confirm that they want to re-register it (e.g. to change the endpoint type) before proceeding.

If the user types "manual", fall back to step 3c.

**If the API call fails** (user not logged in, network error, no environments found, or any other error), tell the user what went wrong and fall back to step 3c.

### 3c. Manual entry — ask for the URL

Ask the user to provide their environment URL directly:

> Please enter your Dataverse environment URL.
>
> Example: `https://myorg.crm10.dynamics.com`
>
> You can find this in the Power Platform Admin Center under Environments.

### 3d. Remember the selected URL

Take the URL determined above (from context, `.env`, manual entry, or `instanceUrl` from discovery) and strip any trailing slash. This is `USER_URL` for the remainder of this reference.

---

## 4. Decide whether to use the "Preview" or "Generally Available (GA)" endpoint

Determine from the context which of these options the user wants to use. If they did not mention either, default to GA:

- If **Generally Available (GA)**: set `MCP_URL` to `{USER_URL}/api/mcp`
- If **Preview**: set `MCP_URL` to `{USER_URL}/api/mcp_preview`

---

## 5. Register the MCP server

**If TOOL_TYPE is `copilot`:**

Update the MCP configuration file at `CONFIG_PATH` (determined in step 1) to add the new server.

**Generate a unique server name** from the `USER_URL`:
1. Extract the subdomain (organization identifier) from the URL
   - Example: `https://orgbc9a965c.crm10.dynamics.com` → `orgbc9a965c`
2. Prepend `DataverseMcp` to create the server name
   - Example: `DataverseMcporgbc9a965c`

This is the `SERVER_NAME`.

**Update the configuration file:**

1. Read the existing configuration file at `CONFIG_PATH`, or create a new empty config if it doesn't exist:
   ```json
   {}
   ```

2. Determine which top-level key to use:
   - If the config already has `"servers"`, use that
   - Otherwise, use `"mcpServers"`

3. Add or update the server entry:
   ```json
   {
     "mcpServers": {
       "{SERVER_NAME}": {
         "type": "http",
         "url": "{MCP_URL}"
       }
     }
   }
   ```

4. Write the updated configuration back to `CONFIG_PATH` with proper JSON formatting (2-space indentation).

**Important notes:**
- Do NOT overwrite other entries in the configuration file
- Preserve the existing structure and formatting
- If `SERVER_NAME` already exists, update it with the new `MCP_URL`

**If TOOL_TYPE is `claude`:**

Generate the CLI command. Do NOT edit any configuration files.

**IMPORTANT: Always use `-t stdio` transport with the npx proxy.** Never use `--transport http` or `--transport sse` for Claude — the Dataverse MCP endpoint requires authentication that only the npx proxy handles. Using HTTP transport directly will fail with connection errors.

**Generate a unique server name** from the `USER_URL`:
1. Extract the subdomain (organization identifier) from the URL
   - Example: `https://orgbc9a965c.crm10.dynamics.com` → `orgbc9a965c`
2. Use lowercase format: `dataverse-{orgid}`
   - Example: `dataverse-orgbc9a965c`

This is the `SERVER_NAME`.

**Build the command:**

Construct the command based on `CLAUDE_SCOPE` and whether the user chose GA or Preview endpoint. **Always pass `-e DATAVERSE_OPERATION_CONTEXT="…"`** so the stdio proxy attaches plugin attribution to outbound requests (same role as the `env` block in the Copilot / Cursor JSON configs):

```
claude mcp add --scope {CLAUDE_SCOPE} {SERVER_NAME} -t stdio -e DATAVERSE_OPERATION_CONTEXT="app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent=claude-code" -- npx -y @microsoft/dataverse@latest mcp "{USER_URL}" {ENDPOINT_FLAG}
```

When running on Windows without WSL, wrap the `npx` call into `cmd //c` and omit the quotes around the URL:

```
claude mcp add --scope {CLAUDE_SCOPE} {SERVER_NAME} -t stdio -e DATAVERSE_OPERATION_CONTEXT="app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent=claude-code" -- cmd //c "npx -y @microsoft/dataverse@latest mcp {USER_URL} {ENDPOINT_FLAG}"
```

Where:
- `{CLAUDE_SCOPE}` is `user`, `project`, or `local` (from step 1)
- `{SERVER_NAME}` is the generated server name (e.g., `dataverse-orgbc9a965c`)
- `{USER_URL}` is the base environment URL (e.g., `https://orgbc9a965c.crm10.dynamics.com`)
- `{ENDPOINT_FLAG}` is `--preview` if the user chose Preview endpoint in step 4, otherwise omit this flag
- `{DATAVERSE_PLUGIN_VERSION}` comes from `.env` (set in dv-connect Step 3)

**Example commands:**
- GA endpoint with user scope: `claude mcp add --scope user dataverse-orgbc9a965c -t stdio -e DATAVERSE_OPERATION_CONTEXT="app=dataverse-skills/1.5.0;skill=mcp-direct;agent=claude-code" -- npx -y @microsoft/dataverse@latest mcp "https://orgbc9a965c.crm10.dynamics.com"`
- Preview endpoint with project scope: `claude mcp add --scope project dataverse-orgbc9a965c -t stdio -e DATAVERSE_OPERATION_CONTEXT="app=dataverse-skills/1.5.0;skill=mcp-direct;agent=claude-code" -- npx -y @microsoft/dataverse@latest mcp "https://orgbc9a965c.crm10.dynamics.com" --preview`
- GA endpoint on Windows with project scope: `claude mcp add --scope project dataverse-orgbc9a965c -t stdio -e DATAVERSE_OPERATION_CONTEXT="app=dataverse-skills/1.5.0;skill=mcp-direct;agent=claude-code" -- cmd //c "npx -y @microsoft/dataverse@latest mcp https://orgbc9a965c.crm10.dynamics.com"`

Store this command as `CLAUDE_COMMAND` for use in step 8.

**If TOOL_TYPE is `cursor`:**

Update the MCP configuration file at `CONFIG_PATH` (determined in step 1) to add the new server.

**IMPORTANT: Always use the stdio transport via the npx proxy.** Do not configure a direct `url` to `/api/mcp` — the Dataverse MCP HTTP endpoint requires the npx proxy to handle authentication. The proxy is `@microsoft/dataverse@latest mcp <url>`.

**Generate a unique server name** from the `USER_URL`:
1. Extract the subdomain (organization identifier) from the URL
   - Example: `https://orgbc9a965c.crm10.dynamics.com` → `orgbc9a965c`
2. Use lowercase format: `dataverse-{orgid}`
   - Example: `dataverse-orgbc9a965c`

This is the `SERVER_NAME`.

**Update the configuration file:**

1. If `CONFIG_PATH` is for a **project-scoped** configuration (`.cursor/mcp.json`), ensure the `.cursor` directory exists first:
   ```bash
   mkdir -p .cursor
   ```

2. Read the existing configuration file at `CONFIG_PATH`, or create a new empty config if it doesn't exist:
   ```json
   { "mcpServers": {} }
   ```

3. Add or update the server entry under `mcpServers`:
   ```json
   {
     "mcpServers": {
       "{SERVER_NAME}": {
         "command": "npx",
         "args": ["-y", "@microsoft/dataverse@latest", "mcp", "{USER_URL}"],
         "env": {
           "DATAVERSE_OPERATION_CONTEXT": "app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent=cursor"
         }
       }
     }
   }
   ```

   Append `"--preview"` to the `args` array if the user chose the Preview endpoint in step 4.

4. Write the updated configuration back to `CONFIG_PATH` with proper JSON formatting (2-space indentation).

**Important notes:**
- Do NOT overwrite other entries in the configuration file — preserve sibling `mcpServers` entries
- If `SERVER_NAME` already exists, update it with the new args
- After writing, ask the user to **reload the Cursor window** (Ctrl+Shift+P → "Developer: Reload Window") for the new MCP server to appear

**If TOOL_TYPE is `codex`:**

Update the `config.toml` file at `CONFIG_PATH` (determined in step 1) to add the new server.

**IMPORTANT: Always use the stdio transport via the npx proxy.** Do not configure a direct `url` to `/api/mcp` — the Dataverse MCP HTTP endpoint requires the npx proxy to handle authentication. The proxy is `@microsoft/dataverse@latest mcp <url>`.

**Generate a unique server name** from the `USER_URL`:
1. Extract the subdomain (organization identifier) from the URL
   - Example: `https://orgbc9a965c.crm10.dynamics.com` → `orgbc9a965c`
2. Use lowercase format: `dataverse-{orgid}`
   - Example: `dataverse-orgbc9a965c`

This is the `SERVER_NAME`.

**Update the configuration file:**

1. If `CONFIG_PATH` is for a **project-scoped** configuration (`.codex/config.toml`), ensure the `.codex` directory exists first:
   ```bash
   mkdir -p .codex
   ```

2. Read the existing `config.toml` at `CONFIG_PATH`, or treat it as empty if it doesn't exist. Preserve all existing content (other settings and `[mcp_servers.*]` tables).

3. Add the server as a `[mcp_servers.{SERVER_NAME}]` table with an `env` sub-table:
   ```toml
   [mcp_servers.{SERVER_NAME}]
   command = "npx"
   args = ["-y", "@microsoft/dataverse@latest", "mcp", "{USER_URL}"]

   [mcp_servers.{SERVER_NAME}.env]
   DATAVERSE_OPERATION_CONTEXT = "app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent=codex"
   ```

   Append `"--preview"` to the `args` array if the user chose the Preview endpoint in step 4.

Where:
- `{SERVER_NAME}` is the generated server name (e.g., `dataverse-orgbc9a965c`)
- `{USER_URL}` is the base environment URL (e.g., `https://orgbc9a965c.crm10.dynamics.com`)
- `{DATAVERSE_PLUGIN_VERSION}` comes from `.env` (set in dv-connect Step 3)

**Important notes:**
- Do NOT overwrite other entries in the file — preserve sibling `[mcp_servers.*]` tables and any other settings
- If `[mcp_servers.{SERVER_NAME}]` already exists, replace that table (and its `.env` sub-table) with the new values; otherwise append the new tables
- After writing, ask the user to **restart Codex** for the new MCP server to load

---

## 6. Ensure tenant-level admin consent (one-time per tenant)

The MCP client app registration must be granted admin consent on the Azure AD tenant. This is a **one-time** action per tenant — once done, it applies to all Dataverse environments in that tenant. It **requires an Azure AD Global Admin or Privileged Role Admin**.

List out the parameters chosen in previous steps:
- Tool type (Copilot, Claude, Cursor, or Codex) from step 0
- Scope from step 1
- Environment URL from step 3
- Endpoint (GA or Preview) from step 4
- MCP Client ID from step 0

Ask the user if admin consent has already been granted for this tenant. If not, provide the consent URL:

> **Tenant-level admin consent** is required for the MCP client app. This is a one-time action per Azure AD tenant — once granted, it covers all environments in the tenant.
>
> An Azure AD Global Admin or Privileged Role Admin must open this URL and click **Accept**:
> ```
> https://login.microsoftonline.com/{TENANT_ID}/adminconsent?client_id={MCP_CLIENT_ID}
> ```
>
> If you don't have admin permissions, send this URL to your Azure AD administrator.

Wait for the user to confirm this is done (or was already done previously) before proceeding.

---

## 7. Add the MCP client to the environment's allowed list (one-time per environment)

Separately from tenant-level consent, each Dataverse environment must explicitly allow the MCP client. This is a **one-time** action per environment and does **NOT** require Azure AD admin permissions — any user with Environment Admin or System Administrator role in the environment can do it.

> **One sign-in for CLI, MCP, and Python.** When the user runs `dataverse auth create` (see `dv-connect` Step 2) the token cache is written to a path / OS keychain entry that the `@microsoft/dataverse` stdio MCP proxy and `scripts/auth.py` both read silently. As a result, the allowlisted MCP client ID (`0c412cc3-…` for the Claude / Cursor stdio proxy, or `aebc6443-…` for Copilot HTTP) is exercised exactly once per environment — there is no separate Python device-code sign-in for the same user/env. If a script does prompt for a device code, the shared cache is missing or stale; re-run `dataverse auth create --environment <url>`.

Present the methods in priority order. **Always attempt Method A first** — it is a single command, needs no portal navigation, and is the most reliable path.

> **Method A (preferred): Dataverse CLI `mcp allow`**
>
> Run the first-class CLI command — it ensures the MCP client app is in the environment's allowed list using the active auth profile's environment:
>
> ```
> dataverse mcp allow {MCP_CLIENT_ID}
> ```
>
> Any of these outputs means success — continue to validation:
> - `Client {MCP_CLIENT_ID} is already enabled. No changes needed.`
> - `Client exists but is disabled. Enabling... Done.`
> - `Client not found. Creating... Done.`
>
> Requires the signed-in user to have Dataverse admin rights (Environment Admin or System Administrator) on the target environment. No Azure AD admin needed.

> **Method B (fallback): Power Platform Admin Center**
>
> Use this only if `dataverse mcp allow` is unavailable (CLI not installed) or fails on permissions:
>
> 1. Go to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/)
> 2. Select **Environments** in the left navigation
> 3. Click on your environment (e.g., the one matching `{USER_URL}`)
> 4. Click **Settings** in the top toolbar
> 5. Expand **Product** and click **Features**
> 6. Scroll down to the **MCP Server** section
> 7. Toggle **Enable MCP Server** to **On** (if not already)
> 8. Under **Allowed clients**, click **Add client**
> 9. Paste the MCP Client ID: `{MCP_CLIENT_ID}`
> 10. Click **Save**

> **Method C (fallback): Programmatic via script**
>
> Run `scripts/enable-mcp-client.py` to add the client ID to the allowed list via the Dataverse API. Useful in non-interactive environments where the CLI isn't present.

**Do not send the user to the portal (Method B) before attempting Method A.** Run `dataverse mcp allow {MCP_CLIENT_ID}` yourself first; fall back to Method B or C only if it fails (CLI missing, or the user lacks Dataverse admin rights).

**Then validate the endpoint:**

```
npx -y @microsoft/dataverse@latest mcp {USER_URL} --validate
```

Treat `GA endpoint is valid, but Preview endpoint is not configured` as **success** for a GA registration (the default). Only revisit enablement if the GA endpoint still returns **403 Forbidden** after `mcp allow` reported success.

---

## 8. Confirm success and provide next steps

**If TOOL_TYPE is `copilot`:**

Tell the user:

> ✅ Dataverse MCP server configured for GitHub Copilot at `{MCP_URL}`.
>
> Configuration saved to: `{CONFIG_PATH}`
>
> **IMPORTANT: You must restart your editor for the changes to take effect.**
>
> Restart your editor or reload the window, then you will be able to:
> - List all tables in your Dataverse environment
> - Query records from any table
> - Create, update, or delete records
> - Explore your schema and relationships

Pause and give the user a chance to restart their editor before proceeding. Do not perform any subsequent or parallel operations until the user responds — they need MCP tools to be active first.

**If TOOL_TYPE is `claude`:**

Run {CLAUDE_COMMAND} to install the Dataverse MCP server, then tell the user:
> ✅ Dataverse MCP server registered. Restart Claude Code to enable MCP tools.
> Remember to **use `claude --continue` to resume the session** without losing context.
>
> **On restart, a browser window will open** asking you to sign in to your Dataverse environment. This is the MCP proxy (`@microsoft/dataverse`) authenticating on your behalf. Sign in with the same account you used earlier. This only happens once — the token is cached for future sessions.
>
> After signing in, you will be able to:
> - List all tables in your Dataverse environment
> - Query records from any table
> - Create, update, or delete records
> - Explore your schema and relationships

Pause and give the user a chance to restart the session to enable it before proceeding. Do not perform any subsequent or parallel operations until the user responds.

**If TOOL_TYPE is `codex`:**

Tell the user:

> ✅ Dataverse MCP server `{SERVER_NAME}` written to `{CONFIG_PATH}`.
>
> **IMPORTANT: Codex loads MCP tools at startup.** Fully **restart Codex** (CLI) or **reload the Codex IDE** for the Dataverse tools to appear — the current session cannot call them yet.
>
> After restart, you will be able to:
> - List all tables in your Dataverse environment
> - Query records from any table
> - Create, update, or delete records
> - Explore your schema and relationships

**Do not claim the Dataverse MCP tools are callable in the current session.** They become available only after a restart, once Codex discovers the `dataverse-*` server. If the user asks you to run an MCP query before restarting, explain that the tools load on restart — do **not** spin up a separate `npx @microsoft/dataverse mcp` stdio proxy as a workaround, and if the user explicitly required MCP, do **not** silently fall back to the SDK or Web API. Surface the restart requirement instead.

Pause and give the user a chance to restart Codex before proceeding.

---

## 9. Troubleshooting

If something goes wrong, help the user check:

- The URL format is correct (`https://<org>.<region>.dynamics.com`)
- They have access to the Dataverse environment
- The environment URL matches what's shown in the Power Platform Admin Center
- **Tenant-level admin consent** has been granted for the MCP client app. This is a one-time per-tenant action requiring an Azure AD admin. Without it, authentication succeeds but the app is denied access. Use the admin consent URL from step 6.
- **Org-level allowed clients** — the MCP client ID has been added to the environment's allowed list. The quickest fix is the CLI command `dataverse mcp allow {MCP_CLIENT_ID}` (Step 7, Method A). To check or fix it via the portal instead:
  1. Go to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/) > Environments > your environment > Settings > Product > Features
  2. Verify **MCP Server** is toggled **On**
  3. Verify the MCP Client ID appears under **Allowed clients**
- If using the Preview endpoint, verify that the Preview MCP endpoint is also enabled in the same Features page
- **If TOOL_TYPE is `copilot`:**
  - For project-scoped configuration, ensure the `.mcp.json` file was created successfully
  - For global configuration, check permissions on the `~/.copilot/` directory
- **If TOOL_TYPE is `claude`:**
  - Ensure the `claude` CLI is installed and available in their PATH
  - If the command fails, check that `npx` and `npm` are installed
  - After running the command, they must restart Claude Code for the changes to take effect (remind them: "Remember to **use `claude --continue` to resume the session** without losing context")
  - They can verify the installation with `claude mcp list`
  - If the MCP proxy version seems outdated or behaves unexpectedly, clear the npx cache and retry:
    ```
    npx clear-npx-cache
    ```
  - To validate authentication independently, run:
    ```
    npx -y @microsoft/dataverse@latest mcp "{USER_URL}" --validate
    ```
    This checks credentials and prints error details if issues are found.
- **If TOOL_TYPE is `codex`:**
  - The Dataverse MCP tools load only on a Codex **restart** after `~/.codex/config.toml` is written — the session that wrote the config cannot see them. Do not treat their absence in the current session as a failure or build a workaround proxy.
  - If `--validate` returns **403 Forbidden** on the GA endpoint, the client isn't allowlisted yet — run `dataverse mcp allow {MCP_CLIENT_ID}` (Step 7, Method A), then re-validate.
  - Confirm the server entry exists: look for `[mcp_servers.{SERVER_NAME}]` in `~/.codex/config.toml` (global) or `.codex/config.toml` (project).
  - If `npx` can't be found when Codex launches the server, ensure Node.js 18+ is on PATH; on Windows the proxy command may need `cmd /c` wrapping (see Step 5).

---

## Reading `--validate` output

`npx @microsoft/dataverse mcp {DATAVERSE_URL} --validate` exercises two Dataverse MCP endpoints with a fresh authentication handshake and reports detailed errors (auth, allowlist, consent, endpoint reachability):

- **GA / Production endpoint** — `{DATAVERSE_URL}/api/mcp`. This is the one the plugin actually uses at runtime.
- **Preview endpoint** — `{DATAVERSE_URL}/api/mcp_preview`. Opt-in per environment; not used by the plugin.

How to interpret the results:

- **Look at the GA / Production endpoint (`/api/mcp`) result first.** If this passes, MCP will work for normal plugin usage regardless of what the Preview endpoint reports.
- **A `403 Forbidden` on the Preview endpoint (`/api/mcp_preview`) is expected for most environments.** Preview is opt-in per environment; if your environment hasn''t enabled it, the Preview check will always fail. This does not indicate a broken setup.
- **Ignore the overall exit code and the `Partial success` warning in this case.** The validator returns exit code `1` (failure) unless BOTH `/api/mcp` and `/api/mcp_preview` pass. Because most environments don''t enable the Preview endpoint, `--validate` will exit `1` even when MCP is fully functional via the GA endpoint. Focus on per-endpoint results, not the aggregate status.
- **If the GA endpoint (`/api/mcp`) fails:** that''s the real signal to investigate — auth, tenant consent, environment allowlist, or endpoint reachability.

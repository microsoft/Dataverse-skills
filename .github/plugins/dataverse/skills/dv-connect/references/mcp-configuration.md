# MCP Server Configuration Reference

Detailed instructions for configuring the Dataverse MCP server for GitHub Copilot or Claude Code.

The environment URL should already be known from the `dv-connect` flow (stored in `DATAVERSE_URL` in `.env`). If it's not set, go back to Step 2 of the `dv-connect` skill to discover and select the environment first.

The parameters for the MCP server should be determined from context or environment variables where possible, and interactive prompts should only be used when it cannot be done.

---

## 0. Determine which tool to configure

Determine whether to configure MCP for GitHub Copilot or for Claude Code:
- If explicitly mentioned in prompt, use that.
- Otherwise, determine which tool the user is running from the context.
- Only if choosing based on the context is impossible, ask the user:

> Which tool would you like to configure the Dataverse MCP server for?
> 1. **GitHub Copilot**
> 2. **Claude**

Based on the result, set the `TOOL_TYPE` variable to either `copilot` or `claude`. Store this for use in all subsequent steps.

Set the `MCP_CLIENT_ID` variable in `.env` based on the tool choice:
- If `copilot`: `MCP_CLIENT_ID` = `aebc6443-996d-45c2-90f0-388ff96faa56`
- If `claude`: `MCP_CLIENT_ID` = `0c412cc3-0dd6-449b-987f-05b053db9457`
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
- **Project**: `.mcp/copilot/mcp.json` (relative to the current working directory)

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

1. If `CONFIG_PATH` is for a **project-scoped** configuration (`.mcp/copilot/mcp.json`), ensure the directory exists first:
   ```bash
   mkdir -p .mcp/copilot
   ```

2. Read the existing configuration file at `CONFIG_PATH`, or create a new empty config if it doesn't exist:
   ```json
   {}
   ```

3. Determine which top-level key to use:
   - If the config already has `"servers"`, use that
   - Otherwise, use `"mcpServers"`

4. Add or update the server entry:
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

5. Write the updated configuration back to `CONFIG_PATH` with proper JSON formatting (2-space indentation).

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

Construct the command based on `CLAUDE_SCOPE` and whether the user chose GA or Preview endpoint:

```
claude mcp add --scope {CLAUDE_SCOPE} {SERVER_NAME} -t stdio -- npx -y @microsoft/dataverse@latest mcp "{USER_URL}" {ENDPOINT_FLAG}
```

When running on Windows without WSL, wrap the `npx` call into `cmd //c` and omit the quotes around the URL:

```
claude mcp add --scope {CLAUDE_SCOPE} {SERVER_NAME} -t stdio -- cmd //c "npx -y @microsoft/dataverse@latest mcp {USER_URL} {ENDPOINT_FLAG}"
```

Where:
- `{CLAUDE_SCOPE}` is `user`, `project`, or `local` (from step 1)
- `{SERVER_NAME}` is the generated server name (e.g., `dataverse-orgbc9a965c`)
- `{USER_URL}` is the base environment URL (e.g., `https://orgbc9a965c.crm10.dynamics.com`)
- `{ENDPOINT_FLAG}` is `--preview` if the user chose Preview endpoint in step 4, otherwise omit this flag

**Example commands:**
- GA endpoint with user scope: `claude mcp add --scope user dataverse-orgbc9a965c -t stdio -- npx -y @microsoft/dataverse@latest mcp "https://orgbc9a965c.crm10.dynamics.com"`
- Preview endpoint with project scope: `claude mcp add --scope project dataverse-orgbc9a965c -t stdio -- npx -y @microsoft/dataverse@latest mcp "https://orgbc9a965c.crm10.dynamics.com" --preview`
- GA endpoint on Windows with project scope: `claude mcp add --scope project dataverse-orgbc9a965c -t stdio -- cmd //c "npx -y @microsoft/dataverse@latest mcp https://orgbc9a965c.crm10.dynamics.com"`

Store this command as `CLAUDE_COMMAND` for use in step 8.

---

## 6. Ensure tenant-level admin consent (one-time per tenant)

The MCP client app registration must be granted admin consent on the Azure AD tenant. This is a **one-time** action per tenant — once done, it applies to all Dataverse environments in that tenant. It **requires an Azure AD Global Admin or Privileged Role Admin**.

List out the parameters chosen in previous steps:
- Tool type (Copilot or Claude) from step 0
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

Present the two methods (PPAC portal is recommended for non-developers):

> **Method A: Power Platform Admin Center (recommended — no Azure AD admin needed)**
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
>
> **Method B: Programmatic (via script)**
>
> Run `scripts/enable-mcp-client.py` to add the client ID to the allowed list via the Dataverse API.

If the user completed Method A, attempt to run `scripts/enable-mcp-client.py` anyway to verify. If it reports the client is already enabled, continue. Do not ask for user confirmation.

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

---

## 9. Troubleshooting

If something goes wrong, help the user check:

- The URL format is correct (`https://<org>.<region>.dynamics.com`)
- They have access to the Dataverse environment
- The environment URL matches what's shown in the Power Platform Admin Center
- **Tenant-level admin consent** has been granted for the MCP client app. This is a one-time per-tenant action requiring an Azure AD admin. Without it, authentication succeeds but the app is denied access. Use the admin consent URL from step 6.
- **Org-level allowed clients** — the MCP client ID has been added to the environment's allowed list. To check or fix this:
  1. Go to [Power Platform Admin Center](https://admin.powerplatform.microsoft.com/) > Environments > your environment > Settings > Product > Features
  2. Verify **MCP Server** is toggled **On**
  3. Verify the MCP Client ID appears under **Allowed clients**
- If using the Preview endpoint, verify that the Preview MCP endpoint is also enabled in the same Features page
- **If TOOL_TYPE is `copilot`:**
  - For project-scoped configuration, ensure the `.mcp/copilot/mcp.json` file was created successfully
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

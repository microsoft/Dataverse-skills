<!-- mcp-name: com.microsoft/dataverse -->

# Microsoft Dataverse MCP Server

Query, create, and manage Microsoft Dataverse tables, records, and solutions from AI agents.

This folder is the public home of the `com.microsoft/dataverse` entry in the [MCP Registry](https://registry.modelcontextprotocol.io). The server ships as the [`@microsoft/dataverse`](https://www.npmjs.com/package/@microsoft/dataverse) npm package and runs locally as a stdio MCP server:

```bash
npx -y @microsoft/dataverse mcp https://yourorg.crm.dynamics.com
```

The local server signs you in to your Dataverse environment and connects your MCP client to the environment's Dataverse MCP endpoint. For the tools it exposes, see [Dataverse MCP server](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp).

## Prerequisites

- **Node.js 18 or later** (for `npx`).
- **Dataverse MCP server enabled** for the environment. See [Configure the Dataverse MCP server](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-other-clients).
- **Tenant admin consent**, granted once per tenant by an Azure tenant administrator:
  `https://login.microsoftonline.com/{tenant-id}/adminconsent?client_id=0c412cc3-0dd6-449b-987f-05b053db9457`
- **Client allowed in the environment.** The environment must allow the Dataverse CLI client (app ID `0c412cc3-0dd6-449b-987f-05b053db9457`). A user with Environment Admin or System Administrator rights can run the following command. It uses the active Dataverse CLI auth profile (`dataverse auth create`):

  ```bash
  npx -y @microsoft/dataverse mcp allow 0c412cc3-0dd6-449b-987f-05b053db9457
  ```

  Or add the client in the Power Platform admin center as described in [Configure the Dataverse MCP server](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-other-clients).

## Install from an MCP registry

If your MCP client lists servers from the MCP Registry, search for **Microsoft Dataverse**, install it, and enter your environment URL (for example, `https://yourorg.crm.dynamics.com`) when prompted. The first start opens a browser sign-in; the token is cached for later sessions.

## Configure manually

Replace `https://yourorg.crm.dynamics.com` with your environment URL.

**Generic `mcpServers` configuration** (Claude Desktop, Cursor, and similar clients):

```json
{
  "mcpServers": {
    "dataverse": {
      "command": "npx",
      "args": ["-y", "@microsoft/dataverse", "mcp", "https://yourorg.crm.dynamics.com"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`), prompting for the URL:

```json
{
  "inputs": [
    {
      "id": "dataverse-url",
      "type": "promptString",
      "description": "Dataverse environment URL, e.g. https://yourorg.crm.dynamics.com"
    }
  ],
  "servers": {
    "dataverse": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@microsoft/dataverse", "mcp", "${input:dataverse-url}"]
    }
  }
}
```

**GitHub Copilot CLI** (`~/.copilot/mcp-config.json`):

```json
{
  "mcpServers": {
    "dataverse": {
      "type": "local",
      "command": "npx",
      "args": ["-y", "@microsoft/dataverse", "mcp", "https://yourorg.crm.dynamics.com"],
      "tools": ["*"]
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add dataverse -t stdio -- npx -y @microsoft/dataverse mcp https://yourorg.crm.dynamics.com
```

### Options

| Option | Description |
| --- | --- |
| `--preview` | Use the preview endpoint (`/api/mcp_preview`) for [preview tools](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-preview-tools). |
| `--validate` | Check authentication, MCP enablement, and the client allowlist without starting the server. |
| `--log-level <level>` | Set logging verbosity (`Trace`, `Debug`, `Information`, `Warning`, `Error`, `Critical`). |
| `--log-file` | Write logs to a file in the temp directory. |

## Troubleshoot

Run validation first. It reports which prerequisite is missing:

```bash
npx -y @microsoft/dataverse mcp https://yourorg.crm.dynamics.com --validate
```

To turn off the Dataverse MCP server for an environment, see [Disable the Dataverse MCP server](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-disable).

## Relationship to the Dataverse skills plugin

The [Dataverse skills plugin](../README.md) in this repository does not register this server automatically. Its `dv-connect` skill signs you in and registers a `dataverse-<orgname>` MCP server for your agent. Use either the plugin or the configuration on this page; you don't need both.

## Support

Report issues in this repository's [issue tracker](https://github.com/microsoft/Dataverse-skills/issues). For security issues, see [SECURITY.md](../SECURITY.md).

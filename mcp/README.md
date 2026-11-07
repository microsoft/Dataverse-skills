<!-- mcp-name: com.microsoft/dataverse -->

# Microsoft Dataverse MCP Server

Connect AI agents to Microsoft Dataverse to query, create, and manage
tables, records, and solutions. The local stdio MCP server is distributed
through the `@microsoft/dataverse` npm package.

Before setup, review the [Microsoft Learn instructions for connecting with
the local proxy](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp-other-clients#connect-using-the-local-proxy)
for prerequisites, authentication, and client configuration.

To start the proxy, replace the example URL with your Dataverse environment
URL and run:

```bash
npx -y @microsoft/dataverse mcp https://yourorg.crm.dynamics.com
```

Sign in when prompted. Once connected, try asking your agent: "List the
tables in my Dataverse environment."

- [Dataverse MCP overview and tools](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-mcp)
- [Official MCP Registry listing](https://registry.modelcontextprotocol.io/?q=com.microsoft%2Fdataverse)
- [Dataverse skills plugin](../README.md)

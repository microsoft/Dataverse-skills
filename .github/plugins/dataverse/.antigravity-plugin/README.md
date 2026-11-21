# Microsoft Dataverse

Build, query, and manage [Microsoft Dataverse](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-intro)
and linked Dynamics 365 Finance and Operations environments in natural language.
The plugin teaches Antigravity to use the Dataverse MCP server, the Dataverse CLI,
the Dataverse Python SDK, and the Power Platform CLI, so you can design data
models, work with records, answer business questions, and ship solutions.

## Prerequisites

- A Dataverse environment (Power Apps, Dynamics 365, or Power Platform plans, or the
  free [Power Apps Developer Plan](https://learn.microsoft.com/en-us/power-platform/developer/plan))
  and an account with access to it.
- Node.js, which runs the bundled Dataverse MCP server through `npx`.
- Python 3.10 or later for scripted and bulk operations. The `dv-connect` skill
  installs the remaining tools it needs, such as the Dataverse CLI and Python SDK.
- Optional: the Power Platform CLI (`pac`) for solution lifecycle, administration,
  and Finance and Operations X++ work.

## Setup

1. Install the plugin. It starts **disabled** until its MCP server is configured.
2. Open the plugin settings (`/plugin` in the CLI, or **Customizations > Plugins**
   in the app) and enter your **Dataverse environment URL**, for example
   `https://contoso.crm.dynamics.com`, then enable the plugin.
3. Ask: *"Connect to Dataverse"*. The `dv-connect` skill checks the tools, signs
   you in, and verifies the environment.

Sign-in happens in your browser with your own account; the plugin cannot exceed
your Dataverse permissions.

## What's included

- **Skills**: `dv-overview`, `dv-connect`, `dv-data`, `dv-query`, `dv-metadata`,
  `dv-solution`, `dv-security`, `dv-admin`, `erp-xpp`, and `erp-sql`.
- **MCP server**: the Dataverse MCP server (`@microsoft/dataverse`), pinned to a
  tested version and scoped to this plugin, so it is removed when the plugin is.

## Try these prompts

- *"Show me my open deals over $100K closing this quarter"*
- *"Create a customer feedback table with name, rating, and comment columns"*
- *"Import this CSV into the contacts table"*
- *"Export my solution and commit it to source control"*

## Learn more

- [Source, issues, and full install guide](https://github.com/microsoft/Dataverse-skills)
- [Safety and guardrails](https://github.com/microsoft/Dataverse-skills/blob/main/docs/safety-and-guardrails.md)
- [Security policy](https://github.com/microsoft/Dataverse-skills/blob/main/SECURITY.md)

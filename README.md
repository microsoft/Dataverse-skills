# Dataverse Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Build, query, and manage [Microsoft Dataverse](https://learn.microsoft.com/en-us/power-apps/maker/data-platform/data-platform-intro) through natural language. The plugin teaches AI coding agents to drive the Dataverse MCP server, Dataverse CLI, Python SDK, and PAC CLI — for everything from designing data models and answering CRM questions to deploying solutions across environments.

| Skill | What it does |
|---|---|
| **dv-connect** | One-time setup that installs the Dataverse CLI, Python SDK, and PAC CLI; authenticates against your Dataverse environment; and registers the Dataverse MCP server with your agent. |
| **dv-query** | Reads, filters, paginates, and aggregates Dataverse records. Handles natural-language questions like *"show me my open deals"*, multi-page result sets, and pandas DataFrame loading for notebook analysis. |
| **dv-data** | Single-record CRUD plus bulk import — CSV loads, multi-table imports with foreign-key dependencies, upsert by alternate key, and AI-generated sample data. |
| **dv-metadata** | Authors and edits the Dataverse data model: tables, columns, relationships, forms, and views. |
| **dv-solution** | Manages solution lifecycle — create, export, import, promote across environments, and validate deployments. |
| **dv-admin** | Environment-level administration: bulk delete, retention/archival, organization settings, OrgDB settings, recycle bin, audit, and the allowlisted PPAC toggles. |
| **dv-security** | Assigns security roles, manages user access, adds application users, configures business units, and handles admin self-elevation. |
| **dv-overview** | Cross-cutting rules and tool routing; loaded before any other skill to direct each request to the right specialist. |

Browse [`.github/plugins/dataverse/skills/`](.github/plugins/dataverse/skills/) for the full source.

## Prerequisites

A Microsoft Dataverse environment, available through Power Apps, Dynamics 365, or Power Platform plans, or via the free [Power Apps Developer Plan](https://learn.microsoft.com/en-us/power-platform/developer/plan).

## Install

### GitHub Copilot

```bash
/plugin install dataverse@awesome-copilot
```

### Claude Code

```bash
/plugin install dataverse@claude-plugins-official
```

### Codex

**Codex app**

1. Open **Plugins → Add marketplace**.
2. Set **Source** to `https://github.com/microsoft/Dataverse-skills.git`.
3. Leave **Git ref** and **Sparse paths** empty.
4. Click **Add marketplace**, then browse the **dataverse-skills** marketplace, open `dataverse`, and select **Install plugin**.

**Codex CLI**

Add the marketplace (first time only), then browse `/plugins` and install `dataverse`:

```bash
codex plugin marketplace add microsoft/Dataverse-skills
```

Update to the latest release:

```bash
codex plugin marketplace upgrade dataverse-skills
```

### Cursor

Install from the [Cursor Marketplace](https://cursor.com/marketplace/microsoft-dataverse) — open the listing and click **Add**, or inside Cursor go to **Settings → Plugins**, search for **Dataverse**, and install **Microsoft Dataverse**.

**Install from source (development)**

```bash
git clone https://github.com/microsoft/Dataverse-skills.git
```

Then copy the plugin directory into your Cursor local plugins folder:

- **Windows:** copy `Dataverse-skills\.github\plugins\dataverse` to `%USERPROFILE%\.cursor\plugins\local\dataverse\`
- **macOS / Linux:** copy `Dataverse-skills/.github/plugins/dataverse` to `~/.cursor/plugins/local/dataverse/`

Reload the Cursor window (Ctrl+Shift+P → "Developer: Reload Window") to load the `dv-*` skills.

## Verify the install

After installation, ask your agent:

> "Connect to Dataverse"

The `dv-connect` skill walks through tool checks, authentication, and MCP registration. When it finishes, you should see a `dataverse-<orgname>` MCP server registered with your agent, and `pac auth list` should show your active environment.

## Try these prompts

After the connect flow finishes, describe what you want — the plugin picks MCP, the Dataverse CLI, the Python SDK, or PAC CLI for you.

- *"Show me my open deals over $100K closing this quarter"*
- *"Import this CSV into the contacts table"*
- *"Create a customer feedback table with name, rating, and comment columns"*
- *"Pull the schema and pack it into a solution"*
- *"Bulk delete activities older than 2024"*
- *"Add a teammate to the sales team on the dev environment"*

## Safety & Security

The plugin is designed around a least-privilege model — it cannot exceed the permissions of the authenticated user. Key safeguards:

- **MCP authorization** — MCP access requires developer auth, tenant admin consent, and per-environment allowlisting; other plugin tools (SDK, PAC CLI) authenticate directly.
- **Security role enforcement** — every API call is authorized server-side by Dataverse; the plugin cannot bypass or escalate permissions.
- **Application-level telemetry only** — outbound Dataverse requests may carry application metadata (plugin / version / skill / agent labels) so server-side dashboards can attribute traffic. No prompts, tool arguments, or record data are transmitted.
- **Token security** — credentials are stored in your OS native credential store or held in memory only; never passed to external services.

For the full safety model — including confirmation flows, logging, irreversible operation handling, and planned improvements — see [docs/safety-and-guardrails.md](docs/safety-and-guardrails.md).

## Contributing

We welcome contributions — new skills, improvements to existing ones, and bug fixes. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines and local-development instructions.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.

## License

This project is licensed under the [MIT License](LICENSE).

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

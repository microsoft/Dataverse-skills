# Microsoft Dataverse

Official Microsoft Dataverse skills for AI coding agents, published by Microsoft
from [microsoft/Dataverse-skills](https://github.com/microsoft/Dataverse-skills).

![Microsoft Dataverse](assets/dataverse-logo.svg)

Build and manage Dataverse solutions using natural language: connect to an
environment, explore and query data, import records, design tables and
relationships, configure security, and manage solution lifecycles. Linked
Dynamics 365 Finance and Operations workflows are also included.

## Requirements

- An Antigravity installation with plugin support.
- Access to a Microsoft Dataverse environment. The
  [Power Apps Developer Plan](https://learn.microsoft.com/en-us/power-platform/developer/plan)
  provides a development environment.
- Appropriate permissions for the operation you request. Schema authoring
  generally requires System Customizer; security and environment administration
  may require additional privileges.
- During setup, `dv-connect` checks the required Dataverse CLI, Python SDK, and
  Power Platform CLI tools and guides installation and authentication. These
  tools are not bundled in the plugin.

## Connect

Ask **Connect to Dataverse**, or invoke `/dv-connect`. Confirm the target
environment before operations run. The connect workflow authenticates and
registers an environment-specific MCP server through `agy mcp add` when needed;
this plugin does not start a bundled Antigravity MCP server automatically.
MCP access also requires tenant consent and environment allowlisting.

Restart Antigravity after MCP registration, then verify with `agy mcp list`.
Use `/skills` to inspect the installed skills.

## Included Skills

| Skill | Coverage |
|---|---|
| `dv-overview` | Tool routing and cross-cutting guardrails |
| `dv-connect` | Authentication, prerequisites, and MCP registration |
| `dv-query` | Queries, aggregates, and notebook analysis |
| `dv-data` | Record CRUD, CSV import, upsert, and sample data |
| `dv-metadata` | Tables, columns, relationships, forms, and views |
| `dv-solution` | Solution packaging and deployment |
| `dv-admin` | Environment settings, audit, retention, and administration |
| `dv-security` | Users, roles, teams, and access |
| `erp-xpp` | Finance and Operations X++ development lifecycle |
| `erp-sql` | Approved, temporary Reader-only developer SQL access |

## Example Requests

- Show the custom tables in my environment.
- Create a support ticket data model in my solution.
- Profile my data and summarize data quality issues.

## Safety and Support

Dataverse enforces the authenticated user's permissions. Review proposed
changes, especially bulk deletes, security updates, and deployments. Authentication
credentials must not be shared in chat or committed to source control.

See the [safety model](https://github.com/microsoft/Dataverse-skills/blob/main/docs/safety-and-guardrails.md),
[support guidance](https://github.com/microsoft/Dataverse-skills/blob/main/SUPPORT.md),
and [security reporting policy](https://github.com/microsoft/Dataverse-skills/blob/main/SECURITY.md).

## License and Branding

Source code is licensed under the
[MIT License](https://github.com/microsoft/Dataverse-skills/blob/main/LICENSE).
Microsoft trademarks and the Dataverse logo are subject to
[Microsoft's Trademark and Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
The source license does not grant trademark rights or imply sponsorship of
modified versions.
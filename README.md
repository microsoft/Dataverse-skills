# Dataverse Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Agent skills and MCP configuration for [Microsoft Dataverse](https://aka.ms/DVinWorkIQLearnMore) — works with Claude Code and GitHub Copilot. These skills teach AI agents how to build and manage Dataverse solutions using natural language.

Browse the [`.github/plugins/dataverse/skills/`](.github/plugins/dataverse/skills/) folder for the full catalog.

## Prerequisites

- **Microsoft Dataverse** environment (included with Power Apps, Dynamics 365, or Power Platform)
- **Python 3.10+** and **Node.js 18+**

## Getting Started

### Claude Code

```bash
/plugin marketplace add microsoft/Dataverse-skills
/plugin install dataverse@dataverse-skills
```

### GitHub Copilot

```bash
copilot plugin marketplace add microsoft/Dataverse-skills
copilot plugin install dataverse@dataverse-skills
```

Or via [awesome-copilot](https://github.com/github/awesome-copilot):

```bash
copilot plugin install dataverse@awesome-copilot
```

## What's Included

- **5 skills** covering connection setup, metadata authoring, solution management, Python SDK data operations, and tool routing
- **MCP server** configuration for Dataverse Web API access
- **Scripts** for authentication and MCP client enablement
- **Templates** for CLAUDE.md project files

## Local Development

Clone the repository first:

```bash
git clone https://github.com/microsoft/Dataverse-skills.git
```

### Testing with Claude Code

Test the plugin locally without installing from a marketplace:

```bash
# 1. Create and cd into a fresh test folder
mkdir my-test-project
cd my-test-project

# 2. Launch Claude Code with the plugin loaded from your local clone
claude --plugin-dir "<path/to/repo>/.github/plugins/dataverse"

# 3. Start with a natural language prompt, e.g.:
#    "Create a support ticket table with customer and agent lookups"
```

The `--plugin-dir` path **must be in double quotes** if it contains spaces or special characters. Use the absolute path to the plugin directory in your local clone of this repo.

### Testing with GitHub Copilot CLI

To register the local plugin marketplace from the cloned repository and install the plugin:

```bash
copilot plugin marketplace add <path/to/repo>/Dataverse-skills
copilot plugin install dataverse@dataverse-skills
```

To reinstall the plugin after pulling or making local changes:

```bash
copilot plugin uninstall dataverse@dataverse-skills
copilot plugin install dataverse@dataverse-skills
```

To install the local version directly without marketplace registration:

```bash
copilot plugin install <path/to/repo>/.github/plugins/dataverse
```

## Safety & Security

The plugin is designed around a least-privilege model — it cannot exceed the permissions of the authenticated user. Key safeguards:

- **MCP authorization** — MCP access requires developer auth, tenant admin consent, and per-environment allowlisting; other plugin tools (SDK, PAC CLI) authenticate directly
- **Security role enforcement** — every API call is authorized server-side by Dataverse; the plugin cannot bypass or escalate permissions
- **No plugin telemetry** — the plugin does not collect or transmit usage analytics; data flows only to Dataverse within your tenant and to the AI host (Claude or Copilot) as part of normal operation
- **Token security** — credentials are stored in your OS native credential store or held in memory only; never passed to external services

For the full safety model — including confirmation flows, logging, irreversible operation handling, and planned improvements — see [docs/safety-and-guardrails.md](docs/safety-and-guardrails.md).

## Contributing

We welcome contributions — new skills, improvements to existing ones, and bug fixes. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

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

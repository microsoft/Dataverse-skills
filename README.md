# Dataverse-skills

Agent skills and MCP configuration for Microsoft Dataverse — works with Claude Code and GitHub Copilot.

## Install

### Claude Code

```
/plugin marketplace add microsoft/Dataverse-skills
/plugin install dataverse@dataverse-skills
```

### GitHub Copilot

```
copilot plugin marketplace add microsoft/Dataverse-skills
copilot plugin install dataverse@microsoft/Dataverse-skills
```

Once the repo is publicly listed in [awesome-copilot](https://github.com/github/awesome-copilot), install simplifies to:

```
copilot plugin install dataverse@awesome-copilot
```

## What's included

- **7 skills** covering machine setup, workspace init, metadata authoring, solution management, Python SDK, MCP configuration, and demo data
- **MCP server** configuration for Dataverse Web API access
- **Scripts** for authentication and MCP client enablement
- **Templates** for CLAUDE.md project files

## Local development
### Claude Code

Test the plugin locally without installing from a marketplace:

```bash
# 1. Create and cd into a fresh test folder
mkdir my-test-project
cd my-test-project

# 2. Launch Claude Code with the plugin loaded from your local clone
claude --plugin-dir "c:/repos/Dataverse-Skills/.github/plugins/dataverse"

# 3. Start with a natural language prompt, e.g.:
#    "Create a support ticket table with customer and agent lookups"
```

The `--plugin-dir` path **must be in double quotes** if it contains spaces or special characters. Use the absolute path to the plugin directory in your local clone of this repo.

### GitHub Copilot CLI

#### Registering the local marketplace

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

#### Installing the local plugin directly

To install the local version of the plugin directly without marketplace registration:

```bash
copilot plugin install <path/to/repo>/.github/plugins/dataverse
```

To uninstall it later (for reinstalling an updated version):

```bash
copilot plugin uninstall dataverse
```

## Contributing

This project welcomes contributions and suggestions. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting security vulnerabilities.

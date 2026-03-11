# Dataverse-skills

Agent skills and MCP configuration for Microsoft Dataverse — works with Claude Code and GitHub Copilot.

## Install

### Claude Code

```
/plugin marketplace add microsoft/Dataverse-skills
/plugin install dataverse@dataverse-skills
```

### GitHub Copilot

Available via [awesome-copilot](https://github.com/github/awesome-copilot) as the `dataverse` plugin.

## What's included

- **10 skills** covering environment setup, metadata authoring, solution management, security, C# plugins, Python SDK, MCP configuration, CI/CD, and demo data
- **MCP server** configuration for Dataverse Web API access
- **Scripts** for authentication, role assignment, and post-deployment validation
- **Templates** for CLAUDE.md project files and CI/CD workflows

## Local development

Test the plugin locally without installing from a marketplace:

```bash
claude --plugin-dir ./.github/plugins/dataverse
```

## Contributing

This project welcomes contributions and suggestions. See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting security vulnerabilities.

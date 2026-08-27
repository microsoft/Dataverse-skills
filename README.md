# Dataverse Skills

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Dataverse Skills is the open-source home of the Microsoft Dataverse plugin for AI coding agents. The plugin lets you describe a Dataverse development or administration outcome in natural language, then gives the agent task-specific guidance for selecting and using the appropriate tools. This reduces the tool-specific syntax you need to include in prompts while preserving confirmation steps and guardrails for changes to environments, solutions, data, and security.

## Project design

The plugin starts with an overview skill that provides shared Dataverse context and routes each request to one or more specialized skills. Those skills guide the agent to the tool that best fits the operation and data volume, including the Dataverse MCP server, Dataverse CLI, Dataverse SDK for Python, Power Platform CLI, and Dataverse Web API.

The project grows through new skills, improvements to existing guidance, bug reports, and documentation updates. See [CONTRIBUTING.md](CONTRIBUTING.md) for the different ways to contribute and instructions for testing changes locally.


## Learn more

Learn more about the Dataverse plugin for AI coding agents:

- [Microsoft Dataverse plugin for AI coding agents (preview)](https://learn.microsoft.com/power-apps/developer/data-platform/agents-plugin/)
- [Microsoft Dataverse plugin for AI coding agents reference (preview)](https://learn.microsoft.com/power-apps/developer/data-platform/agents-plugin/reference)

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

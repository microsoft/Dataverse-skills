# Contributing to Dataverse Skills

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## How to Contribute

### Reporting Issues

- Use the [GitHub issue tracker](https://github.com/microsoft/Dataverse-skills/issues) to report bugs or suggest features
- Search existing issues before creating new ones
- Include as much detail as possible: environment, steps to reproduce, expected vs actual behavior

### Contributing Skills

We welcome new skill contributions! To add a new skill:

1. **Fork the repository** and create a feature branch from `main`
2. **Create a new skill folder** under `.github/plugins/dataverse/skills/` following the naming convention: `your-skill-name/`
3. **Create a `SKILL.md` file** with the required frontmatter and instructions (see existing skills as reference)
4. **Follow the skill structure**:
   - YAML frontmatter with `name`, `description`, and `metadata`
   - Clear step-by-step instructions
   - SDK-first approach: use `PowerPlatform-Dataverse-Client` for all supported operations, raw Web API only for gaps
   - Output formatting examples
5. **Test locally** using `claude --plugin-dir` (see [Local Development](#local-development) below)
6. **Submit a pull request** with a clear description of what the skill does and why it's useful

### Improving Existing Skills

- Fix bugs or edge cases in existing skill logic
- Improve SDK usage patterns or query efficiency
- Add additional edge case handling
- Enhance MCP configuration or auth flows

### Documentation

- Fix typos or unclear instructions
- Add usage examples
- Improve README or skill documentation

## Pull Request Process

1. Update relevant documentation if your change affects usage
2. Ensure your skill follows the existing formatting patterns
3. Test your changes locally with `claude --plugin-dir` (see [Local Development](#local-development) below)
4. Your PR will be reviewed by maintainers
5. Once approved, a maintainer will merge your contribution

## Local Development

Clone the repository:

```bash
git clone https://github.com/microsoft/Dataverse-skills.git
```

Then run the plugin against your local clone with the agent you're testing. The agents differ in how they load plugins from a local path: Claude Code reads the plugin directory on every launch, so edits are picked up automatically. Copilot copies the plugin into its store at install time, so refreshing after edits requires uninstall + reinstall.

### Testing with GitHub Copilot CLI

Install directly from your local plugin directory:

```bash
copilot plugin install <path/to/repo>/.github/plugins/dataverse
```

After making local changes (or pulling), uninstall and reinstall to refresh Copilot's copy:

```bash
copilot plugin uninstall dataverse@dataverse-skills
copilot plugin install <path/to/repo>/.github/plugins/dataverse
```

### Testing with Claude Code

Launch Claude Code with the plugin loaded from your local clone — no install or uninstall needed; edits take effect on the next launch:

```bash
# In a fresh test folder
mkdir my-test-project && cd my-test-project

claude --plugin-dir "<path/to/repo>/.github/plugins/dataverse"
```

Quote the path if it contains spaces or special characters; use an absolute path.

## Legal

This project is licensed under the [MIT License](LICENSE).

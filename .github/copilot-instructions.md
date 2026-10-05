# Gemini CLI Gallery Extension PR Guidelines

When asked to prepare this repository for the Gemini CLI Extensions gallery (https://geminicli.com/extensions/) or to submit a PR for it:

## 1. Required Repository Setup Checklist

Before creating or updating files, verify the following:
- [ ] `gemini-extension.json` exists in the absolute root directory of the repository and contains valid JSON.
- [ ] The `gemini-cli-extension` topic tag is recommended for the GitHub repository settings.

## 2. File Verification & Creation: `gemini-extension.json`

Inspect `gemini-extension.json` at the repository root. If it is missing, create it. Ensure it contains valid JSON with at least these required fields:

```json
{
  "name": "<repository-or-extension-name>",
  "version": "<semver-e.g.-1.0.0>",
  "description": "<concise-summary-of-what-the-extension-does>"
}
```

- **Name:** Lowercase alphanumeric string with hyphens if necessary; it should match the plugin module identifier.
- **Description:** A 1-2 sentence overview for the extension's listing on geminicli.com.
- **Version:** A valid Semantic Versioning string (e.g., `1.0.0`).

## 3. Pull Request Requirements

When opening a Pull Request:

1. **Title:** `feat: add gemini-extension.json manifest for Gemini CLI Extensions gallery`
2. **Description:** Mention that this PR adds the required root manifest `gemini-extension.json` for indexing on `geminicli.com/extensions`. Remind the repository owner to manually add the `gemini-cli-extension` topic tag to the GitHub repository **About** section on GitHub.com, since topic tags cannot be set through a file PR.

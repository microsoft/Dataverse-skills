# CLAUDE.md — Dataverse Skills Plugin

## What This Repo Is

This repo ships a plugin for Claude Code and GitHub Copilot that provides AI-assisted Dataverse / Power Platform development. The plugin consists of skill files (`SKILL.md`) that teach the agent how to use the Python SDK, PAC CLI, MCP server, and Dataverse Web API.

The plugin is loaded via:
```bash
claude --plugin-dir .github/plugins/dataverse
```

Skill files live under `.github/plugins/dataverse/skills/<skill-name>/SKILL.md`.

---

## Before Committing

Run the static eval suite. It checks every skill file for code correctness, auth pattern compliance, and routing consistency:

```bash
python .github/evals/static_checks.py
```

Exit code 0 = all checks pass. Fix any failures before committing. The checks run in under a second and have no external dependencies.

---

## Skill Authoring Rules

### Python only

All code examples in skill files must be Python. No JavaScript, TypeScript, PowerShell, or shell one-liners that substitute for Python logic.

### Auth pattern

Every standalone Python block that imports from `auth` must use this exact pattern:

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env   # SDK operations
# OR
from auth import get_token, load_env        # Raw Web API only
```

`get_credential()` is for SDK (`DataverseClient`) operations. `get_token()` is only for raw Web API calls (forms, views, `$apply`, N:N `$expand`) that the SDK does not support. Never use `get_token()` in a block containing `DataverseClient(`.

The one exception: Jupyter notebook blocks use `InteractiveBrowserCredential` directly (no `scripts/` directory in a notebook environment). Mark this exception explicitly in prose above the block.

### No stub blocks

Every `python` fenced block must contain at least one executable line. Comment-only blocks (`# POST to ...`) must either be completed or removed. Use a plain (unlabelled) fence for non-executable fragments.

### Skill boundaries

Every skill except `dv-overview` and `dv-connect` must have a `## Skill boundaries` section listing what it does not cover and which skill to use instead. This is the primary routing signal for the agent when it hits an out-of-scope request.

### MCP → SDK → Web API priority

Code examples follow this priority order:
- MCP tools for simple reads and writes (≤10 records, no paging)
- Python SDK (`DataverseClient`) for bulk operations, scripted workflows, and analytics
- Raw Web API (`urllib.request`) only for operations the SDK does not support

Do not add Web API examples for operations the SDK covers.

---

## Testing a Skill Change

```bash
claude --plugin-dir .github/plugins/dataverse
```

Then describe a task that exercises the changed skill in plain English. The agent should route correctly without you naming the skill explicitly.

---

## Commit and PR Conventions

- Prefix commits with `feat:`, `fix:`, `refactor:`, `add:`, or `docs:`
- PR descriptions: lead with the theme of the change, not a per-line changelog
- Run `python .github/evals/static_checks.py` and confirm it passes before opening a PR

## Version Bumping

When a PR changes skill files (`.github/plugins/dataverse/skills/**`), bump the plugin version before merging. Version must be updated in all four fields (across three files):

1. `.github/plugin/marketplace.json` — top-level `metadata.version`
2. `.github/plugin/marketplace.json` — plugin entry `version`
3. `.github/plugins/dataverse/.claude-plugin/plugin.json` — `version`
4. `.github/plugins/dataverse/.github/plugin/plugin.json` — `version`

All four must match. The static eval (`python .github/evals/static_checks.py`) verifies version consistency and will fail if any of the four fields drift.

Run the PR-level bump check to verify the bump level matches the structural changes in your branch:

```bash
python .github/evals/version_bump_check.py
```

It compares your branch to `main` and flags common mistakes — e.g., adding a new skill without a MINOR bump, or removing a skill without a MAJOR bump.

### Semver rules (x.y.z)

**MAJOR (x)** — Breaking changes that require user action:
- Renaming or removing a skill
- Removing or renaming a required section in a skill (e.g., `## Skill boundaries`)
- Changing the auth pattern (e.g., switching from `get_credential` to a new import)
- Changing MCP server configuration structure
- Removing supported tools (SDK, PAC CLI, Web API) from routing

**MINOR (y)** — Backward-compatible additions:
- Adding a new skill
- Adding a new section to an existing skill
- New capabilities (new MCP tool guidance, new SDK patterns, new Web API examples)
- New keywords or metadata fields
- Expanding skill boundaries to cover new scenarios

**PATCH (z)** — Backward-compatible fixes:
- Bug fixes in code examples
- Typo and grammar corrections
- Clarifying prose without changing behavior
- Updating links or references
- Minor refactors that don't change skill routing

**Note:** No need to update the `version` field in the [awesome-copilot marketplace](https://github.com/github/awesome-copilot/blob/main/plugins/external.json). The entry there tracks the default branch of this repo, so version updates propagate automatically. The `version` field in awesome-copilot is cosmetic-only.

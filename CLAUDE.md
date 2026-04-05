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

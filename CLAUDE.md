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

Every standalone Python block that imports from `auth` must use one of these patterns:

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client                       # PREFERRED — SDK with plugin attribution
# OR
from auth import get_plugin_headers, get_token    # Raw Web API WITH skill attribution
# OR
from auth import get_token, load_env              # Raw Web API, no attribution (last resort)
```

`get_client(skill)` is the preferred entry point — it handles auth, environment URL, and plugin attribution (User-Agent tagging) in one call. `get_token()` is only for raw Web API calls that no managed surface covers (e.g., an in-process Python loop issuing many attributed requests in one session) — and for those, prefer `get_plugin_headers(skill, get_token())`, which stamps the same skill attribution the SDK path carries (a bare `get_token()` does not). Forms, views, and settings are ordinary entities served by the SDK (`client.records.*`), not urllib. Never use `get_token()` in a block containing `DataverseClient(`.

The one exception: Jupyter notebook blocks use `InteractiveBrowserCredential` directly (no `scripts/` directory in a notebook environment). Mark this exception explicitly in prose above the block.

### No stub blocks

Every `python` fenced block must contain at least one executable line. Comment-only blocks (`# POST to ...`) must either be completed or removed. Use a plain (unlabelled) fence for non-executable fragments.

### Frontmatter description

Follow Anthropic's published Skills format: one third-person descriptive sentence followed by an inline `Use when ...` clause naming user-intent triggers. The two halves do different jobs — the first describes what the skill does, the second describes what to look for in a request. **Describe the capability domain, not the execution tool** — tool choice belongs to the overview's Tool Capabilities matrix + Hard Rule 2, so a description says what the skill covers (e.g. `record CRUD and bulk operations`), not how it runs (e.g. `via the Python SDK`). Don't enumerate quoted trigger phrases (burns Level 1 tokens on every interaction across all skills) and don't include `Do not use when:` lists. Hard cap: 1024 chars.

Example: `Record-level CRUD and bulk operations — create, update, delete, upsert, CSV import, multi-table foreign-key loads. Use when the user wants to write, modify, seed, or import data records into Dataverse tables.`

### Token budget — Anthropic Skills spec

- **Frontmatter (Level 1, always loaded):** ≤ 200 tokens. Strive for ~100.
- **SKILL.md body (Level 2, loaded on trigger):** ≤ 5,000 tokens.
- **`references/<topic>.md` (Level 3, loaded on demand):** unlimited.

When a skill body grows past ~4,000 tokens, split long content (Python snippets, edge-case tables, deep-dive workflows) into `references/<topic>.md`. The body keeps a Quick Reference + key invariants + a one-line pointer to the reference. Keep references one level deep — body links directly, references don't link to other references.

### Critical safety callout

For skills with destructive or irreversible operations (e.g., bulk delete, role assignment, env settings), surface the most-critical rules in a top-of-file callout block right after the H1, not buried mid-body:

```markdown
> ## ⚠️ Critical safety rules — read first
> 1. <hard-stop rule that's destructive and irreversible>
> 2. <allowlist refusal directive, if any>
> ...
```

The body still contains the full enforcement detail; the callout exists so the rules are visible even if a reader doesn't scroll.

### Anti-hallucination tables

For command-heavy skills (PAC CLI, etc.), include a Wrong/Correct mapping table. Eval data on this plugin showed flag hallucination drop from ~58% to ~2.5% with these tables present. One per command group is enough.

### Skill boundaries

Every skill except `dv-overview` and `dv-connect` must have a `## Skill boundaries` section listing what it does not cover and which skill to use instead. This is the primary routing signal for the agent when it hits an out-of-scope request.

### Which surface to demonstrate — capability-based

Show the surface that fits the operation's shape (mirrors the overview's **Tool Capabilities** matrix + Hard Rule 2 — peers, not a fixed order):
- **MCP tools** — simple reads/writes (<=25 records per call, no paging)
- **Dataverse CLI** (`dataverse data ...`) — headless data-plane CRUD / associate / upload with no Python script, plus the `dataverse api` managed escape hatch
- **Python SDK** (`DataverseClient`) — bulk operations, scripted workflows, and analytics
- **Raw Web API** (`urllib.request`) — last resort. Only when no managed surface (MCP / Dataverse CLI / SDK) covers the operation — e.g. an in-process Python loop issuing many attributed requests in one session. Forms, views, and settings records are ordinary entities: use the SDK (`client.records.*`), not urllib.

Do not add raw Web API examples for operations a managed surface already covers.

**Before writing any `urllib` block, apply this test.** If the operation is record CRUD, a query, an aggregation, an N:N read, or a bound/unbound action, a managed surface already covers it — SDK `client.records.*` / `client.tables.*` for entity work (forms, views, OrgDB settings, recycle-bin config, etc. are all ordinary records), and `dataverse api request` for unbound actions like `PublishXml`. urllib is justified only when you need one attributed HTTP session across many rows inside a single Python process. `dv-query/references/web-api-advanced.md` is the canonical (and effectively only) home for that pattern; new urllib examples anywhere else will be flagged in review.

### Verified failures — mistakes that recur

These bit real edits more than once. Check them before committing.

1. **Never claim "the SDK/MCP can't do entity X" without checking `records.py` first.** The claim is almost always false — `client.records.create/retrieve/update/delete/list` are generic over *any* logical entity name with no blocklist. `systemform`, `savedquery`, `organization`, `settingdefinition`, `organizationsetting`, `recyclebinconfig`, `asyncoperation` are all ordinary records. Only genuine unbound actions (e.g. `PublishXml`) need `dataverse api request`. Grep the SDK source before writing an escape-hatch block to "work around" a limitation that doesn't exist.

2. **`--context` is NOT pre-wrapped in parens.** The CLI adds the outer `(...)` itself. Pass the bare `key=value;...` string:
   ```
   dataverse api request ... --context "app=dataverse-skills/<ver>;skill=<skill>;agent=<agent>"
   ```
   Writing `--context "(app=...)"` double-wraps to `((app=...))` and breaks the telemetry classifier. This is silent — nothing errors, attribution just goes unclassified. Grep any new `--context` for a leading `"(` before committing.

3. **Every `dataverse api` call carries `--context` — reads included.** It's easy to add attribution to writes and forget it on `WhoAmI` / role-query / metadata reads. Unattributed reads still show up in telemetry as anonymous traffic. If the block calls `dataverse api`, it has a `--context`.

4. **SKILL.md bodies are hard-capped at 5,000 tokens (EVAL-BUDGET-02).** `dv-connect`, `dv-metadata`, and `dv-overview` sit at/near the cap — new prose there will fail `static_checks`. Put new detail in `references/<topic>.md` and leave a one-line pointer in the body.

5. **Preflight/role guidance defaults to least privilege.** System Customizer (`prvCreateEntity`) is the floor for schema work — do NOT steer users to System Administrator. Only escalate for genuinely admin-scoped operations (security roles, org settings).

Run `python .github/evals/static_checks.py` after every change; it must stay green.

---

## Testing a Skill Change

```bash
claude --plugin-dir .github/plugins/dataverse
```

Then describe a task that exercises the changed skill in plain English. The agent should route correctly without you naming the skill explicitly.

---

## Commit and PR Conventions

- Prefix commits with `feat:`, `fix:`, `refactor:`, `add:`, or `docs:`. Plain prefix only — no scopes (`feat(skills):` etc.) — the `Validate PR title and body` check rejects them.
- PR descriptions: lead with the theme of the change, not a per-line changelog
- Run `python .github/evals/static_checks.py` and confirm it passes before opening a PR

### Branch protection (enforced)

`main` requires:
- 2 approvals, **both** from `@microsoft/dataverse-skills-maintainers`
- Status checks: `Static skill checks`, `Validate PR title and body`, `CodeQL`, `license/cla`
- Last-push approval (any new commit voids prior approvals)
- Stale-review dismissal on push

Contributors who aren't on the maintainers team need two team members to review. Drive-by approvals from non-maintainers don't count toward the merge requirement.

## Version Bumping

When a PR changes skill files (`.github/plugins/dataverse/skills/**`), bump the plugin version before merging. Version must be updated in all six fields (across five files):

1. `.github/plugin/marketplace.json` — top-level `metadata.version`
2. `.github/plugin/marketplace.json` — plugin entry `version`
3. `.github/plugins/dataverse/.claude-plugin/plugin.json` — `version`
4. `.github/plugins/dataverse/.github/plugin/plugin.json` — `version`
5. `.github/plugins/dataverse/.cursor-plugin/plugin.json` — `version`
6. `.github/plugins/dataverse/.codex-plugin/plugin.json` — `version`

All six must match. The static eval (`python .github/evals/static_checks.py`) verifies version consistency and will fail if any of the six fields drift.

Run the PR-level bump check to verify the bump level matches the structural changes in your branch:

```bash
python .github/evals/version_bump_check.py
```

It compares your branch to `main` and flags common mistakes — e.g., adding a new skill without a MINOR bump, or removing a skill without a MAJOR bump.

### Semver rules (x.y.z)

**MAJOR (x)** — Breaking changes that require user action:
- Renaming or removing a skill
- Removing or renaming a required section in a skill (e.g., `## Skill boundaries`)
- Changing the auth pattern (e.g., switching the SDK auth import in `scripts/auth.py`)
- Changing MCP server configuration structure
- Removing supported tools (SDK, PAC CLI, Web API) from routing

**MINOR (y)** — Backward-compatible additions:
- Adding a new skill
- Adding a new section to an existing skill
- New capabilities (new MCP tool guidance, new SDK patterns, new Web API examples)
- New keywords or metadata fields
- Expanding skill boundaries to cover new scenarios

**PATCH (z)** — Backward-compatible fixes and refactors with no user-visible change:
- Bug fixes in code examples
- Typo and grammar corrections
- Clarifying prose without changing behavior
- Updating links or references
- Refactors that preserve every routing trigger and behavior (e.g., splitting a long body into `references/`, deduplicating tables, rewording a description while preserving the same triggers)

**Note:** No need to update the `version` field in the [awesome-copilot marketplace](https://github.com/github/awesome-copilot/blob/main/plugins/external.json). The entry there tracks the default branch of this repo, so version updates propagate automatically. The `version` field in awesome-copilot is cosmetic-only.

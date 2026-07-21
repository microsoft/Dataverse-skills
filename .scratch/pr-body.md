## What

Aligns the Dataverse skills to the **GA `1.0.0`** Python SDK and de-steers tool routing so MCP, the Dataverse CLI, the Python SDK, and PAC are treated as peer surfaces instead of a fixed hierarchy. Restructures `dv-overview` into load-first context (scope -> hard rules -> tool capabilities -> safe change lifecycle) that no longer duplicates specialist-skill frontmatter.

## Why

- The SDK is GA (`1.0.0`, Production/Stable), but skills still called it "preview / breaking changes possible" and gated features behind beta versions (`b6`/`b8`) that are now always satisfied.
- Prior guidance over-steered toward the Python SDK with hard tool-order mandates; the Dataverse CLI and MCP were under-represented despite being first-class.
- `dv-overview` re-described what specialist skills already declare in frontmatter, and mis-stated some capabilities (e.g. aggregation / N:N as "raw-only" when `client.query.fetchxml()` handles both).

## Key changes

- **GA alignment** - removed preview/breaking-changes notes and all `b6`/`b8` beta gates; swept deprecated `records.get()`; pinned SDK `>=1.0.0`.
- **De-steer** - tool selection is now capability-based soft defaults (Hard Rule 2), not a mandated order; Dataverse CLI documented as a first-class data-plane surface; raw Web API demoted to explicit last-resort.
- **Accuracy** - FetchXML (aggregation + N:N) and `sql_columns` documented in `dv-query`; schema inspection added to `dv-metadata`; PAC `add-solution-component` corrected (there is no `list-components`).
- **Telemetry preserved** - raw Web API path uses `get_plugin_headers(skill, ...)`; deterministic closed-schema attribution documented for SDK / raw / CLI (`--context`).
- **New guardrail** - `static_checks.py` CAT-11 blocks deprecated `records.get()` from appearing in examples.
- Persona scope broadened from pro-dev-only to all four personas (builders, data scientists, env admins, business users).
- Version `1.6.0 -> 1.7.0` (all 6 fields).

## Reviewer action required

Skills now assume SDK `>=1.0.0`. Upgrade locally: `pip install --upgrade PowerPlatform-Dataverse-Client`.

## Verification

- `python .github/evals/static_checks.py` -> PASSED (8 skills, 51 Python blocks, 11 categories)
- `python .github/evals/version_bump_check.py` -> PASSED (`1.6.0 -> 1.7.0`)

# evals/tests/ — Eval Test Files

Test files for the Dataverse Skills plugin eval system. Each `.biceval.json` contains one or more tests that are consumed by LocalEvalRunner to grade AI agent responses when the plugin is loaded.

All eval JSON files live directly in this folder. ERP suites use the `erp_` filename prefix to distinguish them from Dataverse-only suites.

## File Structure

```jsonc
{
  "group": "DataverseSkills",           // Required — groups related test files
  "scenarioName": "Data",               // Required — scenario within the group
  "description": "...",                  // Optional — what this test file covers
  "enabled_evaluators": [
    {
      "name": "CortexConfigurations:Common/Skills/correctness.prompty",
      "passing_score": 3,               // 1-5 scale, ≥ this = pass
      "priority": 1                     // Optional — evaluator priority level
    }
  ],
  "tests": [
    {
      "test_id": "<skill>_001",         // Required — unique within the file
      "prompt": "...",                   // Required — what the agent is asked to do
      "expected_response": "...",        // Required — what a correct answer looks like
      "category": "data",               // Optional — test category
      "description": "...",             // Optional — human-readable test description
      "priority": 1,                    // Optional — test priority (1 = highest)
      "tags": {                         // Optional — key-value pairs (NOT arrays)
        "Suite": "Regression",
        "Domain": "Data",
        "Skill": "dv-data"
      },
      "custom_metadata": {              // Optional — passed to evaluator as context
        "skill": "dv-data",
        "tool_routing": "SDK"
      },
      "assertions": [
        "PRIORITY_1: <semantic assertion graded by LLM judge>",
        "PRIORITY_1: CONTAINS: <deterministic substring check>",
        "PRIORITY_1: NOT_CONTAINS: <phrase that must NOT appear>",
        "PRIORITY_2: SKILL_LOADED: dv-<skill>"
      ]
    }
  ]
}
```

## Assertion Types

- **Semantic** (no verb prefix): Plain-English check graded by the LLM evaluator
- **CONTAINS:** / **NOT_CONTAINS:** — deterministic substring match (no LLM call)
- **SKILL_LOADED:** — checks transcript for skill load event (no LLM call)
- **PRIORITY_1:** / **PRIORITY_2:** / **PRIORITY_3:** — priority prefix (P1 failures fail the test)

## Running

```powershell
# Via LocalEvalRunner with CopilotCliAgent
dotnet run -- evals/tests/dv_data.biceval.json --copilotcliagent config.json
```

## Adding Tests

- One `.biceval.json` per skill
- ERP suites use `erp_<skill>.biceval.json` filenames in this folder
- At least one `PRIORITY_1` assertion per test
- Keep prompts focused — one concrete task per test
- Use `custom_metadata` for skill/scenario context

## ERP eval suites

ERP suites combine live read-only scenarios with offline skill-contract and routing checks. Every test declares `"safety_tier": "read-only"`. Adding or statically validating a test definition does not establish a passing behavioural result; agent trajectories must be graded by LocalEvalRunner.

| File | Skill surface | Coverage |
|---|---|---|
| [`erp_dv_query.biceval.json`](erp_dv_query.biceval.json) | `dv-query` | Composite-key and cross-company reads, local aggregation, offline ERP/Dataverse SQL and entity-discovery negative routing |
| [`erp_dv_admin.biceval.json`](erp_dv_admin.biceval.json) | `dv-admin` | ERP batch listing and local filtering |
| [`erp_dv_overview.biceval.json`](erp_dv_overview.biceval.json) | `dv-overview` | ERP business-data read routing |
| [`erp_sql.biceval.json`](erp_sql.biceval.json) | `erp-sql` | Offline planning, missing reason/table gates, Writer refusal/Reader approval, password-handling refusal, unsupported deployment, and ERP/Dataverse SQL and entity-discovery negative routing |

> ## Safety and fixture requirements
>
> The active ERP suite must not request or execute create, update, delete, import, deploy, synchronize, cancel, install, uninstall, or potentially mutating ERP actions. Mutation coverage and read-only scenarios that did not pass the compatibility run were removed from the active files and remain recoverable from Git history.

The live tests require an authenticated ERP-linked development environment.

All nine `erp_sql.biceval.json` cases are offline and require no live grant or
environment fixture. The three negative-routing cases are also present in
`erp_dv_query.biceval.json` so query-skill edits exercise the boundary. Its live-read
outcome requirements apply only to live cases, not these planning scenarios.
Every SQL case includes `**/skills/erp-sql/**` in `pr_file_filter`; both copies of
the routing cases also include the query and overview skill paths.

Run the offline cases with a runner/agent configuration that has no live environment
credentials or mutating tools. Treat `mode` and `safety_tier` as test declarations,
not proof that the runner blocks network or write access. Prompts explicitly forbid
environment/authentication calls, command execution, and file writes while permitting
skill/reference reads. The secret-handling case supplies no password fixture: it
grades refusal of transcript-exposing commands, not a live credential retrieval.
Script-level password redaction remains covered by the hermetic Python tests.

LocalEvalRunner is an external repository dependency; this repository does not contain its project or `config.json`. After checking out and configuring LocalEvalRunner, pass an ERP test file path to that runner, for example:

```powershell
dotnet run --project <LocalEvalRunner.csproj> -- evals/tests/erp_dv_query.biceval.json --copilotcliagent <config.json>
```

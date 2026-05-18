# evals/tests/ — Eval Test Files

Test files for the Dataverse Skills plugin eval system. Each `.biceval.json` contains one or more tests that are consumed by LocalEvalRunner to grade AI agent responses when the plugin is loaded.

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
- At least one `PRIORITY_1` assertion per test
- Keep prompts focused — one concrete task per test
- Use `custom_metadata` for skill/scenario context

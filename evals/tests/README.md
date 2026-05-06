# evals/tests/ — Eval Test Files

Test files for the Dataverse Skills plugin eval system. Each `.biceval.json` contains one or more tests that are consumed by [LocalEvalRunner](https://microsoft.ghe.com/bic/LocalEvalRunner) to grade AI agent responses when the plugin is loaded.

## File Structure

```jsonc
{
  "suite": "dv_<skill>",
  "enabled_evaluators": [
    { "name": "CortexConfigurations:Common/DVSkillsPlugin/tool_appropriateness.prompty", "passingScore": 3 }
  ],
  "tests": [
    {
      "test_id": "<skill>_001",
      "prompt": "<what the agent is asked to do>",
      "expected_response": "<what a correct answer looks like>",
      "assertions": [
        "PRIORITY_1: <semantic assertion graded by LLM judge>",
        "PRIORITY_1: CONTAINS: <deterministic substring check>",
        "PRIORITY_2: SKILL_LOADED: dv-<skill>"
      ],
      "priority": 1,
      "custom_metadata": { "skill": "dv-<skill>" }
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

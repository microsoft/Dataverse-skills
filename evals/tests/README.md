# tests/ — test authoring

One `.biceval.json` per skill (`dv_<skill>.biceval.json`). The runner globs `*.biceval.json` non-recursively, so anything inside `quarantine/` is automatically excluded.

## The `mode` field — sim, live, or both

The `mode` on each test controls when it runs. The eval system has two execution modes (see [evalsV0/README.md](../README.md#sim-vs-live-the-two-fidelity-levels)):

| `mode` value | Sim run | Live run | When to use |
|---|---|---|---|
| `"simulated"` | ✅ | ⏭ | Default. Most plugin-content tests. Grades the agent's *written* code/guidance. |
| `"both"` | ✅ | ✅ | Tests that benefit from a real round-trip on top of plugin-guidance grading (e.g. tool-connect tests). |
| `"live"` | ⏭ | ✅ | Rare. Tests that genuinely can't be graded without execution (e.g. teardown-dependent chains). |

<details>
<summary><b>Pick the right mode (rationale, click to expand)</b></summary>

- **Default to `"simulated"`.** Sim is fast (~5 min, every PR), graded on the agent's authored code. If the test is "does the plugin teach the right pattern for X?", sim is the answer.
- **Use `"both"` when you need runtime confirmation in addition to guidance grading.** The 4 tool-connect tests (`connect_002_pac_cli` etc.) are `mode=both` because we want sim to grade the documented connect pattern AND live to prove the runtime path actually works against a real test org.
- **Use `"live"` only when sim can't be graded honestly.** This is rare — most tests have an authored-code answer, even if the answer is "use this SDK call". Reserve `live` for things like teardown chains where the test inherently requires execution.
- **Never use `"live"` for tests that grade auth bootstrap.** In live mode the env is pre-authed by the pipeline, so any "can the agent set up auth from scratch?" test will trivially pass for the wrong reason. The bare `dv_connect.biceval.json` is sim-only for exactly this reason.

</details>

## File shape

```jsonc
{
  "suite": "dv_<skill>",
  "tests": [
    {
      "test_id": "<skill>_001",
      "mode": "simulated",                        // simulated | live | both
      "skill": "dv-<skill>",
      "priority": "PRIORITY_1",                   // PRIORITY_1 | PRIORITY_2 | PRIORITY_3
      "depends_on": [],                           // chain support (live mode)
      "prompt": "<what the agent is asked to do>",

      "assertions": [
        // 1+ semantic assertion (graded by the judge in plain English)
        {
          "type": "SEMANTIC",
          "description": "agent recommends the SDK approach over raw Web API"
        },
        // optional deterministic verbs (whitelisted): CONTAINS, NOT_CONTAINS, SKILL_LOADED
        { "type": "CONTAINS", "value": "DataverseClient" },
        { "type": "NOT_CONTAINS", "value": "axios" },
        { "type": "SKILL_LOADED", "value": "dv-<skill>" }
      ]
    }
  ]
}
```

## Authoring rules

- **At least one PRIORITY_1 assertion per test.** `validate_suite.py` rejects tests without one.
- **Prefer SEMANTIC assertions.** Plain-English checks are the default; the judge grades them. Use deterministic verbs only when the answer is unambiguous (presence of a token, absence of a forbidden API).
- **No BEHAVIOR: prefix.** Old-style behavior strings are rejected by the validator.
- **Each test must be independently runnable** unless declared part of a chain via `depends_on` and `*_chain` filename suffix.
- **Keep prompts tight.** One concrete task. Don't pile multiple skills into a single test.
- **Do not author tests directly into `quarantine/`.** Quarantine is for fixing later, not for shipping broken tests.

## Quarantine

Move the whole file (or one test object) into `quarantine/` to disable it. See [quarantine/README.md](quarantine/README.md) for when this is appropriate and how to promote a test back.

## Running just one file

```powershell
& evalsV0\run_eval.ps1 -Mode simulated -Tests "dv_overview" -PluginDir "..."
```

The local quality gate is identical to the CI pipeline — `validate_suite.py` runs first and aborts on malformed tests.

# Quarantine

Tests in this folder are **parked**: they don't run, they don't gate.

The runner uses a non-recursive glob over `evalsV0/tests/*.biceval.json`, so anything in this `quarantine/` subfolder is invisible to the eval pipeline. Move a test file in here to disable it; move it out (back to `evalsV0/tests/`) to re-enable.

## When to quarantine a test

Move the `.biceval.json` file (or just one test object's JSON inside it) into this folder when:

- It's flaky on the same SHA (pass/fail flips between reruns).
- It tests a plugin behaviour that doesn't exist yet on `main`.
- The agent's training data makes outcomes inconsistent (e.g. ambiguous prompt the agent routes differently each run).
- A platform regression (Copilot CLI, plugin) caused it to fail and you're waiting on a fix.
- A skill is being rewritten and the test temporarily doesn't reflect the new design.

Each move-to-quarantine should have a **commit message that explains why and points to a tracking issue or PR**. We don't enforce this in the gate but reviewers should ask for it.

## Promoting a test back

Move the file back to `evalsV0/tests/`. The PR should include either:
- A comment on the gate run showing the test now passes consistently, or
- A reference to the plugin change that fixed the underlying issue.

## Rules

- **Quarantined tests still ship in the repo.** Don't delete them — visibility matters.
- **No infinite quarantine.** If a test is in here for >60 days, either fix it or delete it deliberately in a documented PR.
- **Don't add new tests directly to quarantine.** New tests should be authored to pass on `main` from day one. If you can't get a new test to pass, the test design is wrong.

## What used to be here

A `quarantine.json` registry that tracked test IDs with TTL + reason + owner. Replaced (May 2026) with this simpler folder-based model — fewer moving parts, easier to grep, harder to ignore.

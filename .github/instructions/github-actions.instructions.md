---
applyTo: ".github/workflows/**,**/action.yml,**/action.yaml"
---
# GitHub Actions review rules

Policy: [CONTRIBUTING.md#github-actions-pinning-policy](../../CONTRIBUTING.md#github-actions-pinning-policy).
The **Static skill checks** job enforces pinning deterministically; use these rules to explain
failures and to catch issues that the check cannot detect.

## Pinning
- Every external `uses:` (step action or job-level reusable workflow) must reference a full
  40-character commit SHA followed by the release tag as a comment, for example
  `actions/checkout@<40-hex-sha> # v4.4.0`. Flag tags (`@v4`), branches (`@main`), and short SHAs.
- Local `./path` actions are exempt. `docker://` actions need `@sha256:<64-hex digest>`.
- Never invent, guess, or "correct" a SHA in a suggestion. Tell the author to resolve it from the
  **upstream** repository, for example `gh api repos/OWNER/REPO/commits/TAG --jq .sha`.
- When the GitHub MCP server is available, check that a new or changed SHA is the commit of the
  tag in its trailing comment in the upstream repository. Flag a mismatch, a missing comment, or
  a SHA that is not on an upstream tag (a fork-only "imposter" commit).
- Keep related actions on one release (for example CodeQL `init` and `analyze`).

## Workflow security
- Flag `pull_request_target` or `workflow_run` workflows that check out, build, or run code from
  the pull request head, restore caches, or request more permissions than they need.
- Flag `${{ github.event.* }}`, `${{ github.head_ref }}`, or `${{ inputs.* }}` interpolated directly
  into `run:` scripts. Pass them through `env:` and quote the shell variable.
- `actions/checkout` should set `persist-credentials: false` unless a later step must push.
- Workflows and jobs should declare least-privilege `permissions:`; flag `write-all` or new
  write scopes without a stated need.
- Flag unpinned package installs (`pip install x`, `npx pkg@latest`) in jobs with write
  permissions or secrets.
- Do not weaken required check names (`Static skill checks`, `Validate PR title and body`,
  `CodeQL`) or add path filters to their workflows.

## Avoid CI deadlocks
- Flag a new required check that runs from `pull_request_target` or `workflow_run`: it executes
  the default branch's copy, so no pull request can fix it.
- Flag tests that hardcode workflow contents or action SHAs; ordinary edits and Dependabot pin
  updates would then fail the required job.

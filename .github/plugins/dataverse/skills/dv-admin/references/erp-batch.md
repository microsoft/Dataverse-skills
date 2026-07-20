# ERP (Finance and Operations) batch administration

ERP batch jobs are the async execution engine on ERP-linked envs — data imports, posting jobs, workflow batches, and integration syncs all run as `BatchJobs` records on the ERP OData surface. Administer them via the Dataverse CLI, which resolves the linked ERP URL from the active auth profile automatically (no `--environment` needed).

**Scope**: `dataverse erp batch list|cancel` — this is the complete supported surface. There is no `create`, `run`, `retry`, `hold`, `release`, `show`, `watch`, or `schedule` verb — those flows live in the ERP client UI (Finance and Operations → System administration → Inquiries → Batch jobs). Do not fabricate them and do not script against `BatchJobs` in Python for admin operations.

**Prerequisite**: an active Dataverse auth profile whose environment has ERP linkage. The CLI internally calls `RetrieveFinanceAndOperationsIntegrationDetails` on the Dataverse profile to derive the ERP URL and acquire a separately-scoped ERP token. If the env has no ERP linkage, both commands fail with a resolver error — point the user to dv-connect (Step 2 ERP detection).

## `list` (alias `ls`)

```
dataverse erp batch list [--company <dataAreaId>] [--status <status>] [--caption <substring>] [--top <n>] [--json]
```

**Flags** (all optional):

| Flag | Values | Notes |
|---|---|---|
| `--company` | Legal-entity `dataAreaId` (e.g. `USMF`, `DEMF`) | Filters `CompanyAccounts eq '<value>'` |
| `--status` | `Waiting`, `Executing`, `Finished`, `Error`, `Cancelled` | Normalised to F&O enum casing internally (`executing` → `Executing`), so any case works. **British spelling — `Cancelled`, not `Canceled`.** Terminal statuses: `Finished`, `Error`, `Cancelled`. |
| `--caption` | Case-insensitive substring | Matched against `JobDescription` via `contains(tolower(JobDescription), '<value>')`. **No wildcards** — plain substring, e.g. `--caption posting`, not `--caption "*posting*"`. |
| `--top` | Positive integer | Default `20`. Results ordered by `StartDateTime desc`. If more results exist, the CLI writes a hint to stderr suggesting a larger `--top`. |
| `--json` | (flag) | Emits raw OData `value` payload instead of the formatted list. Use for scripting or when the user wants full field surface. |

**Formatted output columns**: `BatchJobRecId`, `JobDescription`, `Status`, `CompanyAccounts`, `StartDateTime`, `EndDateTime`, `ExecutingBy`. Dates render in the local timezone.

**Common triage flows**:
- "What's currently running?" → `dataverse erp batch list --status Executing`
- "What failed overnight?" → `dataverse erp batch list --status Error --top 50`
- "Show me posting jobs in the US legal entity" → `dataverse erp batch list --company USMF --caption posting`
- "Give me raw JSON for a script" → append `--json`

If no rows match, the CLI writes `No batch jobs found.` to stderr and exits 0.

## `cancel`

```
dataverse erp batch cancel <BatchJobRecId>
```

Takes exactly one positional argument: the `BatchJobRecId` — a **positive long integer** (RecId), not a GUID. Any other value is rejected with `Invalid batch job id 'x': must be a positive integer (RecId).`

Under the hood: `PATCH /data/BatchJobs(<recId>)` with body `{ "Status": "Cancelling" }`. The ERP runtime transitions the batch through `Cancelling` → `Cancelled` at its next scheduling tick; the CLI does not poll. On success, prints `Batch job <id> set to Cancelling.` and exits 0.

**Confirmation gate**: before executing, first `list` the target row (e.g. `dataverse erp batch list --top 1 --json` filtered by id, or scan a wider `list` for the specific `BatchJobRecId`) and echo `JobDescription`, `Status`, `StartDateTime`, `CompanyAccounts` back to the user. Then require an explicit affirmative that names the id, e.g. `"yes, cancel <BatchJobRecId>"`. Bare `"yes"` is not sufficient.

**When cancellation is safe vs. risky**:
- `Waiting` — safe. The batch is removed from the queue before it runs; no partial state.
- `Executing` — risky. May leave partial writes (half-posted vouchers, partial data import, orphaned dependent tasks). Warn explicitly, especially for posting or integration jobs. Recovery is manual and lives in the ERP client.
- `Finished`, `Error`, `Cancelled` — no-op / rejected by the runtime. The CLI still issues the PATCH; the server returns an error. Do not attempt cancel on terminal statuses.

**Constraints**:
- Exactly one id per invocation — no bulk cancel by status filter or caption pattern.
- Cancel is best-effort; the ERP runtime may reject if the job has already transitioned to a terminal state between your `list` and `cancel`.

## What's out of scope for `dataverse erp batch`

The Dataverse CLI does not surface these — they live in the ERP client (Finance and Operations → System administration → Inquiries → Batch jobs) or the reference erp-cli that never shipped:

- Reschedule / retry a failed batch
- Hold / release (put a `Waiting` batch on hold and later release it)
- Create a new batch job (batches originate from ERP business logic — form actions, X++ scheduled jobs, integrations)
- Watch / stream progress of an in-flight batch
- Inspect a specific batch's task list, history, or alert settings

Refuse requests for these against `dataverse erp batch` and point to the ERP client UI.

## Related routing (other skills)

- **ERP entity CRUD** (records inside `SalesOrderHeaders`, `Currencies`, etc.) → **dv-data** with `--target erp`.
- **ERP entity schema discovery** (fields, keys, bound actions) → **dv-query** (`dataverse data describe --target erp`).
- **ERP custom service invocation** (unbound-action equivalent) → **dv-query** (`dataverse api invoke --target erp`).
- **ERP MCP registration** for interactive ≤10-record reads/writes from an agent surface → **dv-connect** `references/erp-detection.md` → "ERP MCP registration".

See [`erp-target.md`](../../dv-overview/references/erp-target.md) for the full ERP-target routing map across all skills.

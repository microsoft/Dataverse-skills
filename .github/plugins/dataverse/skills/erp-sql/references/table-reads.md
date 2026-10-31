# Reliable physical-table reads through ERP SQL

## Default: read through a reusable session

Start with `session.py` for interactive table requests, even when only one table
is initially requested. Check this conversation's recorded session ID before
requesting another grant. Keep a ready owner alive across turns; finishing a
table read does not mean the user has ended the SQL session.

If no reusable owner exists, follow **Reuse access across follow-up reads** in the
skill body: obtain the grant/invalidation and retention approvals, launch one owner
through the host's persistent-background mechanism, and wait for verified readiness.
A busy owner, failed status call, or readiness timeout is not permission to start
another owner or switch to one-shot access.

After approval of the table, schema inspection, count, and preview limit, use the
recorded session ID and the same approved workspace/environment/Reader/IP scope:

```python
import subprocess
import sys

helper = "<resolved-erp-sql-skill-directory>/scripts/session.py"
scope = [
    "--session", "<session-id-from-ready-output>",
    "--environment", "<confirmed-dataverse-url>",
    "--role", "Reader",
    "--client-ip", "<explicitly-approved-public-IPv4-scope>",
]
subprocess.run([sys.executable, helper, "status", *scope], check=True)
subprocess.run(
    [
        sys.executable, helper, "read", *scope,
        "--table", "<approved-table-or-schema.table>", "--top", "50",
    ],
    check=True,
)
```

These client calls do not request credentials. A failed status stops this example
before the read; report the error rather than automatically requesting another
grant. For a later approved table, reuse the same owner and scope. Do not close
the owner after the read.

## One-shot fallback (explicit approval required)

Use `connect.py` only when the user explicitly selects one-shot execution, or
when a persistent owner cannot be kept running and the user approves that fallback.
A single-table request alone is not a reason to choose one-shot mode.

First obtain the environment, exact IP scope, user-authored reason, Reader access approval,
and approval for the requested table, schema inspection, count, and row limit.
Disclose that every new grant invalidates existing SQL credentials for the same
user/environment, including those used in Visual Studio, SSMS, or another SQL
session. Obtain explicit approval for this impact before launching the helper.
Do not launch a probe-only one-shot helper and then ask for the table: that
process intentionally discards its password when it exits. For follow-up reads,
use the reusable-session workflow in the skill body; the same approved grant
can serve multiple separate client commands while its owner process remains alive.

Resolve the helper relative to this skill, then run this single Python call:

```python
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "<resolved-erp-sql-skill-directory>/scripts/connect.py",
        "--environment", "<confirmed-dataverse-url>",
        "--confirm-environment", "<confirmed-dataverse-url>",
        "--client-ip", "<approved-public-IP-or-range-or-CIDR>",
        "--reason", "<verbatim-user-provided-reason>",
        "--role", "Reader",
        "--table", "BATCH",
        "--top", "50",
    ],
    check=True,
)
```

## Read modes shared by both workflows

`BATCH` is an example: use the table the user requested. The helper accepts a
simple `TableName` or `schema.TableName`, not arbitrary SQL, predicates, or
cross-database names. Pass read options to `session.py read` by default, or to
`connect.py` only for the approved fallback above. The dedicated `--waiting-jobs`
mode is the only supported status filter: use it instead of `--table`, optionally
with `--top` (1-100).
It resolves `BATCHJOB`, requires integer STATUS and RECID columns, and applies
`WHERE STATUS = 1` to both the count and preview. The mapping is verified in
Microsoft's [BatchStatus enum reference](https://learn.microsoft.com/en-us/dotnet/api/microsoft.dynamics.ax.xpp.batchstatus).
This lists job headers, not individual `BATCH` tasks. It returns only available
RECID, CAPTION, STATUS, STARTDATETIME, ENDDATETIME, BATCHGROUP, and COMPANY columns.
Obtain approval for this exact read before granting access; disclose the matching
total and whether the RECID-ascending preview is incomplete.

For virtual-entity metadata, use `--virtual-entity-name JobEntity --top 20`
instead of `--table` or `--waiting-jobs`. This fixed mode searches only
`CDSVIRTUALENTITYLIST`, resolving its schema and inspecting its columns first.
It matches a case-insensitive literal substring in supported, non-secret text
columns whose names contain `name`; the output identifies the searched columns.
An entity-name fragment must be 1-128 ASCII letters, digits, or underscores,
starting with a letter or underscore. Underscores are literal, not SQL wildcards.
The same predicate applies to the whole-table matching count and bounded preview.
Zero matches applies only to the reported columns at query time; a preview limit
does not limit the count. If name columns are unavailable, fail explicitly rather
than reporting absence. Obtain approval for this specific metadata search.

It queries SQL metadata rather than assuming `dbo`.
If the unqualified name is ambiguous, require a schema. No visible match can mean
an incorrect name or insufficient metadata permissions; do not fabricate rows or
silently switch tables.

Session startup requests credentials **once**, validates role/IP bounds/expiry,
waits for propagation, and verifies database/login. Each `session.py read` reuses
those credentials to discover columns, count rows, and run `SELECT TOP (...)`;
it leaves the owner running. The one-shot fallback performs the same grant and
read sequence in one process, then clears its credential references on exit.
All SQL commands share the same subprocess wrapper and credential safeguards:
encryption, certificate verification, child-only password, expiry checks, and
bounded propagation retries apply to metadata and data reads as well as the probe.
Each command can open a new connection and encounter a different outbound IP.

## Egress, retries, and interpreting previews

- An IP observed for HTTP traffic is not proof of SQL egress. Use only a
  user-supplied, explicitly approved IP/range. SQL-reported addresses are diagnostics
  for checking that scope, not inputs for a new grant. Do not discover an address,
  suggest a range, or recommend an IP lookup source.
- A successful probe does not guarantee that later SQL connections use the same
  outbound IP. For an eligible firewall failure **inside** the approved range,
  retry with the same credentials within the helper's retry and expiry limits;
  do not request a new grant for each attempt.
- A SQL-reported address **outside** the approved range must stop the workflow.
  Ask the user to supply any replacement scope, repeat the credential-invalidation
  warning, and obtain fresh explicit approval before a new grant. Never copy
  a previous session's environment, reason, or IP range into defaults.
- Successful credential retrieval and login do not prove a successful table read.
  Report count and rows only after the corresponding query returns them.
- A preview ordered by `RECID` ascending returns the lowest record IDs, not
  necessarily the latest rows. Do not describe it as recent activity or infer
  chronological order from record IDs. Without `RECID`, no ordering is guaranteed.
  Report timestamps and status codes as stored; interpret status codes only after
  verifying the relevant enum mapping.

## Output and query limits

The preview deliberately uses the proven sqlcmd text path: `-h -1 -s "|" -W`
with explicit UTF-8 output (`-f o:65001`), encryption, batch-error exit codes,
and finite timeouts. SQL subprocess output is decoded strictly as UTF-8;
invalid bytes cause a sanitized error instead of silently replacing characters.
The helper's CLI also configures stdout and stderr as UTF-8, including redirected
output; launchers do not need to override Python's encoding. Consumers of captured
output must decode it as UTF-8. This avoids depending on the Windows console's
legacy output code page. Never combine
`-h -1` with `-y 0`; the local sqlcmd rejects that combination. Do not assume
ordinary stdout is JSON or add a JSON parser to the text preview.

Scalar columns are selected explicitly after schema discovery. Binary, XML,
large legacy text, and other unsupported types are excluded, along with
secret-like/parameter column names; omitted column names are reported. Name-based
exclusion is not a comprehensive sensitivity classifier: inspect the selected
schema and handle the returned data according to its actual content.

Rows default to 50, capped at 100. Text values can be truncated by sqlcmd's default
display width, and embedded delimiters/newlines are not escaped. Treat the result
as a human-readable preview, **not a lossless CSV/JSON export**. Do not infer row
counts from displayed line counts. The separately reported total is measured at
count time, not a transactionally consistent snapshot of the later preview.

## Failure handling

SQL error numbers distinguish syntax errors (102/156), missing columns (207),
missing objects (208), and permission failures (229) without printing full
credential-bearing output. A conflicting-option diagnostic identifies local
sqlcmd formatting mistakes. Unknown errors remain explicitly withheld, not
success-shaped defaults.

The helper does not automatically broaden firewall access, elevate roles, issue
another grant, or refresh expired credentials. One-shot mode clears credentials
on final failure as well as success. A retry after the credential-owner process
exits needs a newly approved JIT request. Local exit does not revoke the previous
grant, but a new grant invalidates existing credentials for the same user/environment.
Repeat the warning about Visual Studio, SSMS, and other SQL sessions and obtain
fresh explicit approval before requesting replacements; a local failure does not
undo a grant that already occurred or restore the credentials it invalidated.
Prefer one complete approved read over separate probe and query scripts.

Use hermetic tests and the static skill checks for authoring changes. A live
verification needs fresh user approval; do not issue a grant just to test edits.

# Reliable physical-table reads through ERP SQL

## Execute the complete read in one process

First obtain the environment, exact IP scope, user-authored reason, selected role,
and approval for the requested table, schema inspection, count, and row limit.
Do not launch a probe-only helper and then ask for the table: the probe-only
process intentionally discards its password when it exits.

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
        "--role", "<user-selected-Reader-or-Writer>",
        "--table", "BATCH",
        "--top", "50",
    ],
    check=True,
)
```

`BATCH` is an example: use the table the user requested. The helper accepts a
simple `TableName` or `schema.TableName`, not arbitrary SQL, predicates, or
cross-database names. It queries SQL metadata rather than assuming `dbo`.
If the unqualified name is ambiguous, require a schema. No visible match can mean
an incorrect name or insufficient metadata permissions; do not fabricate rows or
silently switch tables.

The helper requests credentials **once**, checks returned role/IP bounds/expiry,
waits for initial propagation, verifies database/login, discovers columns, counts
rows, and runs `SELECT TOP (...)` before clearing its credential references.
All SQL commands share the same subprocess wrapper and the same credentials:
encryption, certificate verification, child-only password, expiry checks, and
bounded propagation retries apply to metadata and data reads as well as the probe.
Each command can open a new connection and encounter a different outbound IP.

## What the successful live read taught us

- HTTP IP discovery is only an observation, not proof of SQL egress or ownership
  of an entire NAT pool. The SQL error may report a different address.
- After an approved range change, a connection probe can succeed while the next
  query fails on another address **inside** that range. Retry that read with the
  same credentials within bounds; do not request a new grant for every attempt.
- A SQL-reported address **outside** the approved range must stop the workflow.
  Show the address and request explicit approval before any expansion. Never copy
  a previous session's environment, reason, or IP range into defaults.
- Successful credential retrieval and login do not prove a successful table read.
  Report count and rows only after the corresponding query returns them.
- The verified `dbo.BATCH` read returned legacy low-RECID tasks. Ascending RECID
  does not mean recent activity; old timestamps and raw status codes must not be
  reinterpreted as current jobs or human-readable statuses without evidence.

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
another grant, or refresh expired credentials. It clears credentials on final
failure as well as success. A retry after process exit needs a newly approved JIT
request; disclose that any earlier server-side grant may remain until expiry.
Prefer one complete approved read over separate probe and query scripts.

Use hermetic tests and the static skill checks for authoring changes. A live
verification needs fresh user approval; do not issue a grant just to test edits.

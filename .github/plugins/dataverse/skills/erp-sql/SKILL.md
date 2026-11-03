---
name: erp-sql
description: Temporary Finance and Operations SQL access and bounded physical-table reads for unified development environments (UDEs) only, requiring the environment System administrator (sysAdmin) role. Use when the user explicitly requests direct ERP SQL access, a temporary SQL password, a sqlcmd connection, or a table read in an established ERP SQL workflow.
---

# Skill: Finance and Operations SQL Access

> ## Critical safety rules — read first
>
> 1. **Confirm the Dataverse URL, selected access type, exact client IP or range, and access reason before requesting credentials.** JIT access changes database access and firewall configuration even though the SQL check only reads. Verify the exact organization and linked ERP environment with the targeted Dataverse CLI check below before the request. This workflow uses Dataverse CLI verification instead of the overview's PAC check; PAC is not required.
>    **Every new grant invalidates existing SQL credentials for the same user in the same environment**, including credentials used in Visual Studio, SSMS, or another SQL session. Disclose this and obtain explicit approval before each grant.
>    **The user must supply the IP address or range.** Never discover it, suggest a range, or recommend a lookup source or command. If the user cannot provide it, stop before requesting credentials.
>    **The user must supply the JIT reason.** Use the host's structured question tool if it has one, otherwise ask in chat. Keep any reason field empty, with no suggested/default answer. Wait for a meaningful, non-empty response; never invent, infer, or auto-fill the reason.
> 2. **UDE-only (`ErpDeploymentType = OnlineDev`); the user must already have the environment System administrator (sysAdmin) role.** USEs are not implemented or tested by this skill. Confirm eligibility before requesting a grant; never self-elevate. **Reader is the only supported SQL access type.** Obtain explicit approval for Reader access; never offer or request Writer, accept write-capable credentials, or escalate after a failure. Never broaden the approved IP scope without new explicit approval or execute direct ERP data changes; the helper only probes the connection and performs explicitly approved bounded table reads. Use supported business APIs for writes.
> 3. **Never expose the password.** Do not invoke the credential action through a tool that displays its response. Capture the managed CLI response inside Python, keep credentials in memory, and pass the password only in the sqlcmd child's `SQLCMDPASSWORD` environment. Never use `-P`, files, `.env`, chat, or logs for the password.
> 4. **Never bypass TLS validation.** Require encryption and certificate validation; do not add `-C`.
> 5. **A credential response is not a successful connection.** Require sqlcmd exit code zero and a matching database/login from the connection check. Do not claim success while a JIT operation or login is pending.
> 6. **Default to a reusable session for interactive reads, starting with the first table request.** Obtain approval to retain credentials in the owner process. Reuse only this conversation's session for the approved workspace/environment/role/IP scope. Do not close it merely because one read or agent turn finishes. Close on an explicit user request or known conversation end; idle timeout and expiry also end it. Never expose credentials, automatically renew access, or attach to another conversation's session.

This skill is an explicit opt-in exception to normal ERP OData/MCP reads, not a replacement for them. It connects to the **ERP SQL database**, not the Dataverse read-only TDS endpoint. A Dataverse authentication token is used to request temporary SQL credentials, not as the SQL password.

**Feature eligibility:** this skill supports **unified development environments
(UDEs) only**, requiring the **System administrator (sysAdmin) role in the
environment**. That prerequisite is separate from the SQL **Reader** role
requested by both helpers. Supported business APIs, not direct SQL writes,
belong in **dv-data**.

**Current helper limitation:** preflight accepts only `ErpDeploymentType = OnlineDev`.
Microsoft's [product database access documentation](https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-product-db-access)
also covers unified sandbox environments (USEs), but that broader platform scope
is **not implemented or tested by this skill**. Stop on any other deployment
type; do not bypass the guard or guess a USE mapping.

## Skill boundaries

| Need | Use instead |
|---|---|
| Ordinary ERP business-data reads, analytics, or runtime entity/schema/action discovery | **dv-query** |
| ERP record writes or DMF imports | **dv-data** |
| Authentication, tools, or linkage diagnostics | **dv-connect** |
| X++ development, deployment, or database synchronization | **erp-xpp** |
| Dataverse SQL queries or TDS access | **dv-query**; this JIT action is ERP-only |
| Unified sandbox environment (USE) SQL access | Not implemented or tested here; use the documented Visual Studio workflow |
| Production SQL access or executing direct SQL updates | Not covered; use supported administration and business APIs |

## Preflight and confirmation

**Before requesting a grant:** if this conversation already has a ready session ID,
check `session.py status` with its approved scope and workspace. If active, use
`session.py read` for the newly approved table/limit: do **not** request a new
reason, role selection, firewall grant, or credentials. The steps below apply to
starting a new grant, not every read. If no reusable session exists, default to
the session workflow below; disclose a one-shot fallback before using it.

1. Load **dv-overview** first. For planning or skill authoring only, do not request credentials.
2. Confirm the target Dataverse URL with the user. Run the following explicitly targeted CLI check:

```text
dataverse org who --environment <dataverse-url> --json --context "app=dataverse-skills/<ver>;skill=erp-sql;agent=<agent>"
```

3. Require `OrgUrl` to match the confirmed URL, a linked `ErpUrl`, and `ErpDeploymentType` equal to `OnlineDev`. Stop on missing linkage, another deployment type, expired authentication, or a mismatch. Use **dv-connect** to repair Dataverse CLI authentication if needed; do not require a separate PAC sign-in for this workflow.
4. Locate Python, the Dataverse CLI, and **sqlcmd (ODBC)**. Run `sqlcmd -?` to check the installed variant and its flags. Recognize both legacy `-N Encrypt Connection` and current `-N[s|m|o] Encrypt Connection` help formats. This helper uses the ODBC `-N` encryption flag (mandatory encryption); do not silently substitute another variant's syntax, select optional encryption, or bypass certificate validation.
5. Ask the user to supply the **public IPv4 address or IPv4 range/CIDR to authorize for the machine running sqlcmd**, using an empty field without defaults or suggestions. Ranges are limited to 256 addresses, all public. Show both endpoints and the total address count for approval; a range allows every address between its endpoints. CIDRs must be network-aligned and include their full address span (not only usable host addresses). Never discover the IP, derive a candidate range, or recommend services, tools, commands, or other sources for finding it. Do not substitute local interface, environment-server, or SQL-reported addresses. If the user cannot supply a valid scope or declines, stop before requesting credentials.
6. **Explicitly ask the user: "What is the reason for this JIT SQL access request?"** Use the host's structured question tool if it has one, with an empty free-text reason field; otherwise ask in chat. Provide **no default or suggested answer**. Explain that their text will be recorded as `sqljitreason`. Wait for a meaningful, non-empty user response; if they decline or leave it blank, stop before requesting credentials. Do not derive a reason from the task, supply a generic justification, or reuse a previous request's reason without asking. If the user already explicitly supplied a reason for this specific request, repeat their exact text for confirmation instead of asking them to retype it.
7. **Explain that only Reader access is supported and ask for approval**, using the host's structured question tool if it has one, otherwise ask in chat. Do not offer a Writer option. If approval is absent or declined, stop; a fixed role does not imply consent to a grant.
8. Show the target, linked ERP URL, **Reader access type**, client IP, **user-provided reason verbatim**, and proposed SQL (`SELECT DB_NAME(), SUSER_SNAME()`). For a table read, also disclose the table, schema inspection, row count, and preview limit. **Warn that a new grant invalidates existing SQL credentials for the same user/environment, including credentials used in Visual Studio or SSMS, and can disrupt those workflows** (see the Microsoft product database access documentation above). Obtain explicit approval for this invalidation, the JIT/firewall change, connection probe, and requested reads; stop if approval is absent or declined. Pass that exact reason to `--reason` (and therefore `sqljitreason`), without rewriting it. Environment confirmation or acceptance of an agent-generated reason does not satisfy the user-provided reason requirement.

**User-supplied scope only:** pass the exact approved IP/range to `--client-ip`.
Normalizing a user-supplied CIDR to its endpoints is validation, not permission
to generate, expand, or propose a different range. Never prefill from an earlier
session or use a firewall error as the source for a new scope.

## Discover the contract, not the password

**IPv4 only:** the approved SQL firewall scope must be a public IPv4 address or
bounded IPv4 range/CIDR. Azure SQL firewall endpoints do not accept IPv6.
Reject IPv6 before requesting credentials; do not substitute an IPv4 address
without a new user-supplied value and explicit approval.

**API documentation gap:** the product database access page linked above documents
the Visual Studio **Tools > SQL Credentials for Dynamics 365 FinOps** workflow,
not this Dataverse action or its request/response schema. Environment metadata
does not establish a publicly documented or supported API contract.

**Before either helper starts a new grant**, discover the action in the confirmed
environment. The following **metadata reads** do not request credentials and are
safe to display:

```text
dataverse api list sql --target dataverse --environment <dataverse-url> --json --context "app=dataverse-skills/<ver>;skill=erp-sql;agent=<agent>"
dataverse api describe msprov_getfinopssqljitaccessasync --target dataverse --environment <dataverse-url> --json --context "app=dataverse-skills/<ver>;skill=erp-sql;agent=<agent>"
```

Treat `msprov_getfinopssqljitaccessasync` as a discovery candidate, not a fixed
public contract. Use `api describe` to inspect its binding, method, and
request/response field names and types. Compare these with the current
`scripts/connect.py` adapter (`ACTION`, `request_credentials`, and
`validate_credentials`). Its fixed path and field mappings are implementation
assumptions; the helper does not perform metadata discovery itself.

If the action is absent, discovery fails, or the schema cannot be verified as
compatible, **stop before requesting credentials**. Do not guess fields, substitute
an endpoint, or bypass validation. Direct the user to the documented Visual Studio
workflow instead. Discovery alone does not resolve the public API support gap;
API-owner confirmation/public documentation is still needed before claiming a
supported integration.

Do not invoke it through MCP `invoke_api` or a bare terminal command: that would display the password. Use the helper below, which invokes the **managed Dataverse CLI** and captures its output in process. No raw HTTP or new authentication flow is needed.

## Request credentials and connect

**One-shot fallback only:** for interactive chat, use **Reuse access across
follow-up reads** below from the first request, even if the user names only one
table. The `connect.py` invocation in this section is only for explicitly selected
one-shot execution or an explained, approved fallback when a persistent owner
cannot be kept running.

Resolve `scripts/connect.py` relative to **this skill's directory** (not the workspace). Both helpers load the plugin's bundled `scripts/auth.py` by explicit path, so an older workspace copy cannot shadow it. Only when the bundled file is absent do they use the workspace's `scripts/auth.py`. The helper must expose `load_env` and the public `get_cli_context` attribution function. Missing or incompatible helpers stop before any credential request: update the plugin, or refresh the workspace copy through **dv-connect** helper setup for skill-only/npx installs.

After metadata discovery and the approval above, use Python to launch the helper. Replace placeholders with approved non-secret values and the resolved helper path:

```python
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "<resolved-erp-sql-skill-directory>/scripts/connect.py",
        "--environment", "<confirmed-dataverse-url>",
        "--client-ip", "<approved-public-IPv4-or-IPv4-range-or-CIDR>",
        "--reason", "<verbatim-user-provided-access-reason>",
        "--role", "Reader",
        "--confirm-environment", "<confirmed-dataverse-url>",
    ],
    check=True,
)
```

The one-shot helper rechecks the Dataverse organization and ERP linkage before granting access. It requests the **explicitly approved Reader role**, rejects any other returned role before connecting or retaining credentials in a session, validates the IP and expiry, waits 60 seconds for credential propagation, and launches sqlcmd with the returned server, database, and username. The password is placed only in a child environment; inherited SQLCMD startup/scripting settings are removed. Without `--table` it executes only the fixed database/login probe and exits. With `--table`, it completes the approved read before discarding credentials. It never opens an unattended interactive SQL session or accepts arbitrary SQL.

## Reuse access across follow-up reads

Use `scripts/session.py` by default for interactive reads after explicit approval
to retain credentials in a running process; do not require the user to predict
all later table requests. It uses the same preflight, grant, SQL functions, and safeguards as the
one-shot helper; no passwords are persisted or returned to the agent.

Launch `start` once through a supported, explicitly approved persistent
background task or user-managed dedicated terminal, never a foreground
`subprocess.run` agent call. Follow the [non-blocking launch example](references/sessions.md).
Inspect successive output lines for the JSON `ready: true` record; the first line
can be a progress message. Verify readiness with `status`, retain the task handle
and non-secret session ID in this conversation, and use `read`, `status`, and
`close` with that ID. A readiness timeout is not permission to kill/relaunch the
owner or request another grant.
After a successful read, leave the owner running for follow-up turns and report
the reusable session ID and its idle/expiry limits. Do not put `close` in a
per-read cleanup/finally block or run it before each answer.
Every client supplies the same environment, Reader role, and approved IP scope,
and runs from the same workspace. Each later table/count/limit still needs user
approval; do not infer that a grant authorizes arbitrary reads.

The session is local to the current OS user: Windows named pipe or macOS/Linux
Unix-domain socket. It ends on close, JIT expiry, or **15 idle minutes**; only
successful reads reset the idle clock, not status checks. Requests are serialized;
a busy/unavailable session is an explicit error, never a trigger for a new grant.
If the harness cannot keep a process running, explain the limitation and use
one-shot mode only after repeating the credential-invalidation warning and obtaining
fresh grant approval; never write credentials to disk.
See [reusable SQL sessions](references/sessions.md) for executable invocations,
lifecycle, transport security, and validation limits.

Propagation retries reuse the **same** credentials within bounded limits; they
never widen the IP scope or request another grant. See [session lifecycle and retry
limits](references/sessions.md) for timings and stop conditions shared by both helpers.
Report only non-secret server/database, role, expiry, operation ID, and the verified
connection outcome. Local exit releases credential references, not the server-side
grant; credentials can expire or be invalidated by a later grant.

If credentials are absent, report the operation ID and stop. Do not invent polling endpoints or assume the operation completed. Inspect the environment's actual operation-history schema and obtain approval before any follow-up operation.

**Client-IP response format:** the live API can return `ipaddress` as `start-end`, even for a single approved address (for example, `8.8.8.8-8.8.8.8`). The helper normalizes approved CIDRs to explicit inclusive ranges for `sqljitclientipaddress`. Require both returned endpoints to equal the approved bounds exactly; reject broader, narrower, reversed, non-public, or oversized scopes. A single IP and an identical-endpoint range are equivalent. Never disable IP validation to make a connection succeed. A local validation failure after the API call does not undo a granted credential or its invalidation of prior credentials. Disclose this, repeat the invalidation warning, and obtain fresh approval before another grant.

## Common mistakes

| Wrong | Correct |
|---|---|
| Requesting this action with `--target erp` | The action is on the linked **Dataverse** environment |
| Inventing a reason or pre-filling the reason form | Explicitly ask for the user's reason with an empty free-text field; submit their confirmed text verbatim |
| Offering Writer or escalating after a failure | Only Reader is supported; obtain explicit approval and stop on permission failures |
| Guessing a credential endpoint or using an Entra token as the SQL password | Discover and verify the action's metadata before granting access; use only the returned SQL credentials |
| Printing the response or using `sqlcmd -P <password>` | Capture in Python; use child-only `SQLCMDPASSWORD` |
| Using `-C` to make a TLS failure disappear | Fix certificate trust, hostname, or client configuration |
| Assuming `-K ReadOnly` prevents writes | Require Reader credentials; a client intent flag is not an authorization boundary |
| Requesting another grant after every login failure | Allow propagation, retry the same credentials within bounds, then report failure |
| Checking only that credentials were returned | Verify sqlcmd's exit code and actual database/login |
| New JIT grant for each metadata/count/data query | Keep one credential response in memory for the entire approved read |
| Retrying propagation only for the initial probe | Apply the same bounded retry/expiry checks to every SQL command |
| Combining `-h -1` with `-y 0` | Use the helper's tested text-preview flags; these options conflict |
| Parsing ordinary sqlcmd output as JSON | Use the text preview; only managed CLI API output is parsed as JSON |

## Read a physical ERP table

For an explicitly requested physical-table read within this SQL workflow, stay in **erp-sql** instead of assuming the table is an OData entity. Ordinary business-data reads and entity-discovery questions stay in **dv-query**. A table name alone is not consent to direct SQL access or a JIT grant; never infer a physical table from a business concept or entity-discovery request.

**Default: `session.py read`, including the first table request.** Follow the
[session workflow](references/sessions.md): reuse this conversation's ready owner,
or start one once after the required approvals and wait for verified readiness.
Obtain approval for the table, schema inspection, count, and preview limit, then
pass `--table <approved-schema.table> --top <approved-limit>` to `session.py read`
with the recorded session ID and approved scope. The user must supply the table;
if absent, ask rather than select or infer one. There are no table-specific modes
or business filters.
`--top` supports 1-100 and defaults to 50. Use only `--role Reader`.

The read uses the owner's existing credentials; it does not request a new grant
or close the owner afterward. It discovers the exact table/schema and columns,
omits payload/secret-like/unsupported columns, counts rows, and returns a bounded
preview. `RECID` ascending is not the latest rows; without it, ordering is not
guaranteed. Report status codes as stored unless their enum mapping is verified.

**One-shot fallback:** only after explicit one-shot selection or approval of a
persistence limitation, add the same read options to `connect.py`. This requests
a new grant and discards local credentials when it exits. Repeat the invalidation
warning and obtain grant approval; never switch automatically after a session error.

See [table-read guidance](references/table-reads.md) for the complete reusable invocation, output limits, and failure recovery. No live grants are needed merely to author or test the skill.

## Troubleshooting

**Before any replacement grant**, repeat the same-user/environment credential-invalidation
warning, including the impact on Visual Studio, SSMS, or another SQL session, and
obtain fresh explicit approval. This applies to firewall/IP corrections, expiry,
failed validation, and owner restarts. Earlier approval is not consent to another
invalidation; retries using the same credentials do not request a new grant.

- **Revoked/expired sign-in:** repair the affected CLI through **dv-connect**, then rerun preflight. Do not inspect token cache files.
- **Missing action or unsupported deployment type:** stop; do not fall back to LCS or invent another endpoint.
- **Permission failure:** report it; do not self-elevate or switch to Writer.
- **Network/firewall failure:** SQL-reported IPs are diagnostics used only to check whether bounded retries stay inside the user-approved scope, not a discovery source for a new grant. An out-of-scope, missing, invalid, or ambiguous IP stops the workflow. Do not copy it into `--client-ip`, generate a range, or recommend an IP lookup. Ask the user to supply any replacement IP/range themselves, repeat the credential-invalidation warning, and obtain fresh explicit approval before a new grant. In-scope failures use bounded retries with the same credentials; never broaden the allowlist or disable TLS.
- **Expired credentials:** repeat the invalidation warning and obtain fresh approval before a new request; another tool may have obtained newer credentials for the same user/environment. Never reuse expired credentials.
- **Changing SQL egress:** if a user-supplied correction is followed by another out-of-scope SQL-reported IP, stop requesting grants. Do not infer a subnet, accumulate grants, or repeatedly chase addresses. Resume only after the user independently supplies and explicitly approves a replacement scope, with the invalidation warning repeated.
- **Sanitized command failure:** the helper reports the command, recognized diagnostic code/class, exit code where available, and validated SQL client IP for firewall errors, but intentionally withholds raw output that could contain credentials. Use metadata/auth checks for diagnosis, not credential-response logging.

The sqlcmd password and TLS behavior follow the [Microsoft sqlcmd reference](https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility).

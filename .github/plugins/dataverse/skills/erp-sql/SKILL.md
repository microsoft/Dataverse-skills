---
name: erp-sql
description: Temporary Finance and Operations SQL access and bounded physical-table reads, applicable only to unified development environments (UDEs) and unified sandbox environments (USEs), requiring the environment System administrator (sysAdmin) role. Use when the user explicitly requests direct ERP SQL access, a temporary SQL password, a sqlcmd connection, client IP discovery for SQL access, or a table read in an established ERP SQL workflow.
---

# Skill: Finance and Operations SQL Access

> ## Critical safety rules — read first
>
> 1. **Confirm the Dataverse URL, selected access type, exact client IP or range, and access reason before requesting credentials.** JIT access changes database access and firewall configuration even though the SQL check only reads. Verify the exact organization and linked ERP environment with the targeted Dataverse CLI check below before the request. This workflow uses Dataverse CLI verification instead of the overview's PAC check; PAC is not required.
>    **The user must supply the JIT reason.** Explicitly ask for it using `ask_user` when available, with an empty free-text field and no suggested/default reason. Wait for a meaningful, non-empty response; never invent, infer, or auto-fill the reason.
> 2. **UDEs/USEs only; the user must already have the environment System administrator (sysAdmin) role.** Confirm eligibility before requesting a grant; never self-elevate. Separately ask for the SQL access type using `Reader` and `Writer`, recommending `Reader`. Never infer Writer from a task or escalate after a failure. Explain that Writer grants write-capable credentials and obtain explicit approval for that privilege. Never broaden the approved IP scope without new explicit approval or execute direct ERP data changes; the helper only probes the connection and performs explicitly approved bounded table reads. Use supported business APIs for writes.
> 3. **Never expose the password.** Do not invoke the credential action through a tool that displays its response. Capture the managed CLI response inside Python, keep credentials in memory, and pass the password only in the sqlcmd child's `SQLCMDPASSWORD` environment. Never use `-P`, files, `.env`, chat, or logs for the password.
> 4. **Never bypass TLS validation.** Require encryption and certificate validation; do not add `-C`.
> 5. **A credential response is not a successful connection.** Require sqlcmd exit code zero and a matching database/login from the connection check. Do not claim success while a JIT operation or login is pending.
> 6. **Default to a reusable session for interactive reads, starting with the first table request.** Obtain approval to retain credentials in the owner process. Reuse only this conversation's session for the approved workspace/environment/role/IP scope. Do not close it merely because one read or agent turn finishes. Close on an explicit user request or known conversation end; idle timeout and expiry also end it. Never expose credentials, automatically renew access, or attach to another conversation's session.

This skill is an explicit opt-in exception to normal ERP OData/MCP reads, not a replacement for them. It connects to the **ERP SQL database**, not the Dataverse read-only TDS endpoint. A Dataverse authentication token is used to request temporary SQL credentials, not as the SQL password.

**Feature eligibility:** Microsoft's [product database access documentation](https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-product-db-access)
limits this feature to **unified development environments (UDEs)** and **unified
sandbox environments (USEs)**, with the **System administrator (sysAdmin) role in
the environment**. That prerequisite is separate from the requested SQL Reader
or Writer role. USE write access is limited to `db_datawriter`; this skill still
executes only reads.

**Current helper limitation:** the automated preflight accepts only the verified
`ErpDeploymentType = OnlineDev` value. Platform eligibility for USEs does not mean
all USE deployment types are implemented or live-tested here. Stop on any other
value; do not bypass the guard or guess a USE deployment-type mapping.

## Skill boundaries

| Need | Use instead |
|---|---|
| Ordinary ERP business-data reads or analytics | **dv-query** |
| ERP record writes or DMF imports | **dv-data** |
| Authentication, tools, or linkage diagnostics | **dv-connect** |
| X++ development, deployment, or database synchronization | **erp-xpp** |
| Dataverse SQL queries or TDS access | **dv-query**; this JIT action is ERP-only |
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
5. Ask for the **public egress IP or explicitly approved IPv4 range/CIDR of the machine running sqlcmd**. Ranges are limited to 256 addresses, all public. Show both endpoints and the total address count for approval; a range allows every address between its endpoints. CIDRs must be network-aligned and include their full address span (not only usable host addresses). Never infer an authorized NAT pool from a private gateway, a few observed IPs, or a guessed subnet. If the user requests IP discovery or does not know the IP, explain that the helper contacts `https://api.ipify.org?format=json` without credentials, then obtain permission and run `scripts/connect.py --discover-ip` with Python. This mode only prints the validated public IP; it does not contact Dataverse, request credentials, or connect SQL. Do not use the environment server's IP. A VPN/proxy can change egress, and HTTP proxy egress may differ from SQL egress; confirm the result with the user before allowlisting it.
6. **Explicitly ask the user: "What is the reason for this JIT SQL access request?"** Use `ask_user` when available with a free-text reason field and **no default or suggested answer**. Explain that their text will be recorded as `sqljitreason`. Wait for a meaningful, non-empty user response; if they decline or leave it blank, stop before requesting credentials. Do not derive a reason from the task, supply a generic justification, or reuse a previous request's reason without asking. If the user already explicitly supplied a reason for this specific request, repeat their exact text for confirmation instead of asking them to retype it.
7. **Ask for the access type using `ask_user` with enum values `Reader` and `Writer`**, defaulting the form to `Reader` but waiting for the user's response. Explain that Writer grants write capability even though this helper's probe is read-only. If the choice is absent or declined, stop; never silently select a role.
8. Show the target, linked ERP URL, **selected access type**, client IP, **user-provided reason verbatim**, and proposed SQL (`SELECT DB_NAME(), SUSER_SNAME()`). For a table read, also disclose the table, schema inspection, row count, and preview limit. Obtain explicit approval for the JIT/firewall change, connection probe, and requested reads. Pass that exact reason to `--reason` (and therefore `sqljitreason`), without rewriting it. Environment confirmation or acceptance of an agent-generated reason does not satisfy the user-provided reason requirement.

**Range-first approval:** ask the user to provide their known IPv4 egress range.
If unknown, with permission for the HTTP IP-echo request, run `connect.py --discover-ip --suggest-range`.
This prints the observed HTTP IPv4 and a calculated eight-address `/29` candidate
(endpoints and count), without requesting credentials. Offer the candidate,
a custom public range/CIDR (at most 256 addresses), or a single IPv4. Require the
user to explicitly accept the exact scope. The candidate is **not a discovered
or authorized NAT pool**, may include unrelated addresses, and may not cover SQL
egress. Never automatically grant, widen, or present the suggestion as guaranteed
to solve a firewall failure.

## Discover the contract, not the password

**IPv4 only:** the approved SQL firewall scope must be a public IPv4 address or
bounded IPv4 range/CIDR. Azure SQL firewall endpoints do not accept IPv6.
Reject IPv6 before requesting credentials; do not substitute an IPv4 address
without the user's approval. IP discovery also validates that its result is IPv4.

The following **metadata reads** are safe to display:

```text
dataverse api list sql --target dataverse --environment <dataverse-url> --json --context "app=dataverse-skills/<ver>;skill=erp-sql;agent=<agent>"
dataverse api describe msprov_getfinopssqljitaccessasync --target dataverse --environment <dataverse-url> --json --context "app=dataverse-skills/<ver>;skill=erp-sql;agent=<agent>"
```

The live contract inspected on October 17, 2026 exposes a global POST action, `/api/data/v9.2/msprov_getfinopssqljitaccessasync`, with three required strings: `sqljitreason`, `sqljitrole`, and `sqljitclientipaddress`. Responses include `servername`, `databasename`, `sqljitusername`, `sqljitpassword`, `sqljitexpiration`, `sqljitrole`, `ipaddress`, and `operationhistoryid`.

Do not invoke it through MCP `invoke_api` or a bare terminal command: that would display the password. Use the helper below, which invokes the **managed Dataverse CLI** and captures its output in process. No raw HTTP or new authentication flow is needed.

## Request credentials and connect

For interactive chat, use **Reuse access across follow-up reads** below from the
first request, even if the user names only one table. The `connect.py` invocation
in this section is for explicitly selected one-shot execution or an explained,
approved fallback when a persistent owner cannot be kept running.

Resolve `scripts/connect.py` relative to **this skill's directory** (not the workspace). It needs the shared `auth.py` supplied by **dv-connect**, either in the workspace's `scripts/` directory or the plugin's `scripts/` directory. Skill-only/npx installs must finish **dv-connect** helper setup first.

After the approval above, use Python to launch the helper. Replace placeholders with approved non-secret values and the resolved helper path:

```python
import subprocess
import sys

subprocess.run(
    [
        sys.executable, "<resolved-erp-sql-skill-directory>/scripts/connect.py",
        "--environment", "<confirmed-dataverse-url>",
        "--client-ip", "<approved-public-IPv4-or-IPv4-range-or-CIDR>",
        "--reason", "<verbatim-user-provided-access-reason>",
        "--role", "<user-selected-Reader-or-Writer>",
        "--confirm-environment", "<confirmed-dataverse-url>",
    ],
    check=True,
)
```

For approved IP discovery, use `subprocess.run([sys.executable, "<resolved-erp-sql-skill-directory>/scripts/connect.py", "--discover-ip"], check=True)` instead. Do not combine discovery with an automatic grant; confirm the resulting exact IP first.

The one-shot helper rechecks the Dataverse organization and ERP linkage before granting access. It requests the **explicitly selected Reader or Writer role**, validates the returned role/IP and expiry, waits 60 seconds for credential propagation, and launches sqlcmd with the returned server, database, and username. The password is placed only in a child environment; inherited SQLCMD startup/scripting settings are removed. Without a read option it executes only the fixed database/login probe and exits. With `--table` or `--waiting-jobs`, it completes the approved reads before discarding credentials. It never opens an unattended interactive SQL session or accepts arbitrary SQL.

## Reuse access across follow-up reads

Use `scripts/session.py` by default for interactive reads after explicit approval
to retain credentials in a running process; do not require the user to predict
all later table requests. It uses the same preflight, grant, SQL functions, and safeguards as the
one-shot helper; no passwords are persisted or returned to the agent.

Start it in a dedicated terminal or a supported, explicitly approved persistent
background task. Wait for `ready: true`, record its non-secret session ID in
this conversation, and use `read`, `status`, and `close` with that ID.
After a successful read, leave the owner running for follow-up turns and report
the reusable session ID and its idle/expiry limits. Do not put `close` in a
per-read cleanup/finally block or run it before each answer.
Every client supplies the same environment, selected role, and approved IP scope,
and runs from the same workspace. Each later table/count/limit still needs user
approval; do not infer that a grant authorizes arbitrary reads.

The session is local to the current OS user: Windows named pipe or macOS/Linux
Unix-domain socket. It ends on close, JIT expiry, or **15 idle minutes**; only
successful reads reset the idle clock, not status checks. Requests are serialized;
a busy/unavailable session is an explicit error, never a trigger for a new grant.
If the harness cannot keep a process running, explain the limitation and use
one-shot mode with a freshly approved grant instead of writing credentials to disk.
See [reusable SQL sessions](references/sessions.md) for executable invocations,
lifecycle, transport security, and validation limits.

On a propagation-related login failure, it retries the **same** credentials twice, ten seconds apart; it does not request another grant. If SQL reports a firewall failure for one unambiguous IP **inside the approved scope**, allow up to four further retries at 60-second intervals after the initial 60-second wait, checking expiry before each attempt. Azure SQL firewall updates can take up to five minutes to propagate ([Microsoft firewall guidance](https://learn.microsoft.com/en-us/azure/azure-sql/database/firewall-configure)). Out-of-scope, missing, or ambiguous client IPs stop immediately. These retries never widen the scope or request credentials again. Report only non-secret server/database, role, expiry, operation ID, and the verified connection outcome. The local credential reference is released after the subprocess; Python cannot guarantee zeroization of immutable strings, and the server-side grant remains until its returned expiry.

If credentials are absent, report the operation ID and stop. Do not invent polling endpoints or assume the operation completed. Inspect the environment's actual operation-history schema and obtain approval before any follow-up operation.

**Client-IP response format:** the live API can return `ipaddress` as `start-end`, even for a single approved address (for example, `8.8.8.8-8.8.8.8`). The helper normalizes approved CIDRs to explicit inclusive ranges for `sqljitclientipaddress`. Require both returned endpoints to equal the approved bounds exactly; reject broader, narrower, reversed, non-public, or oversized scopes. A single IP and an identical-endpoint range are equivalent. Never disable IP validation to make a connection succeed. A local validation failure after the API call may leave an active grant; disclose that and obtain approval before requesting another one.

## Common mistakes

| Wrong | Correct |
|---|---|
| Requesting this action with `--target erp` | The action is on the linked **Dataverse** environment |
| Inventing a reason or pre-filling the reason form | Explicitly ask for the user's reason with an empty free-text field; submit their confirmed text verbatim |
| Automatically choosing Writer or escalating after a failure | Ask with a Reader/Writer enum and obtain approval for the selected privilege |
| Guessing `GetDatabasePassword` or using an Entra token as the SQL password | Discover `msprov_getfinopssqljitaccessasync`; consume its returned credentials |
| Printing the response or using `sqlcmd -P <password>` | Capture in Python; use child-only `SQLCMDPASSWORD` |
| Using `-C` to make a TLS failure disappear | Fix certificate trust, hostname, or client configuration |
| Assuming `-K ReadOnly` prevents writes | Reader is the read-only grant; Writer grants write capability regardless of client intent |
| Requesting another grant after every login failure | Allow propagation, retry the same credentials within bounds, then report failure |
| Checking only that credentials were returned | Verify sqlcmd's exit code and actual database/login |
| New JIT grant for each metadata/count/data query | Keep one credential response in memory for the entire approved read |
| Retrying propagation only for the initial probe | Apply the same bounded retry/expiry checks to every SQL command |
| Combining `-h -1` with `-y 0` | Use the helper's tested text-preview flags; these options conflict |
| Parsing ordinary sqlcmd output as JSON | Use the text preview; only managed CLI API output is parsed as JSON |

## Read a physical ERP table

For a table request within this SQL workflow, stay in **erp-sql** instead of assuming the physical table is an OData entity. Ordinary business-data reads outside this context still use **dv-query**.

After approving the table read **before** requesting credentials, add `--table BATCH --top 50` (or `--table dbo.BATCH`) to the helper invocation above. Replace `BATCH` with the requested table, not an inferred alternative. `--top` defaults to 50 and supports 1-100. Use Reader unless the user explicitly selects and approves Writer; these reads never need Writer.

The helper verifies the connection, discovers the exact table/schema and columns, omits payload/secret-like/unsupported columns, counts rows, and returns a bounded text preview using one in-memory credential response. It orders by `RECID` ascending when present, otherwise reports no guaranteed ordering. A low-RECID preview is **not** the latest jobs. Report status codes as stored unless their enum mapping is verified.

See [table reads and operational lessons](references/table-reads.md) for the complete reusable invocation, output limits, and failure recovery. No live grants are needed merely to author or test the skill.

For **waiting batch jobs**, obtain approval for `BATCHJOB` schema inspection, a matching count, and up to 100 matching rows, then use `--waiting-jobs --top 100` instead of `--table`. This fixed read uses `STATUS = 1` ([BatchStatus.Waiting](https://learn.microsoft.com/en-us/dotnet/api/microsoft.dynamics.ax.xpp.batchstatus)), checks integer STATUS/RECID columns, and returns only allowlisted summary columns. Both count and preview use the filter. Report the total separately from the bounded RECID-ascending preview; do not claim the preview is complete when the total exceeds its limit.

## Troubleshooting

- **Revoked/expired sign-in:** repair the affected CLI through **dv-connect**, then rerun preflight. Do not inspect token cache files.
- **Missing action or unsupported deployment type:** stop; do not fall back to LCS or invent another endpoint.
- **Permission failure:** report it; do not self-elevate or switch to Writer.
- **Network/firewall failure:** the helper extracts only validated public IP addresses from SQL Server's `Client with IP address '...'` error text, after redacting the password. It compares the SQL-reported address with the approved IP; an HTTP IP-echo result is not proof of SQL egress. If they differ, show the exact SQL-reported IP and ask for approval of a new JIT request with that `--client-ip`, the selected role, and the user's confirmed reason. Do not run HTTP discovery again and substitute its result. If the IP is within the approved scope, investigate propagation or network policy instead of broadening the allowlist. If the IP is missing, invalid, or ambiguous, report the blocker and involve the network administrator; never guess a range or disable TLS. In-scope firewall failures use the bounded propagation retries above; other firewall failures stop immediately. Neither path automatically requests another grant.
- **Expired credentials:** obtain fresh approval before a new request; never reuse expired credentials.
- **Changing SQL egress:** if an approved correction is followed by another SQL-reported IP, stop requesting grants. This demonstrates that a previously observed IP is not a stable connection target for the firewall rule. Ask the network administrator for a fixed SQL egress route or an explicitly approved egress-pool policy; this helper must not infer a subnet, accumulate grants, or repeatedly chase addresses. Resume only with a stable approved IP or a user-approved bounded range covering the egress pool; never expand it automatically.
- **Sanitized command failure:** the helper reports the command, recognized diagnostic code/class, exit code where available, and validated SQL client IP for firewall errors, but intentionally withholds raw output that could contain credentials. Use metadata/auth checks for diagnosis, not credential-response logging.

The sqlcmd password and TLS behavior follow the [Microsoft sqlcmd reference](https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility).

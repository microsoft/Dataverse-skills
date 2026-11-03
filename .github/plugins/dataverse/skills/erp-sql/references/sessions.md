# Reusable, memory-only ERP SQL sessions

Use this workflow by default from the first interactive table request, keeping
the owner available for later approved reads within the same conversation.
It does not reuse the Dataverse MSAL cache for SQL passwords. Dataverse CLI auth
still uses its existing managed cache; temporary SQL credentials live only inside
one running Python owner process.

## Approval and IP range selection

Confirm the environment/linkage, Reader role, exact public IPv4 scope,
user-authored reason, connection probe, and retention in a running process.
Before approval, warn that starting a new owner requests a grant that invalidates
existing SQL credentials for the same user in the same environment, including
credentials used in Visual Studio, SSMS, or another owner. Obtain explicit approval
for this impact; stop if absent or declined. Reusing an existing owner for
`read` or `status` does not request a new grant.

Reader is the only supported role. Ask the user to supply a public IPv4 address
or range/CIDR of at most 256 addresses, without a default or suggested value.
Show the supplied scope's endpoints and address count and obtain explicit approval.
Do not discover an IP, calculate a candidate range, reuse an earlier session's
scope as a default, or recommend a source or command for finding one.
If the user cannot provide a valid scope or declines, stop before starting an owner.
Every client then uses the same user-approved scope recorded at startup.

## Start the owner process once

Complete the skill's action discovery and schema compatibility check before
starting a new owner. Startup does not perform that metadata discovery; stop if
the action or schema cannot be verified, rather than requesting a grant.

**Do not run `session.py start` with `subprocess.run`, `check_call`, `wait`, or
`communicate` in a foreground agent tool call.** The owner intentionally runs
until close, idle timeout, or expiry. A foreground timeout can kill it after a
grant has already invalidated earlier credentials.

Use the host's supported **persistent background-task mechanism**, from the
intended workspace and with approval to retain credentials across turns.
A plain `Popen` is not sufficient when the host cleans up child processes at
tool-call or turn completion. Confirm that the host supports persistence before
launching; do not bypass its detachment approval or use shell tricks.

### Example: Windows host with a persistent PowerShell tool

When the host exposes the `powershell` tool with `mode`, `detach`, and `shellId`
parameters, generate its arguments below. **This Python block only prints a
launch specification; it does not start the owner or request credentials.**
Replace placeholders with the resolved helper path and approved values.

```python
import json
import sys
import uuid

session_id = uuid.uuid4().hex
argv = [
    sys.executable, "-u", "<resolved-erp-sql-directory>/scripts/session.py", "start",
    "--session", session_id,
    "--environment", "<confirmed-dataverse-url>",
    "--confirm-environment", "<confirmed-dataverse-url>",
    "--role", "Reader",
    "--client-ip", "<explicitly-approved-public-IPv4-scope>",
    "--reason", "<verbatim-user-provided-reason>",
]
# PowerShell literal strings preserve spaces, apostrophes, and metacharacters.
command = "& " + " ".join("'" + value.replace("'", "''") + "'" for value in argv)
print(json.dumps({
    "command": command,
    "description": "Start the approved persistent ERP SQL owner",
    "mode": "async",
    "detach": True,
    "shellId": "erp-sql-" + session_id,
}))
```

Submit the emitted object as the **arguments to the host's `powershell` tool**,
not as a shell script. `mode: "async"` returns control without waiting for owner
exit; `detach: true` requests persistence across tool calls and turns. Retain the
returned task handle and the chosen session ID. Do not submit the launch again.

On other hosts, use their documented persistent-background equivalent; do not
assume these parameter names exist. If persistence is unavailable or denied,
use a user-managed dedicated terminal, or explain the limitation and obtain
approval for one-shot access **before requesting a grant**.

### Wait for readiness, not process exit

Startup performs the same preflight, one JIT request, credential validation, and
encrypted database/login probe as `connect.py`. It prints a JSON readiness line
only after the probe succeeds, containing `ready: true`, session ID, process ID,
workspace, environment, role, IP scope, expiration, and idle timeout. No password
or SQL login is included.

- Use bounded reads of the **same background task's captured output**. For the
  PowerShell host, use `read_powershell` with the returned `shellId`; do not wait
  for a completion notification from this long-lived process.
- Inspect successive output lines until a JSON object contains `ready: true`.
  **The first line is not the readiness record:** target, credential-received,
  propagation, and connection messages can precede it. Do not interpret one
  missing readiness line or a still-running task as startup failure.
- Monitor startup for at most ten minutes per monitoring attempt. If readiness
  has not appeared, report startup as pending/unverified and retain the same
  task handle. Do not kill/relaunch the owner or silently fall back to a new
  one-shot grant. Further monitoring uses the same task.
- After readiness, verify the session ID and approved workspace/environment/
  Reader/IP scope, then run `session.py status` to confirm that the owner is
  responsive before a read. Keep it running across turns.
- If the task exits before readiness, report the sanitized failure. Another
  grant requires the invalidation warning, a user-provided reason, and fresh
  explicit approval; an exit or timeout never authorizes a restart.

Retain the task handle and session ID in the conversation, not a credential file.
`--session` accepts a caller-generated 32-character lowercase UUID hex string;
it cannot attach to or replace an existing owner. A duplicate endpoint fails
before requesting a grant. For session clients, use `subprocess.run` only for
the bounded `read`, `status`, and explicit `close` operations below.

## Read table A, then table B using the same grant

Obtain approval for each requested table's schema inspection, count, and preview
limit before invoking a read. Use the same ID and exact scope from readiness,
and run clients from the same workspace as the owner. The environment is checked
again against the session binding, not silently switched.

```python
import subprocess
import sys

helper = "<resolved-erp-sql-directory>/scripts/session.py"
scope = [
    "--session", "<session-id-from-ready-output>",
    "--environment", "<confirmed-dataverse-url>",
    "--role", "Reader",
    "--client-ip", "<explicitly-approved-public-IPv4-scope>",
]
subprocess.run(
    [sys.executable, helper, "read", *scope, "--table", "<first-approved-schema.table>", "--top", "10"],
    check=True,
)
# Run a later, separately approved request with the same scope and session ID.
subprocess.run(
    [sys.executable, helper, "read", *scope, "--table", "<next-approved-schema.table>", "--top", "10"],
    check=True,
)
```

Replace the placeholders with the user's explicitly supplied tables and approved
limits. A read requires `--table`; there are no table-specific modes or business
filters. Do not select a table or start a grant for an entity-discovery question;
use **dv-query** for that request. Reads accept no arbitrary SQL, writes,
credentials, or shell commands. Writer requests and credentials are rejected;
a persistent owner retains only Reader credentials.

## Status, close, expiry, and failure

Check `status` before follow-up reads without extending the idle lifetime:

```python
import subprocess
import sys

helper = "<resolved-erp-sql-directory>/scripts/session.py"
scope = [
    "--session", "<session-id-from-ready-output>",
    "--environment", "<confirmed-dataverse-url>",
    "--role", "Reader",
    "--client-ip", "<explicitly-approved-public-IPv4-scope>",
]
subprocess.run([sys.executable, helper, "status", *scope], check=True)
```

Do **not** close the session after every read or before returning an answer.
Only when the user explicitly asks to close it or the conversation is known to
have ended, run `session.py close` with the same scope arguments. Closing is a
separate lifecycle action, not part of the read/status sequence above.

- Only a successful read resets the **15-minute idle timeout**. Status, rejected
  requests, and failed reads cannot keep a session alive indefinitely.
- JIT expiry is checked before each SQL command and before returning a read.
  Active SQL commands retain their existing finite timeouts; shutdown is not
  instantaneous cancellation or guaranteed zeroization of immutable strings.
- Close the session on an explicit user request or known conversation end, not
  completion of one table request or agent turn. A terminal/process shutdown
  also releases local credentials. A background owner otherwise remains until
  idle timeout or expiry: it does not magically detect a chat ending.
- Closure does **not** revoke the server-side grant. Disclose its expiry; do not
  claim to revoke access or automatically obtain replacement credentials.
- A failed read does not itself destroy a still-valid session. Inspect the safe
  error/status; do not automatically regrant, expand IPs, or change roles.
- Requests are serialized. A second client may time out waiting for a busy pipe;
  no automatic reconnect/read replay occurs. After an interrupted response,
  report that the read may have run rather than claiming success.
- If the owner exits/crashes, a later command fails explicitly. Do not recover
  credentials from files, memory dumps, logs, or token caches. A new owner needs
  the credential-invalidation warning and fresh explicit approval for a grant,
  even after idle timeout or expiry: the same user may now be using newer
  credentials in Visual Studio, SSMS, or another session.

**Propagation retry limits (both helpers):** after the initial 60-second wait,
retry propagation-related login failures twice, ten seconds apart, using the
same credentials. For a firewall failure reporting one unambiguous IP inside
the approved scope, allow up to four further retries at 60-second intervals.
Check credential expiry before each attempt. Azure SQL firewall changes can take
up to five minutes to propagate ([Microsoft firewall guidance](https://learn.microsoft.com/en-us/azure/azure-sql/database/firewall-configure)).
Out-of-scope, missing, or ambiguous client IPs stop immediately. Neither retry
path widens the approved scope or requests another grant. These limits apply to
every SQL command, not just the initial probe.

Local credential references are released when the owner or one-shot helper exits;
Python cannot guarantee zeroization of immutable strings. Local exit does not
revoke the server-side grant, and closing an owner does not restore credentials
invalidated by its grant.

## Local transport and security boundary

Windows uses a local named pipe with a protected current-user-only DACL, remote
clients rejected, first-instance protection, and non-inheritable handles. The
client verifies the server runs as the same Windows user and opens the pipe with
identification-only security quality of service, not impersonation permission.

macOS/Linux use a Unix-domain socket beneath a current-user-owned mode-0700
temporary directory, with mode-0600 socket permissions. Symlinked directories,
incorrect owners/modes, and existing endpoints are refused. Normal shutdown
removes the socket; a forced kill may leave a non-secret stale socket. Use a
fresh ID after confirming the old owner exited; do not delete broad directories.

The shared interface uses length-bounded UTF-8 JSON, **not pickle**, and accepts
only read/status/close operations. It has request/response deadlines and output
limits, and never listens on TCP. No SQL credentials or IPC authentication
secrets are written to disk; socket paths and session IDs are non-secret metadata.

This is an **OS-user boundary**, not isolation from other processes belonging
to that user or from administrators/root. A session ID is not a password. Bindings
prevent accidental cross-workspace/environment reuse, not malicious same-user
code. The agent must not enumerate or attach to other conversations' sessions.
The password is passed only in each sqlcmd child's environment; never set a
PowerShell-global password or store it in an agent-visible variable.

## Validation

Hermetic tests exercise two separate client processes against one owner and one
simulated grant, Unicode output, redaction, lifecycle/binding validation, bounded
messages, and local transport permissions. The CI matrix runs the ERP SQL suite
on Windows, macOS, and Linux. Passing Windows tests is not evidence that the
other two host runs have passed.

A real validation requires a newly approved grant and two separately approved
reads through the same session ID. Record the host, harness, model if known,
readiness, outcomes, and whether the harness retained the owner process. Do not
record the password or invent cross-harness results. The older one-shot live
tests do not establish that reusable sessions work in every harness.

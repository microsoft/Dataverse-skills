# Reusable, memory-only ERP SQL sessions

Use this workflow for separate approved table reads within the same conversation.
It does not reuse the Dataverse MSAL cache for SQL passwords. Dataverse CLI auth
still uses its existing managed cache; temporary SQL credentials live only inside
one running Python owner process.

## Approval and IP range selection

Confirm the environment/linkage, Reader or Writer role, exact public IPv4 scope,
user-authored reason, connection probe, and retention in a running process.
Reader is sufficient for all supported reads. Ask for the customer's known
egress range first. If unknown, obtain permission to contact the IP-echo service,
then invoke the following discovery-only command:

```python
import subprocess
import sys

subprocess.run(
    [sys.executable, "<resolved-erp-sql-directory>/scripts/connect.py",
     "--discover-ip", "--suggest-range"],
    check=True,
)
```

Show `observed_http_ipv4`, `suggested_range`, `address_count`, and the warning.
Offer the eight-address `/29` candidate, a customer-supplied public IPv4
range/CIDR of at most 256 addresses, or a single IPv4. Only submit the explicitly
accepted scope. This is arithmetic around one observed address, not detection
of a NAT pool; HTTP and SQL may use different egress, and nearby addresses can
belong to other users. Never silently retry a grant with the candidate.

## Start the owner process once

Run from the intended workspace in a dedicated terminal, or a harness-managed
persistent background task with user approval. The `start` command stays in the
foreground; it does not secretly detach. Do not treat a still-running command
as a failure or relaunch it. Use the harness's supported persistent/detached-task
facility if the session must survive the current agent turn. If that facility is
unavailable, use the dedicated terminal or explain the one-shot limitation.

```python
import subprocess
import sys

subprocess.run(
    [sys.executable, "<resolved-erp-sql-directory>/scripts/session.py", "start",
     "--environment", "<confirmed-dataverse-url>",
     "--confirm-environment", "<confirmed-dataverse-url>",
     "--role", "Reader",
     "--client-ip", "<explicitly-approved-public-IPv4-scope>",
     "--reason", "<verbatim-user-provided-reason>"],
    check=True,
)
```

Startup performs the same preflight, one JIT request, credential validation, and
encrypted database/login probe as `connect.py`. It prints a JSON readiness line
only after the probe succeeds, containing `ready: true`, session ID, process ID,
workspace, environment, role, IP scope, expiration, and idle timeout. No password
or SQL login is included. Retain the session ID in the conversation, not a
credential file. An optional `--session` on start accepts a caller-generated
32-character lowercase UUID hex string; it cannot attach to or replace an
existing owner. A duplicate endpoint fails before requesting a grant.

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
    [sys.executable, helper, "read", *scope, "--table", "dbo.BATCH", "--top", "10"],
    check=True,
)
# Run a later, separately approved request with the same scope and session ID.
subprocess.run(
    [sys.executable, helper, "read", *scope, "--table", "dbo.BATCHJOB", "--top", "10"],
    check=True,
)
```

Replace the example table names with the customer's actual requested tables.
`--waiting-jobs` is also supported instead of `--table`, with the existing fixed
BATCHJOB/STATUS=1 query and allowlisted summary columns. Neither mode accepts
arbitrary SQL, writes, credentials, or shell commands. Writer credentials remain
read-only through this interface.

## Status, close, expiry, and failure

Use `status` and `close` with the same scope arguments:

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
subprocess.run([sys.executable, helper, "close", *scope], check=True)
```

- Only a successful read resets the **15-minute idle timeout**. Status, rejected
  requests, and failed reads cannot keep a session alive indefinitely.
- JIT expiry is checked before each SQL command and before returning a read.
  Active SQL commands retain their existing finite timeouts; shutdown is not
  instantaneous cancellation or guaranteed zeroization of immutable strings.
- Close the session when the task/conversation ends. A terminal/process shutdown
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
  new explicit approval for a grant.

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

# Safety & Guardrails

How the Dataverse plugin protects your data, respects your permissions, and keeps you in control.

---

## Supported Operations

| Category | Operations | Notes |
|---|---|---|
| **Read / Query** | Query records, describe tables and columns, list tables, keyword search, explore schema metadata | Always available to any authenticated user with read privileges |
| **Create** | Create records, tables, columns, relationships, forms, views | Requires appropriate Dataverse security role |
| **Update** | Update records, modify schema, edit forms and views | Requires appropriate Dataverse security role |
| **Import / Export** | CSV import with lookup resolution, solution export and import, bulk data operations | Agent chunks large imports (SDK does not auto-batch); upsert with alternate keys recommended for idempotent re-runs |
| **Delete** | Delete records, tables, columns, relationships | Requires appropriate Dataverse security role |

## Authentication

The plugin supports two authentication methods:

### Interactive login (recommended for developers)

- Uses Azure Identity **device code flow** — you sign in via your browser
- Tokens are cached in your OS credential store (Windows Credential Manager, macOS Keychain, or Linux libsecret)
- Silent token refresh on subsequent sessions — no repeated sign-in prompts
- Tokens are scoped to the specific Dataverse environment

### Service principal (recommended for CI/CD)

- Uses client ID and client secret for non-interactive authentication
- Tokens are held in memory only — not persisted to disk
- Configured via environment variables

### Multi-layer MCP authorization

Access to Dataverse through MCP specifically requires three independent authorization layers. Note: other tools used by the plugin (Python SDK, Web API, PAC CLI) authenticate directly and are not subject to these MCP-specific controls.

| Layer | Who approves | When | What it controls |
|---|---|---|---|
| **Developer auth** | Developer (you) | First use, then cached | Can this person access Dataverse? |
| **Tenant admin consent** | Global Admin | One-time per tenant | Can MCP clients be used in this tenant? |
| **Environment allowlist** | Environment Admin | One-time per environment | Can MCP clients be used in this specific environment? |

Each layer can be independently revoked without affecting the others.

## Least-Privilege & Security Role Enforcement

The plugin **cannot exceed the permissions of the authenticated user**. Dataverse data operations respect the caller's Dataverse security roles:

- **Read access** is determined by entity-level read privileges
- **Write access** is determined by entity-level create, update, and delete privileges
- **Field-level security** is applied automatically
- **Ownership-based sharing** is respected
- If the caller lacks permission, the operation fails with a clear error — the plugin does not attempt to bypass or escalate

Role enforcement is handled server-side by Dataverse itself. The plugin is a passthrough — it adds guidance and guardrails, but authorization decisions are made by the platform.

Direct ERP SQL reads are a separate authorization path: they use temporary SQL
Reader credentials, not Dataverse record-level security, field security, or sharing.
See [ERP SQL credentials, firewall scope, and query data](#erp-sql-credentials-firewall-scope-and-query-data).

## Confirmation & Approval Steps

Safety is enforced at two levels: **platform-level** controls that are always on, and **agent-level** guardrails defined in the plugin's skill instructions that guide Claude and Copilot behavior.

### Platform-level (always enforced)

- **Dataverse security roles** — every Dataverse API call is authorized server-side by Dataverse (see [Least-Privilege](#least-privilege--security-role-enforcement) above).
- **Multi-layer MCP authorization** — MCP access requires developer auth, tenant admin consent, and per-environment allowlisting (see [Authentication](#authentication) above). Other plugin tools (SDK, Web API, PAC CLI) authenticate directly and are not subject to these controls.

### Agent-level (guardrails in skill instructions)

The plugin's skill definitions instruct AI agents (Claude, Copilot) to follow these confirmation steps. These are not hard-coded gates in the proxy — they are behavioral rules the agent follows from the skill instructions.

#### 1. Environment confirmation

Before the first operation that touches a specific environment, the agent:

1. Shows the environment URL you are about to modify
2. Asks for explicit confirmation: *"I'm about to make changes to `<environment URL>`. Is this the correct target environment?"*
3. Runs `pac org who` to verify the active connection matches
4. **Does not proceed until you explicitly confirm**

Once confirmed for an environment in a session, re-confirmation is not required for subsequent operations against that same environment.

The ERP SQL skill instead verifies the confirmed organization and linked ERP
environment with targeted `dataverse org who`. Each new SQL grant requires its
own approval, including the credential-invalidation warning described below.

#### 2. Solution confirmation (before schema changes)

Before creating tables, columns, or forms, the agent asks which solution the components should belong to. Creating metadata outside a solution means components cannot be cleanly exported or deployed.

#### 3. Publisher prefix confirmation

Publisher prefixes are permanent on all components. The agent queries existing publishers in your environment and asks you to choose before proceeding.

## Irreversible Operations

Some operations require extra care because they are difficult or impossible to reverse:

| Operation | Risk | Safeguard |
|---|---|---|
| Table deletion | Cascades to columns, forms, views, and plugins | Platform requires appropriate security role; no agent-level confirmation currently implemented |
| Environment deletion | Permanent | Requires admin permissions via PAC CLI (platform-enforced) |
| Solution import to production | Affects all users in the environment | Post-import validation queries provided by skill to verify components are live (skill-enforced) |
| Bulk operations | Affects many records at once | Skills instruct agent to use upsert with alternate keys (idempotent — safe to re-run); agent chunks into batches with adaptive sizing (skill-enforced) |
| Publisher prefix creation | Prefix is permanent on all components | Agent must ask user before creating; skills enforce mandatory confirmation (skill-enforced) |

## Data Handling & Residency

### Token security

- Interactive login tokens: stored in your OS native credential store
- Service principal tokens: held in memory only, never persisted
- Tokens are scoped to your Dataverse environment and are not passed to external services

### ERP SQL credentials, firewall scope, and query data

The `erp-sql` skill is an explicit opt-in path for UDEs reporting
`ErpDeploymentType = OnlineDev`. It requires the environment System administrator
role, but requests only SQL **Reader** credentials. USEs, Writer grants, and direct
SQL writes are not supported by these helpers.

**No IP discovery or range suggestions:** the user must supply the public IPv4
address or range/CIDR to authorize. The skill does not contact an IP-lookup service,
discover an address through another source, propose a range, or direct the user
to lookup tools or services. If the user cannot supply a valid scope, the agent
stops. Ranges must contain at most 256 public IPv4 addresses; every address between
the approved endpoints is included. CIDR normalization preserves that exact span.
SQL-reported IPs are failure diagnostics for checking the approved scope, not a
source for a replacement scope.

**Grant and firewall effects:** the helper sends the user-supplied IP scope,
Reader role, and verbatim access reason to the confirmed Dataverse environment
through the managed CLI. The request creates temporary SQL access and configures
the SQL firewall even though subsequent queries only read data. Before requesting
each grant, the agent must disclose that it invalidates existing SQL credentials
for the same user/environment, including those used in Visual Studio, SSMS, or
another SQL session, and obtain explicit approval. This warning and consent step
is an agent instruction, not an interactive gate in the Python helper. The helper
validates inputs and returned role/IP/expiry, but cannot verify that consent occurred.
It never automatically renews a grant or broadens its IP scope. A failed local
validation or connection does not undo a grant that already occurred.

**Credential handling:** SQL credentials are captured in process memory, never
printed or written to credential files. The password is passed only through the
sqlcmd child's `SQLCMDPASSWORD` environment, not command-line arguments. The helper
does temporarily write the non-secret request body (reason, role, and IP scope)
to a local file, which is removed when the request scope exits. SQL connections
require encryption and certificate validation. A reusable session retains its
credentials in the owner process until explicit close, expiry, or 15 minutes
without a successful read; this is an OS-user boundary, not isolation from other
processes under that user or administrators. Python cannot guarantee memory
zeroization. Local close does not revoke the server-side grant or restore
credentials invalidated by that grant.

**Data handling and residency:** approved bounded SQL results travel from the ERP
database to the machine running the helper and may appear in the agent conversation.
They are not confined to the database's region after being returned. Apply the
organization's data-access, host, transcript retention, and residency requirements.
The helper omits secret-like and unsupported columns and redacts the SQL password,
but these filters are not a complete sensitive-data classifier. Grant requests and
SQL access remain subject to the applicable platform and tenant audit policies;
no separate IP-discovery endpoint receives the user's IP.

## Logging & Auditability

### Client-side logging (local to your machine)

The MCP proxy and Python SDK produce logs that stay on your machine:

- Tool execution calls and authentication flow events
- HTTP request metadata (URLs, status codes)
- Errors and validation failures
- Log verbosity is configurable (Trace, Debug, Information, Warning, Error, Critical)
- Optional file logging to your local temp directory via `--log-file`

Client-side logs do **not** capture customer data records, credentials, or personal information.

### Server-side logging (Dataverse platform)

Dataverse API calls reach Dataverse via HTTP. Once a request hits Dataverse, it is subject to your tenant's standard audit and telemetry policies — the same as any other Dataverse client (model-driven apps, Power Automate, direct API calls). The plugin does not add any additional server-side logging beyond what Dataverse records by default. Direct ERP SQL queries use the SQL connection instead, as described above.

For details on Dataverse auditing, see [Microsoft's auditing documentation](https://learn.microsoft.com/en-us/power-platform/admin/manage-dataverse-auditing).

## Telemetry

The plugin may add an application identifier to its outbound Dataverse requests so server-side dashboards can attribute traffic. The identifier carries plugin / version / skill / agent labels — application-level metadata only, not personal data. Prompts, tool arguments, record data, file contents, and command strings are not transmitted.

## Areas Under Exploration

This document describes the safety model as it exists today. We are exploring ways to further harden the experience, such as environment-tier awareness and improved handling of Dataverse service protection limits. Because the plugin operates through AI agents that we do not fully control, some guardrails can only be influenced via skill instructions rather than enforced deterministically.

If you have feedback on what guardrails matter most to you, [open an issue](https://github.com/microsoft/Dataverse-skills/issues).

## Privacy

This plugin operates under the [Microsoft Privacy Statement](https://go.microsoft.com/fwlink/?LinkId=521839). For security concerns, see [SECURITY.md](../SECURITY.md).

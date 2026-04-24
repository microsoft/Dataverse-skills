---
name: dv-security
description: >
  Assign security roles, manage user access, and handle admin self-elevation in Dataverse environments.
  Use when: "assign role", "system admin", "security role", "give me admin role",
  "assign system administrator", "role assignment", "make me admin",
  "self-elevate", "admin access", "assign user", "application user",
  "business unit", "who has access", "user permissions".
  Do not use when: creating or modifying tables (use dv-metadata),
  managing org settings or audit (use dv-admin),
  tenant governance like DLP (use pac admin --help).
---

# Skill: Security — Role Assignment and Self-Elevation

**This skill uses PAC CLI exclusively.** Do NOT write Python scripts for role operations.

## Preview Before Running

Role grants and self-elevate are destructive (they change security posture and are logged to Purview). Before running, preview the action in plain prose — target user, role, environment(s) — using placeholders (`<ENV_URL>`, `<USER_EMAIL>`) for anything unknown, and ask for confirmation and missing values in the same turn. Skip the raw `pac admin` block; the user shouldn't have to read CLI syntax to approve a security change.

**Key principle:** the user should be able to evaluate what's about to happen from your first response. A bare *"which environment?"* fails that test; a one-line prose preview passes it.

### Examples

<example operation="assign role (user given, env missing)">
<user>Assign System Administrator role to user@contoso.com</user>
<bad>Which environment should I target?</bad>
<good>I'll assign **System Administrator** to `user@contoso.com` on `<ENV_URL>`. Confirm to proceed and provide the target environment URL (or "all" to list and batch).</good>
</example>

<example operation="admin access across all environments">
<user>Give me admin access on all my environments</user>
<bad>Please provide your email address.</bad>
<good>I'll list your environments, then assign **System Administrator** in parallel on each one for `<YOUR_UPN>`. If `assign-user` fails on any environment, I'll fall back to self-elevate (logged to Purview) for that one. Confirm to proceed and provide your UPN.</good>
</example>

## Skill boundaries

| Need | Use instead |
|---|---|
| Create or modify tables, columns, relationships | **dv-metadata** |
| Manage org settings, audit, bulk delete, retention | **dv-admin** |
| Query or read records | **dv-query** |
| Write, update, or delete records | **dv-data** |
| Tenant-level governance (DLP, env lifecycle) | `pac admin --help` |

## Prerequisites

- PAC CLI installed and authenticated (`pac auth create`)
- System Administrator role in target environment (or Global/PP/D365 Admin for self-elevate)
- Active auth profile: `pac auth list`

---

## Assign a Security Role to a User

```bash
pac admin assign-user --user <email-or-object-id> --role "System Administrator" --environment <url>
```

### Arguments

| Argument | Alias | Required | Description |
|----------|-------|----------|-------------|
| `--user` | `-u` | Yes | User email (UPN) or Azure AD object ID |
| `--role` | `-r` | Yes | Security role name (e.g., `System Administrator`, `Basic User`) |
| `--environment` | `-env` | Yes | Target environment URL or ID |
| `--application-user` | `-au` | No | Treat user as an application user (service principal) |
| `--business-unit` | `-bu` | No | Business unit ID. Defaults to the caller's business unit |

---

## Batch Workflow: Assign Role Across Multiple Environments

Run in parallel — never sequentially:

```
Step 1: pac admin list                                              -> Get all environments
Step 2: Filter by type if needed (e.g., Developer, Sandbox)        -> Identify targets
Step 3: Confirm with user — show list of target environments
Step 4: Run ALL assignments in a single bash call:
```

```bash
pac admin assign-user --user user@contoso.com --role "System Administrator" --environment https://dev1.crm.dynamics.com &
pac admin assign-user --user user@contoso.com --role "System Administrator" --environment https://dev2.crm.dynamics.com &
pac admin assign-user --user user@contoso.com --role "System Administrator" --environment https://dev3.crm.dynamics.com &
wait
```

```
Step 5: Report summary ("Assigned System Administrator on 3/3 environments")
```

**Important**: Always confirm which environments will be affected before assigning roles.

---

## Tenant Admin Self-Elevation (Fallback)

**Self-elevation is materially different from assigning a role to another user.** `pac admin assign-user <other>` grants privilege *to someone else*; `pac admin self-elevate` grants privilege *to the caller*. The risk profile and audit posture are different, so the confirmation protocol is stricter.

If `pac admin assign-user` fails with "user has not been assigned any roles", use:

```bash
pac admin self-elevate --environment https://myorg.crm.dynamics.com
```

- Requires Global Admin, Power Platform Admin, or Dynamics 365 Admin
- All elevations are logged to Microsoft Purview
- Uses the active auth profile if `--environment` is omitted

### Self-elevation confirmation protocol (stricter than assign-user)

Before running `pac admin self-elevate`, the agent MUST:

1. **State the risk explicitly.** Include this wording (or equivalent) in the pre-run summary:
   > "This grants YOU System Administrator on `<env>`. The action is logged to Microsoft Purview with your identity and timestamp."
2. **Capture a reason.** Ask for a one-line reason — ticket ID, incident number, or a free-form note such as `"dev sandbox access — no ticket"`. Echo the reason back in the pre-run summary so the user sees what will be on the record.
3. **Wait for an explicit confirmation AFTER the user has seen both (1) and (2).** Do NOT accept a bare "yes" given before the risk statement and reason are on screen.
4. **Do NOT silently fall back.** If `pac admin assign-user` fails, surface the failure first, then offer `self-elevate` with this protocol — never chain them automatically.

**Flow**: Always try `pac admin assign-user` first. `admin self-elevate` is the documented fallback, gated by the protocol above.

**CLI fallback**: If `pac admin self-elevate` errors out, self-elevate manually via **Power Platform Admin Center** → select the environment → **Access** → **System Administrator role**. All elevations are still logged to Purview. (In PAC CLI 2.6.4 the command fails with `bolt.authentication.http.AuthenticatedClientException` / `ApiVersionInvalid` because the CLI sends an empty `api-version=` to the backend.)

---

## Safety Rules

- **Always confirm** before assigning System Administrator role
- Show the list of target environments before batch operations
- Self-elevation is logged and auditable — warn the user


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

If `pac admin assign-user` fails with "user has not been assigned any roles", use:

```bash
pac admin self-elevate --environment https://myorg.crm.dynamics.com
```

- Requires Global Admin, Power Platform Admin, or Dynamics 365 Admin
- All elevations are logged to Microsoft Purview
- Uses the active auth profile if `--environment` is omitted

**Flow**: Always try `pac admin assign-user` first. Only use `admin self-elevate` as fallback.

**Fallback**: If `pac admin self-elevate` errors out, self-elevate manually via **Power Platform Admin Center** → select the environment → **Access** → **System Administrator role**. All elevations are still logged to Purview. (In PAC CLI 2.6.4 the command fails with `bolt.authentication.http.AuthenticatedClientException` / `ApiVersionInvalid` because the CLI sends an empty `api-version=` to the backend.)

---

## Safety Rules

- **Always confirm** before assigning System Administrator role
- Show the list of target environments before batch operations
- Self-elevation is logged and auditable — warn the user

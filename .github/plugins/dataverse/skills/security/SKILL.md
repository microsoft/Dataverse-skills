---
name: dataverse-security
description: >
  Add users to a Dataverse environment and assign or modify security roles.
  WHEN: "add user", "assign role", "security role", "list roles", "user permissions",
  "system administrator", "system customizer".
  DO NOT USE WHEN: creating tables/columns (use dataverse-metadata),
  importing solutions (use dataverse-solution), setting up CI/CD service principals (use dataverse-cicd).
---

# Skill: Security

Add users to a Dataverse environment and manage security role assignments.

## Add a User and Assign a Role (Happy Path)

```
pac admin assign-user \
  --environment <url> \
  --user <email@domain.com> \
  --role "<Security Role Name>"
```

Role name examples: `"System Administrator"`, `"Sales Manager"`, `"Salesperson"`, `"System Customizer"`

If this succeeds, you're done.

## If the User Isn't Provisioned Yet

PAC CLI requires the user to exist as a system user in the environment. If the assign-user command fails with a "user not found" error, run the provisioning script:

```
python scripts/assign-user.py <email@domain.com> "<Security Role Name>"
```

This script:
1. Acquires a Web API token via Azure Identity
2. Triggers AAD user sync by querying `/api/data/v9.2/systemusers`
3. Waits for the user to appear
4. Assigns the role via Web API

## List Security Roles

```
pac solution list-roles --environment <url>
```

Or query via Web API:
```
GET /api/data/v9.2/roles?$select=name,roleid&$orderby=name
```

## Verify Role Assignment

Use the Python SDK to check the user's roles:

```python
pages = client.records.get(
    "systemuser",
    filter="internalemailaddress eq '<email>'",
    expand=["systemuserroles_association"],
    select=["fullname", "internalemailaddress"],
    top=1,
)
users = [u for page in pages for u in page]
if users:
    roles = [r["name"] for r in users[0].get("systemuserroles_association", [])]
    print(f"Roles for {users[0]['fullname']}: {', '.join(roles)}")
```

## Notes

- Users must have a valid AAD/Entra account in the tenant before they can be added to a Dataverse environment.
- Security roles are environment-specific. A role in one environment does not carry to another.
- The `System Administrator` role grants full access and should be used sparingly. Use `System Customizer` for developers who don't need data access.
- Business unit assignment defaults to the root business unit. Pass `--business-unit` to `pac admin assign-user` to place the user in a specific BU.

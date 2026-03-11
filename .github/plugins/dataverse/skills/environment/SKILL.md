---
name: dataverse-environment
description: >
  Create, list, select, and delete Power Platform environments using PAC CLI.
  USE WHEN: "create environment", "new environment", "list environments", "delete environment",
  "provision environment", "sandbox", "developer environment", "switch environment".
  DO NOT USE WHEN: initializing a workspace (use dataverse-init),
  deploying solutions (use dataverse-solution).
---

# Skill: Environment

Manage Power Platform environments via PAC CLI.

## Create an Environment

```
pac admin create \
  --name "<DisplayName>" \
  --type Sandbox \
  --region unitedstates \
  --currency USD \
  --language 1033
```

**Type values:** `Sandbox`, `Production`, `Trial`, `Developer`
**Region values:** `unitedstates`, `europe`, `asia`, `australia`, `india`, `japan`, `canada`, `southamerica`, `unitedkingdom`, `france`, `germany`, `unitedarabemirates`, `southafrica`, `switzerland`, `norway`, `korea`
**Language:** 1033 = English (US)

After running, the command returns an environment ID. The environment takes 2–5 minutes to provision.

## Poll for Readiness

```
pac org list
```

Repeat until the new environment appears with `State: Ready`. The URL column contains the environment URL needed for all subsequent operations.

## Select an Active Environment

```
pac org select --environment <url-or-id>
```

Once selected, PAC CLI commands that take `--environment` will default to this org. Recommended: always pass `--environment` explicitly to avoid ambiguity.

## List Environments

```
pac admin list
```

## Delete an Environment

```
pac admin delete --environment <url-or-id>
```

This is irreversible. Confirm with the user before running.

## Notes

- Environment URLs follow the pattern `https://<org-name>.crm.dynamics.com` (US) or regional variants like `.crm4.dynamics.com` (EMEA).
- After creating an environment, update the `DATAVERSE_URL` in `.env`.
- Sandbox environments can be reset (wiped) via `pac admin reset --environment <url>`.

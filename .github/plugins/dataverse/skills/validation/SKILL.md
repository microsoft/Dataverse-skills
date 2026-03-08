---
name: dataverse-validation
description: Validate that solution components are live after import. Use this after deploying changes to confirm tables, forms, views, and role assignments are correct.
---

# Skill: Validation

Verify that solution components are live and correctly configured after import.

## Run All Checks

```
python scripts/validate.py --all
```

## Individual Checks

**Confirm a table exists and is active:**
```
python scripts/validate.py --check-entity <logical_name>
```
Example: `python scripts/validate.py --check-entity new_projectbudget`

**Confirm a form is published:**
```
python scripts/validate.py --check-form <entity_logical_name> <form_type>
```
Form type values: `main`, `quickcreate`, `card`, `quickview`

**Confirm a view exists:**
```
python scripts/validate.py --check-view <entity_logical_name> "<View Name>"
```

**Confirm a user's role assignment:**
```
python scripts/validate.py --check-role <email@domain.com> "<Security Role Name>"
```

**Read import job errors (run after a failed import):**
```
python scripts/validate.py --import-errors
```

## Direct Web API Queries

If you need to query Dataverse directly without the script, use these patterns. First acquire a token (see `auth.py`).

**Check entity exists:**
```
GET <env_url>/api/data/v9.2/EntityDefinitions?$filter=LogicalName eq '<logical_name>'&$select=LogicalName,DisplayName,IsCustomEntity
```

**Check form is published:**
```
GET <env_url>/api/data/v9.2/systemforms?$filter=objecttypecode eq '<entity_logical_name>' and type eq <form_type_code>&$select=name,iscustomizable,formid
```
Form type codes: `2` = main, `7` = quick create

**Check view exists:**
```
GET <env_url>/api/data/v9.2/savedqueries?$filter=returnedtypecode eq '<entity_logical_name>'&$select=name,savedqueryid,statuscode
```

**Check role assignment:**
```
GET <env_url>/api/data/v9.2/systemusers?$filter=internalemailaddress eq '<email>'&$expand=systemuserroles_association($select=name)&$select=fullname,internalemailaddress
```

## Notes

- Web API base URL is the environment URL from `.env`.
- All Web API calls require a Bearer token. Use `auth.py` to acquire one.
- After import, forms may need to be published. If a form check fails immediately after import, wait 30 seconds and retry — publishing can be async.

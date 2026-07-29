# Detecting and validating ERP (Finance and Operations) linkage

On ERP-linked Dataverse environments, ERP is provisioned on top of the same Dataverse env. After Step 2 resolves `DATAVERSE_URL`, detect whether an ERP endpoint is also linked.

## Detection (Step 2 follow-up)

Try PAC first:

```
pac org who
```

If the output surfaces an `erpUrl` field, capture it.

If PAC does not surface it, fall back to the Dataverse CLI:

```
dataverse org who --environment <DATAVERSE_URL> --json
```

Pass `--environment` explicitly — the Dataverse CLI keeps its own active profile separate from PAC's, and without it `org who` may target a stale URL. Reuse the `DATAVERSE_URL` resolved earlier.

A non-null `erpUrl` / `ErpUrl` in either output is the ERP endpoint. In Step 3, when writing `.env`, append `ERP_URL=<value>` so `--target erp` routing works. If neither surfaces it, the env is Dataverse-only — skip `ERP_URL`.

```python
# inside the .env-writing block in Step 3
if erp_url:
    f.write(f"ERP_URL={erp_url}\n")
```

## Smoke test (Step 5 follow-up)

If `.env` has `ERP_URL`, also smoke-test the ERP linkage:

```
dataverse data query --target erp --table Currencies --top 1
```

A successful one-row response proves the active auth profile can reach the ERP OData endpoint. If this fails but the Dataverse-side checks pass, the user's account likely lacks ERP access — surface that explicitly rather than re-running Steps 1–4.

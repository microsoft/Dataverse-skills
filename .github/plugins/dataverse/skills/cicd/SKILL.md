---
name: dataverse-cicd
description: Set up GitHub Actions to auto-deploy Dataverse solutions on merge to main. Covers app registration, service principal, GitHub secrets, and workflow file creation.
---

# Skill: CI/CD Setup

Wire up a GitHub Actions workflow that automatically deploys the solution on merge to `main`.

**Important:** The app registration, service principal, and environment permission grant must all be in the **same AAD tenant as your Dataverse environment**. Before starting, verify:
```
az account show --query '{tenant:tenantId, account:user.name}' -o table
```
If the tenant shown does not match your Dataverse environment's tenant, run:
```
az login --tenant <DATAVERSE_TENANT_ID>
```
Then re-run the account show check before proceeding.

---

## Step 1: Create an app registration

```
az ad app create --display-name "<repo-name>-deploy"
```

Note the `appId` (client ID) from the output.

---

## Step 2: Create a client secret

```
az ad app credential reset --id <appId> --years 2
```

Note the `password` (client secret) — shown only once. Also note the `tenant` value.

---

## Step 3: Create a service principal

```
az ad sp create --id <appId>
```

---

## Step 4: Grant access to the Dataverse environment

```
pac admin assign-user \
  --environment <DATAVERSE_URL> \
  --user <appId> \
  --role "System Administrator" \
  --application-user
```

`System Administrator` is required — lesser roles will cause silent import failures.

If this fails, verify that `pac auth list` shows an active profile connected to the same tenant as the environment. Run `pac org who` to confirm.

---

## Step 5: Update .env with service principal credentials

Add to `.env` (do not commit):
```
CLIENT_ID=<appId>
CLIENT_SECRET=<password>
TENANT_ID=<tenant>
```

With these set, all scripts (`auth.py`, `validate.py`, `assign-user.py`) and `pac auth create --kind ServicePrincipal` will authenticate non-interactively. No browser required.

---

## Step 6: Set GitHub secrets

```
gh secret set POWERPLATFORM_TENANT_ID --body "<TENANT_ID>"
gh secret set POWERPLATFORM_CLIENT_ID --body "<CLIENT_ID>"
gh secret set POWERPLATFORM_ENVIRONMENT_URL --body "<DATAVERSE_URL>"
gh secret set POWERPLATFORM_SOLUTION_NAME --body "<SOLUTION_NAME>"
```

For the client secret, prompt the user to paste — do not pass inline:
```
gh secret set POWERPLATFORM_CLIENT_SECRET
```

Verify all secrets are set before pushing the workflow:
```
gh secret list
```
Confirm all five names appear: `POWERPLATFORM_TENANT_ID`, `POWERPLATFORM_CLIENT_ID`, `POWERPLATFORM_CLIENT_SECRET`, `POWERPLATFORM_ENVIRONMENT_URL`, `POWERPLATFORM_SOLUTION_NAME`.

**Do not push the workflow file until all five secrets are confirmed.**

---

## Step 7: Deploy the workflow file

```
mkdir -p .github/workflows
cp <plugin-path>/templates/deploy.yml .github/workflows/deploy.yml
git add .github/workflows/deploy.yml
git commit -m "chore: add Power Platform deploy workflow"
git push
```

---

## Step 8: Verify

```
gh run list --workflow=deploy.yml
```

The first run triggers on the push in step 7. Report the run URL. If it fails, run:
```
gh run view <run-id> --log-failed
```

---

## Notes

- The client secret expires after 2 years. When it expires, re-run steps 2 and 5–6.
- For multiple target environments (dev → test → prod), repeat steps 1–6 with different secret name suffixes (e.g., `POWERPLATFORM_TEST_*`).
- If Conditional Access policies block service principal access, the tenant admin needs to create an exclusion. This is outside CLI scope.

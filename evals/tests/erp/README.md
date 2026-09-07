# ERP eval suites

These suites provide a read-only passing baseline for Dataverse skill surfaces that can be exercised without requesting or executing a Finance and Operations mutation. The active set contains four tests, and every test declares `"safety_tier": "read-only"`.

| File | Skill surface | Coverage |
|---|---|---|
| `dv_query.biceval.json` | `dv-query` | ERP composite-key read |
| `dv_admin.biceval.json` | `dv-admin` | ERP batch listing and local filtering |
| `dv_overview.biceval.json` | `dv-overview` | ERP business-data read routing |

> ## Safety and fixture requirements
>
> The active suite must not request or execute create, update, delete, import, deploy, synchronize, cancel, install, uninstall, or potentially mutating ERP actions. Mutation coverage and read-only scenarios that did not pass the compatibility run were removed from the active files and remain recoverable from Git history.

The live tests require an authenticated ERP-linked development environment.

LocalEvalRunner is an external repository dependency; this repository does not contain its project or `config.json`. After checking out and configuring LocalEvalRunner, pass an ERP test file path to that runner, for example:

```powershell
dotnet run --project <LocalEvalRunner.csproj> -- evals/tests/erp/dv_query.biceval.json --copilotcliagent <config.json>
```

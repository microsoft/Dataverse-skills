# ERP eval suites

These suites cover every Dataverse skill surface that routes to a linked Finance and Operations environment:

| File | Skill surface | Coverage |
|---|---|---|
| `dv_connect.biceval.json` | `dv-connect` | ERP linkage detection, `.env`, smoke test, and ERP MCP registration |
| `dv_query.biceval.json` | `dv-query` | ERP MCP/CLI reads, composite keys, cross-company reads, local aggregation, schema/action discovery, and custom services |
| `dv_data.biceval.json` | `dv-data` | ERP MCP/CLI CRUD, relationship updates, and DMF bulk imports |
| `dv_admin.biceval.json` | `dv-admin` | ERP batch listing, filtering, cancellation safety, and unsupported operations |
| `dv_overview.biceval.json` | `dv-overview` | Cross-skill ERP target routing and boundaries |
| `erp_xpp.biceval.json` | `erp-xpp` | X++ scaffolding, SDKs, compilation, deployment, DB sync, authoring, verification, and failure handling |

> ## Safety and fixture requirements
>
> Do not run the entire folder as one unrestricted live suite. Select tests by safety tier:
>
> - **Read-only:** connection detection, ERP reads/describes, MCP identity/read, and batch listing.
> - **Local mutation:** X++ scaffolding, SDK install/uninstall, and compilation. These require a disposable fixture workspace.
> - **Environment mutation:** ERP CRUD, DMF import, deployment, DB sync, runtime invocation, batch cancellation, and package removal. These require explicit opt-in, isolated test data, and the named disposable fixtures.

The live tests require an authenticated ERP-linked development environment. X++ build/deploy tests additionally require a disposable X++ fixture repository, the matching compiler SDK, and deployable test packages named in the prompts. DMF tests require the named package and disposable definition. Confirmation-dependent mutations must be executed as multi-turn evals; a prompt that says approval applies only after the resolved target/effects are displayed is not itself the confirmation.

LocalEvalRunner is an external repository dependency; this repository does not contain its project or `config.json`. After checking out and configuring LocalEvalRunner, pass an ERP test file path to that runner, for example:

```powershell
dotnet run --project <LocalEvalRunner.csproj> -- evals/tests/erp/dv_query.biceval.json --copilotcliagent <config.json>
```

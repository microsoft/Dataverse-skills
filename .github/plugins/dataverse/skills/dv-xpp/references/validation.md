# X++ deployment validation and error reference

Deployment is not validated by upload completion alone. PAC creates a Dataverse async operation, polls it to a terminal state, and reports the server result. Validate both that operation and the deployed artifact.

## Capture deployment diagnostics

Use console and file logging for every deployment:

```bash
pac package deploy --environment <dataverse-url> --package-type erp \
  --package <managed-zip> \
  --build-type Full --release-type Dev --db-sync None \
  --logConsole --logFile <deployment-log-path>
```

Record before execution:

- Exact package path and its current modified time.
- Confirmed Dataverse URL and linked ERP URL/version from `pac org who`.
- Build type, release type, DB-sync mode, modules, and argument-file path.
- Log path. Do not diagnose a new attempt from a stale log.

## Deployment success criteria

All applicable checks must pass:

1. PAC exits with code 0.
2. PAC prints the async operation ID.
3. The operation reaches `Succeeded`; PAC prints `Deploy completed successfully.`
4. In solution mode, every planned model deploys and PAC prints the expected deployed-model count.
5. If deployment includes DB sync, PAC also prints `Database synchronization completed successfully.`
6. The deployed artifact passes its runtime check:
   - Runnable class: run its `SysClassRunner` URL and observe the expected infolog or behavior.
   - Custom service/API: `list`, `describe`, and invoke the expected operation.
   - Public OData data entity: `describe` the entity set, then run a bounded query.

A ZIP upload, package-row creation, async operation ID, or HTTP success is only an intermediate milestone. None independently proves successful deployment.

## Investigate a failed or interrupted operation

Preserve the async operation ID and PAC log. PAC reports the server's friendly message first, then its raw message, and finally the terminal state when no message is available.

Query the corresponding Dataverse async operation when the terminal output is incomplete:

```bash
dataverse data get --target dataverse \
  --table asyncoperations --id <async-operation-id> \
  --select "asyncoperationid,statecode,statuscode,message,friendlymessage" \
  --environment <dataverse-url> --json
```

Dataverse async-operation terminal status codes used by the ERP package flow are:

| `statecode` | `statuscode` | Meaning |
| --- | --- | --- |
| `3` | `30` | Succeeded |
| `3` | `31` | Failed |
| `3` | `32` | Cancelled |

If PAC times out, the server operation may still be running. Query the same operation ID and check LCS/environment history before retrying. Never start a duplicate deployment merely because the client stopped waiting.

## Compile diagnostic validation

Treat compilation as successful only when:

- PAC exits with code 0.
- `Compile summary` reports zero failed models.
- Every requested model has a package line for a ZIP created by the current run.
- Label, X++ compiler, and best-practice stages have no errors.

Use the file path, line/column, diagnostic text, and stage log path printed by PAC. Fix the first causal error, then recompile; later errors may be cascading. Never deploy a ZIP left by an earlier successful run after the current compile fails.

## Validation error reference

| Error or symptom | Likely cause | Action |
| --- | --- | --- |
| `tool xpp`, `compile`, or `db-sync` is missing | PAC CLI is older than the ERP command surface | Update the PAC CLI .NET tool through **dv-connect**, then recheck `pac package help` and `pac tool xpp help`. |
| Target has no linked ERP URL/version | Environment is not ERP-linked or the wrong auth profile is active | Stop; select the confirmed Dataverse environment and rerun `pac org who`. |
| SDK not found or version mismatch | Target application version is not installed locally, or SDK selection is ambiguous | Run `pac tool xpp list`; install the target version or pass `--app-version`. |
| Label stage fails with `XPPLC2010` | The model has no valid label resource and PAC treated LabelC output as an error | Add valid `AxLabelFile` metadata and label text; do not suppress the stage. |
| X++ compile fails | Source/metadata diagnostic from `xppc` | Use the emitted file/line and compiler log, fix the first causal error, and rerun compile. |
| Best-practice stage fails | `xppbp` reported errors | Fix the reported rules. Use `--skip-bp` only when the user explicitly accepts reduced validation. |
| ZIP missing after compile | Packaging did not run, the model failed earlier, or output path differs | Check the compile summary and package line; do not use an older ZIP. |
| Package ZIP not found during solution deployment | A configured model was not compiled into `<root>/bin` | Compile the missing model and rerun the planned solution deployment. |
| Circular model dependency | Model descriptor references form a cycle | Review `<ModuleReferences>` and remove the cycle; do not manually reorder around it. |
| `EnvironmentStateInvalid` | ERP orchestration is still settling from a previous deployment | Check the previous operation state, wait for the environment to settle, then retry once. |
| Deployment reaches `Failed` or `Cancelled` | Server rejected or could not apply the package | Capture operation ID, status code, friendly/raw message, and PAC log; fix that cause before retrying. |
| Deployment polling times out | Client wait limit elapsed; server state is unknown | Query `asyncoperations` and check LCS. Do not redeploy until the original operation is terminal. |
| DB sync fails | Schema synchronization failed after or independently of deployment | Capture its separate operation ID, mode, and server message. Fix the schema/sync issue; do not redeploy unless package deployment itself failed. |
| Custom service is absent from `api list` | `AxService`/`AxServiceGroup` metadata was not deployed, names differ, or activation is incomplete | Confirm exact metadata names and successful deployment; retry discovery after propagation before rebuilding. |
| Custom service invocation fails | Operation name or request contract does not match | Run `dataverse api describe` and invoke with the returned parameter shape. |
| Public entity is absent from `data describe` | Entity is not public, entity-set name is wrong, deployment failed, or required DB sync did not complete | Check `<IsPublic>Yes</IsPublic>`, the exact entity-set name, deployment status, and DB-sync result. |
| Runnable class URL does not execute | Class name differs, `main(Args)` is not public static, or the deployed package lacks the class | Verify metadata/class names and current package contents, then recompile and redeploy if needed. |

## Failure report

Report:

- Command and target Dataverse/ERP URLs.
- Package path/model and selected deployment modes.
- PAC exit code and log path.
- Async operation ID, terminal state, status code, and friendly/raw server message.
- Whether DB sync started, its separate operation ID, and its result.
- Artifact verification command/URL and observed response.

Do not include access tokens, credentials, or raw authentication headers.

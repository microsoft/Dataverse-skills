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
   - Custom service: directly invoke the fully qualified `erp:<ServiceGroup>/<Service>/<Operation>` name and compare the returned value with the expected result.
   - `ICustomAPI` action: find it through ERP MCP `api_find_actions`, validate the action menu-item identity and contract, invoke it through `api_invoke_action`, and compare its `Result` properties with expected values.
   - Public OData data entity: `describe` the entity set, then run a bounded query.

A ZIP upload, package-row creation, async operation ID, or HTTP success is only an intermediate milestone. None independently proves successful deployment.

## Investigate a failed or interrupted operation

Preserve the async operation ID and PAC log. PAC reports the server's friendly message first, then its raw message, and finally the terminal state when no message is available.

Query the corresponding Dataverse async operation when the terminal output is incomplete:

```bash
dataverse data get --target dataverse \
  --table asyncoperations --id <async-operation-id> \
  --select "asyncoperationid,statecode,statuscode,message,friendlymessage" \
  --environment <dataverse-url> --json \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
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
| `api list` or `api describe` stalls | Broad ERP service metadata discovery is slow or unresponsive | Stop the discovery request. If names and parameters are known from source, invoke the fully qualified `erp:<group>/<service>/<operation>` directly. |
| Custom service is absent from `api list` | `AxService`/`AxServiceGroup` metadata was not deployed, names differ, or activation is incomplete | Confirm exact metadata names and successful deployment; use fully qualified invocation when names are known, or retry discovery after propagation. |
| Custom service invocation fails | Operation name or request contract does not match | Run `dataverse api describe erp:<group>/<service>/<operation> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"` to verify the operation identity. Obtain the parameter contract from the X++ method or data-contract source before invoking. |
| ERP MCP `/mcp` returns `403` | The calling application is not allow-listed for the ERP MCP endpoint | Add the approved client application through the supported environment administration flow, then reinitialize MCP. Do not bypass the allow list. |
| `ICustomAPI` is absent from `api_find_actions` | Deployment/DB sync has not completed, the action menu item is missing or named differently, security access is missing, or metadata propagation is incomplete | Confirm successful compile/deploy/sync, exact `AxMenuItemAction` name and class target, privilege/duty/role coverage, and caller access; then reinitialize MCP and retry after propagation. |
| `api_find_actions` reports skipped actions or metadata errors | Another or the requested action has invalid class/menu-item metadata | Record `SkippedActions` and the metadata message. Fix the named action's `ICustomAPI` class, attributes, menu item, or security metadata before claiming complete discovery. |
| `api_invoke_action` rejects parameters | `parameters` is not a JSON-encoded string, data-member names differ, or JSON types do not match the discovered contract | Use the exact input schema from `api_find_actions`; encode it as a JSON string and preserve integer, Boolean, date, and enum types. |
| `api_invoke_action` returns `isError: true` | The action ran unsuccessfully or ERP MCP rejected execution | Capture the MCP activity ID and returned error, verify company context and security, and fix the X++ or request contract. Do not treat JSON-RPC HTTP success as action success. |
| `ICustomAPI` returns an unexpected value | Business logic or parameter mapping is incorrect | Compare the discovered contract and response properties with source, then test representative positive, zero, negative, and boundary inputs. |
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
- For `ICustomAPI`, the discovered action menu-item name, contract, test inputs/outputs, MCP `isError` value, and activity ID on failure.

Do not include access tokens, credentials, or raw authentication headers.

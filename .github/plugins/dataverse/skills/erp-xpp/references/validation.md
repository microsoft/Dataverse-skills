# X++ deployment result and optional validation reference

For `pac package deploy --package-type erp`, PAC creates a Dataverse async operation, polls it to a terminal state, and reports the server result as part of the deployment command. Capture that result, but treat every additional ERP X++ post-deployment check as opt-in. The user decides whether to re-query the operation, execute the X++ artifact, query its ERP entity, or test its security. This policy does not alter Dataverse solution deployment validation.

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

## Deployment command result

Always capture the outcome already produced by PAC:

1. PAC exits with code 0.
2. PAC prints the async operation ID.
3. The operation reaches `Succeeded`; PAC prints `Deploy completed successfully.`
4. In solution mode, every planned model deploys and PAC prints the expected deployed-model count.
5. If deployment includes DB sync, PAC also prints `Database synchronization completed successfully.`
These checks establish what PAC reported; they do not authorize additional validation or prove runtime behavior.

## Optional post-deployment validation

After PAC reaches a terminal state, ask whether the user wants additional validation and which checks to run:

- Dataverse async-operation re-query.
- API or action discovery.
- Runnable-class execution.
- Custom-service or `ICustomAPI` execution.
- Public data-entity query.
- `ICustomAPI` security acceptance.

Run only the selected checks. If all are declined, report the PAC result and state that no additional validation was performed. Selection of one check does not authorize another.

For a selected runtime check:

1. Ask for every required input plus explicit success and failure criteria from the custom artifact's source contract. Use only values and criteria supplied in the prompt or explicitly confirmed by the user; never invent a generic test matrix or invoke unrelated ERP operations. Do not execute a negative case merely because failure criteria were defined.
2. Require the selected Dataverse CLI profile's environment URL and linked `erpUrl` to match the confirmed PAC target. For MCP, direct HTTP targets `<erpUrl>/mcp`, or the stdio proxy receives the base `<erpUrl>` and routes effectively to `/mcp`. Before every MCP invocation, prove the caller through an MCP-originated identity/current-session check; stop when the caller cannot be verified.
3. Evaluate only the approved deployed artifact:
   - Runnable class: run its `SysClassRunner` URL and observe the expected infolog or behavior.
   - Custom service: after side-effect classification and approval, directly invoke the fully qualified `erp:<ServiceGroup>/<Service>/<Operation>` name and compare its response and expected mutations with observed results.
   - `ICustomAPI` action: if discovery was selected, use ERP MCP `api_find_actions` to validate the action menu-item identity and contract. If execution was selected, use the confirmed source contract or approved discovery result with `api_invoke_action`, then compare its `Result` properties and expected mutations with observed results.
   - Public OData data entity: if discovery was selected, `describe` the entity set. If query execution was selected, run only the separately approved bounded query.
4. If both runtime execution and security acceptance were selected, require a fresh MCP session whose caller is proven by an MCP-originated identity/current-session check to be a non-administrator test user assigned the intended custom role. Security acceptance alone does not authorize invocation. Administrator execution or CLI identity alone is not acceptance evidence for the privilege/duty/role chain.

A ZIP upload, package-row creation, async operation ID, or HTTP success is only an intermediate milestone. None independently proves successful deployment.

## Runtime verification safety gates

Before executing a user-selected custom service or action:

- Ask whether the user wants runtime validation after deployment succeeds. Do not execute on an assumed or earlier blanket approval.
- Ask for every contract input and the success and failure criteria, or repeat exact values and criteria already present in the prompt and obtain confirmation. Never invent them.
- Treat failure criteria as evaluation rules, not permission to trigger failure. Ask separately for exact negative-test inputs and effects before executing a failure path.
- Inspect its X++ implementation and contract; classify it as side-effect-free, idempotent mutation, or non-idempotent mutation.
- Use non-production and isolated test data by default.
- Record the exact input, expected response, and expected business-data or downstream mutations in the confirmation.
- Stop for confirmation if those runtime effects were not already approved.
- Run multiple cases only when the user separately selects that check, the logic is proven side-effect-free, and every input is individually confirmed. For non-idempotent logic, run one minimal approved case and verify the resulting state.
- Validate custom security only when the user separately selects that check. Use a fresh, transport-specific MCP session authenticated as a non-administrator user assigned the intended role. Prove the caller through MCP itself; if that is unavailable, use another runtime surface that can prove identity and report MCP security acceptance as unverified. Use System Administrator only as an optional control.
- Run an optional negative check only with a disposable test user and an independently guaranteed restoration path. Capture the exact role assignment, restore it even if invocation fails, verify restoration, and skip the check when those guarantees are unavailable.

## Optional investigation of a failed or interrupted operation

Preserve the async operation ID and PAC log. PAC reports the server's friendly message first, then its raw message, and finally the terminal state when no message is available. Ask whether the user wants additional operation diagnostics before making a Dataverse query.

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
| ERP runtime target differs from PAC target | The active Dataverse CLI profile points to another environment | Stop; run `dataverse auth who` and `dataverse org who --json`, select the correct profile with `dataverse auth select --name <profile-name>`, and repeat both checks before any invocation or query. |
| ERP MCP target differs from linked `erpUrl` | The existing MCP connection was configured for another ERP endpoint | Stop; for direct HTTP use the confirmed `<erpUrl>/mcp`; for stdio pass the confirmed base `<erpUrl>` to the proxy and verify its effective `/mcp` endpoint. Reconnect or reinitialize before discovery or invocation. |
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
| `ICustomAPI` returns an unexpected value | Business logic or parameter mapping is incorrect | Compare the discovered contract and response properties with source, then rerun only an approved input appropriate to the operation's side-effect classification. |
| Action succeeds only as System Administrator | The custom privilege/duty/role chain may be missing, incorrect, not assigned, or the MCP session still uses administrator credentials | Establish a fresh transport-specific MCP session as a non-administrator user assigned the intended role and prove caller identity through MCP before invoking. Treat administrator execution as deployment diagnosis, not security acceptance. |
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
- Which post-deployment checks were accepted or declined; for runtime checks, record the user-confirmed inputs, success criteria, failure criteria, and exact custom artifact tested.
- For `ICustomAPI`, the discovered action menu-item name, contract, test inputs/outputs, MCP `isError` value, and activity ID on failure.
- Selected Dataverse CLI identity/profile URL, linked ERP URL, ERP MCP server URL, and MCP caller used for runtime verification.
- Runtime side-effect classification, approved input, expected mutations, observed state, and the non-administrator role used for security acceptance. If a negative role test ran, include restoration verification.

Do not include access tokens, credentials, or raw authentication headers.

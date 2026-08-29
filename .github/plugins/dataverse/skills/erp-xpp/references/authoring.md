# Authoring X++ metadata

## Scaffold first

For a new model, let PAC create `.erp/xpp.json`, the descriptor, and metadata directories:

```bash
pac package init --outputDirectory <root> --package-type erp \
  --model ContosoVerification --publisher Contoso --layer ISV
```

Inspect before running. If `.erp/xpp.json` already exists, PAC merges the model name; it must not replace existing source. Never reuse a platform model name such as `ApplicationFoundation` for custom code.

Expected layout:

```text
<root>/
  .erp/
    xpp.json
  src/
    ContosoVerification/
      Descriptor/
        ContosoVerification.xml
      ContosoVerification/
        AxClass/
        AxDataEntityView/
        AxLabelFile/
        AxService/
        AxServiceGroup/
```

## Runnable verification class

Create `src/ContosoVerification/ContosoVerification/AxClass/ContosoVerificationJob.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxClass xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>ContosoVerificationJob</Name>
  <SourceCode>
    <Declaration><![CDATA[
/// <summary>
/// Displays a deployment verification message.
/// </summary>
public final class ContosoVerificationJob
{
}
]]></Declaration>
    <Methods>
      <Method>
        <Name>main</Name>
        <Source><![CDATA[
    /// <summary>
    /// Runs the deployment verification.
    /// </summary>
    /// <param name="_args">Runtime arguments.</param>
    public static void main(Args _args)
    {
        info("@ContosoVerification:DeploymentComplete");
    }
]]></Source>
      </Method>
    </Methods>
  </SourceCode>
</AxClass>
```

The class name and XML `<Name>` must match. A runnable class needs a public static `main(Args)` method.

## Label resource

LabelC warns when a model has no labels, and affected PAC versions treat any nonempty LabelC error log as a failed label stage. Add a real label instead of suppressing the stage.

Create `src/ContosoVerification/ContosoVerification/AxLabelFile/ContosoVerification_en-US.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxLabelFile xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>ContosoVerification_en-US</Name>
  <LabelContentFileName>ContosoVerification.en-US.label.txt</LabelContentFileName>
  <LabelFileId>ContosoVerification</LabelFileId>
  <RelativeUriInModelStore>ContosoVerification\ContosoVerification\AxLabelFile\LabelResources\en-US\ContosoVerification.en-US.label.txt</RelativeUriInModelStore>
</AxLabelFile>
```

Create `src/ContosoVerification/ContosoVerification/AxLabelFile/LabelResources/en-US/ContosoVerification.en-US.label.txt`:

```text
DeploymentComplete=Hello, this is done.
 ;Message displayed after deployment verification.
```

Use the label as `@ContosoVerification:DeploymentComplete`. Do not embed user-facing text directly in `info()`; the best-practice checker reports `BPErrorLabelIsText`.

## Compile and optionally run

```bash
pac package compile --solution-root <root> --package-type erp \
  --model ContosoVerification --language en-US
```

After a successful deploy, apply the runtime validation safety gate below. Only when the user explicitly opts in, open:

```text
https://<erp-host>/?mi=SysClassRunner&cls=ContosoVerificationJob
```

The ERP host comes from `pac org who --environment <dataverse-url>`. Do not guess the host by string replacement.

Opening the URL is the execution step. Deployment alone does not prove the class ran or that its infolog message appeared.

## Runtime validation safety

Before executing or querying any deployed artifact, including a runnable class, custom service, `ICustomAPI`, or public data entity:

1. Wait for terminal deployment success, then ask whether the user wants the agent to perform runtime validation. Stop if they decline and report that runtime behavior remains unvalidated.
2. If accepted, inspect only the deployed custom artifact's X++ implementation and request contract. Ask for every required input. If the user's prompt already supplies exact values, repeat them for confirmation; never invent or broaden the test data. For an artifact with no input, confirm the expected behavior and execution context.
3. Classify execution as side-effect-free, idempotent mutation, or non-idempotent mutation. State the approved input, expected response, and expected record, transaction, batch, or downstream effects before execution.
4. Default mutation tests to a non-production environment and isolated test data. If the disclosed runtime effects were not approved, stop and obtain confirmation.
5. Pin the Dataverse CLI profile as required by the skill preflight and verify that its Dataverse URL and linked `erpUrl` match the confirmed PAC target. For MCP, verify direct HTTP against `<erpUrl>/mcp`, or verify that an stdio proxy receives the base `<erpUrl>` and routes effectively to `/mcp`; reconnect or reinitialize it if necessary.
6. For a non-idempotent operation, run one minimal approved case and verify the resulting state. Do not automatically run positive, zero, negative, or boundary matrices.

Discovery calls do not prove runtime behavior. Invocation calls execute X++ business logic and must not be treated as read-only probes.

## ERP custom service

An ERP custom service requires all of the following:

- An X++ service class containing the public operation methods.
- Optional `[DataContract]` classes for structured request and response payloads.
- An `AxService` file mapping each external operation to its X++ method.
- An `AxServiceGroup` file exposing the service.

PAC does not scaffold these artifacts. Create them under the model metadata tree, preserving the naming and XML structure used by existing services in the repository.

Create `AxService/ContosoVerificationService.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxService xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>ContosoVerificationService</Name>
  <Class>ContosoVerificationServiceClass</Class>
  <ExternalName>ContosoVerificationService</ExternalName>
  <ServiceOperations>
    <AxServiceOperation>
      <Name>VerifyDeployment</Name>
      <Method>VerifyDeployment</Method>
    </AxServiceOperation>
  </ServiceOperations>
</AxService>
```

Create `AxServiceGroup/ContosoVerificationServiceGroup.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<AxServiceGroup xmlns:i="http://www.w3.org/2001/XMLSchema-instance">
  <Name>ContosoVerificationServiceGroup</Name>
  <Services>
    <AxServiceGroupService>
      <Name>ContosoVerificationService</Name>
      <Service>ContosoVerificationService</Service>
    </AxServiceGroupService>
  </Services>
</AxServiceGroup>
```

The class named by `<Class>` must exist, and every `<Method>` must match a public method on that class. After compiling and deploying, do not assume deployment made the service callable. If the user opts into runtime validation and confirms the required inputs, invoke the fully qualified ERP operation directly:

```bash
dataverse api invoke \
  'erp:ContosoVerificationServiceGroup/ContosoVerificationService/VerifyDeployment' \
  --target erp --param '<parameter-name>=<value>' --json \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>" \
  --environment <dataverse-url>
```

Use the exact X++ method parameter name, including a leading underscore when present (for example, `--param '_value=7'`). Pass repeated `--param name=value` values for primitive parameters; use `--body` or `--body-file` for structured contracts. Compare the returned value with the expected business result.

Use `dataverse api list --target erp --service-group <group> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"` and `dataverse api describe erp:<group>/<service>/<operation> --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"` only when the deployed names are unknown. Obtain parameter names and types from the X++ method or data-contract source; a fully qualified ERP `api describe` result may not include request parameters. Discovery is not a prerequisite when source metadata provides the names; if discovery stalls, stop it and use the fully qualified invocation rather than waiting indefinitely.

## ERP `ICustomAPI` action

An F&O `ICustomAPI` action is not an `AxService`/`AxServiceGroup` custom service. It requires:

- A final X++ class implementing `ICustomAPI`.
- `[CustomAPI(...)]`, `[AIPluginOperationAttribute]`, and `[DataContract]` class attributes.
- `[CustomAPIRequestParameter(...)]` plus `[DataMember(...)]` on each input accessor.
- `[CustomAPIResponseProperty(...)]` plus `[DataMember(...)]` on each output accessor.
- A public `run(Args _args)` method that sets the response properties.
- An `AxMenuItemAction` targeting the class.
- A security privilege containing that menu-item action as an entry point, referenced by a duty and role.
- Label resources for security labels and descriptions.

PAC does not scaffold these artifacts. Create them under `AxClass`, `AxMenuItemAction`, `AxSecurityPrivilege`, `AxSecurityDuty`, and `AxSecurityRole` in the model metadata tree.

Example class source inside `AxClass/ContosoSubtractCustomAPI.xml`:

```xpp
[CustomAPI('Subtract ten', 'Returns the supplied integer minus ten')]
[AIPluginOperationAttribute]
[DataContract]
public final class ContosoSubtractCustomAPI implements ICustomAPI
{
    private int inputValue;
    private int result;

    [CustomAPIRequestParameter('The integer to subtract ten from', true),
     DataMember('inputValue')]
    public int parmInputValue(int _inputValue = inputValue)
    {
        inputValue = _inputValue;
        return inputValue;
    }

    [CustomAPIResponseProperty('The supplied integer minus ten'),
     DataMember('result')]
    public int parmResult(int _result = result)
    {
        result = _result;
        return result;
    }

    public void run(Args _args)
    {
        this.parmResult(this.parmInputValue() - 10);
    }
}
```

The action menu-item name is the external action identity:

```xml
<AxMenuItemAction xmlns:i="http://www.w3.org/2001/XMLSchema-instance"
                  xmlns="Microsoft.Dynamics.AX.Metadata.V1">
  <Name>ContosoSubtractCustomAPI</Name>
  <Object>ContosoSubtractCustomAPI</Object>
  <ObjectType>Class</ObjectType>
  <SubscriberAccessLevel>
    <Read xmlns="">Allow</Read>
  </SubscriberAccessLevel>
</AxMenuItemAction>
```

Create a privilege whose entry point has `<ObjectName>ContosoSubtractCustomAPI</ObjectName>` and `<ObjectType>MenuItemAction</ObjectType>`, reference that privilege from a duty, and reference the duty from a role. Missing security metadata can produce best-practice warnings or make the action unavailable to callers.

The required security acceptance test uses a non-administrator test user assigned the intended custom role. Successful execution as System Administrator is only an optional deployment diagnostic because it can bypass a broken privilege -> duty -> role chain.

Before acceptance, authenticate the Dataverse CLI as that test user and verify its identity and target with `dataverse auth who` and `dataverse org who --json`. Then establish a fresh transport-specific MCP authentication/session as the test user: direct HTTP uses its host-managed sign-in, while an stdio proxy must be restarted after selecting the intended shared-cache identity. Do not reuse an administrator-authenticated MCP session.

Verify the caller through an MCP-originated identity or current-session check before invoking the action. CLI identity alone is insufficient. If the MCP server exposes no way to prove the caller, report security acceptance as unverified and use another authenticated runtime surface that can prove the non-administrator identity.

A negative role test is optional and may use only a disposable non-administrator test user. Before removing the role, record the exact assignment and establish a restoration path that does not depend on the test user. Restore the assignment immediately even if invocation fails, verify restoration, and do not report completion while access remains altered. Skip the negative test when guaranteed restoration is unavailable.

Compile and deploy with the normal PAC X++ flow. Run Module DB sync for the changed model when the deployment requires metadata synchronization:

```bash
pac package compile --solution-root <root> --package-type erp \
  --model <ModelName> --app-version <x.y.z.w> --language en-US

pac package deploy --environment <dataverse-url> --package-type erp \
  --package <root>/bin/<ModelName>_<version>_managed.zip \
  --build-type Full --release-type Dev --db-sync None \
  --logConsole --logFile <deployment-log-path>

pac package db-sync --environment <dataverse-url> \
  --db-sync Module --modules <ModelName>
```

Verify the action through the ERP MCP server at the linked ERP host's `/mcp` endpoint. Initialize MCP, then call the generic tools rather than expecting one MCP tool per custom action:

1. Call `api_find_actions` with `{"searchTerm":"ContosoSubtractCustomAPI"}`.
2. Require a returned action whose `ActionMenuItemName` exactly matches and whose input/output names and types match the authored data members.
3. After the user accepts runtime validation and confirms the exact input, apply the remaining safety gates above, then call `api_invoke_action` with:

```json
{
  "name": "ContosoSubtractCustomAPI",
  "parameters": "{\"inputValue\":<confirmed-input-value>}",
  "returnAsResource": false
}
```

Replace `<confirmed-input-value>` with a value supplied by the user or an exact value from the prompt that the user reconfirms. `parameters` is a JSON-encoded string, not a nested object. Require `isError: false` and compare the returned `Result` properties and expected mutations with observed results. Do not add matrix or boundary values that the user did not supply. For mutating or non-idempotent actions, follow the single minimal approved-case rule.

4. Repeat the approved acceptance case through a fresh transport-specific MCP session authenticated as the non-administrator test user assigned the intended custom role. Verify the target and caller from the MCP session itself first. Do not claim that the authored security chain works when the caller cannot be proven or based only on System Administrator execution.

## Public OData data entity

An OData-facing entity is authored as `AxDataEntityView` metadata and must have `<IsPublic>Yes</IsPublic>`. Follow an existing entity in the target codebase for its data sources, fields, keys, labels, configuration keys, and entity-set naming; those details are business-schema specific and PAC does not generate them.

After compiling and deploying the model, ask whether the user wants runtime validation. If accepted, confirm the exact entity set, company/filter context, and bounded row count; then use the entity-set name, not the X++ class or metadata file name:

```bash
dataverse data describe --target erp --table <EntitySet> \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
dataverse data query --target erp --table <EntitySet> \
  --top <confirmed-row-limit> --filter "<confirmed-filter>" \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
```

Omit `--filter` only when the user explicitly confirms an unfiltered bounded query. Add `--cross-company` only when cross-company access is explicitly requested and confirmed; otherwise the query uses the caller's default company. `describe` proves the public entity is exposed and shows its exact properties and keys. A successful `query` proves the deployed entity can be reached through ERP OData; an empty result is valid and should not be reported as a deployment failure.

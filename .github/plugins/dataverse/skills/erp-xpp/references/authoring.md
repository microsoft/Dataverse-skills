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

1. Wait for the PAC deployment command's terminal result, then ask whether the user wants runtime validation. This opt-in covers runtime execution only; do not infer permission from approval of another post-deployment check. Stop if they decline and report that runtime behavior remains unvalidated.
2. If accepted, inspect only the deployed custom artifact's X++ implementation and request contract. Ask for every required input and for explicit success and failure criteria. If the user's prompt already supplies exact values or criteria, repeat them for confirmation; never invent or broaden them. For an artifact with no input, confirm the expected behavior and execution context.
3. Classify execution as side-effect-free, idempotent mutation, or non-idempotent mutation. State the approved input, success criteria, failure criteria, expected response, and expected record, transaction, batch, or downstream effects before execution. Failure criteria do not authorize a negative test; ask separately before executing one.
4. Default mutation tests to a non-production environment and isolated test data. If the disclosed runtime effects were not approved, stop and obtain confirmation.
5. Pin the Dataverse CLI profile as required by the skill preflight and verify that its Dataverse URL and linked `erpUrl` match the confirmed PAC target. For MCP, verify direct HTTP against `<erpUrl>/mcp`, or verify that an stdio proxy receives the base `<erpUrl>` and routes effectively to `/mcp`; reconnect or reinitialize it if necessary. Before any MCP invocation, prove the caller through an MCP-originated identity/current-session check; stop if the caller cannot be verified.
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

Use the exact X++ method parameter name, including a leading underscore when present (for example, `--param '_value=<user-confirmed-value>'`). Pass repeated `--param name=value` values for primitive parameters; use `--body` or `--body-file` for structured contracts. Compare the returned value with the user-confirmed success and failure criteria.

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

Use this structural template only after replacing every uppercase placeholder from the user's requested custom behavior. It is intentionally not compile-ready and contains no default business logic or test values:

```xpp
[CustomAPI('CUSTOM_API_DISPLAY_NAME', 'CUSTOM_API_DESCRIPTION')]
[AIPluginOperationAttribute]
[DataContract]
public final class CUSTOM_API_CLASS implements ICustomAPI
{
    private INPUT_TYPE inputValue;
    private OUTPUT_TYPE result;

    [CustomAPIRequestParameter('INPUT_DESCRIPTION', INPUT_IS_OPTIONAL),
     DataMember('INPUT_DATA_MEMBER')]
    public INPUT_TYPE parmInputValue(INPUT_TYPE _inputValue = inputValue)
    {
        inputValue = _inputValue;
        return inputValue;
    }

    [CustomAPIResponseProperty('OUTPUT_DESCRIPTION'),
     DataMember('OUTPUT_DATA_MEMBER')]
    public OUTPUT_TYPE parmResult(OUTPUT_TYPE _result = result)
    {
        result = _result;
        return result;
    }

    public void run(Args _args)
    {
        this.parmResult(RESULT_FROM_USER_REQUESTED_BUSINESS_LOGIC);
    }
}
```

`INPUT_IS_OPTIONAL` is the request parameter's optional flag: use `true` for an optional input and `false` for a required input.

The action menu-item name is the external action identity:

```xml
<AxMenuItemAction xmlns:i="http://www.w3.org/2001/XMLSchema-instance"
                  xmlns="Microsoft.Dynamics.AX.Metadata.V1">
  <Name>CUSTOM_API_MENU_ITEM_NAME</Name>
  <Object>CUSTOM_API_CLASS</Object>
  <ObjectType>Class</ObjectType>
  <SubscriberAccessLevel>
    <Read xmlns="">Allow</Read>
  </SubscriberAccessLevel>
</AxMenuItemAction>
```

Create a privilege whose entry point uses the confirmed custom API menu-item name as `<ObjectName>` and `<ObjectType>MenuItemAction</ObjectType>`, reference that privilege from a duty, and reference the duty from a role. Missing security metadata can produce best-practice warnings or make the action unavailable to callers.

If the user selects security acceptance, use a non-administrator test user assigned the intended custom role. Successful execution as System Administrator is only an optional deployment diagnostic because it can bypass a broken privilege -> duty -> role chain.

Before a selected security-acceptance check, authenticate the Dataverse CLI as that test user and verify its identity and target with `dataverse auth who` and `dataverse org who --json`. Then establish a fresh transport-specific MCP authentication/session as the test user: direct HTTP uses its host-managed sign-in, while an stdio proxy must be restarted after selecting the intended shared-cache identity. Do not reuse an administrator-authenticated MCP session.

For selected security acceptance, verify the caller through an MCP-originated identity or current-session check before invoking the action. CLI identity alone is insufficient. If the MCP server exposes no way to prove the caller, report security acceptance as unverified and use another authenticated runtime surface that can prove the non-administrator identity.

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

If the user selects API/action discovery, use the ERP MCP server at the linked ERP host's `/mcp` endpoint. Initialize MCP, then call the generic tools rather than expecting one MCP tool per custom action:

1. Call `api_find_actions` with the confirmed custom API menu-item name as `searchTerm`.
2. Require a returned action whose `ActionMenuItemName` exactly matches and whose input/output names and types match the authored data members.

Discovery is not required when the source already provides a confirmed menu-item name and contract. Only if the user separately selects runtime execution and confirms the exact inputs and criteria, call `api_invoke_action` using either the confirmed source contract or an approved discovery result:

```json
{
  "name": "CONFIRMED_CUSTOM_API_MENU_ITEM_NAME",
  "parameters": "USER_CONFIRMED_JSON_INPUTS",
  "returnAsResource": false
}
```

Replace both placeholders with the discovered menu-item name and a JSON-encoded string built only from user-confirmed inputs. `parameters` is a JSON-encoded string, not a nested object. Evaluate the result against the user-confirmed success and failure criteria. Do not add matrix, boundary, or negative values that the user did not supply and approve. For mutating or non-idempotent actions, follow the single minimal approved-case rule.

Only if the user separately selects both runtime execution and security acceptance, repeat the approved case through a fresh transport-specific MCP session authenticated as the non-administrator test user assigned the intended custom role. Verify the target and caller from the MCP session itself first. Do not claim that the authored security chain works when the caller cannot be proven or based only on System Administrator execution.

## Public OData data entity

An OData-facing entity is authored as `AxDataEntityView` metadata and must have `<IsPublic>Yes</IsPublic>`. Follow an existing entity in the target codebase for its data sources, fields, keys, labels, configuration keys, and entity-set naming; those details are business-schema specific and PAC does not generate them.

After compiling and deploying the model, ask which data-entity checks the user wants. Confirm the exact entity set from source or approved discovery, company/filter context, and bounded row count.

If entity discovery is selected:

```bash
dataverse data describe --target erp --table <EntitySet> \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
```

If query execution is separately selected:

```bash
dataverse data query --target erp --table <EntitySet> \
  --top <confirmed-row-limit> --filter "<confirmed-filter>" \
  --context "app=dataverse-skills/<ver>;skill=erp-xpp;agent=<agent>"
```

Omit `--filter` only when the user explicitly confirms an unfiltered bounded query. Add `--cross-company` only when cross-company access is explicitly requested and confirmed; otherwise the query uses the caller's default company. A selected `describe` proves the public entity is exposed and shows its exact properties and keys. A selected `query` proves the deployed entity can be reached through ERP OData; an empty result is valid and should not be reported as a deployment failure.

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

## Compile and run

```bash
pac package compile --solution-root <root> --package-type erp \
  --model ContosoVerification --language en-US
```

After a successful deploy, run:

```text
https://<erp-host>/?mi=SysClassRunner&cls=ContosoVerificationJob
```

The ERP host comes from `pac org who --environment <dataverse-url>`. Do not guess the host by string replacement.

Opening the URL is the execution step. Deployment alone does not prove the class ran or that its infolog message appeared.

## ERP custom service/API

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

The class named by `<Class>` must exist, and every `<Method>` must match a public method on that class. After compiling and deploying, verify the service rather than assuming deployment made it callable:

```bash
dataverse api list --target erp --service-group ContosoVerificationServiceGroup
dataverse api describe \
  erp:ContosoVerificationServiceGroup/ContosoVerificationService/VerifyDeployment
dataverse api invoke \
  erp:ContosoVerificationServiceGroup/ContosoVerificationService/VerifyDeployment \
  --body '{"request":{"message":"Hello"}}'
```

Use `dataverse api describe` to confirm the actual parameter shape before invoking. Pass `name=value` or repeated `--param name=value` for simple parameters; use `--body` or `--body-file` for structured contracts.

## Public OData data entity

An OData-facing entity is authored as `AxDataEntityView` metadata and must have `<IsPublic>Yes</IsPublic>`. Follow an existing entity in the target codebase for its data sources, fields, keys, labels, configuration keys, and entity-set naming; those details are business-schema specific and PAC does not generate them.

After compiling and deploying the model, use the entity-set name, not the X++ class or metadata file name:

```bash
dataverse data describe --target erp --table <EntitySet>
dataverse data query --target erp --table <EntitySet> --top 10
```

`describe` proves the public entity is exposed and shows its exact properties and keys. A successful `query` proves the deployed entity can be reached through ERP OData; an empty result is valid and should not be reported as a deployment failure.

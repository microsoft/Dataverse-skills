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
        AxLabelFile/
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


---
name: dataverse-csharp-plugins
description: >
  Scaffold, build, register, and deploy C# Dataverse plugins.
  WHEN: "C# plugin", "write a plugin", "IPlugin", "plugin registration", "pac plugin push",
  "PreOperation", "PostOperation", "server-side logic", "strong-name key",
  "register assembly", "plugin step".
  DO NOT USE WHEN: writing Python scripts (use dataverse-python-sdk),
  creating tables/columns (use dataverse-metadata),
  importing solutions (use dataverse-solution).
---

# Skill: C# Plugins

Write, build, register, and deploy traditional Dataverse C# plugins. Plugin assemblies live in the repo under `/plugins/` and are registered to the environment via PAC CLI.

> **Environment-First Rule** — The plugin assembly and its step registration are deployed to the Dynamics environment first. After deployment, pull the solution to sync the registration metadata back to the repo. Do not commit plugin DLLs to git.

**Complete deployment sequence:**
1. Scaffold and write the plugin class
2. Strong-name the assembly (required by Dataverse)
3. Build the assembly
4. **Confirm the target environment with the user** — ask which environment URL to deploy to; do not assume based on `.env`, memory, or the active PAC auth profile
5. Register the assembly and step via Web API script (first-time) or `pac plugin push --pluginId` (updates)
6. Pull the solution to repo (`pac solution export` + `pac solution unpack`)
7. Commit

## Scaffold a New Plugin Project

Create the project directory and write the `.csproj` directly (`dotnet new classlib --framework net462` fails on .NET 6+ SDKs because net462 is not in the modern template list):

```
mkdir -p plugins/<PluginName>
```

Write `plugins/<PluginName>/<PluginName>.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net462</TargetFramework>
    <AssemblyName><PluginName></AssemblyName>
    <RootNamespace><PluginName></RootNamespace>
    <SignAssembly>true</SignAssembly>
    <AssemblyOriginatorKeyFile><PluginName>.snk</AssemblyOriginatorKeyFile>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.CrmSdk.CoreAssemblies" Version="9.0.2.60" />
  </ItemGroup>
</Project>
```

> **Why net462?** Dataverse sandbox plugin execution uses the .NET Framework 4.6.2 runtime. Use `net462` unless your environment is configured for .NET 6+ (check with your Dataverse admin).

## Minimal Plugin Class

```csharp
using System;
using Microsoft.Xrm.Sdk;

namespace <PluginName>
{
    public class <ClassName> : IPlugin
    {
        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider
                .GetService(typeof(IPluginExecutionContext));
            var serviceFactory = (IOrganizationServiceFactory)serviceProvider
                .GetService(typeof(IOrganizationServiceFactory));
            var service = serviceFactory.CreateOrganizationService(context.UserId);
            var tracingService = (ITracingService)serviceProvider
                .GetService(typeof(ITracingService));

            try
            {
                // Your logic here
                tracingService.Trace("Plugin executing. Message: {0}", context.MessageName);

                if (context.InputParameters.Contains("Target") &&
                    context.InputParameters["Target"] is Entity target)
                {
                    // Example: read/modify target entity before create/update
                }
            }
            catch (InvalidPluginExecutionException)
            {
                throw;
            }
            catch (Exception ex)
            {
                throw new InvalidPluginExecutionException($"Plugin error: {ex.Message}", ex);
            }
        }
    }
}
```

## Strong-naming (Required)

Dataverse requires all plugin assemblies to be strong-named. Do this once per project, before the first build.

**1. Generate the key file:**

```
sn -k plugins/<PluginName>/<PluginName>.snk
```

If `sn` is not available, it ships with the Windows SDK. Find it at:
```
find "/c/Program Files (x86)/Microsoft SDKs/Windows" -name "sn.exe" 2>/dev/null | head -1
```

**2. The `.csproj` already references the key** (added in the scaffold step above via `<SignAssembly>` and `<AssemblyOriginatorKeyFile>`). No further action needed in the project file.

**3. Gitignore the `.snk` file** — it is a private signing key:

```
# Add to .gitignore if not already present
plugins/**/*.snk
```

**4. After building, extract the public key token** — you will need it for the registration script:

```
sn -T plugins/<PluginName>/bin/Release/net462/<PluginName>.dll
```

Output: `Public key token is <16-hex-chars>` — save this value.

**Keep a secure copy of the `.snk` file outside the repo.** If you lose it you cannot update the assembly registration without deleting and re-registering from scratch.

## Build

```
dotnet build plugins/<PluginName> --configuration Release
```

Output: `plugins/<PluginName>/bin/Release/net462/<PluginName>.dll`

## Deploy

**Before running any deploy step, confirm the target environment URL with the user.** Do not proceed based on `.env` values, memory from a previous session, or the active PAC auth profile alone — developers routinely work across multiple environments and credentials.

### First-time: Register via Web API script

`pac plugin push` requires an existing plugin registration ID (`--pluginId`) and cannot create a new one. For first-time deployment, use the Web API to register the assembly and step together.

Write `scripts/register_plugin.py` with this pattern, substituting your values, then run it:

```python
"""
register_plugin.py — Register plugin assembly and step in Dataverse.

Idempotent: safe to run multiple times. On subsequent runs it updates the
assembly content and skips creation of already-existing type/step records.

Run from repo root:
    python scripts/register_plugin.py
"""
import sys, os, base64, requests

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env

load_env()
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
API = f"{DATAVERSE_URL}/api/data/v9.2"
SOLUTION_NAME = os.environ["SOLUTION_NAME"]

# --- Configuration ---
ASSEMBLY_NAME    = "<PluginName>"
TYPE_NAME        = "<Namespace>.<ClassName>"   # Fully-qualified plugin class name
PUBLIC_KEY_TOKEN = "<16-hex-chars>"            # From: sn -T <PluginName>.dll
ASSEMBLY_VERSION = "1.0.0.0"
DLL_PATH         = "plugins/<PluginName>/bin/Release/net462/<PluginName>.dll"
MESSAGE_NAME     = "Create"                    # e.g. Create, Update, Delete
ENTITY_NAME      = "account"                   # Logical entity name
STAGE            = 20                          # 10=PreValidation, 20=PreOperation, 40=PostOperation
MODE             = 0                           # 0=Synchronous, 1=Asynchronous
# ---------------------


def hdrs(token):
    return {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def find_or_register_assembly(token):
    resp = requests.get(
        f"{API}/pluginassemblies?$select=pluginassemblyid,name"
        f"&$filter=name eq '{ASSEMBLY_NAME}'",
        headers=hdrs(token),
    )
    resp.raise_for_status()
    existing = resp.json().get("value", [])
    try:
        with open(DLL_PATH, "rb") as dll_file:
            dll_b64 = base64.b64encode(dll_file.read()).decode()
    except FileNotFoundError:
        print(f"ERROR: DLL file not found at '{DLL_PATH}'. Please build the plugin before deploying.")
        raise

    if existing:
        asm_id = existing[0]["pluginassemblyid"]
        print(f"Assembly already registered ({asm_id}) — updating content...")
        r = requests.patch(
            f"{API}/pluginassemblies({asm_id})",
            json={"content": dll_b64},
            headers=hdrs(token),
        )
        r.raise_for_status()
        print("Assembly content updated.")
        return asm_id

    body = {
        "name": ASSEMBLY_NAME,
        "culture": "neutral",
        "publickeytoken": PUBLIC_KEY_TOKEN,
        "version": ASSEMBLY_VERSION,
        "sourcetype": 0,   # 0 = Database
        "isolationmode": 2, # 2 = Sandbox
        "content": dll_b64,
    }
    resp = requests.post(f"{API}/pluginassemblies", json=body, headers=hdrs(token))
    if not resp.ok:
        print(f"ERROR {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    asm_id = resp.headers["OData-EntityId"].split("(")[1].rstrip(")")
    print(f"Registered assembly: {asm_id}")
    return asm_id


def find_or_register_type(token, asm_id):
    resp = requests.get(
        f"{API}/plugintypes?$select=plugintypeid"
        f"&$filter=typename eq '{TYPE_NAME}'",
        headers=hdrs(token),
    )
    resp.raise_for_status()
    existing = resp.json().get("value", [])
    if existing:
        pt_id = existing[0]["plugintypeid"]
        print(f"Plugin type already registered: {pt_id}")
        return pt_id

    body = {
        "typename": TYPE_NAME,
        "friendlyname": TYPE_NAME,
        "name": TYPE_NAME,
        "pluginassemblyid@odata.bind": f"/pluginassemblies({asm_id})",
    }
    resp = requests.post(f"{API}/plugintypes", json=body, headers=hdrs(token))
    resp.raise_for_status()
    pt_id = resp.headers["OData-EntityId"].split("(")[1].rstrip(")")
    print(f"Registered plugin type: {pt_id}")
    return pt_id


def get_message_and_filter(token):
    resp = requests.get(
        f"{API}/sdkmessages?$select=sdkmessageid&$filter=name eq '{MESSAGE_NAME}'",
        headers=hdrs(token),
    )
    resp.raise_for_status()
    msg_values = resp.json().get("value", [])
    if not msg_values:
        raise ValueError(f"No sdkmessage found with name '{MESSAGE_NAME}'. Please check that the message exists in the environment.")
    msg_id = msg_values[0]["sdkmessageid"]

    resp = requests.get(
        f"{API}/sdkmessagefilters?$select=sdkmessagefilterid"
        f"&$filter=sdkmessageid/sdkmessageid eq '{msg_id}'"
        f" and primaryobjecttypecode eq '{ENTITY_NAME}'",
        headers=hdrs(token),
    )
    resp.raise_for_status()
    fil_id = resp.json()["value"][0]["sdkmessagefilterid"]
    return msg_id, fil_id


def find_or_register_step(token, pt_id, msg_id, fil_id):
    step_name = f"{TYPE_NAME}: {MESSAGE_NAME} of {ENTITY_NAME}"
    resp = requests.get(
        f"{API}/sdkmessageprocessingsteps?$select=sdkmessageprocessingstepid"
        f"&$filter=name eq '{step_name}'",
        headers=hdrs(token),
    )
    resp.raise_for_status()
    existing = resp.json().get("value", [])
    if existing:
        step_id = existing[0]["sdkmessageprocessingstepid"]
        print(f"Step already registered: {step_id}")
        return step_id

    body = {
        "name": step_name,
        "rank": 1,
        "stage": STAGE,
        "mode": MODE,
        "supporteddeployment": 0,
        "plugintypeid@odata.bind": f"/plugintypes({pt_id})",
        "sdkmessageid@odata.bind": f"/sdkmessages({msg_id})",
        "sdkmessagefilterid@odata.bind": f"/sdkmessagefilters({fil_id})",
    }
    resp = requests.post(f"{API}/sdkmessageprocessingsteps", json=body, headers=hdrs(token))
    resp.raise_for_status()
    step_id = resp.headers["OData-EntityId"].split("(")[1].rstrip(")")
    print(f"Registered step: {step_id}")
    return step_id


def add_to_solution(token, component_id, component_type):
    resp = requests.post(
        f"{API}/AddSolutionComponent",
        json={
            "ComponentId": component_id,
            "ComponentType": component_type,
            "SolutionUniqueName": SOLUTION_NAME,
            "AddRequiredComponents": False,
        },
        headers=hdrs(token),
    )
    resp.raise_for_status()


def main():
    print("Authenticating...")
    token = get_token()
    print("OK\n")

    print("Registering assembly...")
    asm_id = find_or_register_assembly(token)

    print("\nRegistering plugin type...")
    pt_id = find_or_register_type(token, asm_id)

    print("\nResolving SDK message and filter...")
    msg_id, fil_id = get_message_and_filter(token)

    print("\nRegistering step...")
    step_id = find_or_register_step(token, pt_id, msg_id, fil_id)

    print(f"\nAdding to solution '{SOLUTION_NAME}'...")
    add_to_solution(token, asm_id, 91)    # 91 = PluginAssembly
    add_to_solution(token, step_id, 92)   # 92 = SdkMessageProcessingStep

    print("\nDone.")


if __name__ == "__main__":
    main()
```

```
python scripts/register_plugin.py
```

### Subsequent updates: Push via PAC CLI

Once the assembly is registered (first-time script has run), you can update the DLL on subsequent builds using `pac plugin push`. You need the assembly's registration ID:

```python
# Get the pluginassemblyid from the environment
import requests, sys, os
sys.path.insert(0, "scripts")
from auth import get_token, load_env
load_env()
token = get_token()
resp = requests.get(
    f"{os.environ['DATAVERSE_URL'].rstrip('/')}/api/data/v9.2/pluginassemblies"
    f"?$select=pluginassemblyid,name&$filter=name eq '<PluginName>'",
    headers={"Authorization": f"Bearer {token}", "OData-Version": "4.0",
             "OData-MaxVersion": "4.0", "Accept": "application/json"}
)
print(resp.json()["value"][0]["pluginassemblyid"])
```

Then push the updated DLL:

```
pac plugin push \
  --pluginId <pluginassemblyid-guid> \
  --pluginFile plugins/<PluginName>/bin/Release/net462/<PluginName>.dll \
  --environment <url>
```

### Pull the solution from the environment to the repo

After deployment, always pull the environment's state back to the repo. This captures the plugin assembly registration and step registration that Dynamics generated:

```
pac solution export --name <SolutionName> --path ./solutions/<SolutionName>.zip --managed false
pac solution unpack --zipfile ./solutions/<SolutionName>.zip --folder ./solutions/<SolutionName>
rm ./solutions/<SolutionName>.zip
git add ./solutions/<SolutionName> && git commit -m "chore: pull <SolutionName>"
```

The pulled files include `solutions/<SolutionName>/PluginAssemblies/` and `solutions/<SolutionName>/SdkMessageProcessingSteps/` — these are generated by Dynamics and should not be hand-edited.

## Repo Layout

```
plugins/
  README.md                    — build and registration instructions
  <PluginName>/
    <PluginName>.csproj
    <PluginName>.snk            — gitignored (private key)
    <ClassName>.cs
    packages.lock.json
  <PluginName>.Tests/
    <PluginName>.Tests.csproj
    <ClassName>Tests.cs
```

## Common Patterns

### Pre-operation validation (throw to block the operation)
```csharp
if (target.GetAttributeValue<Money>("new_amount")?.Value > 1000000)
{
    throw new InvalidPluginExecutionException(
        OperationStatus.Failed,
        "Amount cannot exceed $1,000,000.");
}
```

### Post-operation: read the created record ID
```csharp
// In PostOperation stage, context.OutputParameters["id"] has the new record GUID
var newId = (Guid)context.OutputParameters["id"];
```

### Call the organization service
```csharp
// Retrieve a related record
var account = service.Retrieve("account",
    target.GetAttributeValue<EntityReference>("new_accountid").Id,
    new ColumnSet("name", "creditlimit"));
```

### Plugin execution context stages
| Stage | Code | When |
|---|---|---|
| PreValidation | 10 | Before database transaction |
| PreOperation | 20 | Inside transaction, before write |
| PostOperation | 40 | Inside transaction, after write |

## Unit Tests

### Scaffold the test project

Write `plugins/<PluginName>.Tests/<PluginName>.Tests.csproj` directly (`dotnet new mstest --framework net462` fails on modern SDKs for the same reason as the plugin project):

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net462</TargetFramework>
    <AssemblyName><PluginName>.Tests</AssemblyName>
    <RootNamespace><PluginName>.Tests</RootNamespace>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
    <PackageReference Include="MSTest.TestAdapter" Version="3.1.1" />
    <PackageReference Include="MSTest.TestFramework" Version="3.1.1" />
    <PackageReference Include="FakeXrmEasy.9" Version="1.58.1" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="../<PluginName>/<PluginName>.csproj" />
  </ItemGroup>
</Project>
```

### Example test class

```csharp
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Microsoft.Xrm.Sdk;
using FakeXrmEasy;

namespace <PluginName>.Tests
{
    [TestClass]
    public class <ClassName>Tests
    {
        [TestMethod]
        public void FieldSetFromName_WhenNotProvided()
        {
            var ctx = new XrmFakedContext();
            var target = new Entity("account")
            {
                ["name"] = "Contoso Ltd"
            };

            ctx.ExecutePluginWithTarget<<ClassName>>(target);

            Assert.AreEqual("Contoso Ltd", target["new_myfield"]);
        }

        [TestMethod]
        public void ExistingFieldPreserved_WhenAlreadySet()
        {
            var ctx = new XrmFakedContext();
            var target = new Entity("account")
            {
                ["name"] = "Contoso Ltd",
                ["new_myfield"] = "Custom Value"
            };

            ctx.ExecutePluginWithTarget<<ClassName>>(target);

            Assert.AreEqual("Custom Value", target["new_myfield"]);
        }
    }
}
```

### Build and run tests

```
dotnet test plugins/<PluginName>.Tests
```

## Notes

- Always isolate plugins in **Sandbox** mode for security. Full Trust is only available for on-premises.
- Avoid HTTP calls from plugins unless absolutely necessary — use Azure Service Bus or custom APIs instead.
- Keep plugin execution under 2 minutes (platform limit). Long-running work belongs in Azure Functions or flows.
- Strong-naming is **required** by Dataverse — see the Strong-naming section above. Every plugin must have a `.snk` key file.

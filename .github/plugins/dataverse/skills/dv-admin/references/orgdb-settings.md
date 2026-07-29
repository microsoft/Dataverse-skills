# OrgDB Settings (orgdborgsettings XML)

Settings like search mode, MCP, copilot features, fabric, and retention live inside the `orgdborgsettings` XML blob. The XML uses **direct PascalCase elements** (NOT `<pair>` tags):

```xml
<OrgSettings>
  <IsMCPEnabled>true</IsMCPEnabled>
  <SearchAndCopilotIndexMode>0</SearchAndCopilotIndexMode>
  <IsLinkToFabricEnabled>true</IsLinkToFabricEnabled>
  <IsFabricVirtualTableEnabled>false</IsFabricVirtualTableEnabled>
</OrgSettings>
```

**Read all OrgDB settings:**

```python
import os, sys
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-admin")

# orgdborgsettings is a column on the organization entity — plain SDK record read.
orgs = list(client.records.list("organization", select=["organizationid", "orgdborgsettings"]))
root = ET.fromstring(orgs[0].get("orgdborgsettings") or "<OrgSettings></OrgSettings>")
for child in sorted(root, key=lambda c: c.tag):
    print(f"  {child.tag} = {child.text}", flush=True)
```

**Update or add an OrgDB setting:**

```python
import os, sys
from xml.etree import ElementTree as ET
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-admin")

SETTING_NAME = "SearchAndCopilotIndexMode"  # PascalCase, case-sensitive
SETTING_VALUE = "0"                          # always a string in XML

# organization is an ordinary entity; orgdborgsettings is one of its columns.
orgs = list(client.records.list("organization", select=["organizationid", "orgdborgsettings"]))
org = orgs[0]
org_id = org["organizationid"]

root = ET.fromstring(org.get("orgdborgsettings") or "<OrgSettings></OrgSettings>")

# Update existing or add new
existing = root.find(SETTING_NAME)
if existing is not None:
    print(f"Current {SETTING_NAME} = {existing.text}", flush=True)
    existing.text = SETTING_VALUE
else:
    print(f"{SETTING_NAME} not set -- adding", flush=True)
    ET.SubElement(root, SETTING_NAME).text = SETTING_VALUE

client.records.update("organization", org_id, {"orgdborgsettings": ET.tostring(root, encoding="unicode")})
print(f"SUCCESS: {SETTING_NAME} = {SETTING_VALUE}", flush=True)
```

**Remove an OrgDB setting:**

```python
# After fetching and parsing the XML (same as above):
existing = root.find(SETTING_NAME)
if existing is not None:
    root.remove(existing)
    client.records.update("organization", org_id, {"orgdborgsettings": ET.tostring(root, encoding="unicode")})
```

**Allowed OrgDB settings (17 keys — PascalCase, case-sensitive):**

| Setting | Type | Values | PPAC label |
|---|---|---|---|
| `IsMCPEnabled` | bool | `true` / `false` | Allow MCP clients to interact with Dataverse MCP server |
| `IsMCPPreviewEnabled` | bool | `true` / `false` | Advanced Settings (enable non-Copilot Studio MCP clients) |
| `SearchAndCopilotIndexMode` | int | `0` Search Off / Copilot On; `1` Both On; `2` Both Off; `3` Search On / Copilot Off | Dataverse search + Search for records in Microsoft 365 apps (one key, two UI toggles — see truth table above) |
| `IsLinkToFabricEnabled` | bool | `true` / `false` | Link Dataverse tables with Microsoft Fabric workspace |
| `IsFabricVirtualTableEnabled` | bool | `true` / `false` | Define Dataverse virtual tables using Fabric OneLake data |
| `ShowDataInM365Copilot` | bool | `true` / `false` | Allow data availability in Microsoft 365 Copilot |
| `EnableWorkIQ` | bool | `true` / `false` | Turn on Dataverse intelligence (Work IQ) for agents |
| `IsLockdownOfUnmanagedCustomizationEnabled` | bool | `true` / `false` | Block unmanaged customizations in environment |
| `EnableSecurityOnAttachment` | bool | `true` / `false` | Enable security on Attachment entity |
| `EnableTDSEndpoint` | bool | `true` / `false` | Enable TDS endpoint |
| `AllowAccessToTDSEndpoint` | bool | `true` / `false` | Enable user level access control for TDS endpoint (requires TDS endpoint enabled first) |
| `EnableOwnershipAcrossBusinessUnits` | bool | `true` / `false` | Record ownership across business units |
| `CreateOnlyNonEmptyAddressRecordsForEligibleEntities` | bool | `true` / `false` | Disable empty address record creation (affects Account, Contact, Lead) |
| `EnableDeleteAddressRecords` | bool | `true` / `false` | Enable deletion of address records |
| `BlockDeleteManagedAttributeMap` | bool | `true` / `false` | Block deletion of OOB attribute maps |
| `EnableSystemUserDelete` | bool | `true` / `false` | Enable delete disabled users |
| `IsExcelToExistingTableWithAssistedMappingEnabled` | bool | `true` / `false` | Import Excel to existing table with AI-assisted mapping |

Every other OrgDB key (`IsRetentionEnabled`, `IsArchivalEnabled`, `IsDVCopilotForTextDataEnabled`, `IsShadowLakeEnabled`, `IsCommandingModifiedOnEnabled`, `CanCreateApplicationStubUser`, `AllowRoleAssignmentOnDisabledUsers`, `EnableActivitiesFeatures`, `TDSListenerInitialized`, `AzureSynapseLinkIncrementalUpdateTimeInterval`, etc.) is **out of scope** — refuse and direct the user to the Power Platform admin center. Do NOT dump the whole `orgdborgsettings` XML to "discover" other settings for the user.

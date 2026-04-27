# Forms and Views — Web API patterns

Neither the MCP server nor the Python SDK supports forms or views. Use the Web API directly via `urllib`.

## Create a form

```python
# POST /api/data/v9.2/systemforms
import os, sys, json, urllib.request
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env  # get_token() is correct here — SDK does not support forms

load_env()
env = os.environ["DATAVERSE_URL"].rstrip("/")
token = get_token()

form_xml = """<form type="7" name="Project Budget" id="{FORM-GUID}">
  <tabs>
    <tab name="{TAB-GUID}" id="{TAB-GUID}" expanded="true" showlabel="true">
      <labels><label description="General" languagecode="1033" /></labels>
      <columns><column width="100%">
        <sections>
          <section name="{SEC-GUID}" id="{SEC-GUID}" showlabel="false" showbar="false" columns="111">
            <labels><label description="General" languagecode="1033" /></labels>
            <rows>
              <row>
                <cell id="{CELL-GUID-1}" showlabel="true">
                  <labels><label description="Name" languagecode="1033" /></labels>
                  <control id="new_name" classid="{4273EDBD-AC1D-40d3-9FB2-095C621B552D}"
                           datafieldname="new_name" disabled="false" />
                </cell>
              </row>
            </rows>
          </section>
        </sections>
      </column></columns>
    </tab>
  </tabs>
  <header><rows /></header><footer><rows /></footer>
</form>"""

body = {
    "name": "Project Budget Quick Create",
    "objecttypecode": "new_projectbudget",
    "type": 7,           # 7 = quick create, 2 = main
    "formxml": form_xml,
    "iscustomizable": {"Value": True}
}

req = urllib.request.Request(
    f"{env}/api/data/v9.2/systemforms",
    data=json.dumps(body).encode(),
    headers={"Authorization": f"Bearer {token}",
             "Content-Type": "application/json",
             "OData-MaxVersion": "4.0",
             "OData-Version": "4.0"},
    method="POST"
)
with urllib.request.urlopen(req) as resp:
    print(f"Created. FormId: {resp.headers.get('OData-EntityId')}")
```

**Form type codes:** `2` = Main, `7` = Quick Create, `6` = Quick View, `11` = Card

## Retrieve and modify an existing form

```python
# env and token must be initialized (see form creation setup above)
import json, urllib.request  # SDK does not support forms — raw Web API required

# Step 1: GET the form
url = (f"{env}/api/data/v9.2/systemforms"
       f"?$filter=objecttypecode eq 'new_projectbudget' and type eq 2"
       f"&$select=formid,name,formxml")
req = urllib.request.Request(url, headers={
    "Authorization": f"Bearer {token}",
    "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json",
})
with urllib.request.urlopen(req) as resp:
    forms = json.loads(resp.read()).get("value", [])

if not forms:
    raise ValueError("Form not found")

form_id = forms[0]["formid"]
form_xml = forms[0]["formxml"]

# Step 2: Modify form_xml string as needed (e.g., add a control, reorder fields)
# form_xml = form_xml.replace(...)

# Step 3: PATCH the form back
patch_body = json.dumps({"formxml": form_xml}).encode()
req = urllib.request.Request(
    f"{env}/api/data/v9.2/systemforms({form_id})",
    data=patch_body,
    headers={"Authorization": f"Bearer {token}",
             "Content-Type": "application/json",
             "OData-MaxVersion": "4.0", "OData-Version": "4.0"},
    method="PATCH"
)
with urllib.request.urlopen(req) as resp:
    print(f"Updated. Status: {resp.status}")
# Then publish (see Publish section below)
```

## Publish forms after create/modify

Forms must be published to take effect. Do this immediately after creating or modifying a form. `env` and `token` come from the form creation setup block above — if publishing standalone, re-initialize them:

```python
# env and token must be initialized (see form creation setup above)
# SDK does not support form publishing — raw Web API required
body = json.dumps({
    "ParameterXml": "<importexportxml><entities><entity>new_projectbudget</entity></entities></importexportxml>"
}).encode()
req = urllib.request.Request(
    f"{env}/api/data/v9.2/PublishXml",
    data=body,
    headers={"Authorization": f"Bearer {token}",
             "Content-Type": "application/json",
             "OData-MaxVersion": "4.0", "OData-Version": "4.0"},
    method="POST"
)
with urllib.request.urlopen(req) as resp:
    print(f"Published. Status: {resp.status}")
```

Replace `new_projectbudget` with the logical name of the entity whose form you modified.

## Create a view

```python
# POST /api/data/v9.2/savedqueries
fetch_xml = """<fetch version="1.0" output-format="xml-platform" mapping="logical">
  <entity name="new_projectbudget">
    <attribute name="new_name" />
    <attribute name="new_amount" />
    <attribute name="new_status" />
    <order attribute="new_name" descending="false" />
    <filter type="and">
      <condition attribute="statecode" operator="eq" value="0" />
      <condition attribute="ownerid" operator="eq-userid" />
    </filter>
  </entity>
</fetch>"""

layout_xml = """<grid name="resultset" jump="new_name" select="1" icon="1" preview="1">
  <row name="result" id="new_projectbudgetid">
    <cell name="new_name" width="200" />
    <cell name="new_amount" width="125" />
    <cell name="new_status" width="125" />
  </row>
</grid>"""

body = {
    "name": "My Open Budgets",
    "returnedtypecode": "new_projectbudget",
    "querytype": 0,       # 0 = standard view
    "fetchxml": fetch_xml,
    "layoutxml": layout_xml,
    "isdefault": False,
    "isprivate": False,
    "isquickfindquery": False,
}
# POST to /api/data/v9.2/savedqueries
```

**querytype values:** `0` = standard view, `1` = advanced find default, `2` = associated view, `4` = quick find

## When to Edit Existing Form XML Directly

If the form is already in the repo (pulled via `pac solution unpack`), targeted edits are acceptable — e.g., reordering fields, changing a label, adding a control to an existing section. For these cases, use this control classid reference:

| Field type | Control classid |
|---|---|
| Text (nvarchar) | `{4273EDBD-AC1D-40d3-9FB2-095C621B552D}` |
| Currency (money) | `{533B9108-5A8B-42cb-BD37-52D1B8E7C741}` |
| Choice (picklist) | `{3EF39988-22BB-4f0b-BBBE-64B5A3748AEE}` |
| Lookup | `{270BD3DB-D9AF-4782-9025-509E298DEC0A}` |
| Date/Time | `{5B773807-9FB2-42db-97C3-7A91EFF8ADFF}` |
| Whole Number | `{C6D124CA-7EDA-4a60-AEA9-7FB8D318B68F}` |
| Decimal | `{C3EFE0C3-0EC6-42be-8349-CBD9079C5A6F}` |
| Toggle (boolean) | `{67FAC785-CD58-4f9f-ABB3-4B7DDC6ED5ED}` |
| Subgrid | `{E7A81278-8635-4d9e-8D4D-59480B391C5B}` |
| Multiline Text (memo) | `{E0DECE4B-6FC8-4a8f-A065-082708572369}` |

All `id` attributes in form XML must be unique GUIDs. Generate them inside your Python script:

```python
import uuid
guid = str(uuid.uuid4()).upper()
```

**Do not use `python -c` for GUID generation on Windows** — multiline `python -c` commands break in Git Bash due to quoting differences. Always write a `.py` script instead.

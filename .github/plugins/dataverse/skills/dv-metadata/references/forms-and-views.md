# Forms and Views — creating `systemform` / `savedquery` records

`systemform` (forms) and `savedquery` (views) are **ordinary Dataverse entities**, so the **Python SDK's generic record CRUD creates and modifies them directly** — there is no dedicated helper, and none is needed. The SDK is the default here: it carries managed auth and paging, and you stay in Python to build and mutate the XML. The **only** operation the SDK can't do is **publishing** (`PublishXml` is an unbound Web API action with no SDK method) — route that one call through the **Dataverse CLI** (`dataverse api request`). **Do not use `urllib` for any of this.**

> **The hard part is the XML, not the transport.** `formxml` / `fetchxml` / `layoutxml` are identical no matter how you send them. The reliable way to get valid XML is to **retrieve a live template and mutate it** (below) — not to hand-author the root envelope. A hand-authored `<form>` root is the #1 cause of "required id" / schema-rejection errors.

## Create a form (SDK)

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-metadata")

# For valid XML, prefer the retrieve-a-template pattern below. This literal is
# illustrative; keep the server's root envelope, element id GUIDs, and control
# classids rather than hand-authoring them.
form_xml = """<form>
  <tabs>
    <tab id="{TAB-GUID}" IsUserDefined="1" showlabel="true">
      <labels><label description="General" languagecode="1033" /></labels>
      <columns><column width="100%"><sections>
        <section id="{SEC-GUID}" showlabel="true" showbar="true" IsUserDefined="1">
          <labels><label description="General" languagecode="1033" /></labels>
          <rows><row><cell id="{CELL-GUID}">
            <labels><label description="Name" languagecode="1033" /></labels>
            <control id="new_name" classid="{4273EDBD-AC1D-40d3-9FB2-095C621B552D}" datafieldname="new_name" />
          </cell></row></rows>
        </section>
      </sections></column></columns>
    </tab>
  </tabs>
</form>"""

form_id = client.records.create("systemform", {
    "name": "Project Budget Main",
    "objecttypecode": "new_projectbudget",
    "type": 2,                          # 2 = Main, 7 = Quick Create, 6 = Quick View, 11 = Card
    "formxml": form_xml,
    "iscustomizable": {"Value": True},
})
print(f"Created form: {form_id}")
# Publish so it takes effect (see Publish section).
```

**Form type codes:** `2` = Main, `7` = Quick Create, `6` = Quick View, `11` = Card

## Retrieve a template and modify it (SDK) — the reliable path

Pull a live, environment-valid form as a template, mutate the XML string, and write it back. This inherits the server's correct root envelope, element `id` GUIDs, and control `classid`s for free — which is why it works when hand-authored XML doesn't.

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-metadata")

# Step 1: retrieve an existing Main form for the table as a template.
result = client.records.list(
    "systemform",
    select=["formid", "name", "formxml"],
    filter="objecttypecode eq 'new_projectbudget' and type eq 2",
    top=1,
)
rows = list(result)
if not rows:
    raise ValueError("No form found to use as a template")
form_id = rows[0]["formid"]
form_xml = rows[0]["formxml"]

# Step 2: mutate the XML string — swap datafieldname / labels, add a cell, etc.
# Keep the root envelope, id GUIDs, and classids from the template.
# form_xml = form_xml.replace("new_oldfield", "new_newfield")

# Step 3: write it back (generic record update — systemform is just an entity).
client.records.update("systemform", form_id, {"formxml": form_xml})
print("Form updated from template — publish next.")
```

## Publish after create/modify (Dataverse CLI — the one escape hatch)

Forms and views must be published to take effect. `PublishXml` is an **unbound Web API action** — the SDK has no method for it — so this is the single call that leaves the SDK. Use `dataverse api request` (managed auth, real exit code), **not** `urllib`:

```bash
dataverse api request \
  --target dataverse \
  --method POST \
  --path /api/data/v9.2/PublishXml \
  --body-file ./publish.json \
  --context "app=dataverse-skills/<ver>;skill=dv-metadata;agent=<agent>"
```

Where `publish.json` contains (replace `new_projectbudget` with the modified entity's logical name):

```json
{ "ParameterXml": "<importexportxml><entities><entity>new_projectbudget</entity></entities></importexportxml>" }
```

## Create a view (SDK)

A view is a `savedquery` record. The grid `layoutxml` needs the table's **numeric `ObjectTypeCode`** in its `object=` attribute — read that first (it's not on `TableInfo`, so use a one-shot metadata read via the CLI):

```bash
dataverse api request --target dataverse --method GET \
  --path "/api/data/v9.2/EntityDefinitions(LogicalName='new_projectbudget')?%24select=ObjectTypeCode" \
  --environment <DATAVERSE_URL> \
  --context "app=dataverse-skills/<ver>;skill=dv-metadata;agent=<agent>"
```

Then create the record with the SDK:

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-metadata")

object_type_code = 10123  # from the EntityDefinitions read above

fetch_xml = """<fetch version="1.0" output-format="xml-platform" mapping="logical">
  <entity name="new_projectbudget">
    <attribute name="new_name" />
    <attribute name="new_amount" />
    <attribute name="new_status" />
    <order attribute="new_name" descending="false" />
    <filter type="and"><condition attribute="statecode" operator="eq" value="0" /></filter>
  </entity>
</fetch>"""

layout_xml = f"""<grid name="resultset" object="{object_type_code}" jump="new_name" select="1" icon="1" preview="1">
  <row name="result" id="new_projectbudgetid">
    <cell name="new_name" width="200" />
    <cell name="new_amount" width="125" />
    <cell name="new_status" width="125" />
  </row>
</grid>"""

view_id = client.records.create("savedquery", {
    "name": "My Open Budgets",
    "returnedtypecode": "new_projectbudget",
    "querytype": 0,                     # 0 = standard view
    "fetchxml": fetch_xml,
    "layoutxml": layout_xml,
    "isdefault": False,
    "isprivate": False,
})
print(f"Created view: {view_id}")   # publish next
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

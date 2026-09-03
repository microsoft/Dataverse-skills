# Column Types

Use `client.tables.add_columns(...)` for standard columns:

| Requested type | SDK value | Dataverse metadata type |
|---|---|---|
| Single-line text | `"string"` or `"text"` | `StringAttributeMetadata` |
| Multiline text | `"memo"` or `"multiline"` | `MemoAttributeMetadata` |
| Whole number | `"int"` or `"integer"` | `IntegerAttributeMetadata` |
| Decimal | `"decimal"` or `"money"` | `DecimalAttributeMetadata` |
| Floating point | `"float"` or `"double"` | `DoubleAttributeMetadata` |
| Date and time | `"datetime"` or `"date"` | `DateTimeAttributeMetadata` |
| Yes/no | `"bool"` or `"boolean"` | `BooleanAttributeMetadata` |
| File | `"file"` | `FileAttributeMetadata` |
| Local choice | `IntEnum` subclass | `PicklistAttributeMetadata` |

The SDK's `"money"` alias currently creates a decimal column, not Dataverse currency. Use the Web API payload below only when the requested column is currency (`MoneyAttributeMetadata`); it also demonstrates explicit currency precision. For a decimal column, keep `DecimalAttributeMetadata` and set its precision instead.

```python
def label(text):
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [{
            "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
            "Label": text,
            "LanguageCode": 1033,
        }],
    }

attribute = {
    "@odata.type": "Microsoft.Dynamics.CRM.MoneyAttributeMetadata",
    "SchemaName": "new_EstimatedCost",
    "DisplayName": label("Estimated Cost"),
    "RequiredLevel": {"Value": "None"},
    "MinValue": 0,
    "MaxValue": 1000000000,
    "Precision": 2,
    "PrecisionSource": 0,
}
odata = client._get_odata()
odata._request(
    "post",
    f"{odata.base_url}/api/data/v9.2/EntityDefinitions(LogicalName='new_project')/Attributes",
    json=attribute,
    headers={"MSCRM.SolutionUniqueName": "MySolution"},
)
```

`PrecisionSource: 0` uses the explicit `Precision`; `2` uses the transaction-currency precision instead.

## Existing Tables and Solution Ownership

`client.tables.add_columns(...)` does not accept `solution=`. For a solution-owned column on an existing table, build the SDK's metadata payload and post it with the solution header:

```python
from enum import IntEnum

class BudgetStatus(IntEnum):
    DRAFT = 100000000
    APPROVED = 100000001
    REJECTED = 100000002

odata = client._get_odata()
for schema_name, column_type in {
    "new_Description": "memo",
    "new_Status": BudgetStatus,
}.items():
    payload = odata._attribute_payload(schema_name, column_type)
    odata._request(
        "post",
        f"{odata.api}/EntityDefinitions(LogicalName='new_projectbudget')/Attributes",
        json=payload,
        headers={"MSCRM.SolutionUniqueName": "MySolution"},
    )
```

Use the same metadata endpoint for advanced settings such as a custom Memo maximum length. After metadata propagation, call `client.tables.list_columns(...)` and verify every requested property, including `LogicalName`, `AttributeType`, `MaxLength`, `Precision`, and `PrecisionSource` as applicable. A successful request is not proof that the requested Dataverse type or settings were created.

Also query the confirmed solution's `solutioncomponent` rows and assert that every returned attribute metadata ID is present as component type `2`. Column metadata verification proves shape; solution-component verification separately proves export ownership. Do not report completion unless both pass.
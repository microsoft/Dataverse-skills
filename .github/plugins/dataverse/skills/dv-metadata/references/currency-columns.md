# Currency columns

The Python SDK currently maps both `"decimal"` and `"money"` to `DecimalAttributeMetadata`. For a true Dataverse currency column, use the managed `dataverse api request` escape hatch with `MoneyAttributeMetadata`. Do not send metadata payloads with `requests` or `urllib`.

Create the payload file with Python:

```python
import json

attribute = {
    "@odata.type": "Microsoft.Dynamics.CRM.MoneyAttributeMetadata",
    "SchemaName": "new_amount",
    "DisplayName": {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [{
            "@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
            "Label": "Amount",
            "LanguageCode": 1033,
        }],
    },
    "RequiredLevel": {"Value": "None"},
    "MinValue": 0,
    "MaxValue": 1000000000,
    "Precision": 2,
    "PrecisionSource": 2,
}

with open("money-column.json", "w", encoding="utf-8") as payload_file:
    json.dump(attribute, payload_file)
```

Send it through the authenticated CLI and associate it with the solution:

```
dataverse api request --target dataverse --method POST --path "/api/data/v9.2/EntityDefinitions(LogicalName='new_projectbudget')/Attributes" --body-file money-column.json --header "MSCRM.SolutionUniqueName:MySolution" --context "app=dataverse-skills/<ver>;skill=dv-metadata;agent=<agent>"
```

After creation, read the column metadata and confirm `AttributeType` is `Money` before reporting success.

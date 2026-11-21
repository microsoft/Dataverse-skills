# Create a table with the Web API

Fallback for `dv-metadata` when the SDK's `client.tables.create()` does not expose a property you need (OwnershipType, HasActivities, and similar). Prefer the SDK otherwise.

```python
# Helper for Label boilerplate
def label(text):
    return {"@odata.type": "Microsoft.Dynamics.CRM.Label",
            "LocalizedLabels": [{"@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
                                  "Label": text, "LanguageCode": 1033}]}

entity = {
    "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
    "SchemaName": "new_ProjectBudget",
    "DisplayName": label("Project Budget"),
    "DisplayCollectionName": label("Project Budgets"),
    "Description": label(""),
    "OwnershipType": "UserOwned",
    "HasActivities": False, "HasNotes": False, "IsActivity": False,
    "PrimaryNameAttribute": "new_name",
    "Attributes": [{
        "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
        "SchemaName": "new_name",
        "DisplayName": label("Name"),
        "RequiredLevel": {"Value": "ApplicationRequired"},
        "MaxLength": 100, "IsPrimaryName": True,
    }]
}
# POST to /api/data/v9.2/EntityDefinitions with MSCRM.SolutionUniqueName header
```

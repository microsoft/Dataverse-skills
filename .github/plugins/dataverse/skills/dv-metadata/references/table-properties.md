# Advanced table properties

Prefer SDK table creation. Use this metadata payload only when the required properties, such as `OwnershipType` or `HasActivities`, are not exposed by the installed SDK. Replace the illustrative `new` prefix with the confirmed publisher prefix. Submit to `/api/data/v9.2/EntityDefinitions` through the managed `dataverse api request` surface with skill attribution and the confirmed `MSCRM.SolutionUniqueName` header.

```python
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
```

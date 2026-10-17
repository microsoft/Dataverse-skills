# Currency (Money) columns

The SDK's `"money"` type string is an alias for `"decimal"`. It creates a `DecimalAttributeMetadata` column, not a currency column, and there is no SDK type that creates a real currency column. When the user asks for a currency, money, or cost column, create it with `dataverse api request` (managed auth, real exit code), not `urllib`.

Create the table and all other columns with the SDK first, then add the currency column:

```bash
dataverse api request \
  --target dataverse \
  --method POST \
  --path "/api/data/v9.2/EntityDefinitions(LogicalName='new_projectbudget')/Attributes" \
  --header "MSCRM.SolutionUniqueName:<SolutionUniqueName>" \
  --body-file ./money-column.json \
  --environment <DATAVERSE_URL> \
  --context "app=dataverse-skills/<ver>;skill=dv-metadata;agent=<agent>"
```

`money-column.json` (replace the schema name and labels):

```json
{
  "@odata.type": "Microsoft.Dynamics.CRM.MoneyAttributeMetadata",
  "SchemaName": "new_EstimatedCost",
  "DisplayName": { "LocalizedLabels": [ { "Label": "Estimated Cost", "LanguageCode": 1033 } ] },
  "RequiredLevel": { "Value": "None" },
  "PrecisionSource": 2,
  "MinValue": 0,
  "MaxValue": 1000000000
}
```

- The `MSCRM.SolutionUniqueName` header adds the column to the solution in the same call.
- `PrecisionSource: 2` uses the currency's precision; Dataverse also creates the `_base` column automatically.
- Verify afterwards with `client.tables.get_column("new_projectbudget", "new_estimatedcost")`; the attribute type should be `Money`, not `Decimal`.

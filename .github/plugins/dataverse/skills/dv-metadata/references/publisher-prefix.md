# Publisher Prefix

All custom schema names must use your solution's publisher prefix (e.g., `new_`, `contoso_`). Find yours:

```
pac solution list --environment <url>
```

Or check `solutions/<SOLUTION_NAME>/Other/Solution.xml` after the first pull — look for `<CustomizationPrefix>`.

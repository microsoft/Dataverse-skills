# Solution Membership

Track every changed metadata component as `(object_id, component_type)` when its mutation succeeds. Before exporting, query the confirmed solution and compare exact IDs and types:

```python
sol = client.records.list(
    "solution",
    filter="uniquename eq '<SOLUTION_NAME>'",
    select=["solutionid"],
    top=1,
).first()
if sol is None:
    raise RuntimeError("Solution not found")

components = client.records.list(
    "solutioncomponent",
    filter=f"_solutionid_value eq {sol['solutionid']}",
    select=["componenttype", "objectid"],
)
actual = {(str(row["objectid"]).lower(), row["componenttype"]) for row in components}
expected = {
    (str(component_id).lower(), component_type)
    for component_id, component_type in changed_components
}
missing = expected - actual
if missing:
    raise RuntimeError(f"Components missing from solution: {sorted(missing)}")
```

Common component types:

| Component | Type |
|---|---:|
| Table | 1 |
| Column | 2 |
| Relationship | 10 |
| Alternate key | 14 |
| View | 26 |
| Form | 60 |

Run this check after every mutation mechanism, including SDK methods with `solution=`, raw requests with `MSCRM.SolutionUniqueName`, explicit `AddSolutionComponent` calls, CLI operations, and MCP tools. Metadata shape checks and a nonzero aggregate component count do not prove that the changed object belongs to the intended solution.
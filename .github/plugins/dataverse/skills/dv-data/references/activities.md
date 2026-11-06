# Activities: Phone Calls, Tasks, Emails, Appointments

Activity tables are written like any other table, with two rules that are easy to miss:

1. **Bind the regarding row with the per-table navigation property** `regardingobjectid_<regarding table>_<activity table>` -- for example `regardingobjectid_account_phonecall` or `regardingobjectid_contact_task`. `regardingobjectid` itself is the polymorphic column, not a navigation property you can bind.
2. **Create the activity open, then close it.** Leave `statecode` and `statuscode` off the create. To record that the call, task, email, or meeting already happened, send ONE update that sets both codes as a matching pair -- every status reason belongs to exactly one state, and the numbers differ per table.

## Log a completed phone call against an account

```python
call_id = client.records.create("phonecall", {
    "subject": "Onboarding call",
    "description": "Ran the onboarding call today.",
    "regardingobjectid_account_phonecall@odata.bind": f"/accounts({account_id})",
})
client.records.update("phonecall", call_id, {"statecode": 1, "statuscode": 2})  # Completed / Made
```

## Matching state and status codes

| Table | Mark completed (`statecode`, `statuscode`) | Mark canceled (`statecode`, `statuscode`) |
|---|---|---|
| `phonecall` | `1`, `2` Made (or `4` Received) | `2`, `3` Canceled |
| `task` | `1`, `5` Completed | `2`, `6` Canceled |
| `email` | `1`, `2` Completed | `2`, `5` Canceled |
| `appointment` | `1`, `3` Completed | `2`, `4` Canceled |

For any other activity table, read the **StatusCode** choices in its table reference on Microsoft Learn (each status reason lists the state it belongs to) before writing the update. Do not guess the numbers.

## When a create fails

Fix the payload and create again only the record that failed. If earlier records in the same script were already created, follow [If a create script fails partway](multi-table-fk-import.md#if-a-create-script-fails-partway) -- re-running the whole script duplicates them.

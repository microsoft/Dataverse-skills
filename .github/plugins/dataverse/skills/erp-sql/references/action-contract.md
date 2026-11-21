# ERP SQL credential action contract

Detail for the **Discover the contract, not the password** step in `erp-sql`.
The safety rules in `SKILL.md` still apply; nothing here relaxes them.

## IPv4 only

The approved SQL firewall scope must be a public IPv4 address or bounded IPv4
range/CIDR. Azure SQL firewall endpoints do not accept IPv6. Reject IPv6 before
requesting credentials; do not substitute an IPv4 address without a new
user-supplied value and explicit approval.

## API documentation gap

The [product database access documentation](https://learn.microsoft.com/en-us/power-platform/developer/unified-experience/finance-operations-product-db-access)
documents the Visual Studio **Tools > SQL Credentials for Dynamics 365 FinOps**
workflow, not this Dataverse action or its request/response schema. Environment
metadata does not establish a publicly documented or supported API contract.

## Verify the discovered action against the helper

Treat `msprov_getfinopssqljitaccessasync` as a discovery candidate, not a fixed
public contract. Use `api describe` to inspect its binding, method, and
request/response field names and types. Compare these with the current
`scripts/connect.py` adapter (`ACTION`, `request_credentials`, and
`validate_credentials`). Its fixed path and field mappings are implementation
assumptions; the helper does not perform metadata discovery itself.

If the action is absent, discovery fails, or the schema cannot be verified as
compatible, **stop before requesting credentials**. Do not guess fields,
substitute an endpoint, or bypass validation. Direct the user to the documented
Visual Studio workflow instead. Discovery alone does not resolve the public API
support gap; API-owner confirmation/public documentation is still needed before
claiming a supported integration.

## Client-IP response format

The live API can return `ipaddress` as `start-end`, even for a single approved
address (for example, `8.8.8.8-8.8.8.8`). The helper normalizes approved CIDRs to
explicit inclusive ranges for `sqljitclientipaddress`. Require both returned
endpoints to equal the approved bounds exactly; reject broader, narrower,
reversed, non-public, or oversized scopes. A single IP and an identical-endpoint
range are equivalent. Never disable IP validation to make a connection succeed.

A local validation failure after the API call does not undo a granted credential
or its invalidation of prior credentials. Disclose this, repeat the invalidation
warning, and obtain fresh approval before another grant.

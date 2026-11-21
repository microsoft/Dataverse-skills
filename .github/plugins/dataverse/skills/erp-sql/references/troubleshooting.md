# ERP SQL common mistakes and troubleshooting

Detail for `erp-sql`. The safety rules in `SKILL.md` still apply; nothing here
relaxes them.

## Common mistakes

| Wrong | Correct |
|---|---|
| Requesting this action with `--target erp` | The action is on the linked **Dataverse** environment |
| Inventing a reason or pre-filling the reason form | Explicitly ask for the user's reason with an empty free-text field; submit their confirmed text verbatim |
| Offering Writer or escalating after a failure | Only Reader is supported; obtain explicit approval and stop on permission failures |
| Guessing a credential endpoint or using an Entra token as the SQL password | Discover and verify the action's metadata before granting access; use only the returned SQL credentials |
| Printing the response or using `sqlcmd -P <password>` | Capture in Python; use child-only `SQLCMDPASSWORD` |
| Using `-C` to make a TLS failure disappear | Fix certificate trust, hostname, or client configuration |
| Assuming `-K ReadOnly` prevents writes | Require Reader credentials; a client intent flag is not an authorization boundary |
| Requesting another grant after every login failure | Allow propagation, retry the same credentials within bounds, then report failure |
| Checking only that credentials were returned | Verify sqlcmd's exit code and actual database/login |
| New JIT grant for each metadata/count/data query | Keep one credential response in memory for the entire approved read |
| Retrying propagation only for the initial probe | Apply the same bounded retry/expiry checks to every SQL command |
| Combining `-h -1` with `-y 0` | Use the helper's tested text-preview flags; these options conflict |
| Parsing ordinary sqlcmd output as JSON | Use the text preview; only managed CLI API output is parsed as JSON |

## Troubleshooting

**Before any replacement grant**, repeat the same-user/environment
credential-invalidation warning, including the impact on Visual Studio, SSMS, or
another SQL session, and obtain fresh explicit approval. This applies to
firewall/IP corrections, expiry, failed validation, and owner restarts. Earlier
approval is not consent to another invalidation; retries using the same
credentials do not request a new grant.

- **Revoked/expired sign-in:** repair the affected CLI through **dv-connect**, then rerun preflight. Do not inspect token cache files.
- **Missing action or unsupported deployment type:** stop; do not fall back to LCS or invent another endpoint.
- **Permission failure:** report it; do not self-elevate or switch to Writer.
- **Network/firewall failure:** SQL-reported IPs are diagnostics used only to check whether bounded retries stay inside the user-approved scope, not a discovery source for a new grant. An out-of-scope, missing, invalid, or ambiguous IP stops the workflow. Do not copy it into `--client-ip`, generate a range, or recommend an IP lookup. Ask the user to supply any replacement IP/range themselves, repeat the credential-invalidation warning, and obtain fresh explicit approval before a new grant. In-scope failures use bounded retries with the same credentials; never broaden the allowlist or disable TLS.
- **Expired credentials:** repeat the invalidation warning and obtain fresh approval before a new request; another tool may have obtained newer credentials for the same user/environment. Never reuse expired credentials.
- **Changing SQL egress:** if a user-supplied correction is followed by another out-of-scope SQL-reported IP, stop requesting grants. Do not infer a subnet, accumulate grants, or repeatedly chase addresses. Resume only after the user independently supplies and explicitly approves a replacement scope, with the invalidation warning repeated.
- **Sanitized command failure:** the helper reports the command, recognized diagnostic code/class, exit code where available, and validated SQL client IP for firewall errors, but intentionally withholds raw output that could contain credentials. Use metadata/auth checks for diagnosis, not credential-response logging.

The sqlcmd password and TLS behavior follow the [Microsoft sqlcmd reference](https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility).

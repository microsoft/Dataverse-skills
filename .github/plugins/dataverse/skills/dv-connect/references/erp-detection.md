# Detecting and validating ERP (Finance and Operations) linkage

On ERP-linked Dataverse environments, ERP is provisioned on top of the same Dataverse env. After Step 2 resolves `DATAVERSE_URL`, detect whether an ERP endpoint is also linked.

## Detection (Step 2 follow-up)

Try PAC first:

```
pac org who
```

If the output surfaces an `erpUrl` field, capture it. (PAC CLI ERP-discovery rollout is in flight at the time of writing — this field may not appear yet.)

If PAC does not surface it, fall back to the Dataverse CLI (uses the active profile set up in Step 2b):

```
dataverse org who --json
```

A non-null `erpUrl` / `ErpUrl` in either output is the ERP endpoint. In Step 3, when writing `.env`, append `ERP_URL=<value>` so `--target erp` routing works. If neither surfaces it, the env is Dataverse-only — skip `ERP_URL`.

```python
# inside the .env-writing block in Step 3
if erp_url:
    f.write(f"ERP_URL={erp_url}\n")
```

## Smoke test (Step 5 follow-up)

If `.env` has `ERP_URL`, also smoke-test the ERP linkage:

```
dataverse data query --target erp --table Currencies --top 1
```

A successful one-row response proves the active auth profile can reach the ERP OData endpoint. If this fails but the Dataverse-side checks pass, the user's account likely lacks ERP access — surface that explicitly rather than re-running Steps 1–4.

## ERP MCP registration (Step 6 follow-up)

If `.env` has `ERP_URL`, register an ERP MCP server alongside the Dataverse one, following the same per-host procedure in [mcp-configuration.md](mcp-configuration.md) with two differences:

- **Endpoint:** `{ERP_URL}/mcp` (not `/api/mcp`; the ERP MCP endpoint has no `_preview` variant).
- **Server name:** use `erp-{orgid}` so it sits next to `dataverse-{orgid}` in the same configuration file. Keep the same `orgid` you used for the Dataverse entry.

The MCP client type (`http` for Copilot, stdio proxy for Claude / Cursor / Codex) and the `MCP_CLIENT_ID` value are the same as for the Dataverse entry — read them from `.env`; do not hardcode.

**One-time allowlist per environment** — required only when the client authenticates through the `@microsoft/dataverse` stdio proxy (Claude / Cursor / Codex path):

```
dataverse mcp allow <MCP_CLIENT_ID> --erp
```

The `--erp` flag scopes the DV CLI-proxy consent to the ERP endpoint. Copilot's direct-HTTP client captures consent on the first browser sign-in and does not need this step.

**Copilot config example** — extend the existing `mcpServers` block written in `mcp-configuration.md` step 5:

```jsonc
{
  "mcpServers": {
    "dataverse-{orgid}": { "type": "http", "url": "{DATAVERSE_URL}/api/mcp" },
    "erp-{orgid}":       { "type": "http", "url": "{ERP_URL}/mcp" }
  }
}
```

**Claude Code example:**

```
claude mcp add -t stdio erp-{orgid} \
  -e DATAVERSE_OPERATION_CONTEXT=app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent={DATAVERSE_PLUGIN_AGENT} \
  -- npx @microsoft/dataverse mcp {ERP_URL}
```

For Cursor JSON and Codex TOML, mirror the Dataverse block from `mcp-configuration.md` step 5 with `ERP_URL` and the `erp-{orgid}` name.

### Verification

Restart the editor / CLI, then confirm both entries are loaded:

- **Stdio-proxy hosts (Claude / Cursor / Codex):**
  ```
  npx @microsoft/dataverse mcp {ERP_URL} --validate
  ```
  Runs against `{ERP_URL}/mcp`. **`--preview` is not supported on ERP** and returns an error.
- **Direct-HTTP hosts (Copilot):** the client surfaces the loaded MCP servers and their tools in its own UI — check that `erp-{orgid}` and its tools appear alongside `dataverse-{orgid}`.

**When to skip ERP MCP setup entirely:** if `.env` does not have `ERP_URL`, or the workflow is Dataverse-only. The `--target erp` CLI path (`dataverse data query --target erp ...`) does not depend on the ERP MCP server.

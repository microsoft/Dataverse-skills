# Detecting and validating ERP (Finance and Operations) linkage

On ERP-linked Dataverse environments, ERP is provisioned on top of the same Dataverse env. After Step 2 resolves `DATAVERSE_URL`, detect whether an ERP endpoint is also linked.

## Detection (Step 2 follow-up)

Try PAC first:

```
pac org who
```

If the output surfaces an `erpUrl` field, capture it. (PAC CLI ERP-discovery rollout is in flight at the time of writing — this field may not appear yet.)

If PAC does not surface it, fall back to the Dataverse CLI:

```
dataverse org who --environment <DATAVERSE_URL> --json
```

Pass `--environment` explicitly — the Dataverse CLI keeps its own active profile separate from PAC's, and without it `org who` may target a stale URL. Reuse the `DATAVERSE_URL` resolved earlier.

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

If `.env` has `ERP_URL`, additionally register an ERP MCP server alongside the Dataverse one. The Dataverse CLI ships a single stdio proxy (`npx @microsoft/dataverse mcp <url>`) that auto-routes by URL host — Dataverse hosts hit `{url}/api/mcp`, ERP hosts hit `{url}/mcp`. Two separate server entries — same binary, different URLs, different mount points.

**One-time allowlist per tenant/environment** (independent of the Dataverse allowlist):

```
dataverse mcp allow <MCP_CLIENT_ID> --erp
```

Same client IDs as `dv-connect` uses for Dataverse. The `--erp` flag scopes the consent to the ERP endpoint; without it, the client is only permitted against `/api/mcp` on Dataverse hosts.

**Per-host registration** — copy the exact block from `mcp-configuration.md` and substitute `ERP_URL` for `DATAVERSE_URL`, and a distinct server name (suggest `erp-{orgid}` to sit next to `dataverse-{orgid}`). Include `DATAVERSE_OPERATION_CONTEXT` in the `env` block with `skill=mcp-direct` and the same plugin version / agent as the Dataverse server — the CLI appends it to outbound User-Agent regardless of which backend is being proxied (Dataverse `/api/mcp` or ERP `/mcp`).

**Claude Code example:**

```
claude mcp add -t stdio erp-{orgid} \
  -e DATAVERSE_OPERATION_CONTEXT=app=dataverse-skills/{DATAVERSE_PLUGIN_VERSION};skill=mcp-direct;agent={DATAVERSE_PLUGIN_AGENT} \
  -- npx @microsoft/dataverse mcp {ERP_URL}
```

For Copilot / Cursor JSON configs and Codex TOML, add a second server entry with `url = ERP_URL`, keeping the Dataverse one intact. Both start on editor restart; both cache their tokens independently in the DV CLI credential store.

**Verification:**

```
npx @microsoft/dataverse mcp {ERP_URL} --validate
```

Runs against the single ERP MCP endpoint at `{ERP_URL}/mcp`. **ERP MCP is GA-only — `--preview` is not supported and returns an error** (`ERP MCP does not have a preview endpoint. --preview is not supported.`), unlike Dataverse which validates both `/api/mcp` and `/api/mcp_preview`. `list_tables` from the ERP MCP server surfaces public entities like `SalesOrderHeaders`, `Currencies`, `DataManagementDefinitionGroups`.

**When to skip ERP MCP setup entirely:** if `.env` does not have `ERP_URL`, or if the user's workflow is Dataverse-only. The `--target erp` CLI path (`dataverse data query --target erp ...`) does not depend on the ERP MCP server — CLI works without it. Only wire up the ERP MCP if the user wants ≤10-record interactive reads/writes on ERP entities from the same agent surface as Dataverse MCP.

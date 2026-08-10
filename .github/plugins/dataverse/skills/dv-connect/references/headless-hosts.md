# Headless / Sandboxed Hosts (ChatGPT Work Mode, Codex cloud sandbox, CI, SSH, containers)

This reference overrides the normal `dv-connect` flow **only on constrained hosts**. On such a host
the **Python SDK works and reads live data**; the **CLIs do not**, and **native MCP works only if a
remote connector is enabled** (detect it — see below). This file is the honest, upfront capability map
plus the one working path — so you never chase a dead end or report a result you did not actually retrieve.

---

## ENTRY GATE — does this file apply to you? (decide FIRST)

**Read on only if you are on a constrained host.** You are constrained if **any** of these is true:

- **Context (no install needed)** — you are told, or it is evident, that the host is **ChatGPT Work Mode**, **Codex cloud sandbox**, a **CI runner**, **SSH**, or a **container**.
- **Keyring (no install needed)** — `sys.platform == 'linux'` with no `$DISPLAY` and no running `gnome-keyring` / `dbus`. => no credential store (Axis 2 below).
- **Only if a .NET tool is already installed** — `dataverse --version` (or `pac`) fails to *start* (`Failed to create CoreCLR` / exit `137`, => Axis 1 below), or `dataverse auth list` is empty right after a "successful" sign-in. **Do not install a CLI just to probe** — the two signals above already decide it.

**If NONE apply, STOP — you are on a capable host.** Close this file and run the normal `dv-connect`
flow unchanged (DV CLI + PAC + native MCP + Python SDK all work). Nothing here applies; do not degrade
a capable host with these overrides.

---

## Capability matrix on a constrained host (state this UPFRONT, then act)

| Capability | Works? | Why |
|---|---|---|
| **Python SDK** (data / query / metadata) | Yes | Pure Python + HTTPS. The primary surface here. |
| **Raw Web API** (`urllib`) for SDK gaps (`PublishXml`, custom APIs) | Yes | Covers unbound actions the SDK does not. |
| **Dataverse CLI / PAC CLI** | No | Two independent blockers — Axis 1 (runtime will not start) and/or Axis 2 (no keyring for the profile). |
| **Native MCP tools** | No by default; Yes if a remote connector is enabled | A sandbox-registered / stdio MCP server is never consumable here, but a *remote* connector (ChatGPT Developer mode Pro+/Business, or a published "With MCP" plugin once it ships) surfaces `dataverse_*` tools directly in your tool list. **Detect, don't assume** — see "If native MCP tools ARE present" below. |
| **Local MCP proxy (any language)** | No | ChatGPT consumes MCP *remotely*, not from a process in the sandbox. |
| **Persistent auth cache** | Not by default | Ephemeral `$HOME` re-prompts each turn; see the auth ladder for the once-per-conversation option. |

**Behavioral rule — lead with honesty.** State these limits in ONE upfront line, then go straight to
the SDK. Do **not** attempt the CLI or MCP first and then report a chain of failures — that confusing
experience is exactly what this file exists to prevent.

**If native MCP tools ARE present (forward-looking — detect, don't assume).** The matrix above is the
*default* constrained-host state, with **no** remote connector. The moment one is enabled — a
Developer-mode custom connector today, or the published "With MCP" plugin once it ships to all ChatGPT
plans — `dataverse_*` MCP tools appear directly in your tool list. So before defaulting to SDK-only,
glance at your tools: if you see `search` / `describe` / `read_query` / `create_record` (or similar
`dataverse_*` tools), the connector is live — **prefer those for what they cover** (reads, `describe`,
small CRUD <=25) and fall back to the **SDK** only for what MCP does not do (bulk >25 / `CreateMultiple`,
`$apply` aggregation, N:N joins, forms/views/global-option-sets, analytics). If you see none, you are on
the default path — SDK-only, exactly as this file describes. This detection (the same rule as the
`dv-overview` "MCP Availability Check") is why the guidance does not go stale when the plugin ships: the
agent picks up native MCP automatically the day it appears, no doc change needed.

---
## Which `dv-connect` steps still apply here (KEEP the essentials, SKIP what can't run)

These overrides do **not** replace the whole flow — the SDK path still needs its prerequisites. Do the
groundwork, skip only what cannot run:

| `dv-connect` step | Constrained host |
|---|---|
| **Step 1 — Python 3 + `pip install azure-identity requests PowerPlatform-Dataverse-Client pandas msal msal-extensions`** | **KEEP (required).** The SDK / `scripts/auth.py` path fails without these. |
| Step 1 — Node.js / PAC CLI / Dataverse CLI / .NET SDK / Azure CLI installs | **SKIP.** They cannot run here (see "What does NOT work"). Installing them wastes time and ~1.9 GB. |
| Step 2 / 2b — `dataverse auth create` / `pac auth create` | **SKIP.** They fail; auth is the SDK device-code path below. |
| **Step 3 — create `.env`** (`DATAVERSE_URL`, `TENANT_ID`) | **KEEP (required).** `auth.py` reads these. Add `DATAVERSE_TOKEN_CACHE_DIR=.dataverse` only if using the last-resort cache. |
| **Step 4 — copy `scripts/auth.py`** into `scripts/` | **KEEP (required).** The working path imports `from auth import get_client`. |
| Step 5 — three-way verification | **MODIFY** to a single `python scripts/auth.py --check` (see the Step 5 section below). |
| Step 6 — MCP config | **SKIP.** Native MCP needs a remote connector, not the sandbox. |
| Step 7 — MCP verification | **SKIP.** |

**Net:** you still do the **Python + pip deps + `.env` + `auth.py`** groundwork — you only skip the
CLI / PAC / MCP installs and steps that cannot run. Do **not** shortcut Step 1's `pip install`; it is
what makes the SDK path work.

---

## Which skills work on a constrained host (authoritative per-skill map)

Skills whose default tool is the SDK / MCP just work here (egress permitting). The PAC-CLI-default
skills need the SDK / Web API path or a service principal -- they are **not** "unavailable", just
SDK-first here. This table is the single source of truth; the skills link back to it.

| Skill | Headless story |
|---|---|
| **dv-data**, **dv-query**, **dv-metadata** | SDK / MCP-first -- work unchanged (egress permitting); no special handling. |
| **dv-admin** | Many settings are `organization` records the SDK reads/writes; **service principal** for PAC-only settings. |
| **dv-security** | Role assignment, application users, business units are records the SDK handles; **service principal** for PAC-only ops. |
| **dv-solution** | Raw export/import via the Web API (`ExportSolution` / `ImportSolution`); `pac solution pack`/`unpack` (source control) are local file ops (no auth) but need a host that can **run PAC**. |
| **dv-connect** | This file. The SDK path works; the CLIs and native MCP do not. |

Only a genuinely egress-blocked org domain (a failed `python scripts/auth.py --check`) makes a skill
truly unavailable -- not the absence of the CLI.

---

## Reachability preflight + no fabrication (before ANY claim)

A token is not a connection. Make one real data-plane call:

```bash
python scripts/auth.py --check
```

Prints `REACHABLE: ... N non-private tables` (exit 0) or `NOT REACHABLE: ... <error>` (exit 2). Inline equivalent:

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

# A token can be minted while the org domain is blocked, so only a REAL call proves reachability.
try:
    client = get_client("dv-connect")
    tables = client.tables.list(select=["LogicalName"])
    print(f"REACHABLE: {len(tables)} non-private tables")
except Exception as e:
    print(f"NOT REACHABLE: {type(e).__name__}: {e}")
    print("A device-code prompt means auth is not finished -- complete it and retry.")
    print("A connection/timeout error (rare) means the org domain is blocked by egress.")
```

**Anti-fabrication (mandatory).** Report only counts / rows you actually got back, anchored to
something verifiable (org ID, a metadata GUID, the real number). If it errors, say what failed; never
invent a plausible number to fill the gap.

**If it fails with a connection/timeout error (not a device-code prompt), STOP** — the org domain is
egress-blocked and nothing below helps. Remediation: (1) allowlist `*.dynamics.com` in the sandbox
egress settings; (2) use a server-side ChatGPT connector; (3) run where egress is open (local VS Code
/ Codex CLI / Copilot). Only if the preflight **passes** does the working path below apply.

---

## The working path (constrained host, egress open)

1. **Auth** — `scripts/auth.py` device-code (below). One sign-in.
2. **Reads / writes / metadata** — Python SDK (`get_client(skill)`), identical to every other host.
3. **Unbound actions** the SDK lacks (`PublishXml`, custom APIs) — raw Web API via `urllib`.
4. **CLI / native MCP** — unavailable in-session; skip WITHOUT failing the setup.

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-connect")
tables = client.tables.list(select=["LogicalName"])   # documented default excludes private tables
print(f"{len(tables)} non-private tables")
```

If a device code prints, relay the URL + code to the user, wait for sign-in, then re-run. **A green
run IS a verified connection** — treat it as success even if CLI and MCP are unavailable.

---

## Auth ladder (best -> last resort) — for the repeated-prompt pain

By default the device-code cache lives under `$HOME`, which some sandboxes wipe between turns, so you
re-authenticate on *every* turn. Options, best first:

1. **Native remote connector** (ChatGPT Developer mode / published plugin) — `offline_access` refresh, **no local token at rest**. The endgame; needs the connector + OAuth work, and is not available on ChatGPT Plus today.
2. **Service principal** — set `CLIENT_ID` + `CLIENT_SECRET` in `.env`; `scripts/auth.py` uses them automatically. No browser, and **no *user* token at rest** (a scoped, revocable app identity). The sanctioned unattended pattern.
3. **Accept per-turn prompts** — annoying, but zero token at rest.
4. **[LAST RESORT] Workspace-local cache** — set `DATAVERSE_TOKEN_CACHE_DIR=.dataverse` in `.env`. `scripts/auth.py` then stores the cache in the persisted workspace, so device code is **once per conversation, not per turn**.
   - **Only** on an isolated, ephemeral, gitignored sandbox where the workspace persists across turns (test: write a file one turn, read it the next) and is wiped on session end.
   - **Security:** this writes the user's **refresh token** into `.dataverse/` (plaintext on headless Linux; DPAPI-encrypted on Windows). A leaked *user* refresh token is worse than a scoped SP secret. `auth.py` self-writes a `.gitignore` (`*`) in the dir and creates it owner-only, but keep `.dataverse/` gitignored at the repo root too. Prefer options 1-2. **Opt-in only** — capable hosts are unaffected unless the var is set.

### Credential chain + self-diagnosis

`scripts/auth.py` resolves credentials as a **silent-first fall-through chain**, so a stale or
authority-mismatched shared cache no longer strands you: **service principal** (terminal for CI) ->
**shared DataverseCLI cache** (probed at build time against both the tenant and the `organizations`
authority) -> **`az login`** (a silent tier — if you are `az`-logged-in to the tenant, no prompt) ->
a single **host-gated interactive** tier (workspace-cache device-code when `DATAVERSE_TOKEN_CACHE_DIR`
is set; a system-browser sign-in on a desktop; device-code on a headless host). The interactive tier
runs **only** when every silent tier is unavailable, so a working path wins without a needless prompt.

Stuck on auth? Run **`python scripts/auth.py --diagnose`** — it prints which tiers are available and
which one the next call will use, **without** prompting. On a CA-hardened tenant where device-code is
blocked, `az login` (silent tier) or a desktop browser sign-in is the way through.

---

## What does NOT work here — and why (do not chase these)

### Dataverse CLI + PAC CLI — two independent blockers

- **Axis 1 — execution-environment restriction (ChatGPT Work Mode / Codex cloud sandbox).** The
  self-contained .NET runtime cannot start: `Failed to create CoreCLR, HRESULT: 0x8007000E`, exit `137`.
  Verified **NOT memory** — GC-heap limits, single-processor mode, and .NET 6/10 all fail identically
  and resource limits were unconstrained. The real cause is a sandbox policy: **`/proc/self/exe` masked
  + tracing/ptrace blocked**. The CLIs **install** (~1.9 GB, workspace-local) but **cannot execute**.
  PAC additionally needs the .NET SDK the sandbox lacks. This is a hard policy wall — not tunable, and
  it will not change with any CLI / plugin update.
- **Axis 2 — no OS keyring (other headless Linux, where .NET *can* run).** Profile persistence uses
  libsecret / gnome-keyring via `CrossPlatLock`, which hangs without a keyring: `dataverse auth create`
  "succeeds" but `dataverse auth list` is empty (`System.InvalidOperationException ... CrossPlatLock`).

=> Do not try the CLI beyond the entry-gate probe. Use the **SDK** for data / query / metadata and
**raw Web API** for unbound actions. Reserve CLI / PAC (solution ALM, org settings) for a capable host
or a service principal.

### Native MCP tools

ChatGPT consumes MCP as a **remote connector**, not from the sandbox — so a locally-registered / stdio
MCP server (`npx @microsoft/dataverse mcp`, or any proxy) is not consumable here (and the .NET proxy
also hits Axis 1). Native MCP in ChatGPT requires one of:

- **Developer mode** custom connector — Pro (read/fetch) / Business / Enterprise-Edu (full). **Not ChatGPT Plus / Free.**
- **Published "With MCP" plugin** in the directory — reaches **all** plans after OpenAI review (the strategic path).

When either is enabled, the `dataverse_*` tools show up in your tool list and you use them directly —
see "If native MCP tools ARE present" above. Until then, do **not** write a `~/.codex/config.toml` MCP
entry expecting ChatGPT to load it in-session (it will not), and do **not** run Step 7 MCP `--validate`
as a success gate — it fails for host reasons, not setup.

<!-- MAINTAINER: when the published "With MCP" plugin ships to all ChatGPT plans, no rewrite is needed here.
     The agent already auto-detects native MCP via "If native MCP tools ARE present" above; just confirm the
     detection cue tool names (search / describe / read_query / create_record) still match the shipped server. -->

### Local MCP proxy (any language, however lightweight)

Does not help — there is **no MCP client in the sandbox to consume it** (ChatGPT loads MCP remotely).
This is an architecture limit, not a memory one; a featherweight Python/Node proxy would run and still
have zero consumers.

---

## Step 5 verification on a constrained host

Replace the three-way check (`dataverse auth who` + `pac org who` + `python scripts/auth.py`) with a
**single sufficient gate**: a green `python scripts/auth.py --check`. A bare `python scripts/auth.py`
only mints a token and does not prove reachability — always use `--check` here.

- `dataverse auth who` / `pac org who` failing here is **expected** (Axes 1/2) — not a setup failure.
- `REACHABLE` => connection verified, continue.
- `NOT REACHABLE` with a connection/timeout error => the org domain is egress-blocked; use the preflight
  remediation. Never mark the setup complete or invent a count.

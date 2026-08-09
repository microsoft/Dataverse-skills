# Headless / Sandboxed Hosts (ChatGPT Work Mode, Codex cloud sandbox, CI, SSH, containers)

This reference overrides the normal `dv-connect` flow **only on constrained hosts**. On such a host
the **Python SDK works and reads live data**; the **CLIs and native MCP do not**. This file is the
honest, upfront capability map plus the one working path — so you never chase a dead end or report a
result you did not actually retrieve.

---

## ENTRY GATE — does this file apply to you? (decide FIRST)

**Read on only if you are on a constrained host.** You are constrained if **any** of these is true:

- You are told the host is **ChatGPT Work Mode**, **Codex cloud sandbox**, a **CI runner**, **SSH**, or a **container**.
- **Runtime probe** — a .NET tool fails to *start*: `dataverse --version` (or `pac`) exits with `Failed to create CoreCLR` / exit `137`. => execution-restricted sandbox (Axis 1 below).
- **Keyring probe** — `sys.platform == 'linux'` with no `$DISPLAY` and no running `gnome-keyring` / `dbus`. => no credential store (Axis 2 below).
- **Profile probe** — `dataverse auth create` hangs while saving, or `dataverse auth list` is empty right after a "successful" sign-in.

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
| **Native MCP tools** | No | Need a *remote* connector (ChatGPT Developer mode Pro+/Business, or a published "With MCP" plugin) — a sandbox-registered / stdio MCP server is not consumable here. |
| **Local MCP proxy (any language)** | No | ChatGPT consumes MCP *remotely*, not from a process in the sandbox. |
| **Persistent auth cache** | Not by default | Ephemeral `$HOME` re-prompts each turn; see the auth ladder for the once-per-conversation option. |

**Behavioral rule — lead with honesty.** State these limits in ONE upfront line, then go straight to
the SDK. Do **not** attempt the CLI or MCP first and then report a chain of failures — that confusing
experience is exactly what this file exists to prevent.

---

## STEP 0 — reachability preflight + no fabrication (before ANY claim)

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

Do **not** write a `~/.codex/config.toml` MCP entry expecting ChatGPT to load it in-session — it will
not. Do **not** run Step 7 MCP `--validate` as a success gate — it fails for host reasons, not setup.

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
- `NOT REACHABLE` with a connection/timeout error => the org domain is egress-blocked; use the STEP 0
  remediation. Never mark the setup complete or invent a count.

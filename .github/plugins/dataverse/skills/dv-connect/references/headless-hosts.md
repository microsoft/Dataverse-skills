# Headless / Sandboxed Hosts (ChatGPT browser Work Mode, Codex sandbox, CI, SSH, containers)

This reference **overrides** parts of the main `dv-connect` flow when you are running in a
headless or sandboxed environment. Read it before Step 2 whenever the host has **no interactive
desktop browser and no OS credential store (keyring / Keychain / DPAPI)** — the most common case
is **ChatGPT Plus browser "Work Mode"**, which executes inside a Codex-based headless Linux
container.

In those hosts the **credential store**, **interactive browser**, and (rarely) **network egress**
may each be missing — and they break *different* things. The confirmed, reproducible blocker is the
**Dataverse CLI / PAC profile-persistence layer** on headless Linux; the **Python SDK is unaffected
and reads live data**. This file explains why, how to verify reachability, and how to stop looping
on the CLI so you never report a result you did not actually retrieve.

---

## Three capability axes — do not collapse them into one "headless" flag

| Axis | What it breaks | Reality |
|---|---|---|
| **1. OS credential store** (keyring / Keychain / DPAPI / libsecret) | **Dataverse CLI + PAC profile persistence** (`CrossPlatLock` hang), and the MCP stdio proxy that reuses the CLI cache | **The confirmed blocker.** The Python SDK does not use this path and works. |
| **2. Interactive desktop browser** | Interactive (non-device-code) sign-in; MCP proxy popup | Use `--deviceCode` / the SDK device-code fallback instead |
| **3. Network egress to the org data-plane** (`*.dynamics.com`) | Everything — SDK, CLI, MCP all fail to reach Dataverse | **Rare.** Live sessions read real data from ChatGPT Work Mode. Do not assume it's blocked — the preflight below confirms. |

**Auth success is not a connection — but do not over-rotate on the network either.** Live sessions
confirm the SDK reads real data from ChatGPT Work Mode (org identity, metadata GUIDs, record counts).
The thing that actually fails is the **CLI's profile persistence** (axis 1), not egress. The one-line
preflight below settles it factually instead of guessing.

---

## STEP 0 (do this FIRST): reachability preflight + no fabrication

Before you claim ANY connection works — SDK, CLI, or MCP — make one **real data-plane call** and
look at whether it returned. A token is not proof. Use the built-in gate:

```bash
python scripts/auth.py --check
```

`--check` makes a real metadata call and prints `REACHABLE: ... N non-private tables` (exit 0) or
`NOT REACHABLE: ... <error>` (exit 2). Equivalent inline:

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

**Anti-fabrication rule (mandatory).** Report only counts, rows, and results you got back from a
call that actually returned — anchor them to something verifiable (the org ID, a metadata GUID, the
actual number). If the preflight errors, say what failed (auth not completed, or — rarely — the
domain is unreachable); never invent a plausible number to fill the gap.

**If the preflight fails with a *connection/timeout* error (not a device-code prompt), STOP** — that
is the rare egress case, and none of the Overrides below will help. Give the user the remediation:

1. **Allowlist the environment domain** in the sandbox network settings (add the org host /
   `*.dynamics.com` to the ChatGPT Work Mode / container egress allowlist), then re-run the preflight.
2. **Use ChatGPT's native Dataverse connector** (added via the ChatGPT Connectors UI) — it runs
   server-side, outside the egress-restricted sandbox.
3. **Run the plugin where egress is open** — local VS Code / Codex CLI / Copilot on your machine.

Only if the preflight **passes** do the Overrides below apply.

---

## Which hosts lack what

| Host | Egress to org | Keyring | Browser |
|---|---|---|---|
| **ChatGPT Plus browser Work Mode** | usually open (verify) | no | no |
| **Codex / cloud sandbox** | varies | no | no |
| **CI runners** (GitHub Actions, ADO) | usually open | no | no |
| **SSH / Dev Container / plain Docker** | usually open | often no | no |

**Detection heuristic** (any one is enough to treat the host as restricted):
- `sys.platform` is `linux` with no `DISPLAY` / no running `gnome-keyring` / `dbus` (no keyring, no browser).
- A `dataverse auth create` attempt hangs while persisting the profile (the credential-store blocker).
- The reachability preflight returns `NOT REACHABLE` with a connection/timeout error (the rare egress case).
- You are explicitly told the host is ChatGPT Work Mode / Codex / a container.

---

## Why the SDK works but the CLI doesn't (the mechanism)

Both normally share ONE Microsoft sign-in. On headless Linux they diverge at **how each persists the
token**, and only one survives:

| | Dataverse CLI / PAC / MCP proxy | Python SDK (`scripts/auth.py`) |
|---|---|---|
| Persists | A named auth **profile** + shared MSAL cache | Its own MSAL **AuthenticationRecord** file |
| Backing store on Linux | libsecret / gnome-keyring via **`CrossPlatLock`** | plaintext file, `allow_unencrypted_storage=True` |
| Headless result | **hangs / crashes** persisting the profile -> `dataverse auth list` returns `[]` -> "No active authentication profile" | writes the record successfully, refreshes silently |

Same account, same environment, same permissions, same network. The **only** difference is the
persistence layer: the CLI depends on an OS keyring a headless container doesn't provide; the SDK's
`DeviceCodeCredential` falls back to a plaintext record and keeps working. That is why the SDK returns
live data while `dataverse auth create` leaves no usable profile.

**Systematic fixes for the CLI / PAC / MCP-proxy path on headless hosts** (pick one):
1. **Service principal** — `CLIENT_ID` + `CLIENT_SECRET` in `.env` for the SDK, and `pac auth create
   --applicationId ... --clientSecret ... --tenant ...` (or `dataverse auth create` with an app
   registration) for the CLIs. SP tokens are minted from client credentials, so there is no
   interactive profile to persist — this sidesteps the `CrossPlatLock` hang entirely.
2. **Provide a keyring** — run a `gnome-keyring` / `dbus` session in the container (not possible in
   ChatGPT Work Mode; feasible in a custom Dev Container).
3. **Use the SDK for the operation** — anything `get_client` covers (data, queries, metadata) already
   works headless; reserve CLI/PAC for what has no SDK path (solution ALM, org settings) and route
   those through SP or a keyring-capable host.

**Can the two be truly aligned (one login serves both)?** Yes:
- **Today:** only via **service principal** — no keyring-dependent interactive cache on either side.
- **Device-code:** needs a small Dataverse CLI change. Its plaintext fallback
  (`WithLinuxUnprotectedFile`) is currently reached only on `MsalCachePersistenceException`, so a
  headless `CrossPlatLock` error slips past it and `dataverse auth create` writes no profile; and
  `--accept-cleartext-caching` isn't wired to the interactive token cache. Once the CLI writes the
  plaintext `tokencache_msalv3.dat`, `scripts/auth.py` already reads it (it now also tries the
  plaintext file at `$XDG_DATA_HOME/Microsoft/DataverseCli` on Linux) — so a single device-code
  login would then serve the CLI, the MCP proxy, and Python.

---

## Override 1 — Auth priority: Python SDK device-code is PRIMARY (after the preflight passes)

Once STEP 0 confirms the org is reachable, **do not lead with `dataverse auth create`.** Use the
Python path that `scripts/auth.py` already implements. Its device-code fallback persists a
**plaintext** MSAL cache via the Python `msal-extensions` file lock (`allow_unencrypted_storage=True`)
— which works with no keyring. One sign-in, cached for the session. (If STEP 0 failed with a
*connection/timeout* error, this does **not** help — that's the rare egress case, not auth.)

```python
# Primary auth on headless hosts. Prints a device code on first run, then caches silently.
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-connect")
tables = client.tables.list(select=["LogicalName"])
print(f"Connected. {len(tables)} non-private tables visible.")
```

If this prints a device code, relay the URL + code to the user, wait for them to sign in, then
re-run. **A green run here IS a verified connection** — treat it as success even if the CLI and
MCP paths are unavailable. Do **not** re-run `dataverse auth create --deviceCode` to "fix" a
device-code prompt on a headless host — that command cannot persist its cache here and will loop.

Non-interactive headless hosts (CI) should use **service principal** auth instead: set `CLIENT_ID`
and `CLIENT_SECRET` in `.env` and `scripts/auth.py` uses them automatically (no browser at all).

---

## Override 2 — Dataverse CLI auth is a KNOWN failure on headless Linux

The `@microsoft/dataverse` CLI persists its MSAL cache through .NET `msal-extensions`, which
depends on **libsecret / gnome-keyring over D-Bus**. That daemon does not exist in these
containers, so profile persistence crashes — even with `--accept-cleartext-caching` — with:

```
System.InvalidOperationException: Process has exited
  at Microsoft.Identity.Client.Extensions.Msal.CrossPlatLock
```

The device code may print, sign-in may succeed, but the **profile is never saved** (a follow-up
`dataverse auth list` shows nothing). This is a CLI/platform limitation, not a plugin bug.

**What to do:** treat DV CLI auth as **best-effort** on headless hosts. Try it at most once; if it
hangs or `auth list` is empty afterward, stop and fall back to the Python SDK path (Override 1).
Do not loop. The `dataverse` data-plane commands (`data query/get/create/...`) still need a
persisted profile, so on these hosts prefer the **Python SDK** for reads/writes instead.

`pac auth create` is interactive and browser-based, so it has the same problem — skip it on
headless hosts unless you have a service principal.

---

## Override 3 — MCP is best-effort / unverified in ChatGPT browser Work Mode

You may still write the MCP config (Step 6) so it is ready for a desktop editor later, but in
**ChatGPT browser Work Mode you cannot verify or use it in-session**:

- There is no local Codex/editor process to restart, and the ChatGPT backend does **not** load a
  session-written `~/.codex/config.toml`. MCP servers for ChatGPT are added through the ChatGPT
  **Connectors / MCP** settings UI, not by writing a config file.
- The `npx @microsoft/dataverse mcp` stdio proxy relies on the same broken DV CLI token cache
  (Override 2), so it cannot authenticate here either.

**What to say and do:**
- Write the config if asked, but label it clearly: *"MCP config written for a future desktop
  session — it cannot be loaded or verified inside ChatGPT Work Mode."*
- Do **not** run Step 7's MCP verification or `--validate` as a success gate here; both will fail
  for host reasons, not setup reasons.
- Point the user to the working path (below), and note that native MCP in ChatGPT requires adding
  the connector via the ChatGPT Connectors UI.

---

## The working path on a headless host (egress open)

**Precondition: the STEP 0 reachability preflight passed.** If it did not, there is no in-session
path — use the STEP 0 remediation (allowlist the domain, use the ChatGPT connector, or run locally).
Do not proceed to auth or claim any partial success.

1. **Auth:** `scripts/auth.py` (Override 1) — device code once, cached for the session.
2. **Reads / writes / metadata:** Python SDK (`get_client(skill)`), same as every other host.
3. **MCP / DV CLI data-plane:** unavailable in-session; skip without failing the setup.

Example — the independent table count that works here:

```python
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_client

client = get_client("dv-connect")
tables = client.tables.list(select=["LogicalName"])   # documented default excludes private tables
print(f"{len(tables)} non-private tables")
```

---

## Override 4 — Step 5 verification on headless hosts

Replace Step 5's three-way check (`dataverse auth who` + `pac org who` + `python scripts/auth.py`)
with a **single sufficient check**: a green `python scripts/auth.py --check` (the STEP 0 reachability
gate). A bare `python scripts/auth.py` only mints a token and does **not** prove the org is reachable
— always use `--check` here.

- `dataverse auth who` failing here is **expected** (Override 2) — not a setup failure.
- `pac org who` failing here is **expected** (interactive/browser) — not a setup failure.
- If `python scripts/auth.py --check` prints `REACHABLE`, declare the connection verified and continue.
- If it prints `NOT REACHABLE` with a connection/timeout error, the org domain is blocked (axis 1) —
  report that honestly and use the STEP 0 remediation. Never mark the setup complete or invent a count.

State plainly which surfaces are available: *"Python SDK: connected and verified. Dataverse CLI /
PAC / MCP: unavailable in this headless host."* Never mark CLI or MCP "configured" when they
aren't — report exactly what works.

---

## Agent identity value

ChatGPT Work Mode runs on Codex, so set `DATAVERSE_PLUGIN_AGENT=codex` in `.env` (it is a valid
entry in `_ALLOWED_AGENTS`). If the host is genuinely unknown, use `unknown`.

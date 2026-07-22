# Tool Installation & Authentication Reference

## Required Tools

Check all in parallel. Install any that are missing.

| Tool | Check | Install |
|---|---|---|
| PAC CLI | `pac` (prints version banner; `pac --version` is not valid and returns non-zero) | `winget install Microsoft.PowerAppsCLI` |
| GitHub CLI | `gh --version` | `winget install GitHub.cli` |
| Azure CLI | `az --version` | `winget install Microsoft.AzureCLI` |
| .NET SDK | `dotnet --version` | `winget install Microsoft.DotNet.SDK.9` |
| Python 3 | `python --version` | `winget install Python.Python.3.12` |
| Node.js | `node --version` | `winget install OpenJS.NodeJS.LTS` |
| Dataverse CLI | `npm list -g @microsoft/dataverse` (shows `@microsoft/dataverse@<version>` if installed; `(empty)` if not) | `npm install -g @microsoft/dataverse@latest` (always upgrades to latest — mirrors `pip install --upgrade` for the Python SDK) |
| Git | `git --version` | `winget install Git.Git` |

After any `winget` install, the new tool may not be in PATH until the shell is restarted. If a tool is not found immediately after install, ask the user to close and reopen the terminal (if running in Claude Code, remind them to resume the session correctly: "Remember to **use `claude --continue` to resume the session** without losing context"), then proceed.

### PAC CLI on Windows Git Bash

PAC CLI is a `.cmd` wrapper. In Git Bash (used by Claude Code), `pac` alone may fail or hang. Use the PowerShell wrapper:

```bash
powershell -Command "& 'C:\Users\$USER\AppData\Local\Microsoft\PowerAppsCLI\pac.cmd' help"
```

Or, if installed via `dotnet tool install --global`:

```bash
powershell -Command "& pac help"
```

To avoid repeating this, add an alias to `~/.bashrc`:

```bash
echo 'alias pac="powershell -Command \"& pac.cmd\""' >> ~/.bashrc
source ~/.bashrc
```

If `pac` works directly in your shell, skip the PowerShell wrapper — it's only needed when Git Bash can't execute `.cmd` files.

### PAC version mismatch when shelling PAC from Python

On Windows, a Python `subprocess` may resolve a **different `pac` executable** than your interactive shell — e.g. an older `pac.exe` on `PATH` (2.4.1) while the shell uses the current `.cmd` shim (2.9.3). The old binary silently lacks newer commands (`pac model create`), so a script fails with "unknown command" even though `pac` works in your terminal. Fix: shell PAC through `cmd.exe /c pac ...` (or resolve `shutil.which('pac.cmd')`) so the subprocess uses the same shim, and check the version banner matches before relying on newer subcommands.

### Python SDK

After Python is confirmed available:
```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client pandas msal msal-extensions
```

### If winget is unavailable

- PAC CLI: `dotnet tool install --global Microsoft.PowerApps.CLI.Tool`
- GitHub CLI: download from https://cli.github.com
- Azure CLI: download from https://aka.ms/installazurecliwindows

---

## Authentication

> **Multi-environment note:** Pro developers typically work across multiple environments (dev, test, staging, prod) and maintain one named PAC auth profile per environment. Before any environment operation, always run `pac auth list` + `pac org who` to confirm which profile is active, and ask the user which environment they intend to target. Never assume the currently active profile is correct.

### Identify your tenant ID first

If working in a **non-production or separate tenant** (different from your corporate AAD), you need that tenant's ID before authenticating. Options:

```
# If you already have PAC CLI authenticated to any environment:
pac org who

# Or: run this after az login (see below) and check the tenantId field
az account show
```

The tenant ID is a GUID like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`. Set it in `.env` as `TENANT_ID` before running any scripts.

---

### PAC CLI

**Recommended for non-prod / separate tenants: service principal auth (non-interactive)**

```
pac auth create \
  --name nonprod \
  --applicationId <CLIENT_ID> \
  --clientSecret <CLIENT_SECRET> \
  --tenant <TENANT_ID>
```

This requires a service principal in your dev tenant. Once created, record `CLIENT_ID`, `CLIENT_SECRET`, and `TENANT_ID` in `.env`. With service principal auth, no browser is ever needed.

**Interactive user auth (corporate tenant or if no service principal yet)**

```
pac auth create --name dev
```

This opens a browser. If you use a **non-corporate tenant**, ensure you are logged out of your corporate Microsoft account in the browser before the prompt opens — otherwise the browser will auto-complete with corporate credentials. Use an InPrivate/Incognito window if needed.

Verify the correct auth is active:
```
pac auth list
pac org who
```

To switch between profiles:
```
pac auth activate --name <profile-name>
```

Name profiles to reflect the environment they target (e.g., `dev`, `staging`, `prod`, `contoso-dev`).

**When starting any deployment task:** run `pac auth list` and `pac org who`, show the output to the user, and confirm this is the environment they want to target before proceeding.

---

### GitHub CLI

```
gh auth status
```

If not authenticated:
```
gh auth login
```

If you have multiple GitHub accounts (corporate + personal), verify the correct one is active:
```
gh api user --jq .login
```

---

### Azure CLI (needed for CI/CD setup only — skip until needed)

For a non-prod or separate tenant, always specify the tenant explicitly:

```
az login --tenant <TENANT_ID>
az account show --query '{tenant:tenantId, subscription:name}' -o table
```

Confirm the tenant ID in the output matches your dev tenant before proceeding.

---

## PAC CLI PATH setup

If `pac` is not in PATH, check these common Windows install locations in order (fastest first):

```bash
# 1. winget install location (most common)
ls "/c/Users/$USER/AppData/Local/Microsoft/PowerAppsCLI/pac.exe" 2>/dev/null

# 2. dotnet tool install location
ls "/c/Users/$USER/.dotnet/tools/pac.exe" 2>/dev/null

# 3. nuget global packages (if installed via Microsoft.PowerApps.CLI nuget package)
ls /c/Users/$USER/.nuget/packages/microsoft.powerapps.cli/*/tools/pac.exe 2>/dev/null
```

Do NOT use `find` or recursive search — it's slow and unnecessary when the install locations are known.

Once found, add to `~/.bashrc` (for Git Bash / Claude Code):

```bash
# Use the directory where pac.exe was found, e.g.:
echo 'export PATH="$PATH:/c/Users/$USER/AppData/Local/Microsoft/PowerAppsCLI"' >> ~/.bashrc
source ~/.bashrc
```

---

## Privilege preflight

A valid auth token proves *identity*, not *customization rights*. Check the **effective privilege for the specific operation** up front, instead of discovering a gap mid-flow on the first `create`.

**Do not preflight by listing role names.** Role-name listing misses privileges granted through **team roles** or **custom roles**, and can pass a user whose named role lacks the effective privilege (or fail one who has it via a team). Use the `RetrieveUserSetOfPrivilegesByNames` function bound to the systemuser -- it returns the privileges the user actually holds **through their roles and team membership**, in one call:

```bash
# 1. Who am I? (returns UserId). --context carries plugin/skill/agent attribution.
dataverse api request --target dataverse --method GET \
  --path "/api/data/v9.2/WhoAmI" --environment <DATAVERSE_URL> \
  --context "app=dataverse-skills/<ver>;skill=dv-connect;agent=<agent>"

# 2. Check EFFECTIVE privileges for the operations you're about to run.
#    Bound to systemuser; includes team-inherited privileges. Pass only the
#    privileges the task needs (see the operation map below). Single-quote the
#    --path so the JSON array's quotes survive the shell.
dataverse api request --target dataverse --method GET \
  --path '/api/data/v9.2/systemusers(<UserId>)/Microsoft.Dynamics.CRM.RetrieveUserSetOfPrivilegesByNames(PrivilegeNames=@p)?@p=["prvCreateEntity","prvCreateAttribute"]' \
  --environment <DATAVERSE_URL> \
  --context "app=dataverse-skills/<ver>;skill=dv-connect;agent=<agent>"
```

A required privilege is granted when it appears in the returned privilege set; if it's absent, the operation will fail on the first write -- stop and surface a least-privilege fix.

**Privilege is per operation -- `prvCreateEntity` is table-only.** Check the privilege(s) that match the work:

| Operation | Privilege(s) to check |
|---|---|
| Create table | `prvCreateEntity` |
| Create column | `prvCreateAttribute` |
| Create form | `prvCreateSystemForm` |
| Create view | `prvCreateSavedQuery` |
| Register plug-in assembly | `prvCreatePluginAssembly` |
| Register plug-in step | `prvCreateSdkMessageProcessingStep` |

**Least privilege:** these customization privileges come from **System Customizer** -- the minimal built-in role for metadata / plug-in work. Do NOT grant System Administrator just to create tables. Reserve **System Administrator** for sessions that *also* need security or org-admin operations (role assignment, org settings) -- not for pure customization. Missing the needed privilege? Assign **System Customizer** (or a custom role that grants it) via the **dv-security** skill.

> `systemuserroles_association` (role-name listing) is for **confirming that a specific direct role assignment landed** (see **dv-security**) -- not for privilege preflight, since it can't see team- or custom-role-granted privileges.

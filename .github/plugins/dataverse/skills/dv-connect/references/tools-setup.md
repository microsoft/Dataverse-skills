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

### Python SDK

After Python is confirmed available:
```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client
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

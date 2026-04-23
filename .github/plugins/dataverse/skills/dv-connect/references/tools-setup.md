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

After any `winget` install, the new tool may not be in PATH until the shell is restarted. For PAC CLI specifically, don't rely on shell restart — discover the install location and add it to PATH inline (see PAC CLI section below). For other tools, if not found immediately after install, ask the user to close and reopen the terminal (if running in Claude Code, remind them: "Remember to **use `claude --continue` to resume the session** without losing context"), then proceed.

### PAC CLI install — winget is the primary path

**Use `winget install Microsoft.PowerAppsCLI`.** Do NOT use `dotnet tool install --global Microsoft.PowerApps.CLI.Tool` as the primary install method — it has a known packaging bug (missing `DotnetToolSettings.xml`) that fails on recent .NET SDK versions with the error "The settings file in the tool's NuGet package is invalid." Reserve `dotnet tool install` as a last-resort fallback only when winget is unavailable.

After `winget install Microsoft.PowerAppsCLI` completes, PAC CLI is typically installed at:

```
C:\Users\<user>\AppData\Local\Microsoft\PowerAppsCLI\Microsoft.PowerApps.CLI.<version>\tools\
```

Don't require a shell restart. Instead, add the install directory to PATH inline in the current session and persist it to `~/.bashrc`:

```bash
# 1. Find the install directory (the versioned subfolder)
PAC_DIR=$(ls -d /c/Users/$USER/AppData/Local/Microsoft/PowerAppsCLI/Microsoft.PowerApps.CLI.*/tools 2>/dev/null | tail -1)

# 2. Add to current session
export PATH="$PAC_DIR:$PATH"

# 3. Persist to ~/.bashrc (skip if already present)
touch ~/.bashrc
grep -q "PowerAppsCLI" ~/.bashrc || echo "export PATH=\"$PAC_DIR:\$PATH\"" >> ~/.bashrc

# 4. Verify
pac
```

### PAC CLI on Windows Git Bash

PAC CLI is a `.cmd` wrapper. In Git Bash (used by Claude Code), `pac` alone may fail or hang. If after the PATH setup above `pac` still fails, use the PowerShell wrapper:

```bash
powershell -Command "& 'C:\Users\$USER\AppData\Local\Microsoft\PowerAppsCLI\pac.cmd' help"
```

To avoid repeating this, add an alias to `~/.bashrc`:

```bash
echo 'alias pac="powershell -Command \"& pac.cmd\""' >> ~/.bashrc
source ~/.bashrc
```

If `pac` works directly in your shell (after PATH setup above), skip the PowerShell wrapper — it's only needed when Git Bash can't execute `.cmd` files.

### Python SDK

After Python is confirmed available:
```
pip install --upgrade azure-identity requests PowerPlatform-Dataverse-Client pandas
```

### If winget is unavailable

- PAC CLI: download the latest NuGet package from https://www.nuget.org/packages/Microsoft.PowerApps.CLI and extract to a local directory, or (last resort) `dotnet tool install --global Microsoft.PowerApps.CLI.Tool` (known to fail with "settings file invalid" — retry with a specific version if the latest is broken)
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

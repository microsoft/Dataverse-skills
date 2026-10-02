# Helper scripts -- provisioning

`dv-connect` uses two helper scripts at the project root:

- `scripts/auth.py` -- the Python-SDK authentication path.
- `scripts/enable-mcp-client.py` -- the MCP allowlist helper.

When the plugin is installed as a repo clone or a native plugin, both are already local. When it is installed via `npx skills add` or the JetBrains AI Assistant registry (which install **skill folders only**), they are absent -- copy them from a local checkout if one is present, otherwise fetch them from the canonical repo.

**PowerShell:**
```
$base = 'https://raw.githubusercontent.com/microsoft/Dataverse-skills/main/.github/plugins/dataverse/scripts'
New-Item -ItemType Directory -Force scripts | Out-Null
foreach ($f in 'auth.py','enable-mcp-client.py') {
  $src = ".github/plugins/dataverse/scripts/$f"
  if (Test-Path $src) { Copy-Item $src "scripts/$f" -Force }
  else { Invoke-WebRequest "$base/$f" -OutFile "scripts/$f" }
}
```

**bash / zsh:**
```
base='https://raw.githubusercontent.com/microsoft/Dataverse-skills/main/.github/plugins/dataverse/scripts'
mkdir -p scripts
for f in auth.py enable-mcp-client.py; do
  src=".github/plugins/dataverse/scripts/$f"
  if [ -f "$src" ]; then cp "$src" "scripts/$f"; else curl -fsSL "$base/$f" -o "scripts/$f"; fi
done
```

**Skip condition:** `scripts/auth.py` and `scripts/enable-mcp-client.py` both exist.

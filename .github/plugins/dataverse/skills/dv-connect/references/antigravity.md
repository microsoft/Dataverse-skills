# Google Antigravity Support

The canonical Dataverse package is both a Gemini extension and an Antigravity
plugin. It contains one shared `skills/` and `scripts/` tree with thin host
manifests at the package root.

## Install

Install the native package from the latest GitHub Release:

```
agy plugin install https://github.com/microsoft/Dataverse-skills/releases/latest/download/dataverse-agent-plugin.zip
```

If the Dataverse extension is already installed in Gemini CLI, convert that
installation instead:

```
agy plugin import gemini
```

Antigravity stages plugins in `~/.gemini/antigravity-cli/plugins/`. Restart
`agy` after installing or importing, then verify that `/skills` lists the
Dataverse skills.

## Restore the canonical auth helper when needed

Current Antigravity releases can selectively stage recognized plugin
components and omit a package-root `scripts/` directory. Do not copy or
maintain another auth helper in this repository. If the staged plugin has no
`scripts/auth.py`, extract the canonical file from the same release archive
into the project:

```python
# SDK does not support downloading GitHub release assets.
import io
import pathlib
import urllib.request
import zipfile

release_url = (
    "https://github.com/microsoft/Dataverse-skills/releases/latest/download/"
    "dataverse-agent-plugin.zip"
)
with urllib.request.urlopen(release_url) as response:
    package = response.read()

with zipfile.ZipFile(io.BytesIO(package)) as archive:
    auth_source = archive.read("scripts/auth.py")

auth_path = pathlib.Path("scripts/auth.py")
auth_path.parent.mkdir(parents=True, exist_ok=True)
auth_path.write_bytes(auth_source)
```

The project copy is runtime scaffolding, just as it is for other hosts. The
repository source remains `.github/plugins/dataverse/scripts/auth.py` only.

## Configure Dataverse MCP

The native `plugin.json` intentionally does not include `mcp_config.json`:
Dataverse URLs are workspace-specific, and Antigravity's plugin manifest has no
settings contract. Follow the `antigravity` blocks in
[mcp-configuration.md](mcp-configuration.md) to merge a concrete URL into
`.agents/mcp_config.json`, then restart `agy` and verify the server in `/mcp`.

Official references:

- [Antigravity plugins and skills](https://antigravity.google/docs/cli/plugins)
- [Migrating from Gemini CLI](https://antigravity.google/docs/cli/gcli-migration)
- [Antigravity MCP configuration](https://antigravity.google/docs/cli/mcp)
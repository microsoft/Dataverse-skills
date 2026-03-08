# Dataverse Workspace

## Environment
- **URL:** {{DATAVERSE_URL}}
- **Solution:** {{SOLUTION_NAME}}
- **PAC Auth Profile:** {{PAC_AUTH_PROFILE}}

## Repo Layout
- `/solutions/{{SOLUTION_NAME}}/` — unpacked solution source files (source of truth)
- `/plugins/` — C# Dataverse plugin projects
- `/.dataverse/` — plugin skills, scripts, and templates (committed, no credentials)
- `.env` — local environment config (not committed, gitignored)
- `.vscode/settings.json` — MCP server config (not committed, gitignored)

## Workflows

**Pull from environment to repo:**
```
pac solution export --name {{SOLUTION_NAME}} --path ./solutions/{{SOLUTION_NAME}}.zip --managed false
pac solution unpack --zipfile ./solutions/{{SOLUTION_NAME}}.zip --folder ./solutions/{{SOLUTION_NAME}}
rm ./solutions/{{SOLUTION_NAME}}.zip
git add ./solutions/{{SOLUTION_NAME}} && git commit -m "chore: pull {{SOLUTION_NAME}}" && git push
```

**Push from repo to environment:**
```
pac solution pack --zipfile ./solutions/{{SOLUTION_NAME}}.zip --folder ./solutions/{{SOLUTION_NAME}}
pac solution import --path ./solutions/{{SOLUTION_NAME}}.zip --environment {{DATAVERSE_URL}} --async --activate-plugins
rm ./solutions/{{SOLUTION_NAME}}.zip
```

**Validate after push:**
```
python scripts/validate.py --all
```

## Metadata Conventions
- Table prefix: `new_` (confirm publisher prefix in `solutions/{{SOLUTION_NAME}}/Other/Solution.xml`)
- All GUIDs in form and view XML must be unique — generate with `python -c "import uuid; print(str(uuid.uuid4()).upper())"`
- Business rules are stored as JSON in `Entities/<table>/Workflows/`

## C# Plugins
- Projects live in `/plugins/<PluginName>/`
- All assemblies must be strong-named (`.snk` key file, gitignored)
- Register via `scripts/register_plugin.py` (first time) or `pac plugin push --pluginId` (updates)
- See `/plugins/README.md` for the full build and registration steps

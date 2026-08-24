# PAC CLI X++ command reference

Use these forms exactly. The X++ commands require the PAC CLI .NET tool version 2.11.1 or later. They are preview commands and may be absent from older installations; check `pac package help` and `pac tool xpp help` before use.

## Package initialization

```bash
pac package init \
  --outputDirectory <root> \
  --package-type erp \
  --model <ModelA,ModelB> \
  --source-root ./src \
  --publisher <publisher> \
  --layer ISV
```

| Argument | Alias | Required | Notes |
|---|---|---|---|
| `--outputDirectory` | `-o` | No | Target root |
| `--package-type` | `-pt` | Yes for ERP | Use `erp` |
| `--model` | `-m` | Yes for ERP | One name or comma-separated names |
| `--source-root` | `-sr` | No | Defaults to `./src` |
| `--publisher` | `-pub` | No | Defaults to `Microsoft`; choose an appropriate publisher for customer code |
| `--layer` | `-l` | No | `USR`, `CUS`, `VAR`, `SL1`, `SL2`, `SL3`, `BUS`, `HFX`, `GLS`, `DIS`, `ISV`; defaults to `ISV` |

Model names must start with a letter and contain only letters, digits, and underscores.

## X++ SDK lifecycle

```bash
pac tool xpp install --environment <dataverse-url>
pac tool xpp install --environment <dataverse-url> --app-version <x.y.z.w>
pac tool xpp list
pac tool xpp uninstall --version <x.y.z.w>
```

- `install` is Windows-only. Without `--app-version`, PAC queries the linked environment's application version.
- Reinstalling an already-present version refreshes its environment registration without redownloading when the compiler exists.
- `uninstall` recursively removes the version-specific SDK directory. Treat it as destructive local cleanup and ask before running.
- If several SDKs are installed, always specify a version for uninstall and preferably for compile.

## Compile/build

```bash
pac package compile \
  --solution-root <root> \
  --package-type erp \
  [--model <ModelA,ModelB>] \
  [--incremental] \
  [--license-file <path>] \
  [--app-version <x.y.z.w>] \
  [--output <directory>] \
  [--skip-bp] \
  [--language <en-US,fr,de>]
```

| Argument | Alias | Meaning |
|---|---|---|
| `--solution-root` | `-sr` | Root containing `.erp/xpp.json`; defaults to current directory |
| `--package-type` | `-pt` | Must be `erp` |
| `--model` | `-m` | Optional subset; omission compiles every configured model |
| `--incremental` | | Pass incremental mode to `xppc` |
| `--license-file` | `-lf` | Inject an ISV license into each produced ZIP |
| `--app-version` | `-av` | Select an installed SDK explicitly |
| `--output` | | ZIP destination; defaults to `<root>/bin` |
| `--skip-bp` | | Skip best-practice checks; avoid for final builds |
| `--language` | `-lang` | Compile selected label locales; omission compiles every locale found |

`--outputDirectory` / `-o` is retained as a compatibility alias for the project root. Prefer `--solution-root`.

## Package deployment

```bash
pac package deploy \
  --environment <dataverse-url> \
  --package-type erp \
  [--package <managed-zip>] \
  [--solution-root <root>] \
  [--build-type Full|Incremental|Delete] \
  [--release-type Dev|Release] \
  [--db-sync None|Full|Module|Incremental] \
  [--modules <ModelA,ModelB>] \
  [--argument-file <json>] \
  [--logConsole] \
  [--logFile <path>]
```

Defaults are `build-type Full`, `release-type Dev`, and `db-sync None`. Specify them explicitly in automation.

- With `--package`, deploy exactly one ZIP.
- Without `--package`, PAC enters solution mode and requires `.erp/xpp.json` under `--solution-root` (or current directory).
- Solution mode finds each model's current ZIP under `<root>/bin`, orders model dependencies, deploys each package, and runs DB sync once at the end.
- The command waits for the asynchronous deployment to reach a terminal state.

## Standalone database synchronization

```bash
# Full
pac package db-sync --environment <dataverse-url> --db-sync Full

# Selected modules
pac package db-sync --environment <dataverse-url> \
  --db-sync Module --modules ModelA,ModelB

# Incremental contract supplied by the caller/platform
pac package db-sync --environment <dataverse-url> \
  --db-sync Incremental --argument-file <incremental-sync.json>
```

| Mode | Required argument | Prohibited/ignored |
|---|---|---|
| `Full` | None | `--modules` is invalid |
| `Module` | `--modules` or a valid module argument file | Empty module list is invalid |
| `Incremental` | `--argument-file` | Do not invent the JSON schema |

The argument file is passed through as the server's `ModuleSyncParameters` or `IncrementalSyncParameters` JSON contract. Validate that it exists and was supplied/generated for the target environment. Do not synthesize an incremental contract from guesses.

## Deployment/DB-sync interactions

| Combination | Behavior |
|---|---|
| `Dev` + any supported sync | Uses the requested sync |
| `Release` + `Module` or `Incremental` | PAC warns and changes the requested sync to `Full` |
| `Delete` + any non-None sync | PAC warns and ignores the sync |
| Solution mode + sync | Deploys all models first, then performs one final sync |

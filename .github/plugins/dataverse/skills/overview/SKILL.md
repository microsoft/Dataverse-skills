---
name: dataverse-overview
description: Start here for any Dataverse task. Routes natural-language requests to the right tools (MCP, Python SDK, Web API, PAC CLI) and chains multi-step workflows automatically.
---

# Skill: Overview — What to Use and When

This is the routing guide. Consult it when deciding how to accomplish a task.

---

## UX Principle: Natural Language First

Users should never need to invoke skills or slash commands directly. The intended workflow is:

1. Install the plugin
2. Describe what you want in plain English
3. Claude figures out the right sequence of tools, APIs, and scripts

**Example prompt:** *"I want to create an extension called IronHandle for Dynamics CRM in this Git repo folder that adds a 'nickname' column to the account table and populates it with a clever nickname every time a new account is created."*

From that single prompt, Claude should orchestrate the full sequence: check if the workspace is initialized → create metadata via Web API → write and deploy a C# plugin → pull the solution to the repo. No skill names, no commands — just intent.

Skills exist as **Claude's knowledge**, not as user-facing commands. Each skill documents how to do one thing well. Claude chains them together based on what the user describes. If a capability gap exists (e.g., prompt columns aren't programmatically creatable yet), say so honestly and suggest workarounds rather than hallucinating a path.

---

## Multi-Environment Rule

Pro-dev scenarios involve multiple environments (dev, test, staging, prod) and multiple sets of credentials. **Never assume** the active PAC auth profile, values in `.env`, or anything from memory or a previous session reflects the correct target for the current task.

**Before any operation that touches a specific environment** — deploying a plugin, pushing a solution, registering a step, running a script against the Web API — ask the user:

> "Which environment should I target for this? Please confirm the URL."

Then verify the active PAC profile matches:
```
pac auth list
pac org who
```

The more impactful the operation (plugin deploy, solution import, step registration), the more important this confirmation is. Do not proceed against an environment the user hasn't explicitly confirmed in the current session.

---

## What This Plugin Covers

This plugin covers **Dataverse / Power Platform development**: environments, solutions, tables, columns, forms, views, security roles, C# plugins, and CI/CD for solution deployment.

It does **not** cover:
- Power Automate flows (use the maker portal or Power Automate Management API)
- Canvas apps (use `pac canvas` or the maker portal)
- Azure infrastructure beyond what's needed for service principal setup
- Business Central or other Dynamics products

---

## Tool Capabilities — What Each Tool Actually Supports

Understanding the real limits of each tool is critical. Do not assume a tool covers something it doesn't.

### Dataverse MCP Server
**Supports:** Data CRUD (create/read/update/delete records), table create/list/describe/delete, keyword search across Dataverse.

**Does NOT support:** Forms (FormXml), Views (SavedQueries), Relationships, Option Sets, column-level metadata operations.

Use it for: talking to data and basic table operations during a conversation.

### Official Python SDK (`PowerPlatform-Dataverse-Client`)
**Supports:** Data CRUD, bulk create/update, OData queries, table create/delete, file column uploads.

**Does NOT support:** Forms, Views, Relationships, Lookup columns (explicitly listed as a current limitation), Option Sets. Note: currently in **preview** — breaking changes possible.

Use it for: data operations in scripts and automation — not metadata.

### Direct Dataverse Web API
**Supports:** Everything. Forms, views, relationships, option sets, columns, table definitions — the full MetadataService and all other APIs.

Use it for: anything the MCP server and Python SDK can't do, which includes all form and view work, relationship creation, and option set management.

### PAC CLI
**Supports:** Solution export/import/pack/unpack, environment provisioning, auth management, plugin registration, solution component management.

Use it for: solution lifecycle. Do not try to replicate these with Python or the Web API.

### Azure CLI (`az`)
**Supports:** App registrations, service principals, credential management.

Use it for: CI/CD credential setup only. Scope is narrow in this plugin.

### GitHub CLI (`gh`)
**Supports:** Repo management, GitHub secrets, Actions workflow status.

---

## Tool Routing Decision Tree

```
What are you trying to do?
│
├── Read or write data records (rows in a table)?
│     └── MCP server (conversational) → Python SDK (scripts/automation)
│
├── Create a new table?
│     └── MCP server (conversational) → Web API Python script (if MCP unavailable)
│
├── Add a column to an existing table?
│     └── Web API directly (Python script) — MCP update_table may work but is unreliable for column-level ops
│
├── Create or modify a relationship (lookup, N:N)?
│     └── Web API directly (Python script) — neither MCP nor Python SDK supports this
│
├── Create or modify an option set?
│     └── Web API directly (Python script) — not covered by MCP or Python SDK
│
├── Create or modify a form (FormXml)?
│     └── Web API directly (Python script) — not supported by MCP or Python SDK
│
├── Create or modify a view (SavedQuery)?
│     └── Web API directly (Python script) — not supported by MCP or Python SDK
│
├── Export, import, pack, or unpack a solution?
│     └── PAC CLI
│
├── Provision or manage an environment?
│     └── PAC CLI
│
├── Add a user or assign a security role?
│     └── PAC CLI (happy path) → scripts/assign-user.py (fallback)
│
├── Post-import validation?
│     └── scripts/validate.py (works in CI/CD too)
│
├── Write a C# plugin?
│     └── dataverse-csharp-plugins/SKILL.md (dotnet + pac plugin push)
│
├── Set up CI/CD?
│     └── dataverse-cicd/SKILL.md (az + gh + PAC CLI + deploy.yml template)
│
└── Something else?
      └── Check if it's actually a Power Platform task.
          If not, this plugin probably doesn't cover it.
```

---

## Web API Scripts Belong in the Repo

Any Web API call that goes beyond a one-off conversational query should be written as a Python script and committed to `/scripts/`. These scripts:
- Run the same way in CI/CD as they do locally
- Are reviewable by teammates
- Are reusable across sessions without re-explaining the auth pattern

Use `scripts/auth.py` for token acquisition in all scripts. See `dataverse-metadata/SKILL.md` for Web API patterns.

---

## After Any Change: Pull to Repo

Any time you make a metadata change (via MCP, Web API, or the maker portal), end the session by pulling:

```
pac solution export --name <SOLUTION_NAME> --path ./solutions/<SOLUTION_NAME>.zip --managed false
pac solution unpack --zipfile ./solutions/<SOLUTION_NAME>.zip --folder ./solutions/<SOLUTION_NAME>
rm ./solutions/<SOLUTION_NAME>.zip
git add ./solutions/<SOLUTION_NAME>
git commit -m "feat: <description>"
git push
```

The repo is always the source of truth.

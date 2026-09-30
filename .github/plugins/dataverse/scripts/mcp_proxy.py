#!/usr/bin/env python3
"""
mcp_proxy.py -- self-refreshing attribution launcher for the Dataverse MCP proxy.

Registered as the MCP server command in place of invoking
`npx @microsoft/dataverse@latest mcp <url>` directly. At every proxy start it
resolves the CURRENTLY-INSTALLED plugin version live from the manifest, builds
the DATAVERSE_OPERATION_CONTEXT attribution string, and execs the npx stdio
proxy with that value in the child environment.

Why (issue #114): the plugin version used for server-side telemetry attribution
must not be a frozen literal baked into the host MCP config at registration
time. A baked literal never updates when the plugin is upgraded unless the user
re-runs dv-connect and re-registers MCP -- which telemetry shows almost never
happens, so the fleet keeps reporting old versions. Reading the manifest here,
at launch, makes MCP-path attribution track in-place upgrades with no
re-registration (the editor/session restart that starts the proxy is enough).

Fail-open: every version-resolution failure degrades to .env, then "unknown".
The npx proxy is ALWAYS launched, so MCP availability is never gated on
attribution. Nothing is written to stdout before exec so the MCP stream stays
clean; diagnostics go to stderr only.

Attribution schema (closed): app=dataverse-skills/<version>;skill=mcp-direct;agent=<agent>
mirrors scripts/auth.py so the SDK and MCP paths report identically.

Usage (invoked by the MCP host, not by hand):
    python mcp_proxy.py <environment-url> [extra mcp flags, e.g. --preview]

Env:
    DATAVERSE_PLUGIN_AGENT  host id (claude-code|copilot|cursor|codex); default unknown
    DATAVERSE_PLUGIN_ROOT   optional: plugin dir containing the manifest, used only
                            if the in-package manifest cannot be found from __file__
"""
import os
import re
import sys

# Kept in sync with _ALLOWED_AGENTS in scripts/auth.py (closed schema).
_ALLOWED_AGENTS = {"claude-code", "copilot", "cursor", "codex", "unknown"}

# Manifest filenames carrying the plugin `version`, relative to the plugin's
# scripts/ dir, in preference order. All four are kept identical by the eval
# suite (EVAL-VERSION-01), so the first readable one wins.
_MANIFEST_RELPATHS = (
    os.path.join("..", ".claude-plugin", "plugin.json"),
    os.path.join("..", ".github", "plugin", "plugin.json"),
    os.path.join("..", ".cursor-plugin", "plugin.json"),
    os.path.join("..", ".codex-plugin", "plugin.json"),
)

# Attribution values are written to HTTP headers + telemetry: allow only a safe
# closed character set, never reject (rejecting would drop attribution entirely).
_VERSION_SANITIZE = re.compile(r"[^A-Za-z0-9_.-]")


def _read_version_from_scripts_dir(scripts_dir):
    """Read the plugin `version` from a manifest next to the given scripts/ dir."""
    import json
    for rel in _MANIFEST_RELPATHS:
        path = os.path.normpath(os.path.join(scripts_dir, rel))
        try:
            with open(path, "r", encoding="utf-8") as f:
                version = json.load(f).get("version")
            if version:
                return str(version)
        except Exception:
            continue
    return None


def _read_version_from_env_file():
    """Best-effort fallback: DATAVERSE_PLUGIN_VERSION from a .env at/above CWD."""
    here = os.getcwd()
    for _ in range(4):
        try:
            with open(os.path.join(here, ".env"), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DATAVERSE_PLUGIN_VERSION="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return None


def _resolve_version():
    """Live plugin version, fail-open: in-package manifest -> ROOT -> .env -> unknown."""
    version = None
    try:
        version = _read_version_from_scripts_dir(os.path.dirname(os.path.abspath(__file__)))
        if not version:
            root = os.environ.get("DATAVERSE_PLUGIN_ROOT")
            if root:
                version = _read_version_from_scripts_dir(os.path.join(root, "scripts"))
        if not version:
            version = _read_version_from_env_file()
    except Exception:
        version = None
    version = _VERSION_SANITIZE.sub("", version or "").strip(".-_")
    return version or "unknown"


def _resolve_agent():
    agent = (os.environ.get("DATAVERSE_PLUGIN_AGENT") or "unknown").strip()
    return agent if agent in _ALLOWED_AGENTS else "unknown"


def _build_context():
    return f"app=dataverse-skills/{_resolve_version()};skill=mcp-direct;agent={_resolve_agent()}"


def main(argv):
    child_env = dict(os.environ)
    try:
        child_env["DATAVERSE_OPERATION_CONTEXT"] = _build_context()
    except Exception as exc:  # never gate MCP on attribution
        sys.stderr.write(f"[mcp_proxy] attribution skipped: {exc}\n")

    npx_args = ["-y", "@microsoft/dataverse@latest", "mcp", *argv]
    try:
        if os.name == "nt":
            import subprocess
            # npx is a .cmd on Windows -> route through cmd; stdio is inherited.
            return subprocess.run(["cmd", "/c", "npx", *npx_args], env=child_env).returncode
        # POSIX: replace this process so npx owns stdin/stdout directly.
        os.execvpe("npx", ["npx", *npx_args], child_env)
    except FileNotFoundError:
        sys.stderr.write(
            "[mcp_proxy] 'npx' not found on PATH. Install Node.js "
            "(dv-connect Step 1) so the Dataverse MCP proxy can start.\n"
        )
        return 127
    return 0  # unreachable on POSIX success (process was replaced)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

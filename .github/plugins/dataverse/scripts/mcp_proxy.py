"""
mcp_proxy.py — Stdio-to-HTTP proxy for the Dataverse MCP server.

Reads JSON-RPC messages from stdin, adds a Bearer token (via auth.py),
forwards them to the Dataverse /api/mcp endpoint, and writes responses
to stdout. Handles token refresh automatically.

Usage (in .claude/mcp_settings.json):
    {
      "mcpServers": {
        "dataverse": {
          "command": "python",
          "args": ["scripts/mcp_proxy.py"]
        }
      }
    }
"""

import sys
import os
import json
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env


def forward(env_url, token, message):
    url = env_url + "/api/mcp"
    data = json.dumps(message).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def main():
    load_env()
    env_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not env_url:
        sys.stderr.write("ERROR: DATAVERSE_URL not set\n")
        sys.exit(1)

    token = get_token()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        try:
            response = forward(env_url, token, message)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Token expired, refresh and retry
                token = get_token()
                try:
                    response = forward(env_url, token, message)
                except Exception as retry_err:
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "error": {"code": -1, "message": str(retry_err)},
                    }
            else:
                body = e.read().decode(errors="replace")
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": e.code, "message": body},
                }
        except Exception as err:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -1, "message": str(err)},
            }

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()

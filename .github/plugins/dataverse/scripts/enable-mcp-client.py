"""
enable-mcp-client.py — Ensure an app registration is in the Dataverse MCP allowed clients list.

Queries the 'allowedmcpclient' entity by applicationid (from MCP_CLIENT_ID in .env).
- If the record exists with isenabled=false, updates it to true.
- If the record does not exist, creates it with isenabled=true.
- If the record already has isenabled=true, exits with no changes.

Usage:
    python enable-mcp-client.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_credential, load_env


def find_client(client, app_id):
    """Find an allowedmcpclient record by applicationid."""
    pages = client.records.get(
        "allowedmcpclient",
        filter=f"applicationid eq '{app_id}'",
        select=["allowedmcpclientid", "applicationid", "isenabled"],
        top=1,
    )
    return next((r for page in pages for r in page), None)


def main():
    load_env()
    env_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    mcp_client_id = os.environ.get("MCP_CLIENT_ID")

    if not env_url:
        print("ERROR: DATAVERSE_URL not set in .env", flush=True)
        sys.exit(1)
    if not mcp_client_id:
        print("ERROR: MCP_CLIENT_ID not set in .env", flush=True)
        sys.exit(1)

    from PowerPlatform.Dataverse.client import DataverseClient
    client = DataverseClient(base_url=env_url, credential=get_credential())

    print(f"Looking up MCP client {mcp_client_id}...", flush=True)
    record = find_client(client, mcp_client_id)

    if record and record.get("isenabled"):
        print(f"Client {mcp_client_id} is already enabled. No changes needed.", flush=True)
        return

    if record:
        print(f"Client exists but is disabled. Enabling...", flush=True)
        client.records.update("allowedmcpclient", record["allowedmcpclientid"], {"isenabled": True})
        print(f"Done. Client {mcp_client_id} enabled.", flush=True)
    else:
        print(f"Client not found. Creating with isenabled=true...", flush=True)
        client.records.create("allowedmcpclient", {
            "applicationid": mcp_client_id,
            "name": "DV_CLI_MCP_Client",
            "uniquename": "new_DV_CLI_MCP_Client",
            "isenabled": True,
        })
        print(f"Done. Client {mcp_client_id} created and enabled.", flush=True)


if __name__ == "__main__":
    main()

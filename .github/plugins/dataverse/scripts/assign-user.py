"""
assign-user.py — Add a user to a Dataverse environment and assign a security role.

Usage:
    python assign-user.py <email> "<Role Name>"

Example:
    python assign-user.py jordan@contoso.com "Sales Manager"

Uses the Python SDK for user/role queries. Falls back to Web API only for
the role association ($ref) which the SDK does not yet support.
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, get_credential, load_env


def try_pac_assign(email, role, env_url):
    """Try PAC CLI first — fast path when available."""
    try:
        result = subprocess.run(
            ["pac", "admin", "assign-user",
             "--environment", env_url,
             "--user", email,
             "--role", role],
            capture_output=True, text=True
        )
        return result.returncode == 0, result.stderr
    except FileNotFoundError:
        return False, "pac CLI not found"


def escape_odata_value(value):
    """Escape single quotes by doubling them, per OData spec."""
    return value.replace("'", "''")


def get_system_user(client, email):
    """Find a user by email using the Python SDK."""
    escaped = escape_odata_value(email)
    pages = client.records.get(
        "systemuser",
        filter=f"internalemailaddress eq '{escaped}'",
        select=["systemuserid", "fullname", "internalemailaddress"],
        top=1,
    )
    users = [u for page in pages for u in page]
    return users[0] if users else None


def get_role_id(client, role_name):
    """Find a role by name using the Python SDK."""
    escaped = escape_odata_value(role_name)
    pages = client.records.get(
        "role",
        filter=f"name eq '{escaped}'",
        select=["roleid", "name"],
        top=1,
    )
    roles = [r for page in pages for r in page]
    return roles[0]["roleid"] if roles else None


def assign_role_via_api(user_id, role_id, env_url, token):
    """Associate role to user via Web API $ref (SDK doesn't support this yet)."""
    url = f"{env_url}/api/data/v9.2/systemusers({user_id})/systemuserroles_association/$ref"
    body = {"@odata.id": f"{env_url}/api/data/v9.2/roles({role_id})"}
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return 204  # 204 No Content = success for association
        raise


def main():
    if len(sys.argv) < 3:
        print("Usage: python assign-user.py <email> \"<Role Name>\"", flush=True)
        sys.exit(1)

    email = sys.argv[1]
    role = sys.argv[2]

    load_env()
    env_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not env_url:
        print("ERROR: DATAVERSE_URL not set in .env", flush=True)
        sys.exit(1)

    print(f"Assigning {email} to role '{role}'...", flush=True)

    # Try PAC CLI first (fast path)
    success, err = try_pac_assign(email, role, env_url)
    if success:
        print(f"Done. {email} assigned to '{role}' via PAC CLI.", flush=True)
        return

    print(f"PAC CLI failed ({err.strip()}). Falling back to SDK + Web API...", flush=True)

    # Initialize SDK client for user/role queries
    from PowerPlatform.Dataverse.client import DataverseClient
    client = DataverseClient(base_url=env_url, credential=get_credential())

    # Wait for user to be provisioned (AAD sync can take a moment)
    user = None
    for attempt in range(6):
        user = get_system_user(client, email)
        if user:
            break
        print(f"  User not yet provisioned, waiting 10s... ({attempt + 1}/6)", flush=True)
        time.sleep(10)

    if not user:
        print(f"ERROR: {email} not found in this environment after 60s.", flush=True)
        print("Ensure the user has a valid AAD account in this tenant and has logged into a Power Platform app at least once.", flush=True)
        sys.exit(1)

    role_id = get_role_id(client, role)
    if not role_id:
        print(f"ERROR: Role '{role}' not found in this environment.", flush=True)
        print("Run: pac solution list-roles --environment <url>  to see available roles.", flush=True)
        sys.exit(1)

    # Role association requires Web API $ref — SDK doesn't support this yet
    token = get_token()
    assign_role_via_api(user["systemuserid"], role_id, env_url, token)
    print(f"Done. {email} ({user['fullname']}) assigned to '{role}'.", flush=True)


if __name__ == "__main__":
    main()

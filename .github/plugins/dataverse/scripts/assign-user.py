"""
assign-user.py — Add a user to a Dataverse environment and assign a security role.

Usage:
    python assign-user.py <email> "<Role Name>"

Example:
    python assign-user.py jordan@contoso.com "Sales Manager"

Falls back to Web API if pac CLI user-not-found error occurs.
"""

import sys
import os
import json
import time
import subprocess
import urllib.request
import urllib.parse
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, load_env

def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def api_post(url, token, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return resp.status

def try_pac_assign(email, role, env_url):
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

def get_system_user(email, env_url, token):
    escaped_email = escape_odata_value(email)
    filter_str = urllib.parse.quote(f"internalemailaddress eq '{escaped_email}'")
    url = f"{env_url}/api/data/v9.2/systemusers?$filter={filter_str}&$select=systemuserid,fullname,internalemailaddress"
    result = api_get(url, token)
    users = result.get("value", [])
    return users[0] if users else None

def get_role_id(role_name, env_url, token):
    escaped_role_name = escape_odata_value(role_name)
    filter_str = urllib.parse.quote(f"name eq '{escaped_role_name}'")
    url = f"{env_url}/api/data/v9.2/roles?$filter={filter_str}&$select=roleid,name"
    result = api_get(url, token)
    roles = result.get("value", [])
    return roles[0]["roleid"] if roles else None

def assign_role_via_api(user_id, role_id, env_url, token):
    url = f"{env_url}/api/data/v9.2/systemusers({user_id})/systemuserroles_association/$ref"
    body = {"@odata.id": f"{env_url}/api/data/v9.2/roles({role_id})"}
    try:
        api_post(url, token, body)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return True  # 204 No Content = success for association
        raise

def main():
    if len(sys.argv) < 3:
        print("Usage: python assign-user.py <email> \"<Role Name>\"")
        sys.exit(1)

    email = sys.argv[1]
    role = sys.argv[2]

    load_env()
    env_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not env_url:
        print("ERROR: DATAVERSE_URL not set in .env")
        sys.exit(1)

    print(f"Assigning {email} to role '{role}'...")

    # Try PAC CLI first (fast path)
    success, err = try_pac_assign(email, role, env_url)
    if success:
        print(f"Done. {email} assigned to '{role}' via PAC CLI.")
        return

    print(f"PAC CLI failed ({err.strip()}). Falling back to Web API...")

    token = get_token()

    # Wait for user to be provisioned (AAD sync can take a moment)
    user = None
    for attempt in range(6):
        user = get_system_user(email, env_url, token)
        if user:
            break
        print(f"  User not yet provisioned, waiting 10s... ({attempt + 1}/6)")
        time.sleep(10)

    if not user:
        print(f"ERROR: {email} not found in this environment after 60s.")
        print("Ensure the user has a valid AAD account in this tenant and has logged into a Power Platform app at least once.")
        sys.exit(1)

    role_id = get_role_id(role, env_url, token)
    if not role_id:
        print(f"ERROR: Role '{role}' not found in this environment.")
        print("Run: pac solution list-roles --environment <url>  to see available roles.")
        sys.exit(1)

    assign_role_via_api(user["systemuserid"], role_id, env_url, token)
    print(f"Done. {email} ({user['fullname']}) assigned to '{role}'.")

if __name__ == "__main__":
    main()

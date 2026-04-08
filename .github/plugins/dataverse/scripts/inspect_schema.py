"""
Inspect a Dataverse table schema to identify required fields, column types, and constraints.
Useful before generating sample data for any table.

Usage:
    python scripts/inspect_schema.py                   # defaults to 'account'
    python scripts/inspect_schema.py contact
    python scripts/inspect_schema.py cr123_customtable
"""

import os
import sys
import json
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_token, load_env


# System fields to skip -- these are auto-managed by Dataverse
SYSTEM_PREFIXES = (
    "createdon", "modifiedon", "ownerid", "statecode",
    "statuscode", "versionnumber", "timezoneruleversion",
    "importsequencenumber", "overriddencreatedon",
    "utcconversiontimezonecode", "owningbusinessunit",
    "owninguser", "owningteam",
)


def inspect_schema(table_name="account"):
    load_env()
    env_url = os.environ["DATAVERSE_URL"].rstrip("/")
    token = get_token()

    params = urllib.parse.urlencode({
        "$select": "LogicalName,AttributeType,RequiredLevel,DisplayName",
        "$filter": "AttributeOf eq null",
    })
    url = f"{env_url}/api/data/v9.2/EntityDefinitions(LogicalName='{table_name}')/Attributes?{params}"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
    })

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    print(f"{table_name} Table Schema", flush=True)
    print("=" * 80, flush=True)

    required_fields = []
    common_fields = []

    for attr in data["value"]:
        logical_name = attr["LogicalName"]
        attr_type = attr["AttributeType"]
        required_level = attr["RequiredLevel"]["Value"]

        # Skip system fields
        if logical_name.startswith(SYSTEM_PREFIXES):
            continue

        # Get display name safely
        display_name_obj = attr.get("DisplayName", {}).get("UserLocalizedLabel")
        display_name = display_name_obj.get("Label", logical_name) if display_name_obj else logical_name

        if required_level == "ApplicationRequired":
            required_fields.append({
                "name": logical_name,
                "type": attr_type,
                "display_name": display_name,
            })

        # Track fields useful for sample data (customize per table as needed)
        if attr_type in ("String", "Memo", "Integer", "Decimal", "Money",
                         "Double", "Boolean", "DateTime", "Picklist"):
            common_fields.append({
                "name": logical_name,
                "type": attr_type,
                "required": required_level,
                "display_name": display_name,
            })

    print("\nREQUIRED FIELDS:", flush=True)
    if required_fields:
        for field in required_fields:
            print(f"  - {field['name']} ({field['type']}) - {field['display_name']}", flush=True)
    else:
        print("  (none)", flush=True)

    print(f"\n\nCOMMON FIELDS ({len(common_fields)} non-system columns):", flush=True)
    for field in sorted(common_fields, key=lambda x: x["name"]):
        req_marker = " [REQUIRED]" if field["required"] == "ApplicationRequired" else ""
        print(f"  - {field['name']:30} ({field['type']:12}) - {field['display_name']}{req_marker}", flush=True)

    print("\n" + "=" * 80, flush=True)
    return required_fields, common_fields


if __name__ == "__main__":
    table = sys.argv[1] if len(sys.argv) > 1 else "account"
    try:
        inspect_schema(table)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"Error {e.code}: {error_body[:300]}", flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

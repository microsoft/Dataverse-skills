"""
Create sample records in a Dataverse table using the Python SDK.

Usage:
    python scripts/create_sample_data.py                # creates 5 sample accounts
    python scripts/create_sample_data.py --table account --count 5

Requires:
    pip install PowerPlatform-Dataverse-Client azure-identity
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
from auth import get_credential, load_env


# Sample data templates keyed by table logical name.
# Add more tables here as needed.
SAMPLE_DATA = {
    "account": [
        {
            "name": "Contoso Electronics Ltd",
            "telephone1": "555-0100",
            "emailaddress1": "contact@contoso.example.com",
            "revenue": 2500000.00,
            "numberofemployees": 150,
            "address1_city": "Seattle",
            "address1_stateorprovince": "WA",
            "address1_country": "United States",
            "address1_postalcode": "98101",
            "websiteurl": "https://contoso.example.com",
            "description": "Leading electronics manufacturer and distributor",
        },
        {
            "name": "Fabrikam Manufacturing Inc",
            "telephone1": "555-0101",
            "emailaddress1": "info@fabrikam.example.com",
            "revenue": 4200000.00,
            "numberofemployees": 280,
            "address1_city": "Chicago",
            "address1_stateorprovince": "IL",
            "address1_country": "United States",
            "address1_postalcode": "60601",
            "websiteurl": "https://fabrikam.example.com",
            "description": "Industrial equipment and machinery manufacturer",
        },
        {
            "name": "Adventure Works Cycles",
            "telephone1": "555-0102",
            "emailaddress1": "sales@adventureworks.example.com",
            "revenue": 1850000.00,
            "numberofemployees": 95,
            "address1_city": "Portland",
            "address1_stateorprovince": "OR",
            "address1_country": "United States",
            "address1_postalcode": "97201",
            "websiteurl": "https://adventureworks.example.com",
            "description": "Premium bicycle manufacturer and outdoor sports retailer",
        },
        {
            "name": "Northwind Traders",
            "telephone1": "555-0103",
            "emailaddress1": "hello@northwind.example.com",
            "revenue": 980000.00,
            "numberofemployees": 62,
            "address1_city": "Austin",
            "address1_stateorprovince": "TX",
            "address1_country": "United States",
            "address1_postalcode": "78701",
            "websiteurl": "https://northwind.example.com",
            "description": "Specialty food importer and distributor",
        },
        {
            "name": "Alpine Ski House",
            "telephone1": "555-0104",
            "emailaddress1": "contact@alpineskihouse.example.com",
            "revenue": 1350000.00,
            "numberofemployees": 78,
            "address1_city": "Denver",
            "address1_stateorprovince": "CO",
            "address1_country": "United States",
            "address1_postalcode": "80201",
            "websiteurl": "https://alpineskihouse.example.com",
            "description": "Winter sports equipment retailer and rental services",
        },
    ],
}


def create_sample_data(table_name="account", count=5):
    load_env()
    env_url = os.environ["DATAVERSE_URL"].rstrip("/")

    print(f"Target environment: {env_url}", flush=True)
    print(f"Table: {table_name}", flush=True)
    print(f"Records to create: {count}", flush=True)
    print("-" * 80, flush=True)

    try:
        from PowerPlatform.Dataverse.client import DataverseClient
        from PowerPlatform.Dataverse.core.errors import HttpError
    except ImportError:
        print("ERROR: PowerPlatform-Dataverse-Client not installed.", flush=True)
        print("Run: pip install --upgrade PowerPlatform-Dataverse-Client", flush=True)
        sys.exit(1)

    client = DataverseClient(base_url=env_url, credential=get_credential())

    # Get sample records (cycle through templates if count > available)
    templates = SAMPLE_DATA.get(table_name)
    if not templates:
        print(f"ERROR: No sample data templates defined for '{table_name}'.", flush=True)
        print("Add templates to SAMPLE_DATA in this script, or create a custom script.", flush=True)
        sys.exit(1)

    records_to_create = []
    for i in range(count):
        records_to_create.append(templates[i % len(templates)])

    # Create records
    created = []
    if count > 10:
        # Bulk create via CreateMultiple
        print(f"\nCreating {count} records via bulk create...", flush=True)
        try:
            guids = client.records.create(table_name, records_to_create)
            for i, guid in enumerate(guids):
                name = records_to_create[i].get("name", f"Record {i+1}")
                created.append({"id": guid, "name": name})
            print(f"  Created {len(guids)} records.", flush=True)
        except HttpError as e:
            print(f"  Bulk create failed: {e.status_code}: {e.message}", flush=True)
            print("  Falling back to individual creates...", flush=True)
            count_mode = "individual"
        else:
            count_mode = "bulk"

        if len(created) == 0:
            count_mode = "individual"

        if count_mode == "individual":
            for i, record in enumerate(records_to_create, 1):
                try:
                    guid = client.records.create(table_name, record)
                    name = record.get("name", f"Record {i}")
                    created.append({"id": guid, "name": name})
                    print(f"  [{i}/{count}] Created: {name} (ID: {guid})", flush=True)
                except HttpError as e:
                    name = record.get("name", f"Record {i}")
                    print(f"  [{i}/{count}] FAILED: {name} - {e.status_code}: {e.message}", flush=True)
    else:
        # Individual creates with progress
        for i, record in enumerate(records_to_create, 1):
            try:
                guid = client.records.create(table_name, record)
                name = record.get("name", f"Record {i}")
                created.append({"id": guid, "name": name})
                print(f"  [{i}/{count}] Created: {name} (ID: {guid})", flush=True)
            except HttpError as e:
                name = record.get("name", f"Record {i}")
                print(f"  [{i}/{count}] FAILED: {name} - {e.status_code}: {e.message}", flush=True)

    # Summary
    print("\n" + "=" * 80, flush=True)
    print("SAMPLE DATA CREATION SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print(f"\nCreated {len(created)}/{count} records.", flush=True)

    if created:
        print(f"\n{'#':<4} {'Record ID':<38} {'Name':<35}", flush=True)
        print("-" * 80, flush=True)
        for i, rec in enumerate(created, 1):
            print(f"{i:<4} {rec['id']:<38} {rec['name']:<35}", flush=True)

        print(f"\nView records: {env_url}/main.aspx?pagetype=entitylist&etn={table_name}", flush=True)
        print("To clean up later, use bulk delete.", flush=True)

    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create sample Dataverse records")
    parser.add_argument("--table", "-t", default="account", help="Table logical name (default: account)")
    parser.add_argument("--count", "-c", type=int, default=5, help="Number of records (default: 5)")
    args = parser.parse_args()

    try:
        create_sample_data(args.table, args.count)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled.", flush=True)
    except Exception as e:
        print(f"\nERROR: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

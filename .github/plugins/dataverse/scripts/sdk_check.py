"""
sdk_check.py — Verify the Dataverse Python SDK works against the current environment.

Usage:
    python scripts/sdk_check.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from auth import load_env, get_credential

load_env()

from PowerPlatform.Dataverse.client import DataverseClient

base_url = os.environ["DATAVERSE_URL"].rstrip("/")
client = DataverseClient(base_url=base_url, credential=get_credential())

# 1. Query systemuser table
pages = client.records.get(
    "systemuser",
    select=["fullname", "internalemailaddress"],
    top=3,
)
users = [u for page in pages for u in page]
print(f"[PASS] Queried systemuser — got {len(users)} record(s):")
for u in users:
    print(f"  - {u.get('fullname', '(no name)')} <{u.get('internalemailaddress', '')}>")

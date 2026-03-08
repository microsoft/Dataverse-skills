"""
validate.py — Post-import validation checks for a Dataverse environment.

Uses the Python Dataverse SDK where possible (table existence, role checks),
falls back to raw Web API for operations the SDK doesn't support (forms,
views, import job history).

Usage:
    python validate.py --all
    python validate.py --check-entity new_projectbudget
    python validate.py --check-form new_projectbudget quickcreate
    python validate.py --check-view new_projectbudget "My Open Budgets"
    python validate.py --check-role jordan@contoso.com "Sales Manager"
    python validate.py --import-errors
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error

sys.path.insert(0, os.path.dirname(__file__))
from auth import get_token, get_credential, load_env


# ---------------------------------------------------------------------------
# SDK client (lazy init)
# ---------------------------------------------------------------------------

_sdk_client = None


def _get_sdk_client(env_url):
    global _sdk_client
    if _sdk_client is None:
        from PowerPlatform.Dataverse.client import DataverseClient
        _sdk_client = DataverseClient(base_url=env_url, credential=get_credential())
    return _sdk_client


# ---------------------------------------------------------------------------
# SDK-powered checks
# ---------------------------------------------------------------------------

def check_entity(env_url, logical_name):
    """Check if a table exists using the Python SDK."""
    client = _get_sdk_client(env_url)
    info = client.tables.get(logical_name)
    if info:
        return True, f"Table '{logical_name}' exists (set: {info.get('entity_set_name', '?')})"
    return False, f"Table '{logical_name}' not found"


def check_role(env_url, email, role_name):
    """Check if a user has a security role using the Python SDK."""
    client = _get_sdk_client(env_url)
    pages = client.records.get(
        "systemuser",
        filter=f"internalemailaddress eq '{escape_odata_value(email)}'",
        expand=["systemuserroles_association"],
        select=["fullname", "internalemailaddress"],
        top=1,
    )
    users = [u for page in pages for u in page]
    if not users:
        return False, f"User '{email}' not found in this environment"
    user = users[0]
    roles = [r["name"] for r in user.get("systemuserroles_association", [])]
    if role_name in roles:
        return True, f"{user['fullname']} has role '{role_name}'"
    return False, f"{user['fullname']} does not have role '{role_name}'. Current roles: {', '.join(roles) or 'none'}"


def check_sdk_connectivity(env_url):
    """Basic SDK connectivity check — list custom tables."""
    client = _get_sdk_client(env_url)
    tables = client.tables.list(select=["LogicalName"], filter="IsCustomEntity eq true")
    return True, f"SDK connected — {len(tables)} custom table(s) in environment"


# ---------------------------------------------------------------------------
# Web API fallbacks (SDK doesn't support forms, views, or import history)
# ---------------------------------------------------------------------------

def escape_odata_value(value):
    """Escape single quotes by doubling them, per OData spec."""
    return value.replace("'", "''")


FORM_TYPE_CODES = {
    "main": 2,
    "quickcreate": 7,
    "card": 11,
    "quickview": 6,
}


def _api_get(url, token):
    """Raw Web API GET request for checks the SDK doesn't support."""
    parts = urllib.parse.urlsplit(url)
    encoded_query = urllib.parse.quote(parts.query, safe="=&$,.'()")
    url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, encoded_query, parts.fragment))
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Prefer": "odata.include-annotations=*",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()}"


def check_form(env_url, token, entity_logical_name, form_type):
    type_code = FORM_TYPE_CODES.get(form_type.lower())
    if not type_code:
        return False, f"Unknown form type '{form_type}'. Valid: {list(FORM_TYPE_CODES.keys())}"
    safe_entity = escape_odata_value(entity_logical_name)
    url = (f"{env_url}/api/data/v9.2/systemforms"
           f"?$filter=objecttypecode eq '{safe_entity}' and type eq {type_code}"
           f"&$select=name,formid,iscustomizable")
    result, err = _api_get(url, token)
    if err:
        return False, f"API error: {err}"
    forms = result.get("value", [])
    if forms:
        names = [f["name"] for f in forms]
        return True, f"{form_type} form(s) found on '{entity_logical_name}': {', '.join(names)}"
    return False, f"No {form_type} form found on '{entity_logical_name}'"


def check_view(env_url, token, entity_logical_name, view_name):
    safe_entity = escape_odata_value(entity_logical_name)
    safe_view = escape_odata_value(view_name)
    url = (f"{env_url}/api/data/v9.2/savedqueries"
           f"?$filter=returnedtypecode eq '{safe_entity}' and name eq '{safe_view}'"
           f"&$select=name,savedqueryid,statuscode")
    result, err = _api_get(url, token)
    if err:
        return False, f"API error: {err}"
    views = result.get("value", [])
    if views:
        return True, f"View '{view_name}' found on '{entity_logical_name}'"
    return False, f"View '{view_name}' not found on '{entity_logical_name}'"


def check_import_errors(env_url, token):
    url = (f"{env_url}/api/data/v9.2/importjobs"
           f"?$select=name,progress,solutionname,completedon,startedon"
           f"&$orderby=completedon desc&$top=5")
    result, err = _api_get(url, token)
    if err:
        return False, f"API error: {err}"
    jobs = result.get("value", [])
    if not jobs:
        return True, "No import jobs found"
    lines = []
    has_failure = False
    for job in jobs:
        progress = job.get("progress", 0)
        solution_name = job.get("solutionname", "unknown")
        status_label, detail = _check_solution_history(env_url, token, solution_name)
        if status_label == "Failed":
            has_failure = True
        line = f"  [{status_label}] {solution_name} - {progress:.0f}%"
        if detail:
            line += f" ({detail})"
        lines.append(line)
    return not has_failure, "\n".join(lines)


def _check_solution_history(env_url, token, solution_name):
    """Look up the latest import record in msdyn_solutionhistories for a definitive result."""
    safe_name = escape_odata_value(solution_name)
    url = (f"{env_url}/api/data/v9.2/msdyn_solutionhistories"
           f"?$filter=msdyn_name eq '{safe_name}' and msdyn_operation eq 0"
           f"&$select=msdyn_result,msdyn_status,msdyn_errorcode,msdyn_exceptionmessage"
           f"&$orderby=msdyn_starttime desc&$top=1")
    result, err = _api_get(url, token)
    if err:
        return "In Progress", f"history API error: {err[:80]}"
    if not result.get("value"):
        return "In Progress", "no history record"
    record = result["value"][0]
    status = record.get("msdyn_status")
    msdyn_result = record.get("msdyn_result")
    # msdyn_status: 0 = Started, 1 = Completed, 2 = Queued
    if status in (0, 2):
        status_name = "Started" if status == 0 else "Queued"
        return "In Progress", f"history: {status_name}"
    # msdyn_result: True = Success, False = Failure
    if msdyn_result is True:
        return "Completed", "history: Success"
    errorcode = record.get("msdyn_errorcode", 0)
    message = record.get("msdyn_exceptionmessage", "")
    detail = "history: Failure"
    if errorcode:
        detail += f", errorcode={errorcode}"
    if message:
        detail += f", {message[:100]}"
    return "Failed", detail


# ---------------------------------------------------------------------------
# Output and main
# ---------------------------------------------------------------------------

def print_result(ok, message):
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {message}", flush=True)
    return ok


def main():
    load_env()
    env_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not env_url:
        print("ERROR: DATAVERSE_URL not set in .env", flush=True)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Validate a Dataverse environment.")
    parser.add_argument("--all", action="store_true", help="Run all general checks (SDK connectivity + import errors)")
    parser.add_argument("--check-entity", metavar="LOGICAL_NAME", help="Check if a table exists (via SDK)")
    parser.add_argument("--check-form", nargs=2, metavar=("ENTITY", "FORM_TYPE"), help="Check if a form exists (via Web API)")
    parser.add_argument("--check-view", nargs=2, metavar=("ENTITY", "VIEW_NAME"), help="Check if a view exists (via Web API)")
    parser.add_argument("--check-role", nargs=2, metavar=("EMAIL", "ROLE_NAME"), help="Check if a user has a role (via SDK)")
    parser.add_argument("--import-errors", action="store_true", help="Check recent import job status (via Web API)")
    args = parser.parse_args()

    all_ok = True

    # SDK-powered checks (no token needed — SDK uses credential directly)
    if args.check_entity:
        ok, msg = check_entity(env_url, args.check_entity)
        all_ok &= print_result(ok, msg)

    if args.check_role:
        ok, msg = check_role(env_url, args.check_role[0], args.check_role[1])
        all_ok &= print_result(ok, msg)

    # Web API checks (need a Bearer token)
    if args.check_form or args.check_view or args.import_errors or args.all:
        token = get_token()

        if args.check_form:
            ok, msg = check_form(env_url, token, args.check_form[0], args.check_form[1])
            all_ok &= print_result(ok, msg)

        if args.check_view:
            ok, msg = check_view(env_url, token, args.check_view[0], args.check_view[1])
            all_ok &= print_result(ok, msg)

        if args.all or args.import_errors:
            ok, msg = check_import_errors(env_url, token)
            print_result(ok, "Recent import jobs:")
            print(msg, flush=True)

    # --all also runs SDK connectivity
    if args.all:
        ok, msg = check_sdk_connectivity(env_url)
        all_ok &= print_result(ok, msg)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

"""Request approved JIT access, verify ERP SQL, and optionally read a bounded table preview."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

def _load_auth_helpers():
    candidates = (
        Path(__file__).resolve().parents[3] / "scripts" / "auth.py",
        Path.cwd() / "scripts" / "auth.py",
    )
    for path in candidates:
        if not path.is_file():
            continue
        # An explicit file load also avoids a workspace auth cached in sys.modules.
        spec = importlib.util.spec_from_file_location("_erp_sql_auth", path)
        if spec is None or spec.loader is None:
            raise ImportError("Cannot load the auth helper.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        load_env = getattr(module, "load_env", None)
        get_cli_context = getattr(module, "get_cli_context", None)
        if not callable(load_env) or not callable(get_cli_context):
            raise ImportError("The auth helper is outdated.")
        return load_env, get_cli_context
    raise ImportError("The auth helper is missing.")


try:
    load_env, get_cli_context = _load_auth_helpers()
except (ImportError, OSError):
    raise SystemExit(
        "ERROR: ERP SQL requires a current auth.py with load_env and get_cli_context. "
        "Update the plugin; for skill-only installs, re-run the dv-connect helper setup "
        "to refresh scripts/auth.py. No credential request was made."
    ) from None


ACTION = "/api/data/v9.2/msprov_getfinopssqljitaccessasync"
PROBE = "SET NOCOUNT ON; SELECT DB_NAME(), SUSER_SNAME();"


class ConnectionFailure(RuntimeError):
    """A safe diagnostic without raw command output or credential values."""


class SqlFirewallFailure(ConnectionFailure):
    def __init__(self, client_ips):
        self.client_ips = tuple(sorted(set(client_ips)))
        detail = ", ".join(self.client_ips) if self.client_ips else "not reported"
        super().__init__(f"sqlcmd firewall failure; SQL-reported client IP: {detail}.")


def sql_firewall_failure(output):
    candidates = re.findall(
        r"\bClient\s+with\s+IP\s+address\s+['\"]([^'\"\r\n]+)['\"]",
        output, re.IGNORECASE,
    )
    if not candidates and not re.search(r"\b40615\b|\bfirewall\b", output, re.IGNORECASE):
        return None
    addresses = []
    for candidate in candidates:
        try:
            addresses.append(public_ip(candidate))
        except ConnectionFailure:
            continue
    return SqlFirewallFailure(addresses)


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        raise ConnectionFailure("Supply one valid public IP address, not a range.") from None
    if not address.is_global or address.is_multicast:
        raise ConnectionFailure("Supply one public egress IP; ranges and private IPs are not allowed.")
    return str(address)


def ip_scope(value):
    """Resolve an approved IPv4 address or bounded range without widening it."""
    value = value.strip()
    try:
        if "/" in value:
            network = ipaddress.IPv4Network(value, strict=True)
            start, end = network.network_address, network.broadcast_address
        elif "-" in value:
            first, last = value.split("-")
            start = ipaddress.IPv4Address(first.strip())
            end = ipaddress.IPv4Address(last.strip())
        else:
            address = ipaddress.IPv4Address(public_ip(value))
            return address, address
    except ValueError:
        raise ConnectionFailure("Supply a public IPv4 address, ordered IPv4 start-end range, or aligned IPv4 CIDR; IPv6 is not supported.") from None
    size = int(end) - int(start) + 1
    if not 1 <= size <= 256:
        raise ConnectionFailure("Approved IPv4 ranges must contain 1 to 256 addresses.")
    for number in range(int(start), int(end) + 1):
        public_ip(str(ipaddress.IPv4Address(number)))
    return start, end


def canonical_ip_scope(value):
    start, end = ip_scope(value)
    return str(start) if start == end else f"{start}-{end}"


def environment_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username or parsed.password or parsed.port
        or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or not re.fullmatch(r"[a-zA-Z0-9.-]+", parsed.netloc)
    ):
        raise ValueError("Environment must be an HTTPS organization URL without a path.")
    return f"https://{parsed.hostname}"


def diagnostic(output):
    sql_errors = {
        "102": "SQL syntax error",
        "156": "SQL syntax error",
        "207": "SQL column not found",
        "208": "SQL object not found",
        "229": "SQL permission denied",
    }
    messages = re.findall(r"\bMsg\s+(\d+),\s*Level\s+\d+", output, re.IGNORECASE)
    if messages:
        return ", ".join(
            f"SQL Msg {number}: {sql_errors.get(number, 'server error; raw output withheld')}"
            for number in sorted(set(messages))
        )
    if re.search(r"Sqlcmd:.*options are mutually exclusive", output, re.IGNORECASE):
        return "incompatible sqlcmd output flags"
    codes = re.findall(r"\b(?:AADSTS\d+|18456|4060|40615)\b", output)
    if codes:
        return ", ".join(sorted(set(codes)))
    for pattern, label in (
        (r"login failed", "SQL login failed"),
        (r"certificate|SSL Provider|TLS", "TLS/certificate failure"),
        (r"firewall|client.*IP address", "firewall/client-IP failure"),
        (r"timeout|timed out", "timeout"),
        (r"forbidden|unauthorized|permission|403|401", "authorization failure"),
    ):
        if re.search(pattern, output, re.IGNORECASE):
            return label
    return "raw output withheld to protect credentials"


def run_command(command, label, *, env=None, timeout=120):
    try:
        result = subprocess.run(
            command, capture_output=True, env=env, timeout=timeout, check=False,
            stdin=subprocess.DEVNULL,
        )
        # Decode on this thread: Windows subprocess reader threads can swallow decoding errors.
        errors = "strict" if label == "sqlcmd" else "replace"
        stdout = result.stdout.decode("utf-8", errors=errors)
        stderr = result.stderr.decode("utf-8", errors=errors)
    except subprocess.TimeoutExpired:
        raise ConnectionFailure(f"{label} timed out; output withheld.") from None
    except UnicodeDecodeError:
        raise ConnectionFailure(f"{label} returned invalid UTF-8; check output encoding. Output withheld.") from None
    except OSError:
        raise ConnectionFailure(f"{label} could not start; check its installation.") from None
    if result.returncode:
        output = stdout + "\n" + stderr
        if env and env.get("SQLCMDPASSWORD"):
            output = output.replace(env["SQLCMDPASSWORD"], "<redacted>")
        if label == "sqlcmd":
            firewall_error = sql_firewall_failure(output)
            if firewall_error:
                raise firewall_error
        detail = diagnostic(output)
        raise ConnectionFailure(f"{label} failed (exit {result.returncode}): {detail}.")
    output = stdout
    if env and env.get("SQLCMDPASSWORD"):
        output = output.replace(env["SQLCMDPASSWORD"], "<redacted>")
    return output


def read_json(output, label):
    try:
        value = json.loads(output)
    except (ValueError, TypeError):
        raise ConnectionFailure(f"{label} did not return valid JSON; output withheld.") from None
    if not isinstance(value, dict):
        raise ConnectionFailure(f"{label} did not return a JSON object.")
    return value


def required_string(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ConnectionFailure(f"Missing or invalid response field: {key}.")
    return value


def require_reader(role):
    if role != "Reader":
        raise ConnectionFailure("Only the Reader SQL access type is supported.")


def expiration(data):
    value = required_string(data, "sqljitexpiration")
    try:
        expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ConnectionFailure("Invalid credential expiration timestamp.") from None
    if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
        raise ConnectionFailure("Credentials have expired or have no explicit timezone.")
    return expires


def validate_credentials(data, client_ip, role):
    require_reader(role)
    operation = data.get("operationhistoryid")
    if not all(data.get(key) for key in (
        "servername", "databasename", "sqljitusername", "sqljitpassword",
    )):
        operation_id = str(operation) if operation else ""
        safe_id = operation_id if re.fullmatch(r"[0-9a-fA-F-]{36}", operation_id) else "not returned"
        raise ConnectionFailure(f"Credentials not ready; operation ID: {safe_id}.")
    for key in ("servername", "databasename", "sqljitusername", "sqljitpassword"):
        required_string(data, key)
    if not re.fullmatch(r"(?:tcp:)?[a-zA-Z0-9][a-zA-Z0-9.-]*(?:,\d{1,5})?", data["servername"]):
        raise ConnectionFailure("Invalid SQL server name.")
    if required_string(data, "sqljitrole") != role:
        raise ConnectionFailure("The returned SQL role does not match the approved role.")
    ip_value = required_string(data, "ipaddress")
    try:
        returned_scope = ip_scope(ip_value)
    except ConnectionFailure:
        raise ConnectionFailure("Invalid returned client IP scope; response withheld.") from None
    if returned_scope != ip_scope(client_ip):
        raise ConnectionFailure("The returned client IP scope does not exactly match the approved scope.")
    return expiration(data)


def request_credentials(cli, url, context, reason, client_ip, role):
    require_reader(role)
    client_ip = canonical_ip_scope(client_ip)
    # Only the non-secret request is on disk; the response stays in memory.
    with tempfile.TemporaryDirectory(prefix="erp-sql-") as directory:
        body_path = Path(directory) / "request.json"
        body_path.write_text(json.dumps({
            "sqljitreason": reason,
            "sqljitrole": role,
            "sqljitclientipaddress": client_ip,
        }), encoding="utf-8")
        output = run_command([
            cli, "api", "request", "--target", "dataverse",
            "--environment", url, "--path", ACTION, "--method", "POST",
            "--body-file", str(body_path), "--context", context,
        ], "Dataverse JIT request")
    return read_json(output, "Dataverse JIT request")


def execute_sql(sqlcmd, credentials, statement):
    """Run one read with shared secret handling, expiry checks, and bounded retries."""
    child_env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("SQLCMD") and key.upper() != "OSQLPASSWORD"
    }
    child_env["SQLCMDPASSWORD"] = credentials["sqljitpassword"]
    command = [
        sqlcmd, "-S", credentials["servername"], "-d", credentials["databasename"],
        "-U", credentials["sqljitusername"], "-N", "-b", "-l", "30", "-t", "30",
        "-h", "-1", "-s", "|", "-W", "-w", "65535", "-f", "o:65001", "-x", "-Q", statement,
    ]
    try:
        login_retries = 0
        firewall_retries = 0
        while True:
            expiration(credentials)
            try:
                output = run_command(command, "sqlcmd", env=child_env, timeout=75)
            except SqlFirewallFailure as error:
                start, end = ip_scope(credentials["ipaddress"])
                approved_ip = canonical_ip_scope(credentials["ipaddress"])
                observed_ip = ipaddress.ip_address(error.client_ips[0]) if len(error.client_ips) == 1 else None
                if observed_ip is not None and observed_ip.version == start.version and start <= observed_ip <= end:
                    if firewall_retries < 4:
                        firewall_retries += 1
                        print(
                            "SQL client IP is within the approved scope; waiting 60 seconds "
                            f"for firewall propagation ({firewall_retries}/4), using the same credentials.",
                            flush=True,
                        )
                        time.sleep(60)
                        continue
                    action = (
                        "The reported IP is within the approved scope; check JIT/firewall "
                        "propagation and network policy. Do not broaden the allowlist."
                    )
                elif len(error.client_ips) == 1:
                    action = (
                        f"The approved IP scope was {approved_ip}. SQL egress is outside the approved scope. "
                        "Stop and ask the user to supply an IPv4 address or range and approve a new JIT request. "
                        "Do not copy the SQL-reported IP or infer a range. "
                        "A new grant invalidates existing credentials for the same user/environment."
                    )
                else:
                    action = (
                        "No unambiguous public SQL client IP was reported. "
                        "Stop; do not discover addresses, guess, or broaden the allowlist."
                    )
                raise ConnectionFailure(f"{error} {action}") from None
            except ConnectionFailure as error:
                if login_retries == 2 or not re.search(r"18456|SQL login failed|4060", str(error)):
                    raise
                login_retries += 1
                print("SQL login not ready; retrying the same credentials in 10 seconds.", flush=True)
                time.sleep(10)
                continue
            return output
    finally:
        child_env.pop("SQLCMDPASSWORD", None)


def probe_sql(sqlcmd, credentials, *, wait_seconds=60):
    time.sleep(wait_seconds)
    output = execute_sql(sqlcmd, credentials, PROBE)
    rows = [line.strip() for line in output.splitlines() if line.strip()]
    expected = [credentials["databasename"], credentials["sqljitusername"]]
    if len(rows) != 1 or [part.strip() for part in rows[0].split("|")] != expected:
        raise ConnectionFailure("sqlcmd returned an unexpected database/login; output withheld.")


def table_parts(value):
    parts = value.split(".")
    if len(parts) not in (1, 2) or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", part) for part in parts
    ):
        raise ConnectionFailure("Use a simple table name or schema.table; arbitrary SQL is not accepted.")
    return (parts[0], parts[1]) if len(parts) == 2 else (None, parts[0])


def metadata_rows(output, width):
    rows = [[part.strip() for part in line.split("|")] for line in output.splitlines() if line.strip()]
    if any(len(row) != width for row in rows):
        raise ConnectionFailure("Unexpected SQL metadata format; output withheld.")
    return rows


def quote_identifier(value):
    return "[" + value.replace("]", "]]") + "]"


def entity_name_fragment(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value):
        raise ConnectionFailure("Use an entity-name fragment of 1-128 ASCII letters, digits, or underscores, starting with a letter or underscore.")
    return value.lower()


def read_table(sqlcmd, credentials, table, top, *, waiting_only=False, virtual_entity_name=None):
    schema, name = table_parts(table)
    if not 1 <= top <= 100:
        raise ConnectionFailure("Table previews require --top between 1 and 100.")
    if waiting_only and name.lower() != "batchjob":
        raise ConnectionFailure("Waiting-job reads require the BATCHJOB table.")
    if virtual_entity_name is not None:
        virtual_entity_name = entity_name_fragment(virtual_entity_name)
        if waiting_only or name.lower() != "cdsvirtualentitylist":
            raise ConnectionFailure("Virtual-entity name searches require CDSVIRTUALENTITYLIST and cannot use waiting-job mode.")
    schema_filter = f" AND LOWER(s.name) = N'{schema.lower()}'" if schema else ""
    matches = metadata_rows(execute_sql(sqlcmd, credentials, f"""
SET NOCOUNT ON;
SELECT s.name, t.name, t.object_id
FROM sys.tables AS t JOIN sys.schemas AS s ON t.schema_id = s.schema_id
WHERE LOWER(t.name) = N'{name.lower()}'{schema_filter}
ORDER BY s.name;
"""), 3)
    if not matches:
        raise ConnectionFailure("No visible matching table; verify its name and Reader metadata permissions.")
    if len(matches) != 1:
        raise ConnectionFailure("Table name is ambiguous; specify schema.table before requesting access again.")
    resolved_schema, resolved_name, object_id = matches[0]
    if not object_id.isdecimal():
        raise ConnectionFailure("Invalid SQL object metadata.")
    qualified = quote_identifier(resolved_schema) + "." + quote_identifier(resolved_name)
    columns = metadata_rows(execute_sql(sqlcmd, credentials, f"""
SET NOCOUNT ON;
SELECT c.name, ty.name
FROM sys.columns AS c JOIN sys.types AS ty ON c.user_type_id = ty.user_type_id
WHERE c.object_id = {object_id}
ORDER BY c.column_id;
"""), 2)
    scalar_types = {
        "bigint", "int", "smallint", "tinyint", "bit", "decimal", "numeric",
        "float", "real", "money", "smallmoney", "date", "datetime", "datetime2",
        "smalldatetime", "datetimeoffset", "time", "char", "varchar", "nchar",
        "nvarchar", "uniqueidentifier",
    }
    selected = [
        column for column, kind in columns
        if kind.lower() in scalar_types
        and not re.search(r"password|secret|token|privatekey|credential|connectionstring|parameter", column, re.IGNORECASE)
    ]
    predicate = ""
    if waiting_only:
        integer_columns = {
            column.lower(): column for column, kind in columns
            if kind.lower() in {"bigint", "int", "smallint", "tinyint"}
        }
        if not {"status", "recid"} <= integer_columns.keys():
            raise ConnectionFailure("Waiting-job reads require integer STATUS and RECID columns.")
        predicate = f" WHERE {quote_identifier(integer_columns['status'])} = 1"
        allowed = {"recid", "caption", "status", "startdatetime", "enddatetime", "batchgroup", "company"}
        selected = [column for column in selected if column.lower() in allowed]
    search_columns = []
    if virtual_entity_name is not None:
        search_columns = [
            column for column, kind in columns
            if column in selected and kind.lower() in {"char", "varchar", "nchar", "nvarchar"}
            and "name" in column.lower()
        ]
        if not search_columns:
            raise ConnectionFailure("No supported non-secret name-like text columns exist in CDSVIRTUALENTITYLIST; no name search was performed.")
        pattern = virtual_entity_name.replace("_", "[_]")
        predicate = " WHERE (" + " OR ".join(
            f"LOWER({quote_identifier(column)}) LIKE N'%{pattern}%'" for column in search_columns
        ) + ")"
    if not selected:
        raise ConnectionFailure("No supported non-secret scalar columns are available for preview.")
    omitted = [column for column, _ in columns if column not in selected]
    print(f"Table: {qualified}", flush=True)
    if omitted:
        print("Omitted payload/secret-like/unsupported columns: " + ", ".join(omitted), flush=True)
    if waiting_only:
        print("Filter: BatchStatus.Waiting = 1 (Microsoft BatchStatus enum reference).", flush=True)
    if virtual_entity_name is not None:
        print(f"Filter: case-insensitive literal substring '{virtual_entity_name}' in name-like columns: "
              + ", ".join(search_columns), flush=True)
    count = execute_sql(sqlcmd, credentials, f"SET NOCOUNT ON; SELECT COUNT_BIG(*) FROM {qualified}{predicate};").strip()
    if not count.isdecimal():
        raise ConnectionFailure("Unexpected table row-count response; output withheld.")
    label = "Total matching entities" if virtual_entity_name is not None else ("Total waiting jobs" if waiting_only else "Total rows")
    print(f"{label} at count time: {count}", flush=True)
    recid = next((column for column in selected if column.lower() == "recid"), None)
    order = " ORDER BY " + quote_identifier(recid) if recid else ""
    print(
        f"Preview limit: {top}; " + ("RECID ascending, not latest jobs." if recid else "no guaranteed ordering."),
        flush=True,
    )
    print("Text preview only: long values may be truncated; delimiters/newlines in values are not escaped.", flush=True)
    output = execute_sql(
        sqlcmd, credentials,
        f"SET NOCOUNT ON; SELECT TOP ({top}) "
        + ", ".join(quote_identifier(column) for column in selected) + f" FROM {qualified}{predicate}{order};",
    )
    print(" | ".join(selected), flush=True)
    print(output.rstrip() or "(No rows returned.)", flush=True)


@contextmanager
def sql_access(args):
    """Own one approved grant for either a one-shot read or a reusable session."""
    url = environment_url(args.environment)
    if environment_url(args.confirm_environment) != url:
        raise ConnectionFailure("Approval URL does not match the target environment.")
    client_ip = canonical_ip_scope(args.client_ip)
    if not args.reason.strip():
        raise ConnectionFailure("An approved, non-empty access reason is required.")
    require_reader(args.role)
    virtual_entity_name = getattr(args, "virtual_entity_name", None)
    if sum((bool(args.table), bool(args.waiting_jobs), virtual_entity_name is not None)) > 1:
        raise ConnectionFailure("Choose only one of --table, --waiting-jobs, or --virtual-entity-name.")
    if virtual_entity_name is not None:
        entity_name_fragment(virtual_entity_name)
    if args.table or args.waiting_jobs or virtual_entity_name is not None:
        if args.table:
            table_parts(args.table)
        if not 1 <= args.top <= 100:
            raise ConnectionFailure("Table previews require --top between 1 and 100.")
    tools = {name: shutil.which(name) for name in ("dataverse", "sqlcmd")}
    if missing := [name for name, path in tools.items() if path is None]:
        raise ConnectionFailure("Missing tools: " + ", ".join(missing))
    sqlcmd_help = run_command([tools["sqlcmd"], "-?"], "sqlcmd variant check")
    if "SQL Server Command Line Tool" not in sqlcmd_help or not re.search(r"-N(?:\[s\|m\|o\])?\s+Encrypt Connection", sqlcmd_help):
        raise ConnectionFailure("This helper requires sqlcmd (ODBC) with the -N encryption flag.")
    load_env()
    context = get_cli_context("erp-sql")
    print(f"Target: {url}; role: {args.role}; client IP scope: {client_ip}", flush=True)
    org = read_json(run_command([
        tools["dataverse"], "org", "who", "--environment", url,
        "--json", "--context", context,
    ], "Dataverse environment check"), "Dataverse environment check")
    if environment_url(required_string(org, "OrgUrl")) != url:
        raise ConnectionFailure("Dataverse organization does not match the approved target.")
    required_string(org, "ErpUrl")
    if org.get("ErpDeploymentType") != "OnlineDev":
        raise ConnectionFailure("Only an OnlineDev unified developer environment is supported.")
    credentials = request_credentials(
        tools["dataverse"], url, context, args.reason, str(client_ip), args.role,
    )
    try:
        expires = validate_credentials(credentials, str(client_ip), args.role)
        print(f"{args.role} credentials received; expiry: {expires.isoformat()}. Waiting for propagation.", flush=True)
        probe_sql(tools["sqlcmd"], credentials)
        print("Connected successfully; sqlcmd verified the expected database and login.")
        yield tools["sqlcmd"], credentials
    finally:
        credentials.clear()


def connect(args):
    with sql_access(args) as (sqlcmd, credentials):
        if args.table:
            read_table(sqlcmd, credentials, args.table, args.top)
        elif args.waiting_jobs:
            read_table(sqlcmd, credentials, "BATCHJOB", args.top, waiting_only=True)
        elif getattr(args, "virtual_entity_name", None) is not None:
            read_table(sqlcmd, credentials, "CDSVIRTUALENTITYLIST", args.top, virtual_entity_name=args.virtual_entity_name)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--client-ip", required=True, help="User-supplied, approved public IPv4 address or range/CIDR (maximum 256 addresses; no discovery)")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--role", choices=("Reader",), required=True, help="Explicitly approved Reader-only JIT access")
    parser.add_argument("--confirm-environment", required=True)
    parser.add_argument("--table", help="Approved table or schema.table to preview after connecting")
    parser.add_argument("--waiting-jobs", action="store_true", help="Read BATCHJOB with STATUS = 1 (Waiting); no arbitrary SQL")
    parser.add_argument("--virtual-entity-name", help="Search CDSVIRTUALENTITYLIST name-like text columns for a literal entity-name fragment (case-insensitive)")
    parser.add_argument("--top", type=int, help="Preview limit, 1-100 (default 50 with a read mode)")
    args = parser.parse_args()
    if sum((args.table is not None, args.waiting_jobs, args.virtual_entity_name is not None)) > 1:
        parser.error("Choose only one of --table, --waiting-jobs, or --virtual-entity-name.")
    if args.top is not None and not (args.table or args.waiting_jobs or args.virtual_entity_name is not None):
        parser.error("--top requires --table, --waiting-jobs, or --virtual-entity-name.")
    if args.top is None:
        args.top = 50
    try:
        connect(args)
    except (ConnectionFailure, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

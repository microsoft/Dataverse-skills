"""Request approved JIT access, verify ERP SQL, and optionally read a bounded table preview."""

import argparse
from datetime import datetime, timezone
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
from urllib.error import URLError
from urllib.request import Request, urlopen

for scripts in (Path(__file__).resolve().parents[3] / "scripts", Path.cwd() / "scripts"):
    if scripts.is_dir():
        sys.path.insert(0, str(scripts))

from auth import load_env, _operation_context_str


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
    """Resolve an approved address or bounded IPv4 range without widening it."""
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
            address = ipaddress.ip_address(public_ip(value))
            return address, address
    except ValueError:
        raise ConnectionFailure("Supply a public IP, ordered IPv4 start-end range, or aligned IPv4 CIDR.") from None
    size = int(end) - int(start) + 1
    if not 1 <= size <= 256:
        raise ConnectionFailure("Approved IPv4 ranges must contain 1 to 256 addresses.")
    for number in range(int(start), int(end) + 1):
        public_ip(str(ipaddress.IPv4Address(number)))
    return start, end


def canonical_ip_scope(value):
    start, end = ip_scope(value)
    return str(start) if start == end else f"{start}-{end}"


def discover_public_ip():
    # IP discovery is separate from granting access and never includes auth.
    request = Request("https://api.ipify.org?format=json", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(1025)
    except (URLError, TimeoutError, OSError):
        raise ConnectionFailure("Public IP discovery failed; supply the IP explicitly.") from None
    if len(body) > 1024:
        raise ConnectionFailure("Public IP service returned an oversized response.")
    data = read_json(body, "Public IP service")
    return public_ip(required_string(data, "ip"))


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
    if role not in ("Reader", "Writer"):
        raise ConnectionFailure("Access type must be Reader or Writer.")
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
                        "Confirm the SQL-reported IP and obtain approval for a new JIT request "
                        "using that exact --client-ip; do not reuse the HTTP-discovered IP. "
                        "If SQL reports a different IP after an approved correction, stop issuing "
                        "grants and arrange stable SQL egress with the network administrator."
                    )
                else:
                    action = (
                        "No unambiguous public SQL client IP was reported. Check network policy "
                        "with the administrator; do not guess or broaden the allowlist."
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


def read_table(sqlcmd, credentials, table, top):
    schema, name = table_parts(table)
    if not 1 <= top <= 100:
        raise ConnectionFailure("Table previews require --top between 1 and 100.")
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
    if not selected:
        raise ConnectionFailure("No supported non-secret scalar columns are available for preview.")
    omitted = [column for column, _ in columns if column not in selected]
    print(f"Table: {qualified}", flush=True)
    if omitted:
        print("Omitted payload/secret-like/unsupported columns: " + ", ".join(omitted), flush=True)
    count = execute_sql(sqlcmd, credentials, f"SET NOCOUNT ON; SELECT COUNT_BIG(*) FROM {qualified};").strip()
    if not count.isdecimal():
        raise ConnectionFailure("Unexpected table row-count response; output withheld.")
    print(f"Total rows at count time: {count}", flush=True)
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
        + ", ".join(quote_identifier(column) for column in selected) + f" FROM {qualified}{order};",
    )
    print(" | ".join(selected), flush=True)
    print(output.rstrip() or "(No rows returned.)", flush=True)


def connect(args):
    url = environment_url(args.environment)
    if environment_url(args.confirm_environment) != url:
        raise ConnectionFailure("Approval URL does not match the target environment.")
    client_ip = canonical_ip_scope(args.client_ip)
    if not args.reason.strip():
        raise ConnectionFailure("An approved, non-empty access reason is required.")
    if args.role not in ("Reader", "Writer"):
        raise ConnectionFailure("An explicitly selected Reader or Writer access type is required.")
    if args.table:
        table_parts(args.table)
        if not 1 <= args.top <= 100:
            raise ConnectionFailure("Table previews require --top between 1 and 100.")
    tools = {name: shutil.which(name) for name in ("dataverse", "sqlcmd")}
    if missing := [name for name, path in tools.items() if path is None]:
        raise ConnectionFailure("Missing tools: " + ", ".join(missing))
    sqlcmd_help = run_command([tools["sqlcmd"], "-?"], "sqlcmd variant check")
    if "SQL Server Command Line Tool" not in sqlcmd_help or not re.search(r"-N\s+Encrypt Connection", sqlcmd_help):
        raise ConnectionFailure("This helper requires sqlcmd (ODBC) with the -N encryption flag.")
    load_env()
    context = _operation_context_str("erp-sql")
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
        if args.table:
            read_table(tools["sqlcmd"], credentials, args.table, args.top)
    finally:
        credentials.clear()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover-ip", action="store_true", help="Discover public IP only; no JIT grant or SQL connection")
    parser.add_argument("--environment")
    parser.add_argument("--client-ip", help="Approved public IP or IPv4 range/CIDR (maximum 256 addresses)")
    parser.add_argument("--reason")
    parser.add_argument("--role", choices=("Reader", "Writer"), help="Explicitly approved JIT access type")
    parser.add_argument("--confirm-environment")
    parser.add_argument("--table", help="Approved table or schema.table to preview after connecting")
    parser.add_argument("--top", type=int, help="Preview limit, 1-100 (default 50 with --table)")
    args = parser.parse_args()
    connection_args = (args.environment, args.client_ip, args.reason, args.role, args.confirm_environment)
    if args.discover_ip and (any(connection_args) or args.table is not None or args.top is not None):
        parser.error("--discover-ip cannot be combined with connection arguments.")
    if args.top is not None and not args.table:
        parser.error("--top requires --table.")
    if args.top is None:
        args.top = 50
    if not args.discover_ip and not all(connection_args):
        parser.error("--environment, --client-ip, --reason, --role, and --confirm-environment are required.")
    try:
        if args.discover_ip:
            print(discover_public_ip())
        else:
            connect(args)
    except (ConnectionFailure, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

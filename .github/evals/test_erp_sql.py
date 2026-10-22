"""Hermetic tests for the ERP SQL credential-to-sqlcmd workflow."""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[1] / "plugins" / "dataverse"
    / "skills" / "erp-sql" / "scripts" / "connect.py"
)
spec = importlib.util.spec_from_file_location("erp_sql_connect", SCRIPT)
sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sql)

URL = "https://example.crm.dynamics.com"
IP = "8.8.8.8"


def credentials(**updates):
    value = {
        "servername": "example.database.windows.net",
        "databasename": "AxDB",
        "sqljitusername": "temporary_reader",
        "sqljitpassword": "test-only-not-a-real-password",
        "sqljitrole": "Reader",
        "ipaddress": IP,
        "sqljitexpiration": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "operationhistoryid": "12345678-1234-1234-1234-123456789abc",
    }
    value.update(updates)
    return value


class ContractTests(unittest.TestCase):
    def test_environment_normalization_and_rejections(self):
        self.assertEqual(sql.environment_url(URL.upper() + "/"), URL)
        for url in (
            "http://example.com", "https://user:password@example.com",
            URL + "/api/data", URL + "?other=env", URL + "#fragment",
            "https://example.com:443", "https://example.com&whoami",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sql.environment_url(url)

    def test_credentials_validate_exact_contract(self):
        self.assertGreater(sql.validate_credentials(credentials(), IP, "Reader"), datetime.now(timezone.utc))
        for changes in (
            {"sqljitrole": "Writer"}, {"ipaddress": "1.1.1.1"},
            {"sqljitexpiration": "2020-01-01T00:00:00Z"},
            {"sqljitexpiration": "2099-01-01T00:00:00"},
            {"sqljitexpiration": "invalid"}, {"servername": "host;bad"},
            {"sqljitpassword": ""}, {"sqljitusername": None},
            {"ipaddress": "2606:4700:4700::1111"},
        ):
            with self.subTest(changes=changes), self.assertRaises(sql.ConnectionFailure):
                sql.validate_credentials(credentials(**changes), IP, "Reader")

    def test_pending_response_exposes_only_operation_id(self):
        with self.assertRaises(sql.ConnectionFailure) as raised:
            sql.validate_credentials(credentials(sqljitpassword=None), IP, "Reader")
        self.assertIn("12345678-1234-1234-1234-123456789abc", str(raised.exception))

    def test_single_address_range_is_accepted_but_broad_ranges_are_rejected(self):
        sql.validate_credentials(credentials(ipaddress=f"{IP}-{IP}"), IP, "Reader")
        for value in (f"{IP}-8.8.8.9", f"8.8.8.7-{IP}", f"{IP}-{IP}-{IP}", f"{IP}/24"):
            with self.subTest(value=value), self.assertRaises(sql.ConnectionFailure):
                sql.validate_credentials(credentials(ipaddress=value), IP, "Reader")

    def test_approved_range_and_cidr_have_identical_exact_bounds(self):
        scope = "8.8.8.8-8.8.8.15"
        self.assertEqual(sql.canonical_ip_scope("8.8.8.8/29"), scope)
        self.assertEqual(sql.canonical_ip_scope(f"{IP}-{IP}"), IP)
        self.assertEqual(sql.canonical_ip_scope("8.8.8.0/24"), "8.8.8.0-8.8.8.255")
        sql.validate_credentials(credentials(ipaddress=scope), "8.8.8.8/29", "Reader")
        sql.validate_credentials(credentials(ipaddress="8.8.8.8/29"), scope, "Reader")
        for returned in ("8.8.8.7-8.8.8.15", "8.8.8.8-8.8.8.16", "8.8.8.8-8.8.8.14", IP):
            with self.subTest(returned=returned), self.assertRaises(sql.ConnectionFailure):
                sql.validate_credentials(credentials(ipaddress=returned), scope, "Reader")

    def test_invalid_or_overbroad_scopes_are_rejected_before_request(self):
        for value in (
            "8.8.8.15-8.8.8.8", "8.8.8.0-8.8.9.0", "8.8.8.0/23",
            "8.8.8.9/29", "8.8.8.8-8.8.8.9-8.8.8.10", "8.8.8.8,8.8.8.9",
            "10.0.0.0/24", "9.255.255.255-10.0.0.1", "224.0.0.0/24",
            "2606:4700:4700::1111-2606:4700:4700::1112", "8.8.8.8-::1", "0.0.0.0/0",
            "2606:4700:4700::1111", "::ffff:8.8.8.8", "2606:4700:4700::/120",
        ):
            with self.subTest(value=value), mock.patch.object(sql, "run_command") as run:
                with self.assertRaises(sql.ConnectionFailure):
                    sql.request_credentials("dataverse", URL, "context", "User reason", value, "Reader")
                run.assert_not_called()

    def test_cidr_request_sends_exact_range_and_preserves_reason(self):
        def run(command, label):
            body = json.loads(Path(command[command.index("--body-file") + 1]).read_text())
            self.assertEqual(body["sqljitclientipaddress"], "8.8.8.8-8.8.8.15")
            self.assertEqual(body["sqljitreason"], "Exact user reason ")
            return json.dumps(credentials(ipaddress="8.8.8.8-8.8.8.15"))

        with mock.patch.object(sql, "run_command", side_effect=run):
            sql.request_credentials("dataverse", URL, "context", "Exact user reason ", "8.8.8.8/29", "Reader")

    def test_selected_writer_is_preserved_and_unselected_writer_is_rejected(self):
        sql.validate_credentials(credentials(sqljitrole="Writer"), IP, "Writer")
        with self.assertRaises(sql.ConnectionFailure):
            sql.validate_credentials(credentials(sqljitrole="Writer"), IP, "Reader")
        with mock.patch.object(sql, "run_command", return_value=json.dumps(credentials(sqljitrole="Writer"))) as run:
            sql.request_credentials("dataverse", URL, "context", "User reason", IP, "Writer")
        self.assertEqual(run.call_count, 1)
        with mock.patch.object(sql, "run_command") as run:
            with self.assertRaises(sql.ConnectionFailure):
                sql.request_credentials("dataverse", URL, "context", "User reason", IP, "Admin")
            run.assert_not_called()

    def test_public_ip_validation(self):
        self.assertEqual(sql.public_ip(IP), IP)
        for value in ("127.0.0.1", "10.0.0.1", "0.0.0.0", "::1", "224.0.0.1", "8.8.8.0/24"):
            with self.subTest(value=value), self.assertRaises(sql.ConnectionFailure):
                sql.public_ip(value)

    def test_ip_discovery_is_separate_and_unauthenticated(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"ip": IP}).encode()
        with mock.patch.object(sql, "urlopen", return_value=response) as fetch:
            self.assertEqual(sql.discover_public_ip(), IP)
        request = fetch.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.ipify.org?format=json")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(fetch.call_args.kwargs["timeout"], 15)
        response.__enter__.return_value.read.assert_called_once_with(1025)

    def test_ip_discovery_rejects_bad_responses(self):
        for body in (b"x" * 1025, b"not json", b'{"ip":"127.0.0.1"}', b'{"ip":"2606:4700:4700::1111"}', b"[]"):
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = body
            with self.subTest(body=body[:40]), mock.patch.object(sql, "urlopen", return_value=response):
                with self.assertRaises(sql.ConnectionFailure):
                    sql.discover_public_ip()

    def test_request_uses_managed_cli_and_only_nonsecret_body_file(self):
        paths = []
        response = credentials()

        def run(command, label):
            self.assertEqual(label, "Dataverse JIT request")
            self.assertIn("--target", command)
            self.assertEqual(command[command.index("--target") + 1], "dataverse")
            self.assertEqual(command[command.index("--environment") + 1], URL)
            self.assertEqual(command[command.index("--path") + 1], sql.ACTION)
            self.assertIn("--context", command)
            path = Path(command[command.index("--body-file") + 1])
            paths.append(path)
            self.assertEqual(json.loads(path.read_text()), {
                "sqljitreason": "Approved reason", "sqljitrole": "Reader",
                "sqljitclientipaddress": IP,
            })
            return json.dumps(response)

        with mock.patch.object(sql, "run_command", side_effect=run), redirect_stdout(io.StringIO()) as output:
            result = sql.request_credentials("dataverse", URL, "context", "Approved reason", IP, "Reader")
        self.assertEqual(result, response)
        self.assertNotIn(response["sqljitpassword"], output.getvalue())
        self.assertFalse(paths[0].exists())

    def test_failed_command_and_timeout_do_not_leak_output(self):
        secret = credentials()["sqljitpassword"]
        failed = subprocess.CompletedProcess(["fake"], 1, secret.encode(), ("AADSTS50173 " + secret).encode())
        with mock.patch.object(sql.subprocess, "run", return_value=failed):
            with self.assertRaises(sql.ConnectionFailure) as raised:
                sql.run_command(["fake"], "JIT")
        self.assertIn("AADSTS50173", str(raised.exception))
        self.assertNotIn(secret, str(raised.exception))
        timed_out = subprocess.TimeoutExpired(["fake"], 1, output=secret, stderr=secret)
        with mock.patch.object(sql.subprocess, "run", side_effect=timed_out):
            with self.assertRaises(sql.ConnectionFailure) as raised:
                sql.run_command(["fake"], "JIT")
        self.assertNotIn(secret, str(raised.exception))

    def test_firewall_error_preserves_only_valid_client_ips(self):
        for candidate, expected in (
            ("1.1.1.1", ("1.1.1.1",)),
            ("2606:4700:4700::1111", ("2606:4700:4700::1111",)),
            ("not-an-ip-or-safe-message", ()),
            ("10.0.0.1", ()),
            ("1.1.1.0/24", ()),
        ):
            with self.subTest(candidate=candidate):
                error = sql.sql_firewall_failure(
                    f"40615: Client with IP address '{candidate}' is not allowed to access the server."
                )
                self.assertEqual(error.client_ips, expected)
                self.assertNotIn("not-an-ip-or-safe-message", str(error))
        self.assertIsNone(sql.sql_firewall_failure("Login failed. 18456"))

    def test_sql_password_is_redacted_before_firewall_ip_extraction(self):
        for secret in ("test-secret", "1.1.1.1"):
            output = (
                f"40615 Client with IP address '1.1.1.1' is not allowed. "
                f"secret={secret}"
            )
            failed = subprocess.CompletedProcess(["sqlcmd"], 1, b"", output.encode())
            with mock.patch.object(sql.subprocess, "run", return_value=failed):
                with self.assertRaises(sql.SqlFirewallFailure) as raised:
                    sql.run_command(["sqlcmd"], "sqlcmd", env={"SQLCMDPASSWORD": secret})
            self.assertNotIn(secret, str(raised.exception))
            self.assertEqual(
                raised.exception.client_ips, () if secret == "1.1.1.1" else ("1.1.1.1",),
            )

    def test_firewall_code_without_ip_is_explicit_and_not_invented(self):
        error = sql.sql_firewall_failure("40615 access denied")
        self.assertEqual(error.client_ips, ())
        self.assertIn("not reported", str(error))


class ProbeTests(unittest.TestCase):
    def test_firewall_diagnostics_stop_and_require_exact_ip_approval(self):
        for addresses, expected in (
            (("1.1.1.1",), "Confirm the SQL-reported IP"),
            ((IP,), "within the approved scope"),
            ((), "No unambiguous"),
            (("1.1.1.1", IP), "No unambiguous"),
        ):
            with self.subTest(addresses=addresses), mock.patch.object(sql.time, "sleep"):
                with mock.patch.object(sql, "run_command", side_effect=sql.SqlFirewallFailure(addresses)) as run:
                    with self.assertRaises(sql.ConnectionFailure) as raised:
                        sql.probe_sql("sqlcmd", credentials(), wait_seconds=0)
                    self.assertIn(expected, str(raised.exception))
                    self.assertEqual(run.call_count, 5 if addresses == (IP,) else 1)
                    self.assertNotIn("SQLCMDPASSWORD", run.call_args.kwargs["env"])

    def test_firewall_compares_observed_ip_to_entire_approved_range(self):
        for observed, expected in (
            ("8.8.8.8", "within the approved scope"),
            ("8.8.8.12", "within the approved scope"),
            ("8.8.8.15", "within the approved scope"),
            ("8.8.8.16", "outside the approved scope"),
            ("2606:4700:4700::1111", "outside the approved scope"),
        ):
            with self.subTest(observed=observed), mock.patch.object(sql.time, "sleep"):
                with mock.patch.object(sql, "run_command", side_effect=sql.SqlFirewallFailure([observed])) as run:
                    with self.assertRaises(sql.ConnectionFailure) as raised:
                        sql.probe_sql("sqlcmd", credentials(ipaddress="8.8.8.8-8.8.8.15"), wait_seconds=0)
                    self.assertIn(expected, str(raised.exception))
                    self.assertEqual(run.call_count, 5 if expected == "within the approved scope" else 1)

    def test_in_scope_firewall_propagation_retries_same_credentials_then_connects(self):
        value = credentials(ipaddress="8.8.8.8-8.8.8.15")
        with mock.patch.object(sql.time, "sleep") as sleep:
            with mock.patch.object(sql, "run_command", side_effect=[
                sql.SqlFirewallFailure(["8.8.8.12"]),
                sql.SqlFirewallFailure(["8.8.8.15"]),
                "AxDB|temporary_reader\n",
            ]) as run, redirect_stdout(io.StringIO()):
                sql.probe_sql("sqlcmd", value)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].args, run.call_args_list[-1].args)
        self.assertEqual(sleep.call_args_list, [mock.call(60)] * 3)

    def test_firewall_retry_stops_if_egress_leaves_approved_range(self):
        with mock.patch.object(sql.time, "sleep"):
            with mock.patch.object(sql, "run_command", side_effect=[
                sql.SqlFirewallFailure(["8.8.8.12"]),
                sql.SqlFirewallFailure(["8.8.8.16"]),
            ]) as run, redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(sql.ConnectionFailure, "outside the approved scope"):
                    sql.probe_sql("sqlcmd", credentials(ipaddress="8.8.8.8-8.8.8.15"), wait_seconds=0)
        self.assertEqual(run.call_count, 2)

    def test_expiry_is_rechecked_after_firewall_propagation_wait(self):
        value = credentials()
        def sleep(seconds):
            if seconds:
                value["sqljitexpiration"] = "2020-01-01T00:00:00Z"

        with mock.patch.object(sql.time, "sleep", side_effect=sleep):
            with mock.patch.object(sql, "run_command", side_effect=sql.SqlFirewallFailure([IP])) as run:
                with self.assertRaisesRegex(sql.ConnectionFailure, "expired"), redirect_stdout(io.StringIO()):
                    sql.probe_sql("sqlcmd", value, wait_seconds=0)
                run.assert_called_once()

    def test_password_only_in_child_environment_and_fixed_encrypted_probe(self):
        value = credentials()
        with mock.patch.dict(os.environ, {
            "SQLCMDPASSWORD": "parent-password", "SQLCMDINI": "untrusted.sql",
            "SQLCMDSERVER": "wrong-server", "OSQLPASSWORD": "old-password",
        }), mock.patch.object(sql.time, "sleep"), mock.patch.object(sql, "run_command") as run:
            def check(command, label, **kwargs):
                self.assertNotIn(value["sqljitpassword"], command)
                self.assertNotIn("-P", command)
                self.assertNotIn("-C", command)
                self.assertIn("-N", command)
                self.assertIn("-b", command)
                self.assertEqual(command[command.index("-Q") + 1], sql.PROBE)
                self.assertEqual(kwargs["env"]["SQLCMDPASSWORD"], value["sqljitpassword"])
                for key in ("SQLCMDINI", "SQLCMDSERVER", "OSQLPASSWORD"):
                    self.assertNotIn(key, kwargs["env"])
                return "AxDB | temporary_reader\n"

            run.side_effect = check
            sql.probe_sql("sqlcmd", value, wait_seconds=0)
            self.assertEqual(os.environ["SQLCMDPASSWORD"], "parent-password")
            self.assertNotIn("SQLCMDPASSWORD", run.call_args.kwargs["env"])

    def test_retries_same_credentials_only_for_login_propagation(self):
        value = credentials()
        with mock.patch.object(sql.time, "sleep"), mock.patch.object(sql, "run_command") as run:
            run.side_effect = [
                sql.ConnectionFailure("sqlcmd failed: 18456"),
                sql.ConnectionFailure("sqlcmd failed: SQL login failed"),
                "AxDB|temporary_reader\n",
            ]
            with redirect_stdout(io.StringIO()):
                sql.probe_sql("sqlcmd", value, wait_seconds=0)
            self.assertEqual(run.call_count, 3)
            self.assertEqual(run.call_args_list[0].args, run.call_args_list[-1].args)

    def test_retry_bound_and_non_login_failure(self):
        for message, count in (("18456", 3), ("TLS/certificate failure", 1)):
            with self.subTest(message=message), mock.patch.object(sql.time, "sleep"):
                with mock.patch.object(sql, "run_command", side_effect=sql.ConnectionFailure(message)) as run:
                    with self.assertRaises(sql.ConnectionFailure), redirect_stdout(io.StringIO()):
                        sql.probe_sql("sqlcmd", credentials(), wait_seconds=0)
                    self.assertEqual(run.call_count, count)

    def test_wrong_database_or_login_is_not_success(self):
        for output in ("OtherDB|temporary_reader", "AxDB|admin", "", "AxDB|temporary_reader\nextra"):
            with self.subTest(output=output), mock.patch.object(sql.time, "sleep"):
                with mock.patch.object(sql, "run_command", return_value=output):
                    with self.assertRaises(sql.ConnectionFailure):
                        sql.probe_sql("sqlcmd", credentials(), wait_seconds=0)

    def test_expired_credentials_never_start_sqlcmd(self):
        with mock.patch.object(sql.time, "sleep"), mock.patch.object(sql, "run_command") as run:
            with self.assertRaises(sql.ConnectionFailure):
                sql.probe_sql("sqlcmd", credentials(sqljitexpiration="2020-01-01T00:00:00Z"), wait_seconds=0)
            run.assert_not_called()


class PreflightTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(environment=URL, confirm_environment=URL, client_ip=IP, reason="Approved probe", role="Reader", table=None, top=50)
        values.update(changes)
        return argparse.Namespace(**values)

    def test_mismatched_approval_stops_before_commands(self):
        with mock.patch.object(sql, "run_command") as run:
            with self.assertRaises(sql.ConnectionFailure):
                sql.connect(self.args(confirm_environment="https://wrong.crm.dynamics.com"))
            run.assert_not_called()

    def test_ipv6_stops_before_commands_or_grant(self):
        with mock.patch.object(sql, "run_command") as run, mock.patch.object(sql, "request_credentials") as grant:
            with self.assertRaisesRegex(sql.ConnectionFailure, "IPv4"):
                sql.connect(self.args(client_ip="2606:4700:4700::1111"))
            run.assert_not_called()
            grant.assert_not_called()

    def test_current_odbc_help_passes_preflight_and_retains_tls_flags(self):
        value = credentials()
        org = {"OrgUrl": URL, "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "OnlineDev"}
        with mock.patch.object(sql.shutil, "which", side_effect=lambda name: name):
            with mock.patch.object(sql, "load_env"), mock.patch.object(sql, "_operation_context_str", return_value="context"):
                with mock.patch.object(sql, "run_command", side_effect=[
                    "Microsoft (R) SQL Server Command Line Tool\n[-N[s|m|o] Encrypt Connection]",
                    json.dumps(org), "AxDB|temporary_reader\n",
                ]) as run, mock.patch.object(sql, "request_credentials", return_value=value) as grant:
                    with mock.patch.object(sql.time, "sleep"), redirect_stdout(io.StringIO()):
                        sql.connect(self.args())
        grant.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("-N", command)
        self.assertNotIn("-No", command)
        self.assertNotIn("-C", command)
        self.assertEqual(value, {})

    def test_unsupported_sqlcmd_help_stops_before_grant(self):
        for help_text in (
            "sqlcmd (Go)\n-N Encrypt Connection",
            "SQL Server Command Line Tool\n-N",
            "SQL Server Command Line Tool\n-N[true|false|disable] Encrypt Connection",
        ):
            with self.subTest(help_text=help_text), mock.patch.object(sql.shutil, "which", side_effect=lambda name: name):
                with mock.patch.object(sql, "run_command", return_value=help_text) as run:
                    with mock.patch.object(sql, "request_credentials") as grant:
                        with self.assertRaisesRegex(sql.ConnectionFailure, "ODBC"):
                            sql.connect(self.args())
                run.assert_called_once()
                grant.assert_not_called()

    def test_preflight_must_succeed_before_grant(self):
        help_text = "SQL Server Command Line Tool\n-N Encrypt Connection"
        for org in (
            {"OrgUrl": URL, "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "Production"},
            {"OrgUrl": URL, "ErpDeploymentType": "OnlineDev"},
            {"OrgUrl": "https://wrong.crm.dynamics.com", "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "OnlineDev"},
        ):
            with self.subTest(org=org), mock.patch.object(sql.shutil, "which", side_effect=lambda x: x):
                with mock.patch.object(sql, "load_env"), mock.patch.object(sql, "_operation_context_str", return_value="context"):
                    with mock.patch.object(sql, "run_command", side_effect=[help_text, json.dumps(org)]):
                        with mock.patch.object(sql, "request_credentials") as grant, redirect_stdout(io.StringIO()):
                            with self.assertRaises(sql.ConnectionFailure):
                                sql.connect(self.args())
                            grant.assert_not_called()

    def test_success_clears_credentials_and_uses_confirmed_target(self):
        value = credentials()
        org = {"OrgUrl": URL, "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "OnlineDev"}
        with mock.patch.object(sql.shutil, "which", side_effect=lambda x: x):
            with mock.patch.object(sql, "load_env"), mock.patch.object(sql, "_operation_context_str", return_value="context"):
                with mock.patch.object(sql, "run_command", side_effect=[
                    "SQL Server Command Line Tool\n-N Encrypt Connection", json.dumps(org),
                ]):
                    with mock.patch.object(sql, "request_credentials", return_value=value) as grant:
                        with mock.patch.object(sql, "probe_sql") as probe, redirect_stdout(io.StringIO()) as output:
                            sql.connect(self.args())
        grant.assert_called_once_with("dataverse", URL, "context", "Approved probe", IP, "Reader")
        probe.assert_called_once()
        self.assertEqual(value, {})
        self.assertIn("Connected successfully", output.getvalue())
        self.assertNotIn("test-only-not-a-real-password", output.getvalue())

    def test_erp_sql_is_an_allowed_attribution_skill(self):
        sql._operation_context_str.__globals__["_validate_skill"]("erp-sql")

    def test_table_preview_uses_one_grant_and_clears_credentials_on_failure(self):
        value = credentials()
        org = {"OrgUrl": URL, "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "OnlineDev"}
        with mock.patch.object(sql.shutil, "which", side_effect=lambda name: name):
            with mock.patch.object(sql, "load_env"), mock.patch.object(sql, "_operation_context_str", return_value="context"):
                with mock.patch.object(sql, "run_command", side_effect=[
                    "SQL Server Command Line Tool\n-N Encrypt Connection", json.dumps(org),
                ]):
                    with mock.patch.object(sql, "request_credentials", return_value=value) as grant:
                        with mock.patch.object(sql, "probe_sql"), mock.patch.object(
                            sql, "read_table", side_effect=sql.ConnectionFailure("Read failed"),
                        ) as read, redirect_stdout(io.StringIO()):
                            with self.assertRaisesRegex(sql.ConnectionFailure, "Read failed"):
                                sql.connect(self.args(table="dbo.BATCH"))
        grant.assert_called_once()
        read.assert_called_once_with("sqlcmd", value, "dbo.BATCH", 50)
        self.assertEqual(value, {})

    def test_invalid_table_options_fail_before_any_commands(self):
        for changes in ({"table": "BATCH;DELETE"}, {"table": "BATCH", "top": 0}, {"table": "BATCH", "top": 101}):
            with self.subTest(changes=changes), mock.patch.object(sql, "run_command") as run:
                with self.assertRaises(sql.ConnectionFailure):
                    sql.connect(self.args(**changes))
                run.assert_not_called()


class TableReadTests(unittest.TestCase):
    def test_read_discovers_exact_schema_and_reports_count_preview_and_omissions(self):
        replies = [
            "dbo|BATCH|123\n",
            "RECID|bigint\nCAPTION|nvarchar\nSTATUS|int\nPARAMETERS|varbinary\nClientSecret|nvarchar\n",
            "20128\n",
            "1|A sample task|0\n",
        ]
        value = credentials()
        with mock.patch.object(sql, "execute_sql", side_effect=replies) as execute, redirect_stdout(io.StringIO()) as output:
            sql.read_table("sqlcmd", value, "dbo.BATCH", 50)
        statements = [call.args[2] for call in execute.call_args_list]
        self.assertIn("LOWER(s.name) = N'dbo'", statements[0])
        self.assertIn("LOWER(t.name) = N'batch'", statements[0])
        self.assertIn("c.object_id = 123", statements[1])
        self.assertIn("COUNT_BIG(*) FROM [dbo].[BATCH]", statements[2])
        self.assertIn("TOP (50) [RECID], [CAPTION], [STATUS]", statements[3])
        self.assertIn("ORDER BY [RECID]", statements[3])
        self.assertNotIn("ClientSecret", statements[3])
        self.assertNotIn("PARAMETERS", statements[3])
        self.assertIn("20128", output.getvalue())
        self.assertIn("1|A sample task|0", output.getvalue())
        self.assertIn("PARAMETERS, ClientSecret", output.getvalue())
        self.assertIn("not latest jobs", output.getvalue())
        self.assertTrue(all(call.args[1] is value for call in execute.call_args_list))

    def test_no_recid_and_empty_table_are_explicit(self):
        with mock.patch.object(sql, "execute_sql", side_effect=[
            "app|Clients|123\n", "ClientId|uniqueidentifier\n", "0\n", "",
        ]) as execute, redirect_stdout(io.StringIO()) as output:
            sql.read_table("sqlcmd", credentials(), "Clients", 10)
        self.assertNotIn("ORDER BY", execute.call_args.args[2])
        self.assertIn("no guaranteed ordering", output.getvalue())
        self.assertIn("(No rows returned.)", output.getvalue())

    def test_missing_ambiguous_and_malformed_metadata_stop_without_guessing(self):
        for reply in ("", "dbo|BATCH|123\nother|BATCH|456\n", "dbo|BATCH|123|extra", "dbo|BATCH|not-an-id"):
            with self.subTest(reply=reply), mock.patch.object(sql, "execute_sql", return_value=reply) as execute:
                with self.assertRaises(sql.ConnectionFailure):
                    sql.read_table("sqlcmd", credentials(), "BATCH", 50)
                execute.assert_called_once()

    def test_bad_identifiers_and_limits_are_rejected(self):
        for name in ("dbo.BATCH;DROP TABLE BATCH", "dbo.BATCH--", "db.dbo.BATCH", "BATCH\nGO", "$(SQLCMDPASSWORD)", "", "[BATCH]"):
            with self.subTest(name=name), mock.patch.object(sql, "execute_sql") as execute:
                with self.assertRaises(sql.ConnectionFailure):
                    sql.read_table("sqlcmd", credentials(), name, 50)
                execute.assert_not_called()

    def test_unsafe_columns_and_bad_count_are_not_read(self):
        for replies in (
            ["dbo|BATCH|123\n", "PARAMETERS|varbinary\nPassword|nvarchar\n"],
            ["dbo|BATCH|123\n", "RECID|bigint\n", "not a count\n"],
            ["dbo|BATCH|123\n", "unexpected|format|extra\n"],
        ):
            with self.subTest(replies=replies), mock.patch.object(sql, "execute_sql", side_effect=replies) as execute:
                with self.assertRaises(sql.ConnectionFailure), redirect_stdout(io.StringIO()):
                    sql.read_table("sqlcmd", credentials(), "BATCH", 50)
                self.assertEqual(execute.call_count, len(replies))

    def test_all_reads_share_propagation_retry_and_safe_output_flags(self):
        with mock.patch.object(sql.time, "sleep"), mock.patch.object(sql, "run_command", side_effect=[
            sql.SqlFirewallFailure([IP]), "123\n",
        ]) as run, redirect_stdout(io.StringIO()):
            self.assertEqual(sql.execute_sql("sqlcmd", credentials(), "SELECT COUNT_BIG(*) FROM [dbo].[BATCH];"), "123\n")
        self.assertEqual(run.call_count, 2)
        command = run.call_args.args[0]
        for flag in ("-N", "-b", "-h", "-W", "-x"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("-f") + 1], "o:65001")
        self.assertNotIn("-y", command)
        self.assertNotIn("-P", command)
        self.assertNotIn("SQLCMDPASSWORD", run.call_args.kwargs["env"])

    def test_sql_diagnostics_expose_codes_not_secret_text(self):
        for number, expected in (("208", "object not found"), ("229", "permission denied"), ("102", "syntax error")):
            secret = "do-not-print-this"
            failed = subprocess.CompletedProcess(["sqlcmd"], 1, b"", f"Msg {number}, Level 16, State 1\n{secret}".encode())
            with self.subTest(number=number), mock.patch.object(sql.subprocess, "run", return_value=failed):
                with self.assertRaises(sql.ConnectionFailure) as raised:
                    sql.run_command(["sqlcmd"], "sqlcmd", env={"SQLCMDPASSWORD": secret})
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn(secret, str(raised.exception))
        self.assertIn("incompatible", sql.diagnostic("Sqlcmd: The -h and the -y 0 options are mutually exclusive."))

    def test_successful_query_output_also_redacts_password(self):
        result = subprocess.CompletedProcess(["sqlcmd"], 0, b"value|test-secret\n", b"")
        with mock.patch.object(sql.subprocess, "run", return_value=result):
            output = sql.run_command(["sqlcmd"], "sqlcmd", env={"SQLCMDPASSWORD": "test-secret"})
        self.assertEqual(output, "value|<redacted>\n")

    def test_sql_utf8_survives_real_subprocess_boundary(self):
        expected = "1|caf\u00e9|\u6771\u4eac|\U0001f600\n"
        command = [
            sys.executable, "-c",
            f"import sys; sys.stdout.buffer.write(bytes.fromhex('{expected.encode('utf-8').hex()}'))",
        ]
        self.assertEqual(sql.run_command(command, "sqlcmd"), expected)

    def test_non_utf8_sql_output_fails_without_leaking_bytes(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                command = [
                    sys.executable, "-c",
                    f"import sys; sys.{stream}.buffer.write(b'private-test-value\\x82')",
                ]
                with self.assertRaisesRegex(sql.ConnectionFailure, "invalid UTF-8") as raised:
                    sql.run_command(command, "sqlcmd")
                self.assertNotIn("private-test-value", str(raised.exception))

    def test_execute_sql_requests_utf8_from_a_legacy_codepage_process(self):
        real_run = subprocess.run
        expected = "1|caf\u00e9\n"

        def launch_fake_sqlcmd(command, **kwargs):
            encoding = "utf-8" if "-f" in command and command[command.index("-f") + 1] == "o:65001" else "cp437"
            payload = expected.encode(encoding).hex()
            return real_run([
                sys.executable, "-c",
                f"import sys; sys.stdout.buffer.write(bytes.fromhex('{payload}'))",
            ], **kwargs)

        with mock.patch.object(sql.subprocess, "run", side_effect=launch_fake_sqlcmd):
            self.assertEqual(sql.execute_sql("sqlcmd", credentials(), "SELECT 1;"), expected)

    def test_cli_prints_unicode_preview_and_errors_from_legacy_stdout(self):
        expected = "caf\u00e9|\u6771\u4eac|\U0001f600"
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                driver = Path(directory) / "cli_output_test.py"
                driver.write_text(f"""
import sys
from unittest import mock

sys.path.insert(0, {str(SCRIPT.parent)!r})
import connect as sql

assert sys.stdout.encoding == "cp1252"
assert sys.stderr.encoding == "cp1252"
expected = {ascii(expected)}
sys.argv = [
    "connect.py", "--environment", {URL!r}, "--confirm-environment", {URL!r},
    "--client-ip", {IP!r}, "--reason", "Output regression test",
    "--role", "Reader", "--table", "dbo.BATCH", "--top", "1",
]

def local_connect(args):
    if {fail!r}:
        raise sql.ConnectionFailure(expected)
    with mock.patch.object(sql, "execute_sql", side_effect=[
        "dbo|BATCH|123\\n", "RECID|bigint\\nCAPTION|nvarchar\\n",
        "1\\n", "1|" + expected + "\\n",
    ]):
        sql.read_table("sqlcmd", {{}}, args.table, args.top)

with mock.patch.object(sql, "connect", side_effect=local_connect):
    sys.exit(sql.main())
""", encoding="ascii")
                result = subprocess.run(
                    [sys.executable, str(driver)], capture_output=True, timeout=30,
                    env={**os.environ, "PYTHONIOENCODING": "cp1252:strict", "PYTHONUTF8": "0"},
                )
                stdout = result.stdout.decode("utf-8")
                stderr = result.stderr.decode("utf-8")
                self.assertEqual(result.returncode, int(fail), stderr)
                if fail:
                    self.assertEqual(stderr.strip(), "ERROR: " + expected)
                    self.assertEqual(stdout, "")
                else:
                    self.assertIn("1|" + expected, stdout)
                    self.assertIn("Table: [dbo].[BATCH]", stdout)
                    self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()

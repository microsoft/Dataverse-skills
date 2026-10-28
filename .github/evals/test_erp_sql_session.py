"""Hermetic lifecycle tests and real local IPC tests; no live grants or SQL connections."""

from datetime import datetime, timedelta, timezone
import ctypes
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid


SCRIPTS = Path(__file__).resolve().parents[1] / "plugins" / "dataverse" / "skills" / "erp-sql" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import session as sessions
import session_ipc as ipc
import connect as sql

URL = "https://example.crm.dynamics.com"
IP = "8.8.8.8-8.8.8.15"
SECRET = "test-only-session-password"


def credentials():
    return {
        "servername": "example.database.windows.net", "databasename": "AxDB",
        "sqljitusername": "temporary_reader", "sqljitpassword": SECRET,
        "sqljitrole": "Reader", "ipaddress": IP,
        "sqljitexpiration": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }


def scope():
    return {"environment": URL, "role": "Reader", "client_ip": IP, "workspace": sessions.workspace()}


def request(operation="read", **changes):
    value = {"operation": operation, **scope()}
    if operation == "read":
        value.update(table="dbo.BATCH", top=10, waiting_jobs=False)
    value.update(changes)
    return value


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.credentials = credentials()
        self.session = sessions.Session("sqlcmd", self.credentials, scope(), uuid.uuid4().hex)

    def test_reads_reuse_same_credentials_and_redact_output(self):
        def read(tool, creds, table, top):
            self.assertIs(creds, self.credentials)
            self.assertIsInstance(sys.stdout, sessions.BoundedOutput)
            print(f"{table}|caf\u00e9|\u6771\u4eac|\U0001f600|")

        original_getvalue = sessions.BoundedOutput.getvalue

        def captured_output(buffer):
            # Inject the synthetic credential only into the in-memory redaction input.
            return original_getvalue(buffer) + SECRET

        with mock.patch.object(sql, "read_table", side_effect=read) as reads, mock.patch.object(
            sessions.BoundedOutput, "getvalue", new=captured_output,
        ):
            with mock.patch.object(sql, "request_credentials") as grant:
                first = self.session.handle(request())
                second = self.session.handle(request(table="dbo.BATCHJOB"))
        self.assertEqual(reads.call_count, 2)
        grant.assert_not_called()
        for result in (first, second):
            self.assertTrue(result["ok"])
            self.assertNotIn(SECRET, json.dumps(result))
            self.assertIn("<redacted>", result["output"])
        self.assertIn("dbo.BATCHJOB", second["output"])

    def test_waiting_jobs_reuses_existing_read(self):
        with mock.patch.object(sql, "read_table") as read:
            self.session.handle(request(table=None, waiting_jobs=True))
        read.assert_called_once_with("sqlcmd", self.credentials, "BATCHJOB", 10, waiting_only=True)

    def test_status_does_not_extend_idle_lifetime_or_return_credentials(self):
        before = self.session.last_read
        response = self.session.handle(request("status"))
        self.assertEqual(before, self.session.last_read)
        self.assertEqual(response["role"], "Reader")
        for text in (SECRET, "temporary_reader", "sqljitpassword"):
            self.assertNotIn(text, json.dumps(response))

    def test_close_releases_credentials_without_revocation_claim(self):
        response = self.session.handle(request("close"))
        self.assertIn("not revoked", response["output"])
        self.assertEqual(self.credentials, {})
        self.assertTrue(self.session.closed)

    def test_expiry_and_idle_fail_closed(self):
        for expired in (True, False):
            with self.subTest(expired=expired):
                value = credentials()
                session = sessions.Session("sqlcmd", value, scope(), uuid.uuid4().hex)
                if expired:
                    value["sqljitexpiration"] = "2020-01-01T00:00:00Z"
                else:
                    session.last_read -= sessions.IDLE_SECONDS + 1
                with mock.patch.object(sql, "read_table") as read:
                    with self.assertRaisesRegex(sql.ConnectionFailure, "expired"):
                        session.handle(request())
                read.assert_not_called()
                self.assertEqual(value, {})

    def test_no_scope_changes_unknown_operations_or_arbitrary_sql(self):
        invalid = [
            request(environment="https://other.crm.dynamics.com"),
            request(role="Writer"), request(client_ip="8.8.8.0/24"),
            request(workspace="another workspace"), request("grant"), request("password"),
            request("status", sql="SELECT 1"), request(operation=[]),
            request(table="BATCH;DELETE"), request(top=True), request(top=101),
            request(top=0), request(top="10"), request(waiting_jobs="true"),
            request(table=None), request(waiting_jobs=True),
        ]
        with mock.patch.object(sql, "read_table") as read:
            for value in invalid:
                with self.subTest(value=value), self.assertRaises(sql.ConnectionFailure):
                    self.session.handle(value)
        read.assert_not_called()

    def test_read_errors_do_not_extend_idle_lifetime(self):
        before = self.session.last_read
        with mock.patch.object(sql, "read_table", side_effect=sql.ConnectionFailure("SQL permission denied")):
            with self.assertRaisesRegex(sql.ConnectionFailure, "permission"):
                self.session.handle(request())
        self.assertEqual(before, self.session.last_read)

    def test_oversized_output_is_explicit_failure(self):
        with mock.patch.object(sessions, "RESPONSE_LIMIT", 10000):
            with mock.patch.object(sql, "read_table", side_effect=lambda *a: print("x" * 10000)):
                with self.assertRaisesRegex(sql.ConnectionFailure, "response limit"):
                    self.session.handle(request())

    def test_protocol_rejects_non_objects_invalid_utf8_and_bad_ids(self):
        for payload in (b"[]", b"null", b"\xff", b"{"):
            with self.subTest(payload=payload), self.assertRaises(sql.ConnectionFailure):
                sessions.decode(payload)
        for value in ("../other", "", "a" * 33, "Z" * 32, None):
            with self.subTest(value=value), self.assertRaises(ipc.IpcError):
                ipc.checked_session(value)

    def test_length_limit_checked_before_body_read(self):
        channel = mock.Mock()
        channel.read.return_value = struct.pack("!I", sessions.REQUEST_LIMIT + 1)
        with self.assertRaises(ipc.IpcError):
            ipc.receive(channel, sessions.REQUEST_LIMIT, time.monotonic() + 1)
        channel.read.assert_called_once()

    def test_split_frames_round_trip(self):
        class Channel:
            def __init__(self):
                self.data = bytearray()

            def write(self, data, deadline):
                self.data.extend(data[:3])
                return len(data[:3])

            def read(self, size, deadline):
                result = self.data[:min(size, 2)]
                del self.data[:len(result)]
                return bytes(result)

        channel = Channel()
        ipc.send(channel, b"example", 100, time.monotonic() + 1)
        self.assertEqual(ipc.receive(channel, 100, time.monotonic() + 1), b"example")

    def test_range_suggestion_is_bounded_and_separate_from_grants(self):
        with mock.patch.object(sql, "request_credentials") as grant:
            result = sql.suggest_ip_range("4.213.232.53")
        self.assertEqual(result["suggested_range"], "4.213.232.48-4.213.232.55")
        self.assertEqual(result["address_count"], 8)
        self.assertIn("not a discovered NAT pool", result["warning"])
        self.assertIn("approve", result["warning"])
        grant.assert_not_called()
        for address in ("2606:4700:4700::1111", "10.0.0.1", IP):
            with self.subTest(address=address), self.assertRaises(sql.ConnectionFailure):
                sql.suggest_ip_range(address)

    def test_suggest_range_cannot_be_combined_with_grant_arguments(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "connect.py"), "--suggest-range",
             "--environment", URL, "--confirm-environment", URL,
             "--client-ip", IP, "--reason", "No grant permitted", "--role", "Reader"],
            capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"--suggest-range requires --discover-ip", result.stderr)

    def test_listener_failure_precedes_grant(self):
        args = mock.Mock(environment=URL, role="Reader", client_ip=IP, session=uuid.uuid4().hex)
        with mock.patch.object(ipc, "listen", side_effect=ipc.IpcError("Permission denied")):
            with mock.patch.object(sql, "sql_access") as access:
                with self.assertRaises(ipc.IpcError):
                    sessions.serve(args)
                access.assert_not_called()

    def test_expiry_during_read_does_not_return_rows(self):
        def expire(*args):
            print("These rows must not be returned.")
            self.credentials["sqljitexpiration"] = "2020-01-01T00:00:00Z"

        with mock.patch.object(sql, "read_table", side_effect=expire):
            with self.assertRaisesRegex(sql.ConnectionFailure, "expired"):
                self.session.handle(request())


class LocalTransportTests(unittest.TestCase):
    def test_real_transport_frames_and_duplicate_listener(self):
        session_id = uuid.uuid4().hex
        listener = ipc.listen(session_id)
        errors = []

        def server():
            try:
                channel = listener.accept(5)
                try:
                    message = ipc.receive(channel, 512000, time.monotonic() + 5)
                    ipc.send(channel, message, 512000, time.monotonic() + 5)
                    self.assertEqual(ipc.receive(channel, 16, time.monotonic() + 5), b"received")
                finally:
                    channel.close()
            except Exception as error:
                errors.append(error)

        try:
            with self.assertRaises(ipc.IpcError):
                ipc.listen(session_id)
            thread = threading.Thread(target=server)
            thread.start()
            channel = ipc.client(session_id)
            try:
                payload = "caf\u00e9|\u6771\u4eac|\U0001f600".encode("utf-8") * 10000
                ipc.send(channel, payload, 512000, time.monotonic() + 5)
                self.assertEqual(ipc.receive(channel, 512000, time.monotonic() + 5), payload)
                ipc.send(channel, b"received", 16, time.monotonic() + 5)
            finally:
                channel.close()
            thread.join(10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
        finally:
            listener.close()

    def test_idle_accept_and_missing_session_are_bounded(self):
        listener = ipc.listen(uuid.uuid4().hex)
        try:
            with self.assertRaises(TimeoutError):
                listener.accept(0.03)
        finally:
            listener.close()
        with self.assertRaises((ipc.IpcError, OSError)):
            ipc.client(uuid.uuid4().hex, timeout=0.1)

    @unittest.skipUnless(os.name == "nt", "Windows pipe permissions")
    def test_pipe_dacl_is_protected_and_allows_only_current_user(self):
        session_id = uuid.uuid4().hex
        listener = ipc.listen(session_id)
        api = listener.api
        descriptor = ctypes.c_void_p()
        expected_descriptor = ctypes.c_void_p()
        text = api.w.LPWSTR()
        expected_text = api.w.LPWSTR()
        get_security = api.advapi.GetSecurityInfo
        get_security.restype = api.w.DWORD
        get_security.argtypes = [
            api.w.HANDLE, ctypes.c_int, api.w.DWORD,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        to_string = api.advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
        to_string.restype = api.w.BOOL
        to_string.argtypes = [
            ctypes.c_void_p, api.w.DWORD, api.w.DWORD,
            ctypes.POINTER(api.w.LPWSTR), ctypes.c_void_p,
        ]
        try:
            self.assertEqual(get_security(listener.handle, 6, 4, None, None, None, None, ctypes.byref(descriptor)), 0)
            self.assertTrue(to_string(descriptor, 1, 4, ctypes.byref(text), None))
            # Canonicalize both descriptors: Windows can render a numeric SID as an alias.
            self.assertTrue(api.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"D:P(A;;FA;;;{api.sid})", 1, ctypes.byref(expected_descriptor), None,
            ))
            self.assertTrue(to_string(expected_descriptor, 1, 4, ctypes.byref(expected_text), None))
            self.assertEqual(text.value, expected_text.value)
        finally:
            if expected_text:
                api.kernel.LocalFree(ctypes.cast(expected_text, ctypes.c_void_p))
            if expected_descriptor:
                api.kernel.LocalFree(expected_descriptor)
            if text:
                api.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
            if descriptor:
                api.kernel.LocalFree(descriptor)
            listener.close()

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_unix_private_directory_and_socket(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            with mock.patch.object(ipc.tempfile, "gettempdir", return_value=directory):
                listener = ipc.listen(uuid.uuid4().hex)
                try:
                    self.assertEqual(listener.path.parent.stat().st_mode & 0o777, 0o700)
                    self.assertEqual(listener.path.stat().st_mode & 0o777, 0o600)
                    os.chmod(listener.path.parent, 0o755)
                    with self.assertRaises(ipc.IpcError):
                        ipc.client(listener.path.stem)
                finally:
                    listener.close()

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_unix_symlink_directory_is_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as directory:
            actual = Path(directory) / "actual"
            actual.mkdir(mode=0o700)
            (Path(directory) / f"dvsql-{os.getuid()}").symlink_to(actual, target_is_directory=True)
            with mock.patch.object(ipc.tempfile, "gettempdir", return_value=directory):
                with self.assertRaises(ipc.IpcError):
                    ipc.listen(uuid.uuid4().hex)


class ProcessReuseTests(unittest.TestCase):
    def test_owner_exits_and_clears_credentials_on_idle_or_expiry(self):
        for idle in (True, False):
            with self.subTest(idle=idle):
                driver = f"""
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
sys.path.insert(0, {str(SCRIPTS)!r})
import session

if {idle!r}:
    session.IDLE_SECONDS = 0.1

@contextmanager
def access(args):
    credentials = {{
        "sqljitpassword": {SECRET!r},
        "sqljitexpiration": (datetime.now(timezone.utc) + timedelta(seconds={60 if idle else 0.2})).isoformat(),
    }}
    try:
        yield "sqlcmd", credentials
    finally:
        credentials.clear()
        print("TEST_CREDENTIALS_CLEARED=" + str(not credentials), flush=True)

session.sql.sql_access = access
sys.exit(session.main())
"""
                session_id = uuid.uuid4().hex
                common = ["--session", session_id, "--environment", URL, "--role", "Reader", "--client-ip", IP]
                result = subprocess.run(
                    [sys.executable, "-", "start", *common, "--confirm-environment", URL, "--reason", "Hermetic test"],
                    input=driver.encode("ascii"), capture_output=True, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                self.assertIn(b'"ready": true', result.stdout)
                self.assertIn(b"SQL session ended", result.stdout)
                self.assertIn(b"TEST_CREDENTIALS_CLEARED=True", result.stdout)
                self.assertNotIn(SECRET.encode(), result.stdout + result.stderr)
                with self.assertRaises((ipc.IpcError, OSError)):
                    ipc.client(session_id, timeout=0.1)

    def test_two_cli_reads_use_one_grant_then_close(self):
        with tempfile.TemporaryDirectory() as directory:
            driver = f"""
import sys
import json
from datetime import datetime, timedelta, timezone
sys.path.insert(0, {str(SCRIPTS)!r})
import session
sql = session.sql
sql.shutil.which = lambda name: name
sql.load_env = lambda: None
sql._operation_context_str = lambda skill: "test-context"
original_probe = sql.probe_sql
sql.probe_sql = lambda tool, credentials: original_probe(tool, credentials, wait_seconds=0)

def fake_run(command, label, **kwargs):
    if label == "sqlcmd variant check":
        return "SQL Server Command Line Tool\\n-N[s|m|o] Encrypt Connection"
    if label == "Dataverse environment check":
        return json.dumps({{"OrgUrl": {URL!r}, "ErpUrl": "https://erp.example.com", "ErpDeploymentType": "OnlineDev"}})
    if label == "Dataverse JIT request":
        print("TEST_GRANT_REQUESTED", flush=True)
        return json.dumps({{
            "servername": "example.database.windows.net", "databasename": "AxDB",
            "sqljitusername": "temporary_reader", "sqljitpassword": {SECRET!r},
            "sqljitrole": "Reader", "ipaddress": {IP!r},
            "sqljitexpiration": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }})
    statement = command[-1]
    if statement == sql.PROBE:
        return "AxDB|temporary_reader\\n"
    if "sys.tables" in statement:
        table = "BATCHJOB" if "batchjob" in statement else "BATCH"
        return "dbo|" + table + "|123\\n"
    if "sys.columns" in statement:
        return "RECID|bigint\\nCAPTION|nvarchar\\nSTATUS|int\\n"
    if "COUNT_BIG" in statement:
        return "1\\n"
    return "1|caf\\u00e9-\\u6771\\u4eac-\\U0001f600|0|" + {SECRET!r} + "\\n"

sql.run_command = fake_run
sys.exit(session.main())
"""
            session_id = uuid.uuid4().hex
            common = ["--session", session_id, "--environment", URL, "--role", "Reader", "--client-ip", IP]
            process = subprocess.Popen(
                [sys.executable, "-u", "-", "start", *common, "--confirm-environment", URL, "--reason", "Hermetic test"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=directory,
                env={**os.environ, "PYTHONIOENCODING": "cp1252:strict"},
            )
            lines = queue.Queue()
            seen = []

            def collect():
                for line in process.stdout:
                    lines.put(line)

            reader = threading.Thread(target=collect, daemon=True)
            reader.start()
            try:
                process.stdin.write(driver.encode("ascii"))
                process.stdin.close()
                deadline = time.monotonic() + 15
                while True:
                    line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
                    seen.append(line)
                    if b'"ready": true' in line:
                        break
                for table in ("dbo.BATCH", "dbo.BATCHJOB"):
                    result = subprocess.run(
                        [sys.executable, str(SCRIPTS / "session.py"), "read", *common, "--table", table, "--top", "1"],
                        cwd=directory, capture_output=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                    self.assertIn("caf\u00e9-\u6771\u4eac-\U0001f600", result.stdout.decode("utf-8"))
                    self.assertNotIn(SECRET.encode(), result.stdout + result.stderr)
                mismatched = common.copy()
                mismatched[mismatched.index("--role") + 1] = "Writer"
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "session.py"), "status", *mismatched],
                    cwd=directory, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 1)
                self.assertIn(b"does not match", result.stderr)
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "session.py"), "status", *common],
                    cwd=directory, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(json.loads(result.stdout)["session"], session_id)
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "session.py"), "close", *common],
                    cwd=directory, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                process.wait(timeout=10)
                reader.join(5)
                while not lines.empty():
                    seen.append(lines.get_nowait())
                stderr = process.stderr.read()
                self.assertEqual(process.returncode, 0, stderr.decode("utf-8"))
                self.assertEqual(b"".join(seen).count(b"TEST_GRANT_REQUESTED"), 1)
                self.assertNotIn(SECRET.encode(), b"".join(seen) + stderr)
                self.assertEqual(stderr, b"")
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "session.py"), "status", *common],
                    cwd=directory, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(SECRET.encode(), result.stdout + result.stderr)
            finally:
                process.stdin.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                reader.join(5)
                process.stdout.close()
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()

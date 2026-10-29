"""Memory-only ERP SQL sessions: start in a dedicated process, then read/status/close."""

import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

import connect as sql
import session_ipc as ipc


REQUEST_LIMIT = 4096
RESPONSE_LIMIT = 2 * 1024 * 1024
READ_TIMEOUT = 1800  # Four SQL commands, each with the existing bounded retries.
IDLE_SECONDS = 15 * 60


def workspace():
    return os.path.normcase(str(Path.cwd().resolve()))


def binding(args):
    return {
        "environment": sql.environment_url(args.environment),
        "role": args.role,
        "client_ip": sql.canonical_ip_scope(args.client_ip),
        "workspace": workspace(),
    }


def decode(payload):
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise sql.ConnectionFailure("Invalid local session JSON; payload withheld.") from None
    if not isinstance(value, dict):
        raise sql.ConnectionFailure("Local session request must be a JSON object.")
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=True).encode("ascii")


class BoundedOutput(io.StringIO):
    def __init__(self):
        super().__init__()
        self.size = 0

    def write(self, text):
        # Bound the JSON-escaped result, not just its number of Unicode characters.
        self.size += len(json.dumps(text, ensure_ascii=True))
        if self.size > RESPONSE_LIMIT - 8192:
            raise sql.ConnectionFailure("Preview exceeds the session response limit; request fewer rows.")
        return super().write(text)


class Session:
    def __init__(self, sqlcmd, credentials, scope, session_id):
        self.sqlcmd = sqlcmd
        self.credentials = credentials
        self.scope = scope
        self.session_id = session_id
        self.last_read = time.monotonic()
        self.closed = False

    def remaining(self):
        try:
            expires = sql.expiration(self.credentials)
        except sql.ConnectionFailure:
            return 0
        return max(0, min(
            (expires - datetime.now(timezone.utc)).total_seconds(),
            IDLE_SECONDS - (time.monotonic() - self.last_read),
        ))

    def close(self):
        self.credentials.clear()
        self.closed = True

    def handle(self, request):
        if self.closed or self.remaining() <= 0:
            self.close()
            raise sql.ConnectionFailure("SQL session expired or was idle for 15 minutes; obtain fresh approval.")
        base = {"operation", "environment", "role", "client_ip", "workspace"}
        operation = request.get("operation")
        if not isinstance(operation, str):
            raise sql.ConnectionFailure("Session operation must be a string.")
        allowed = base | ({"table", "top", "waiting_jobs"} if operation == "read" else set())
        if set(request) != allowed or operation not in {"read", "status", "close"}:
            raise sql.ConnectionFailure("Unsupported session operation or fields; arbitrary SQL is not accepted.")
        if any(request.get(key) != value for key, value in self.scope.items()):
            raise sql.ConnectionFailure("Session environment, role, IP scope, or workspace does not match; no grant requested.")
        if operation == "close":
            self.close()
            return {"ok": True, "output": "Local SQL session closed; the server-side grant is not revoked."}
        if operation == "status":
            return {
                "ok": True, "session": self.session_id, **self.scope,
                "expires": sql.expiration(self.credentials).isoformat(),
                "remaining_seconds": int(self.remaining()),
            }
        table, top, waiting = request["table"], request["top"], request["waiting_jobs"]
        if type(top) is not int or not 1 <= top <= 100 or type(waiting) is not bool:
            raise sql.ConnectionFailure("Session reads require a limit of 1-100 and a boolean waiting-jobs flag.")
        if waiting:
            if table is not None:
                raise sql.ConnectionFailure("Waiting-jobs cannot be combined with a table.")
        elif not isinstance(table, str):
            raise sql.ConnectionFailure("A table is required for this session read.")
        else:
            sql.table_parts(table)
        with BoundedOutput() as output, redirect_stdout(output):
            if waiting:
                sql.read_table(self.sqlcmd, self.credentials, "BATCHJOB", top, waiting_only=True)
            else:
                sql.read_table(self.sqlcmd, self.credentials, table, top)
            sql.expiration(self.credentials)
            text = output.getvalue().replace(self.credentials["sqljitpassword"], "<redacted>")
        self.last_read = time.monotonic()
        return {"ok": True, "output": text}


def serve(args):
    scope = binding(args)
    session_id = args.session or uuid.uuid4().hex
    # Bind before the grant, so unsupported/denied/duplicate endpoints cannot create access.
    listener = ipc.listen(session_id)
    session = None
    try:
        with sql.sql_access(args) as (sqlcmd, credentials):
            session = Session(sqlcmd, credentials, scope, session_id)
            print(json.dumps({
                "ready": True, "session": session_id, "pid": os.getpid(),
                **scope, "expires": sql.expiration(credentials).isoformat(),
                "idle_seconds": IDLE_SECONDS,
            }), flush=True)
            while not session.closed and session.remaining() > 0:
                try:
                    channel = listener.accept(min(1, session.remaining()))
                except TimeoutError:
                    continue
                try:
                    deadline = time.monotonic() + min(5, session.remaining())
                    try:
                        request = decode(ipc.receive(channel, REQUEST_LIMIT, deadline))
                        response = session.handle(request)
                    except sql.ConnectionFailure as error:
                        response = {"ok": False, "error": str(error)}
                    payload = encode(response)
                    # Preserve the final password redaction even on error/status paths.
                    password = credentials.get("sqljitpassword")
                    if password:
                        escaped = json.dumps(password, ensure_ascii=True)[1:-1].encode("ascii")
                        payload = payload.replace(escaped, b"<redacted>")
                    ipc.send(channel, payload, RESPONSE_LIMIT, time.monotonic() + 5)
                    # DisconnectNamedPipe discards unread data: wait for the client to consume it.
                    if ipc.receive(channel, 16, time.monotonic() + 5) != b"received":
                        raise ipc.IpcError("Invalid local session response acknowledgment.")
                except (ipc.IpcError, OSError, TimeoutError):
                    print("Local session request interrupted or invalid; payload withheld. No grant was retried.", file=sys.stderr, flush=True)
                finally:
                    channel.close()
            print("SQL session ended; local credentials released. The server-side grant is not revoked.", flush=True)
    finally:
        if session is not None:
            session.close()
        listener.close()


def request(args):
    data = {"operation": args.command, **binding(args)}
    if args.command == "read":
        if args.table:
            sql.table_parts(args.table)
        data.update(table=args.table, top=args.top, waiting_jobs=args.waiting_jobs)
    channel = ipc.client(args.session)
    try:
        ipc.send(channel, encode(data), REQUEST_LIMIT, time.monotonic() + 5)
        response = decode(ipc.receive(channel, RESPONSE_LIMIT, time.monotonic() + READ_TIMEOUT))
        ipc.send(channel, b"received", 16, time.monotonic() + 5)
    finally:
        channel.close()
    if response.get("ok") is not True:
        error = response.get("error")
        raise sql.ConnectionFailure(error if isinstance(error, str) else "SQL session failed; no grant requested.")
    if isinstance(response.get("output"), str):
        print(response["output"], end="" if response["output"].endswith("\n") else "\n")
    else:
        print(json.dumps(response, ensure_ascii=True))


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    sys.stderr.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("start", "read", "status", "close"):
        command = commands.add_parser(name)
        command.add_argument("--session", required=name != "start")
        command.add_argument("--environment", required=True)
        command.add_argument("--role", choices=("Reader", "Writer"), required=True)
        command.add_argument("--client-ip", required=True, help="Previously approved public IPv4 scope")
        if name == "start":
            command.add_argument("--confirm-environment", required=True)
            command.add_argument("--reason", required=True)
            command.set_defaults(table=None, waiting_jobs=False, top=50)
        elif name == "read":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--table")
            selection.add_argument("--waiting-jobs", action="store_true")
            command.add_argument("--top", type=int, choices=range(1, 101), default=50, metavar="1-100")
    args = parser.parse_args()
    try:
        if args.session:
            ipc.checked_session(args.session)
        if args.command == "start":
            serve(args)
        else:
            request(args)
    except (sql.ConnectionFailure, ipc.IpcError, OSError, ValueError) as error:
        # OSError messages can include local paths; don't echo transport/system payloads.
        detail = str(error) if isinstance(error, (sql.ConnectionFailure, ipc.IpcError)) else "Local session I/O or configuration failed; no automatic retry or new grant."
        print(f"ERROR: {detail}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("SQL session interrupted; local credentials released.", file=sys.stderr)
        return 130
    return 0


def interrupt(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupt)
    sys.exit(main())

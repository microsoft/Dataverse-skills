"""Local, same-user byte streams for the ERP SQL session protocol. No TCP or pickle."""

import ctypes
import os
from pathlib import Path
import re
import socket
import stat
import struct
import tempfile
import time


class IpcError(RuntimeError):
    """A safe local-transport diagnostic without request or response content."""


def checked_session(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise IpcError("Session ID must be 32 lowercase hexadecimal characters.")
    return value


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Local session communication timed out.")
    return seconds


def receive(channel, limit, deadline):
    header = _read_exact(channel, 4, deadline)
    size = struct.unpack("!I", header)[0]
    if not 0 < size <= limit:
        raise IpcError("Invalid or oversized local session message.")
    return _read_exact(channel, size, deadline)


def _read_exact(channel, size, deadline):
    chunks = bytearray()
    while len(chunks) < size:
        chunk = channel.read(size - len(chunks), deadline)
        if not chunk:
            raise IpcError("Local session connection closed before the response completed.")
        chunks.extend(chunk)
    return bytes(chunks)


def send(channel, payload, limit, deadline):
    if not 0 < len(payload) <= limit:
        raise IpcError("Invalid or oversized local session message.")
    data = struct.pack("!I", len(payload)) + payload
    offset = 0
    while offset < len(data):
        written = channel.write(data[offset:], deadline)
        if written <= 0:
            raise IpcError("Local session connection closed while writing.")
        offset += written


def _unix_directory():
    directory = Path(tempfile.gettempdir()) / f"dvsql-{os.getuid()}"
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise IpcError("SQL session directory must be owned by this user with mode 0700, without symlinks.")
    return directory


class UnixChannel:
    def __init__(self, stream):
        self.stream = stream

    def read(self, size, deadline):
        self.stream.settimeout(remaining(deadline))
        return self.stream.recv(size)

    def write(self, data, deadline):
        self.stream.settimeout(remaining(deadline))
        return self.stream.send(data)

    def close(self):
        self.stream.close()


class UnixListener:
    def __init__(self, session):
        self.path = _unix_directory() / (checked_session(session) + ".sock")
        self.stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.bound = False
        try:
            self.stream.bind(str(self.path))
            self.bound = True
            os.chmod(self.path, 0o600)
            self.stream.listen(1)
        except OSError:
            self.close()
            raise IpcError("Cannot create SQL session socket; choose a fresh session ID and check local permissions.") from None

    def accept(self, timeout):
        self.stream.settimeout(timeout)
        stream, _ = self.stream.accept()
        return UnixChannel(stream)

    def close(self):
        self.stream.close()
        if self.bound:
            self.path.unlink(missing_ok=True)
            self.bound = False


def _unix_client(session, timeout):
    path = _unix_directory() / (checked_session(session) + ".sock")
    info = path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise IpcError("SQL session endpoint is not a private socket owned by this user.")
    stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        stream.settimeout(timeout)
        stream.connect(str(path))
    except OSError:
        stream.close()
        raise
    return UnixChannel(stream)


class WindowsApi:
    """Small explicit Win32 binding; imported lazily so other platforms need no Windows packages."""

    def __init__(self):
        from ctypes import wintypes as w

        self.w = w
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        handle, dword, pointer = w.HANDLE, w.DWORD, ctypes.c_void_p
        signatures = {
            "GetCurrentProcess": (handle, []),
            "OpenProcess": (handle, [dword, w.BOOL, dword]),
            "GetNamedPipeServerProcessId": (w.BOOL, [handle, ctypes.POINTER(dword)]),
            "CloseHandle": (w.BOOL, [handle]),
            "LocalFree": (pointer, [pointer]),
            "CreateNamedPipeW": (handle, [w.LPCWSTR, dword, dword, dword, dword, dword, dword, pointer]),
            "ConnectNamedPipe": (w.BOOL, [handle, pointer]),
            "DisconnectNamedPipe": (w.BOOL, [handle]),
            "CreateFileW": (handle, [w.LPCWSTR, dword, dword, pointer, dword, dword, handle]),
            "SetNamedPipeHandleState": (w.BOOL, [handle, ctypes.POINTER(dword), pointer, pointer]),
            "ReadFile": (w.BOOL, [handle, pointer, dword, ctypes.POINTER(dword), pointer]),
            "WriteFile": (w.BOOL, [handle, pointer, dword, ctypes.POINTER(dword), pointer]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.kernel, name)
            function.restype, function.argtypes = result, arguments
        for name, result, arguments in (
            ("OpenProcessToken", w.BOOL, [handle, dword, ctypes.POINTER(handle)]),
            ("GetTokenInformation", w.BOOL, [handle, ctypes.c_int, pointer, dword, ctypes.POINTER(dword)]),
            ("ConvertSidToStringSidW", w.BOOL, [pointer, ctypes.POINTER(w.LPWSTR)]),
            ("ConvertStringSecurityDescriptorToSecurityDescriptorW", w.BOOL, [w.LPCWSTR, dword, ctypes.POINTER(pointer), pointer]),
        ):
            function = getattr(self.advapi, name)
            function.restype, function.argtypes = result, arguments
        self.sid = self._current_sid()

    def _current_sid(self, process=None):
        token = self.w.HANDLE()
        if not self.advapi.OpenProcessToken(process or self.kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise IpcError("Cannot inspect the current Windows user for SQL session isolation.")
        try:
            size = self.w.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not size.value:
                raise IpcError("Cannot determine the current Windows user.")
            buffer = ctypes.create_string_buffer(size.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise IpcError("Cannot read the current Windows user identity.")
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            text = self.w.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise IpcError("Cannot encode the current Windows user identity.")
            try:
                return text.value
            finally:
                self.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))
        finally:
            self.kernel.CloseHandle(token)

    def name(self, session):
        return rf"\\.\pipe\dataverse-erp-sql-{self.sid}-{checked_session(session)}"

    def check_server(self, handle):
        pid = self.w.DWORD()
        if not self.kernel.GetNamedPipeServerProcessId(handle, ctypes.byref(pid)):
            raise IpcError("Cannot verify the SQL session server identity.")
        process = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not process:
            raise IpcError("Cannot verify the SQL session server owner.")
        try:
            if self._current_sid(process) != self.sid:
                raise IpcError("SQL session server is not running as the current user.")
        finally:
            self.kernel.CloseHandle(process)

    def create(self, session):
        class SecurityAttributes(ctypes.Structure):
            _fields_ = [
                ("length", self.w.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", self.w.BOOL),
            ]

        descriptor = ctypes.c_void_p()
        # Never use the default pipe DACL: it can allow Everyone to read.
        if not self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            f"D:P(A;;GA;;;{self.sid})", 1, ctypes.byref(descriptor), None,
        ):
            raise IpcError("Cannot create the SQL session's current-user-only pipe permissions.")
        try:
            attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
            handle = self.kernel.CreateNamedPipeW(
                self.name(session), 0x00000003 | 0x00080000,  # duplex, first instance only
                0x00000001 | 0x00000008,  # byte mode, nonblocking, reject remote clients
                1, 65536, 65536, 0, ctypes.byref(attributes),
            )
        finally:
            self.kernel.LocalFree(descriptor)
        if handle == ctypes.c_void_p(-1).value:
            raise IpcError("Cannot create SQL session pipe; choose a fresh ID and check local permissions.")
        return handle


class WindowsChannel:
    def __init__(self, api, handle, *, server=False):
        self.api, self.handle, self.server = api, handle, server

    def read(self, size, deadline):
        buffer = ctypes.create_string_buffer(min(size, 65536))
        count = self.api.w.DWORD()
        while True:
            remaining(deadline)
            if self.api.kernel.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(count), None):
                if count.value:
                    return buffer.raw[:count.value]
            elif ctypes.get_last_error() != 232:  # no data yet on a nonblocking pipe
                raise IpcError("SQL session pipe read failed or the session has ended.")
            time.sleep(min(0.01, remaining(deadline)))

    def write(self, data, deadline):
        data = data[:65536]
        count = self.api.w.DWORD()
        while True:
            remaining(deadline)
            if not self.api.kernel.WriteFile(self.handle, data, len(data), ctypes.byref(count), None):
                raise IpcError("SQL session pipe write failed or the session has ended.")
            if count.value:
                return count.value
            time.sleep(min(0.01, remaining(deadline)))

    def close(self):
        if self.server:
            self.api.kernel.DisconnectNamedPipe(self.handle)
        else:
            self.api.kernel.CloseHandle(self.handle)


class WindowsListener:
    def __init__(self, session):
        self.api = WindowsApi()
        self.handle = self.api.create(session)

    def accept(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining(deadline)
            if self.api.kernel.ConnectNamedPipe(self.handle, None):
                return WindowsChannel(self.api, self.handle, server=True)
            error = ctypes.get_last_error()
            if error == 535:  # already connected
                return WindowsChannel(self.api, self.handle, server=True)
            if error == 232:  # previous client disconnected before accept
                self.api.kernel.DisconnectNamedPipe(self.handle)
            elif error != 536:  # listening, no client yet
                raise IpcError("SQL session pipe accept failed.")
            time.sleep(min(0.01, remaining(deadline)))

    def close(self):
        self.api.kernel.CloseHandle(self.handle)


def _windows_client(session, timeout):
    api = WindowsApi()
    deadline = time.monotonic() + timeout
    while True:
        remaining(deadline)
        # Identification-only SQOS prevents a pipe server from impersonating the caller.
        handle = api.kernel.CreateFileW(api.name(session), 0xC0000000, 0, None, 3, 0x00110000, None)
        if handle != ctypes.c_void_p(-1).value:
            break
        if ctypes.get_last_error() != 231:  # busy: serialize requests, with a bounded wait
            raise IpcError("SQL session is unavailable or access was denied; no new grant was requested.")
        time.sleep(min(0.01, remaining(deadline)))
    try:
        api.check_server(handle)
        mode = api.w.DWORD(1)  # byte mode, nonblocking
        if not api.kernel.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
            raise IpcError("Cannot configure the SQL session pipe.")
    except (IpcError, OSError):
        api.kernel.CloseHandle(handle)
        raise
    return WindowsChannel(api, handle)


def listen(session):
    checked_session(session)
    if os.name == "nt":
        return WindowsListener(session)
    return UnixListener(session)


def client(session, timeout=5):
    checked_session(session)
    if os.name == "nt":
        return _windows_client(session, timeout)
    return _unix_client(session, timeout)

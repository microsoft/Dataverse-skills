"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth priority:
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) — non-interactive
  2. Device code flow — interactive on first login, silent refresh thereafter

Token caching:
  - Service principal: in-memory (tokens are short-lived, no persistent cache needed)
  - Device code: OS credential store (Windows Credential Manager, macOS Keychain,
    Linux libsecret) via TokenCachePersistenceOptions. An AuthenticationRecord is
    persisted alongside the token cache so that new processes can silently refresh
    without re-prompting the user.

Functions:
  load_env()            — loads .env into os.environ
  get_client(skill)     — returns a DataverseClient with plugin attribution
  get_token(scope=None) — returns a raw access token string
  get_plugin_headers(skill, token) — returns headers dict for raw Web API calls

Usage:
    # PREFERRED — SDK with plugin attribution:
    from auth import get_client
    client = get_client("dv-data")

    # Raw Web API only (forms, views, $ref, $apply):
    from auth import get_token, get_plugin_headers
    headers = get_plugin_headers("dv-metadata", get_token())

Reads from .env in the repo root (parent of scripts/) or current working directory:
    DATAVERSE_URL      — required
    TENANT_ID          — required
    CLIENT_ID          — optional, enables service principal auth
    CLIENT_SECRET      — optional, enables service principal auth
"""

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

# AuthenticationRecord is persisted here so new processes skip device code flow
_AUTH_RECORD_PATH = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / ".IdentityService" / "dataverse_cli_auth_record.json"


def load_env():
    """Load key=value pairs from .env into os.environ (does not overwrite existing vars).

    Searches for .env in two locations (first match wins):
      1. The repo root (parent of the directory containing this script)
      2. The current working directory
    This ensures ``cd scripts && python auth.py`` works the same as
    ``python scripts/auth.py`` from the repo root.
    """
    script_dir = Path(__file__).resolve().parent
    candidates = [script_dir.parent / ".env", Path(".env")]
    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is not None:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_credential = None


def _get_credential():
    """
    Return an Azure Identity TokenCredential, creating one on first call.

    The credential is cached for the lifetime of the process. Uses
    ClientSecretCredential when CLIENT_ID + CLIENT_SECRET are set,
    otherwise falls back to DeviceCodeCredential with persistent OS-level
    token caching.
    """
    global _credential
    if _credential is not None:
        return _credential

    load_env()

    tenant_id = os.environ.get("TENANT_ID")
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")

    if not tenant_id or not dataverse_url:
        missing = [k for k, v in [("TENANT_ID", tenant_id), ("DATAVERSE_URL", dataverse_url)] if not v]
        print(f"ERROR: .env is missing required values: {', '.join(missing)}", flush=True)
        print("  Run the init sequence (/dataverse:init) to create .env.", flush=True)
        sys.exit(1)

    try:
        from azure.identity import (
            ClientSecretCredential,
            DeviceCodeCredential,
            TokenCachePersistenceOptions,
        )
    except ImportError:
        print("ERROR: azure-identity not installed. Run: pip install --upgrade azure-identity", flush=True)
        sys.exit(1)

    # Warn if only one of CLIENT_ID / CLIENT_SECRET is set
    if bool(client_id) != bool(client_secret):
        print("WARNING: Only one of CLIENT_ID / CLIENT_SECRET is set. Both are required for", flush=True)
        print("  service principal auth. Falling back to interactive device code flow.", flush=True)

    # Path 1: Service principal (non-interactive)
    if client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        # Path 2: Device code flow (interactive) with persistent OS-level token cache.
        # AuthenticationRecord tells the credential which cached account to silently
        # refresh, avoiding a device code prompt on every new process.
        from azure.identity import AuthenticationRecord

        auth_record = None
        if _AUTH_RECORD_PATH.exists():
            try:
                auth_record = AuthenticationRecord.deserialize(_AUTH_RECORD_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass  # Corrupt or stale record — will re-authenticate

        def _prompt_callback(verification_uri, user_code, _expires_on):
            print(f"\nTo sign in, visit {verification_uri} and enter code: {user_code}", flush=True)
            print("(Waiting for you to complete the login in your browser...)\n", flush=True)

        _credential = DeviceCodeCredential(
            tenant_id=tenant_id,
            client_id="51f81489-12ee-4a9e-aaae-a2591f45987d",  # Well-known Microsoft Power Apps public client app ID
            prompt_callback=_prompt_callback,
            cache_persistence_options=TokenCachePersistenceOptions(
                name="dataverse_cli",
                allow_unencrypted_storage=True,
            ),
            authentication_record=auth_record,
        )

    return _credential


_auth_record_saved = False


def get_token(scope=None):
    """
    Acquire a raw access token string for the Dataverse environment.

    On first call with a DeviceCodeCredential that has no saved AuthenticationRecord,
    this triggers authenticate() to get the record and persist it. Subsequent calls
    (same process or new processes) use silent refresh via the cached record + token cache.

    :param scope: OAuth2 scope. Defaults to "{DATAVERSE_URL}/.default".
    :returns: Access token string suitable for a Bearer Authorization header.
    """
    global _auth_record_saved
    load_env()
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not scope:
        scope = f"{dataverse_url}/.default"

    credential = _get_credential()

    try:
        from azure.identity import DeviceCodeCredential
        if isinstance(credential, DeviceCodeCredential) and not _auth_record_saved and not _AUTH_RECORD_PATH.exists():
            # First login ever — use authenticate() to get and save the record
            record = credential.authenticate(scopes=[scope])
            _AUTH_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
            _AUTH_RECORD_PATH.write_text(record.serialize(), encoding="utf-8")
            _auth_record_saved = True
    except Exception:
        pass  # Fall through to normal get_token flow

    try:
        token = credential.get_token(scope)
    except Exception as e:
        print(f"ERROR: Failed to acquire access token: {e}", flush=True)
        print("  Check your network connection, credentials, and .env configuration.", flush=True)
        sys.exit(1)

    return token.token


_ALLOWED_SKILLS = frozenset({
    "dv-overview", "dv-connect", "dv-data", "dv-query",
    "dv-metadata", "dv-solution", "dv-admin", "dv-security",
    "unknown",
})
_ALLOWED_AGENTS = frozenset({
    "claude-code", "copilot", "cursor", "codex", "unknown",
})
# Strict format: key=value pairs, semicolon-separated. No spaces, no PII.
_CONTEXT_RE = re.compile(
    r"^[a-zA-Z0-9_-]+=[a-zA-Z0-9_./-]+(;[a-zA-Z0-9_-]+=[a-zA-Z0-9_./-]+)*$"
)


def _plugin_version():
    """Read plugin version from .env (set by dv-connect at setup time)."""
    return os.environ.get("DATAVERSE_PLUGIN_VERSION", "unknown")


def _current_agent():
    agent = os.environ.get("DATAVERSE_PLUGIN_AGENT", "unknown")
    if agent not in _ALLOWED_AGENTS:
        raise ValueError(f"Unknown agent '{agent}'; allowed: {_ALLOWED_AGENTS}")
    return agent


def _validate_skill(skill):
    if skill not in _ALLOWED_SKILLS:
        raise ValueError(f"Unknown skill '{skill}'; allowed: {_ALLOWED_SKILLS}")
    return skill


def _build_operation_context(skill):
    """Build and validate the operation_context string.

    Returns an OperationContext object for the SDK.  The string is validated
    both here (via allowlists) and inside OperationContext.__post_init__
    (via regex + control-char check).

    SECURITY: Only closed-schema values from _ALLOWED_SKILLS and
    _ALLOWED_AGENTS are used.  Never pass user-provided or free-form
    strings into operation_context — it is written to HTTP headers and
    server-side telemetry logs.
    """
    ctx_str = f"app=dataverse-skills/{_plugin_version()};skill={skill};agent={_current_agent()}"
    if not _CONTEXT_RE.match(ctx_str):
        raise ValueError(
            f"operation_context failed format validation: {ctx_str!r}. "
            "Must be semicolon-separated key=value pairs with no spaces or special characters."
        )
    from PowerPlatform.Dataverse.core.config import OperationContext
    return OperationContext(user_agent_context=ctx_str)


# --------------------------------------------------------------------------
# Optional SkillOpt trace hook.
#
# When the env var DATAVERSE_TRACE_FILE is set, every SDK records-namespace
# call made through a get_client(...) result is logged to that file as one
# JSON line per call. Created-record GUIDs are written to a sibling file
# named `created_guids.jsonl` in the same directory.
#
# When the env var is unset, behavior is unchanged — no overhead, no files.
#
# Scope: SDK records.create / .update / .delete / .upsert and the bulk
# variants. The raw Web API path (get_token() + requests) is NOT traced —
# see SkillOpt env docs if you need wider coverage.
#
# Thread-safe via a module-level lock around file appends.
# --------------------------------------------------------------------------

_TRACE_LOCK = threading.Lock()


def _trace_file_path():
    return os.environ.get("DATAVERSE_TRACE_FILE", "")


def _guids_file_path():
    trace = _trace_file_path()
    if not trace:
        return ""
    return os.path.join(os.path.dirname(trace) or ".", "created_guids.jsonl")


def _record_trace(method, table, args_summary, status, error=None):
    """Append one JSON line to the trace file. NO-OP when env var is unset."""
    path = _trace_file_path()
    if not path:
        return
    rec = {
        "ts": time.time(),
        "method": method,
        "table": table,
        "url": f"/sdk/records/{method}/{table}",  # synthetic URL for regex matching
        "endpoint": f"/sdk/records/{method}/{table}",
        "args": args_summary,
        "status": status,
    }
    if error:
        rec["error"] = error
    try:
        with _TRACE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass  # Tracing must never break the actual call.


def _record_guids(table, guids):
    """Append created GUIDs to the sibling guids file."""
    path = _guids_file_path()
    if not path or not guids:
        return
    try:
        with _TRACE_LOCK:
            with open(path, "a", encoding="utf-8") as f:
                for g in guids:
                    f.write(json.dumps({"table": table, "guid": str(g), "ts": time.time()}) + "\n")
    except Exception:
        pass


def _summarize_record(rec):
    """Return a small summary of a record dict for the trace log (no large blobs).

    Captures the keys and the size of any string/bytes values without writing
    the full content. Used purely for trace observability.
    """
    if not isinstance(rec, dict):
        try:
            n = len(rec)
            return {"_type": type(rec).__name__, "_len": n}
        except Exception:
            return {"_type": type(rec).__name__}
    summary = {"_keys": sorted(list(rec.keys())), "_n_keys": len(rec)}
    return summary


class _TracingRecords:
    """Lightweight wrapper around a DataverseClient.records namespace.

    Intercepts CRUD calls to write to the trace + GUIDs files when
    DATAVERSE_TRACE_FILE is set. Forwards everything else unchanged.
    """

    def __init__(self, wrapped):
        self._wrapped = wrapped

    def __getattr__(self, name):
        # Forward any other attribute access (e.g., bulk helpers) directly.
        return getattr(self._wrapped, name)

    def create(self, table, records, *args, **kwargs):
        is_bulk = isinstance(records, list)
        args_summary = {
            "is_bulk": is_bulk,
            "count": len(records) if is_bulk else 1,
            "record_summary": (
                [_summarize_record(r) for r in records[:3]] if is_bulk else _summarize_record(records)
            ),
        }
        try:
            result = self._wrapped.create(table, records, *args, **kwargs)
            # The SDK returns a single GUID (single create) or a list of GUIDs (bulk).
            guids = result if isinstance(result, list) else [result]
            _record_trace("create", table, args_summary, status=200)
            _record_guids(table, [g for g in guids if g])
            return result
        except Exception as e:
            _record_trace("create", table, args_summary, status=0, error=str(e))
            raise

    def update(self, table, record_id_or_ids, payload, *args, **kwargs):
        is_bulk = isinstance(record_id_or_ids, list)
        args_summary = {
            "is_bulk": is_bulk,
            "count": len(record_id_or_ids) if is_bulk else 1,
            "payload_summary": _summarize_record(payload),
        }
        try:
            result = self._wrapped.update(table, record_id_or_ids, payload, *args, **kwargs)
            _record_trace("update", table, args_summary, status=200)
            return result
        except Exception as e:
            _record_trace("update", table, args_summary, status=0, error=str(e))
            raise

    def delete(self, table, record_id_or_ids, *args, **kwargs):
        is_bulk = isinstance(record_id_or_ids, list)
        args_summary = {
            "is_bulk": is_bulk,
            "count": len(record_id_or_ids) if is_bulk else 1,
        }
        try:
            result = self._wrapped.delete(table, record_id_or_ids, *args, **kwargs)
            _record_trace("delete", table, args_summary, status=200)
            return result
        except Exception as e:
            _record_trace("delete", table, args_summary, status=0, error=str(e))
            raise

    def upsert(self, table, items, *args, **kwargs):
        is_bulk = isinstance(items, list) and len(items) > 1
        args_summary = {
            "is_bulk": is_bulk,
            "count": len(items) if isinstance(items, list) else 1,
        }
        try:
            result = self._wrapped.upsert(table, items, *args, **kwargs)
            _record_trace("upsert", table, args_summary, status=200)
            # upsert may return GUIDs depending on SDK version
            if isinstance(result, list):
                _record_guids(table, [str(g) for g in result if g])
            return result
        except Exception as e:
            _record_trace("upsert", table, args_summary, status=0, error=str(e))
            raise

    def get(self, *args, **kwargs):
        # Read; no GUIDs to record, but log for request_count checks.
        table = args[0] if args else kwargs.get("table", "<unknown>")
        try:
            result = self._wrapped.get(*args, **kwargs)
            _record_trace("get", table, {}, status=200)
            return result
        except Exception as e:
            _record_trace("get", table, {}, status=0, error=str(e))
            raise


class _TracingClient:
    """Lightweight wrapper that swaps in a _TracingRecords for the records attr.

    Forwards all other attribute access unchanged. Used only when
    DATAVERSE_TRACE_FILE is set; otherwise the underlying client is returned bare.
    """

    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.records = _TracingRecords(wrapped.records)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


def get_client(skill, **kwargs):
    """Return a DataverseClient with plugin attribution baked in.

    The operation_context is appended to the User-Agent header as a
    parenthesized comment for server-side traffic attribution.

    IMPORTANT: Do not modify the operation_context — it uses a closed
    schema (app/skill/agent) for safe server-side attribution.  Never
    include secrets, PII, or free-form text.

    When DATAVERSE_TRACE_FILE is set, the returned client wraps the SDK's
    records namespace to log every create/update/delete/upsert/get to the
    trace file and record created GUIDs to a sibling created_guids.jsonl.
    Used by SkillOpt's live-verification subsystem; safe NO-OP otherwise.

    :param skill: Skill name (e.g. "dv-data", "dv-query").
    :param kwargs: Extra keyword arguments forwarded to DataverseClient.
    :returns: Configured DataverseClient instance (or wrapped, when tracing).
    """
    load_env()
    _validate_skill(skill)
    from PowerPlatform.Dataverse.client import DataverseClient
    client = DataverseClient(
        base_url=os.environ["DATAVERSE_URL"],
        credential=_get_credential(),
        context=_build_operation_context(skill),
        **kwargs,
    )
    if _trace_file_path():
        return _TracingClient(client)
    return client


def get_plugin_headers(skill, token=None):
    """Return HTTP headers for raw Web API calls, with plugin attribution.

    Use this for operations the SDK does not support (forms, views, $apply,
    N:N $expand, unbound actions).

    IMPORTANT: Do not modify the User-Agent context — it uses a closed
    schema (app/skill/agent) for safe server-side attribution.  Never
    include secrets, PII, or free-form text.

    :param skill: Skill name (e.g. "dv-metadata").
    :param token: Optional bearer token (from get_token()).
    :returns: Headers dict with User-Agent and optional Authorization.
    """
    _validate_skill(skill)
    ctx_str = f"app=dataverse-skills/{_plugin_version()};skill={skill};agent={_current_agent()}"
    if not _CONTEXT_RE.match(ctx_str):
        raise ValueError(
            f"operation_context failed format validation: {ctx_str!r}."
        )
    headers = {"User-Agent": f"Python-urllib ({ctx_str})"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


if __name__ == "__main__":
    token = get_token()
    print(token)

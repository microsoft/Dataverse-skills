"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth priority:
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) — non-interactive
  2. Interactive browser flow — opens a browser window once, silent refresh
     thereafter. Matches the auth UX used by PAC CLI and the Dataverse MCP proxy,
     so users see one browser sign-in instead of a device code they must type.

Token caching:
  - Service principal: in-memory (tokens are short-lived, no persistent cache needed)
  - Interactive browser: OS credential store (Windows Credential Manager, macOS
    Keychain, Linux libsecret) via TokenCachePersistenceOptions. An
    AuthenticationRecord is persisted alongside the token cache so that new
    processes can silently refresh without re-prompting the user. The record is
    stored **per tenant** — switching tenants does not invalidate other tenants'
    records. A legacy global record from older versions of auth.py is read on
    first run and migrated forward via the next successful auth.

Functions:
  load_env()            — loads .env into os.environ
  get_credential()      — returns a TokenCredential for use with DataverseClient
  get_token(scope=None) — returns a raw access token string

Usage:
    # PREFERRED — use the Python SDK for all supported operations:
    from auth import get_credential, load_env
    from PowerPlatform.Dataverse.client import DataverseClient
    load_env()
    client = DataverseClient(os.environ["DATAVERSE_URL"], get_credential())

    # ONLY for operations the SDK does NOT support (forms, views, $ref, $apply):
    from auth import get_token, load_env
    token = get_token()

Reads from .env in the repo root (parent of scripts/) or current working directory:
    DATAVERSE_URL      — required
    TENANT_ID          — required
    CLIENT_ID          — optional, enables service principal auth
    CLIENT_SECRET      — optional, enables service principal auth
"""

import os
import sys
from pathlib import Path

# AuthenticationRecord is persisted here so new processes skip device code flow.
# Keyed by TENANT_ID because a record's home_account_id is tenant-bound; a single
# global file gets overwritten on tenant switch and forces re-auth. See
# _auth_record_path() for the resolved path and legacy fallback.
_AUTH_RECORD_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / ".IdentityService"
_AUTH_RECORD_LEGACY_PATH = _AUTH_RECORD_DIR / "dataverse_cli_auth_record.json"


def _auth_record_path(tenant_id):
    """Return the per-tenant AuthenticationRecord file path.

    If tenant_id is falsy, falls back to the legacy global path so we still
    work when TENANT_ID is missing from .env.
    """
    if not tenant_id:
        return _AUTH_RECORD_LEGACY_PATH
    return _AUTH_RECORD_DIR / f"dataverse_cli_auth_record_{tenant_id}.json"


def _read_auth_record(tenant_id):
    """Deserialize the AuthenticationRecord for this tenant.

    Tries the per-tenant path first, then falls back to the legacy global path
    for smooth upgrade (the legacy file is read-only from here; the first
    successful re-auth writes to the new per-tenant path).
    Returns None if no record is found or the record cannot be deserialized.
    """
    from azure.identity import AuthenticationRecord
    for path in (_auth_record_path(tenant_id), _AUTH_RECORD_LEGACY_PATH):
        if path.exists():
            try:
                return AuthenticationRecord.deserialize(path.read_text(encoding="utf-8"))
            except Exception:
                continue  # Corrupt or stale — try next
    return None


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


def get_credential():
    """
    Return an Azure Identity TokenCredential, creating one on first call.

    The credential is cached for the lifetime of the process. Uses
    ClientSecretCredential when CLIENT_ID + CLIENT_SECRET are set,
    otherwise falls back to InteractiveBrowserCredential with persistent
    OS-level token caching.
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
            InteractiveBrowserCredential,
            TokenCachePersistenceOptions,
        )
    except ImportError:
        print("ERROR: azure-identity not installed. Run: pip install --upgrade azure-identity", flush=True)
        sys.exit(1)

    # Warn if only one of CLIENT_ID / CLIENT_SECRET is set
    if bool(client_id) != bool(client_secret):
        print("WARNING: Only one of CLIENT_ID / CLIENT_SECRET is set. Both are required for", flush=True)
        print("  service principal auth. Falling back to interactive browser flow.", flush=True)

    # Path 1: Service principal (non-interactive)
    if client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        # Path 2: Interactive browser flow with persistent OS-level token cache.
        # AuthenticationRecord tells the credential which cached account to silently
        # refresh, avoiding a browser prompt on every new process. The record is
        # stored per-tenant so switching tenants does not invalidate other tenants'
        # records. Matches PAC CLI and MCP proxy auth UX (one browser sign-in, no
        # code-typing).
        auth_record = _read_auth_record(tenant_id)

        _credential = InteractiveBrowserCredential(
            tenant_id=tenant_id,
            client_id="51f81489-12ee-4a9e-aaae-a2591f45987d",  # Well-known Microsoft Power Apps public client app ID
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

    On first call with an InteractiveBrowserCredential that has no saved
    AuthenticationRecord for this tenant, this triggers authenticate() to get
    the record and persist it at the per-tenant path. Subsequent calls (same
    process or new processes, same tenant) use silent refresh via the cached
    record + token cache.

    :param scope: OAuth2 scope. Defaults to "{DATAVERSE_URL}/.default".
    :returns: Access token string suitable for a Bearer Authorization header.
    """
    global _auth_record_saved
    load_env()
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    tenant_id = os.environ.get("TENANT_ID")
    if not scope:
        scope = f"{dataverse_url}/.default"

    credential = get_credential()

    try:
        from azure.identity import InteractiveBrowserCredential
        record_path = _auth_record_path(tenant_id)
        if (
            isinstance(credential, InteractiveBrowserCredential)
            and not _auth_record_saved
            and not record_path.exists()
        ):
            # First login ever for this tenant — authenticate() to get and save
            # the record at the per-tenant path.
            record = credential.authenticate(scopes=[scope])
            record_path.parent.mkdir(parents=True, exist_ok=True)
            record_path.write_text(record.serialize(), encoding="utf-8")
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


if __name__ == "__main__":
    token = get_token()
    print(token)

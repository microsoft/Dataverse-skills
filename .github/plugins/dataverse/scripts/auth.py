"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth priority:
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) — non-interactive
  2. Interactive browser flow — opens a browser window once, silent refresh thereafter
     (best for local development on Windows/Mac/Linux machines with a browser)
  3. Device code flow — fallback for headless environments (SSH, containers, CI)
     Enabled by setting DATAVERSE_AUTH_DEVICE_CODE=1 in the environment, or used
     automatically when the interactive browser flow fails (e.g., no browser available).

Token caching:
  - Service principal: in-memory (tokens are short-lived, no persistent cache needed)
  - Interactive browser / device code: OS credential store (Windows Credential Manager,
    macOS Keychain, Linux libsecret) via TokenCachePersistenceOptions. An
    AuthenticationRecord is persisted alongside the token cache so that new processes
    can silently refresh without re-prompting the user.

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
    DATAVERSE_URL              — required
    TENANT_ID                  — required
    CLIENT_ID                  — optional, enables service principal auth
    CLIENT_SECRET              — optional, enables service principal auth
    DATAVERSE_AUTH_DEVICE_CODE — optional, set to "1" to force device code flow
                                 (use in headless/CI environments where no browser is available)
"""

import os
import sys
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


def get_credential():
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
    force_device_code = os.environ.get("DATAVERSE_AUTH_DEVICE_CODE", "").strip() == "1"

    if not tenant_id or not dataverse_url:
        missing = [k for k, v in [("TENANT_ID", tenant_id), ("DATAVERSE_URL", dataverse_url)] if not v]
        print(f"ERROR: .env is missing required values: {', '.join(missing)}", flush=True)
        print("  Run the init sequence (/dataverse:init) to create .env.", flush=True)
        sys.exit(1)

    try:
        from azure.identity import (
            ClientSecretCredential,
            DeviceCodeCredential,
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
        # Paths 2 & 3 share the same token cache and AuthenticationRecord.
        # AuthenticationRecord tells the credential which cached account to silently
        # refresh, avoiding an auth prompt on every new process.
        from azure.identity import AuthenticationRecord

        auth_record = None
        if _AUTH_RECORD_PATH.exists():
            try:
                auth_record = AuthenticationRecord.deserialize(_AUTH_RECORD_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass  # Corrupt or stale record — will re-authenticate

        # Well-known Microsoft Power Apps public client app ID
        PUBLIC_CLIENT_ID = "51f81489-12ee-4a9e-aaae-a2591f45987d"

        cache_opts = TokenCachePersistenceOptions(
            name="dataverse_cli",
            allow_unencrypted_storage=True,
        )

        if force_device_code:
            # Path 3 explicit: user opted into device code (headless / CI / SSH)
            def _prompt_callback(verification_uri, user_code, _expires_on):
                print(f"\nTo sign in, visit {verification_uri} and enter code: {user_code}", flush=True)
                print("(Waiting for you to complete the login in your browser...)\n", flush=True)

            _credential = DeviceCodeCredential(
                tenant_id=tenant_id,
                client_id=PUBLIC_CLIENT_ID,
                prompt_callback=_prompt_callback,
                cache_persistence_options=cache_opts,
                authentication_record=auth_record,
            )
        else:
            # Path 2 (default): Interactive browser flow. Opens a browser window once;
            # subsequent processes silently refresh via the persisted token cache.
            # No code-copying needed — better UX than device code on local dev machines.
            #
            # If no browser is available (SSH, headless CI), the first get_token()
            # call will fail; set DATAVERSE_AUTH_DEVICE_CODE=1 to opt into device
            # code flow instead.
            _credential = InteractiveBrowserCredential(
                tenant_id=tenant_id,
                client_id=PUBLIC_CLIENT_ID,
                cache_persistence_options=cache_opts,
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

    credential = get_credential()

    try:
        from azure.identity import DeviceCodeCredential, InteractiveBrowserCredential
        interactive_types = (DeviceCodeCredential, InteractiveBrowserCredential)
        if isinstance(credential, interactive_types) and not _auth_record_saved and not _AUTH_RECORD_PATH.exists():
            # First login ever — use authenticate() to get and save the record
            record = credential.authenticate(scopes=[scope])
            _AUTH_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
            _AUTH_RECORD_PATH.write_text(record.serialize(), encoding="utf-8")
            _auth_record_saved = True
    except Exception as e:
        # If interactive browser auth fails (e.g., no browser available),
        # suggest the device-code fallback before failing.
        try:
            from azure.identity import InteractiveBrowserCredential
            if isinstance(credential, InteractiveBrowserCredential):
                print(f"ERROR: Interactive browser authentication failed: {e}", flush=True)
                print("  If no browser is available on this machine (SSH, headless CI, container),", flush=True)
                print("  set DATAVERSE_AUTH_DEVICE_CODE=1 to use the device code flow instead.", flush=True)
                sys.exit(1)
        except ImportError:
            pass
        # For other credential types, fall through to normal get_token flow

    try:
        token = credential.get_token(scope)
    except Exception as e:
        print(f"ERROR: Failed to acquire access token: {e}", flush=True)
        print("  Check your network connection, credentials, and .env configuration.", flush=True)
        try:
            from azure.identity import InteractiveBrowserCredential
            if isinstance(credential, InteractiveBrowserCredential):
                print("  If no browser is available (SSH/headless/CI), set DATAVERSE_AUTH_DEVICE_CODE=1.", flush=True)
        except ImportError:
            pass
        sys.exit(1)

    return token.token


if __name__ == "__main__":
    token = get_token()
    print(token)

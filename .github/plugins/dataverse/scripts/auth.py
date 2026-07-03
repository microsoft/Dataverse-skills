"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth priority (first match wins):
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) — non-interactive
  2. Shared Dataverse CLI token cache — silent, no prompt, populated by
     `dataverse auth create` (see dv-connect Step 2). Uses the same MSAL
     v3 cache file / OS keychain entry that the `@microsoft/dataverse`
     stdio MCP proxy reads, so one login serves the CLI, the MCP proxy,
     and every Python script in the plugin.
  3. Device code flow (legacy fallback) — interactive on first login,
     silent refresh thereafter via this script's own cache.

The shared cache uses the Dataverse CLI app registration
(``0c412cc3-0dd6-449b-987f-05b053db9457``) so every Dataverse-skills tool
authenticates as the same OAuth client and AAD treats it as one sign-in.

Token caching layout (path 2):
  Windows: %LocalAppData%\\Microsoft\\DataverseCli\\tokencache_msalv3.dat (DPAPI)
  macOS:   Keychain service ``dataverse_cli_service`` / account ``dataverse_cli_account``
  Linux:   libsecret schema ``com.microsoft.dataversecli``

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

import os
import re
import sys
import time
from pathlib import Path

# Dataverse CLI app registration. Must match McpOAuth.Config.ClientId in
# DataverseCli/Auth/AuthClientConfig.cs so that tokens minted by
# `dataverse auth create` and the @microsoft/dataverse stdio MCP proxy can
# be silently reused by Python scripts (no second device-code prompt).
_DATAVERSE_CLI_CLIENT_ID = "0c412cc3-0dd6-449b-987f-05b053db9457"

# Legacy AuthenticationRecord path for the device-code fallback (path 3).
# Kept for backward compatibility with workspaces that authenticated via the
# previous auth.py before the shared-cache change.
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


def _build_shared_msal_cache():
    """Open the DataverseCLI MSAL token cache for silent cross-process reuse.

    Returns a tuple ``(msal.PublicClientApplication, list[account])`` if the
    cache exists and contains at least one account, otherwise ``None``.

    The cache is the same one written by ``dataverse auth create`` and read
    by the ``@microsoft/dataverse`` stdio MCP proxy. Sharing it is what makes
    a single ``dataverse auth create`` cover the CLI, the MCP proxy, and
    every Python script in this plugin.

    Returns ``None`` on any failure (missing dependency, unsupported
    platform, empty cache, corrupt cache) so the caller can fall through to
    the device-code fallback.
    """
    try:
        import msal
        from msal_extensions import PersistedTokenCache
    except ImportError:
        return None

    tenant_id = os.environ.get("TENANT_ID")
    if not tenant_id:
        return None

    try:
        if sys.platform == "win32":
            from msal_extensions import FilePersistenceWithDataProtection
            cache_path = (
                Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                / "Microsoft" / "DataverseCli" / "tokencache_msalv3.dat"
            )
            if not cache_path.exists():
                return None
            persistence = FilePersistenceWithDataProtection(str(cache_path))
        elif sys.platform == "darwin":
            from msal_extensions import KeychainPersistence
            # Fallback file path is required by msal-extensions but unused on
            # macOS — the Keychain service/account match DataverseCLI's
            # PacAuthApplicationFactory constants exactly.
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            persistence = KeychainPersistence(
                fallback, "dataverse_cli_service", "dataverse_cli_account"
            )
        else:
            from msal_extensions import LibsecretPersistence
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            persistence = LibsecretPersistence(
                fallback,
                schema_name="com.microsoft.dataversecli",
                attributes={"Version": "1", "ProductGroup": "DataverseCli"},
            )

        cache = PersistedTokenCache(persistence)
        app = msal.PublicClientApplication(
            client_id=_DATAVERSE_CLI_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=cache,
        )
        accounts = app.get_accounts()
        if not accounts:
            return None
        return app, accounts
    except Exception:
        # Any failure (permissions, unsupported keyring, corrupt cache) →
        # silently fall through to device-code fallback. Keeping this broad
        # is deliberate: we never want the shared-cache path to break auth.
        return None


class _MsalSharedCacheCredential:
    """TokenCredential adapter over an msal PublicClientApplication.

    Implements just enough of the azure-core TokenCredential protocol
    (`get_token(*scopes, **kwargs)` returning AccessToken) to satisfy
    DataverseClient and direct urllib callers.
    """

    def __init__(self, app, accounts):
        self._app = app
        self._accounts = accounts

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken
        # Single-account is the common case. If the shared cache happens to
        # contain multiple accounts, the first one wins — deterministic and
        # matches what `dataverse auth select` would surface as active.
        result = self._app.acquire_token_silent(list(scopes), account=self._accounts[0])
        if not result or "access_token" not in result:
            raise RuntimeError(
                "Shared DataverseCLI token cache is present but silent token "
                "acquisition failed. Re-run `dataverse auth create --environment "
                f"{os.environ.get('DATAVERSE_URL', '<url>')}` and try again."
            )
        expires_on = int(time.time()) + int(result.get("expires_in", 3600))
        return AccessToken(result["access_token"], expires_on)

    def close(self):  # pragma: no cover — parity with azure-identity credentials
        pass


def _get_credential():
    """
    Return a TokenCredential, creating one on first call.

    The credential is cached for the lifetime of the process. Resolution
    order matches the module docstring: service principal → shared
    DataverseCLI cache → device-code fallback.
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
        print("  service principal auth. Falling back to shared cache / device code flow.", flush=True)

    # Path 1: Service principal (non-interactive). Best for CI.
    if client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        return _credential

    # Path 2: Shared DataverseCLI MSAL cache (populated by `dataverse auth
    # create`). Silent for the whole process lifetime, no prompt. Same
    # client ID as the @microsoft/dataverse stdio MCP proxy, so AAD treats
    # CLI / MCP / Python as one sign-in.
    shared = _build_shared_msal_cache()
    if shared is not None:
        app, accounts = shared
        _credential = _MsalSharedCacheCredential(app, accounts)
        return _credential

    # Path 3: Legacy device-code fallback with this script's own cache.
    # Kept so an existing workspace that authenticated before the shared-
    # cache change keeps working without forcing a re-login.
    from azure.identity import AuthenticationRecord

    auth_record = None
    if _AUTH_RECORD_PATH.exists():
        try:
            auth_record = AuthenticationRecord.deserialize(_AUTH_RECORD_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass  # Corrupt or stale record — will re-authenticate

    def _prompt_callback(verification_uri, user_code, _expires_on):
        print(f"\nTo sign in, visit {verification_uri} and enter code: {user_code}", flush=True)
        print("  Tip: run `dataverse auth create --environment "
              f"{dataverse_url}` once and Python scripts will reuse that", flush=True)
        print("  cache silently in the future (no device code).", flush=True)
        print("(Waiting for you to complete the login in your browser...)\n", flush=True)

    _credential = DeviceCodeCredential(
        tenant_id=tenant_id,
        client_id=_DATAVERSE_CLI_CLIENT_ID,
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

    Resolution order is set by ``_get_credential()``: service principal,
    then the shared DataverseCLI MSAL cache (silent), then a device-code
    fallback. The device-code path persists an AuthenticationRecord on
    first login so subsequent processes refresh silently.

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
            # First login on the device-code fallback path — call authenticate()
            # once to capture and persist the AuthenticationRecord. The shared-
            # cache path (path 2) needs none of this; it relies on the cache
            # populated by `dataverse auth create`.
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
        print("  Tip: run `dataverse auth create --environment "
              f"{dataverse_url}` to populate the shared token cache.", flush=True)
        sys.exit(1)

    return token.token


_ALLOWED_SKILLS = frozenset({
    "dv-overview", "dv-connect", "dv-data", "dv-query",
    "dv-metadata", "dv-solution", "dv-admin", "dv-security",
    "unknown",
})
_ALLOWED_AGENTS = frozenset({
    "claude-code", "copilot", "cursor", "codex", "opencode", "unknown",
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


def get_client(skill, **kwargs):
    """Return a DataverseClient with plugin attribution baked in.

    The operation_context is appended to the User-Agent header as a
    parenthesized comment for server-side traffic attribution.

    IMPORTANT: Do not modify the operation_context — it uses a closed
    schema (app/skill/agent) for safe server-side attribution.  Never
    include secrets, PII, or free-form text.

    :param skill: Skill name (e.g. "dv-data", "dv-query").
    :param kwargs: Extra keyword arguments forwarded to DataverseClient.
    :returns: Configured DataverseClient instance.
    """
    load_env()
    _validate_skill(skill)
    from PowerPlatform.Dataverse.client import DataverseClient
    return DataverseClient(
        base_url=os.environ["DATAVERSE_URL"],
        credential=_get_credential(),
        context=_build_operation_context(skill),
        **kwargs,
    )


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

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
  Linux:   libsecret schema ``com.microsoft.dataversecli`` (desktop), or a plaintext
           ``tokencache_msalv3.dat`` under ``$XDG_DATA_HOME/Microsoft/DataverseCli``
           on headless hosts with no keyring (matches the CLI's WithLinuxUnprotectedFile)

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
    DATAVERSE_TOKEN_CACHE_DIR — optional; on ephemeral hosts (ChatGPT web / Codex
                         sandbox) where $HOME is wiped between turns, set this to a
                         workspace-relative dir (e.g. .dataverse) so the device-code
                         token cache persists and refreshes silently within a session
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
        # Collect candidate MSAL cache persistences to try in order. The first
        # one that yields a signed-in account wins. On Linux this lets a single
        # login serve both the DataverseCLI and Python: the CLI writes its
        # public-client cache to the libsecret keyring on desktop, or to a
        # plaintext MSAL v3 file on headless hosts that lack a keyring.
        candidates = []
        if sys.platform == "win32":
            from msal_extensions import FilePersistenceWithDataProtection
            cache_path = (
                Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                / "Microsoft" / "DataverseCli" / "tokencache_msalv3.dat"
            )
            if cache_path.exists():
                candidates.append(FilePersistenceWithDataProtection(str(cache_path)))
        elif sys.platform == "darwin":
            from msal_extensions import KeychainPersistence
            # Fallback file path is required by msal-extensions but unused on
            # macOS — the Keychain service/account match DataverseCLI's
            # PacAuthApplicationFactory constants exactly.
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            candidates.append(
                KeychainPersistence(fallback, "dataverse_cli_service", "dataverse_cli_account")
            )
        else:
            # Linux: try the libsecret keyring first (desktop), then the CLI's
            # plaintext MSAL v3 file (headless, once the CLI falls back to
            # WithLinuxUnprotectedFile). Same MSAL v3 format both sides read.
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            try:
                from msal_extensions import LibsecretPersistence
                candidates.append(
                    LibsecretPersistence(
                        fallback,
                        schema_name="com.microsoft.dataversecli",
                        attributes={"Version": "1", "ProductGroup": "DataverseCli"},
                    )
                )
            except Exception:
                pass  # libsecret backend unavailable on this host — skip it.
            from msal_extensions import FilePersistence
            xdg_data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
            plaintext_path = Path(xdg_data) / "Microsoft" / "DataverseCli" / "tokencache_msalv3.dat"
            if plaintext_path.exists():
                candidates.append(FilePersistence(str(plaintext_path)))

        for persistence in candidates:
            try:
                cache = PersistedTokenCache(persistence)
                app = msal.PublicClientApplication(
                    client_id=_DATAVERSE_CLI_CLIENT_ID,
                    authority=f"https://login.microsoftonline.com/{tenant_id}",
                    token_cache=cache,
                )
                accounts = app.get_accounts()
                if accounts:
                    return app, accounts
            except Exception:
                # This candidate failed (missing backend, corrupt/locked file) —
                # try the next; never let the shared-cache path break auth.
                continue
        return None
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


def _workspace_token_cache_path():
    """Return an explicit MSAL v3 cache file path when DATAVERSE_TOKEN_CACHE_DIR is set.

    Opt-in. On ephemeral hosts (ChatGPT web / Codex sandbox) the process $HOME is
    wiped between turns while the workspace directory persists within a conversation.
    Setting DATAVERSE_TOKEN_CACHE_DIR (e.g. ".dataverse") relocates the device-code
    token cache into the persisted workspace, so the first sign-in is silently reused
    on later turns. Returns None when the var is unset, which leaves capable hosts
    (Windows DPAPI / macOS Keychain / Linux desktop keyring) on their default secure
    cache with NO behavior change.

    Security hardening: the cache holds a refresh token (plaintext on headless Linux;
    DPAPI-encrypted on Windows -- see _get_credential). The directory is created
    owner-only (0700 on POSIX) with a self-contained `.gitignore` (`*`) so the token
    is excluded from version control even if the repo-root .gitignore misses it.
    """
    cache_dir = os.environ.get("DATAVERSE_TOKEN_CACHE_DIR")
    if not cache_dir:
        return None
    try:
        path = Path(cache_dir)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.mkdir(parents=True, exist_ok=True)
        # Defense in depth: exclude the token cache from git even if the repo-root
        # .gitignore does not cover this dir.
        gitignore = path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        try:
            os.chmod(path, 0o700)  # owner-only on POSIX; benign on Windows
        except Exception:
            pass
        return path / "tokencache_msalv3.dat"
    except Exception:
        return None


class _MsalDeviceCodeCredential:
    """TokenCredential over an msal app that persists at an explicit cache path.

    Silent-refresh from the cache when possible; device-code sign-in on a cache miss.
    Used only when DATAVERSE_TOKEN_CACHE_DIR is set (opt-in, ephemeral hosts) so the
    refresh token lives in the persisted workspace cache and is reused across turns.
    Implements the azure-core TokenCredential protocol (get_token).
    """

    def __init__(self, app):
        self._app = app

    def get_token(self, *scopes, **kwargs):
        from azure.core.credentials import AccessToken
        scope_list = list(scopes)
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(scope_list, account=accounts[0])
        if not result or "access_token" not in result:
            flow = self._app.initiate_device_flow(scopes=scope_list)
            if "user_code" not in flow:
                raise RuntimeError(
                    "Failed to start device-code flow: "
                    f"{flow.get('error_description', flow)}"
                )
            print(
                f"\nTo sign in, visit {flow['verification_uri']} and enter code: "
                f"{flow['user_code']}",
                flush=True,
            )
            print("(Waiting for you to complete the login in your browser...)\n", flush=True)
            result = self._app.acquire_token_by_device_flow(flow)  # blocks until complete
        if not result or "access_token" not in result:
            detail = result.get("error_description", result) if result else "no response"
            raise RuntimeError(f"Device-code authentication failed: {detail}")
        expires_on = int(time.time()) + int(result.get("expires_in", 3600))
        return AccessToken(result["access_token"], expires_on)

    def close(self):  # pragma: no cover
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

    # Path 3a: Workspace-local device-code cache (opt-in via DATAVERSE_TOKEN_CACHE_DIR).
    # On ephemeral hosts (ChatGPT web / Codex sandbox) $HOME is wiped between turns but
    # the workspace persists within a conversation. When the var is set, put the MSAL
    # cache (incl. refresh token) in the workspace so the first device-code sign-in is
    # silently reused on later turns -- device code once per conversation, not per turn.
    # Unset (the default on capable hosts) -> fall through to the standard path below.
    workspace_cache = _workspace_token_cache_path()
    if workspace_cache is not None:
        try:
            import msal
            from msal_extensions import PersistedTokenCache
            if sys.platform == "win32":
                # Encrypt the workspace cache at rest with DPAPI on Windows.
                from msal_extensions import FilePersistenceWithDataProtection
                persistence = FilePersistenceWithDataProtection(str(workspace_cache))
            else:
                # Headless Linux / macOS: no keyring, plaintext file (owner-only dir).
                from msal_extensions import FilePersistence
                persistence = FilePersistence(str(workspace_cache))
            cache = PersistedTokenCache(persistence)
            app = msal.PublicClientApplication(
                client_id=_DATAVERSE_CLI_CLIENT_ID,
                authority=f"https://login.microsoftonline.com/{tenant_id}",
                token_cache=cache,
            )
            _credential = _MsalDeviceCodeCredential(app)
            return _credential
        except ImportError:
            pass  # msal/msal-extensions missing -- fall through to azure-identity device code

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
    import argparse

    parser = argparse.ArgumentParser(
        description="Acquire a Dataverse token, or verify the environment is reachable."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Make a REAL data-plane call and report reachability instead of printing a token. "
        "A token can be minted while the org domain is blocked (restricted-egress hosts), so "
        "this is the only proof of an actual connection. Exit 0 = reachable, 2 = not reachable.",
    )
    args = parser.parse_args()

    if not args.check:
        # Default (unchanged) behavior: print a bearer token.
        print(get_token())
        sys.exit(0)

    # Reachability gate. A green token is NOT a connection: auth traffic goes to
    # login.microsoftonline.com (often reachable) while the org's data plane
    # (*.dynamics.com) may be blocked by a sandbox egress allowlist. Only a real
    # call proves it. Bound the wait so a blocked domain fails fast instead of hanging.
    import socket

    socket.setdefaulttimeout(30)
    load_env()
    url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    try:
        client = get_client("dv-connect")
        tables = client.tables.list(select=["LogicalName"])
        print(f"REACHABLE: {url} -- {len(tables)} non-private tables")
        sys.exit(0)
    except Exception as e:
        print(f"NOT REACHABLE: {url} -- {type(e).__name__}: {e}", flush=True)
        print(
            "If this is a connection/timeout error, the org domain is blocked by the host "
            "network egress allowlist -- auth is fine; the data plane is unreachable. Do NOT "
            "report a table count or query result: nothing was retrieved.",
            flush=True,
        )
        sys.exit(2)

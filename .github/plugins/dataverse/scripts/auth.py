"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth chain (silent tiers first; interactive only when every silent tier is
unavailable, so a working path wins without stranding the user -- issue #108):
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) -- non-interactive,
     terminal (CI fails fast; no interactive fallback when SP is configured).
  2. Certificate (CLIENT_ID + CLIENT_CERTIFICATE_PATH in .env) -- non-interactive,
     terminal (CI fails fast; no interactive fallback when configured).
  3. Shared Dataverse CLI token cache -- silent, no prompt, populated by
     `dataverse auth create` (see dv-connect Step 2). Uses the same MSAL v3
     cache the `@microsoft/dataverse` stdio MCP proxy reads. Probed at build
     time against both the tenant-specific and `organizations` authority so an
     authority mismatch falls through instead of hard-failing.
  4. Azure CLI (`az login`) -- silent, scoped to TENANT_ID; skipped when az is
     absent or not logged in.
  5. Interactive (host-gated, last): workspace-cache device-code when
     DATAVERSE_TOKEN_CACHE_DIR is set (ephemeral hosts); else a system-browser
     InteractiveBrowserCredential on a desktop host (beats the CA device-code
     block, and uses the browser not the MSAL broker so it sidesteps the macOS
     broker bug); else DeviceCodeCredential on a headless host. Each persists an
     AuthenticationRecord so later processes refresh silently.

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
    CLIENT_CERTIFICATE_PATH — optional, enables certificate auth (.pfx or .pem)
    CLIENT_CERTIFICATE_PASSWORD — optional, decrypts a password-protected certificate
    CLIENT_SEND_CERTIFICATE_CHAIN — optional, set to 1 for SNI authentication
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

# Cross-workspace config so returning users skip the full dv-connect dance.
_USER_CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / ".dataverse-skills"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "config.json"


def _load_user_config():
    """Load DATAVERSE_URL and TENANT_ID from user-level config when .env is absent."""
    if not _USER_CONFIG_PATH.exists():
        return
    try:
        import json
        cfg = json.loads(_USER_CONFIG_PATH.read_text(encoding="utf-8"))
        loaded = []
        for key in ("DATAVERSE_URL", "TENANT_ID"):
            val = cfg.get(key)
            if val and not os.environ.get(key):
                os.environ.setdefault(key, val)
                loaded.append(key)
        if loaded:
            print(
                f"NOTE: loaded {', '.join(loaded)} from {_USER_CONFIG_PATH} "
                f"(no .env found). Target: {cfg.get('DATAVERSE_URL', '?')}",
                flush=True,
            )
    except Exception:
        pass


def _save_user_config():
    """Persist URL and tenant to user-level config for cross-workspace reuse."""
    import json
    url = os.environ.get("DATAVERSE_URL")
    tenant = os.environ.get("TENANT_ID")
    if not url or not tenant:
        return
    try:
        _USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(_USER_CONFIG_DIR, 0o700)
        except Exception:
            pass
        _USER_CONFIG_PATH.write_text(
            json.dumps({"DATAVERSE_URL": url, "TENANT_ID": tenant}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_env():
    """Load key=value pairs from .env into os.environ (does not overwrite existing vars).

    Searches for .env in two locations (first match wins):
      1. The repo root (parent of the directory containing this script)
      2. The current working directory
    This ensures ``cd scripts && python auth.py`` works the same as
    ``python scripts/auth.py`` from the repo root.

    Falls back to user-level config (~/.dataverse-skills/config.json) when .env
    is absent, so returning users on ephemeral-workspace hosts (ChatGPT desktop
    app, Codex) skip the full dv-connect setup.
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
    if not os.environ.get("DATAVERSE_URL") or not os.environ.get("TENANT_ID"):
        _load_user_config()


_credential = None


def _dataverse_scope():
    """Return the ``{DATAVERSE_URL}/.default`` OAuth scope, or None if unset."""
    url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not url:
        return None
    return f"{url}/.default"


def _shared_cache_persistences():
    """Return the ordered list of MSAL cache persistences to try for the shared
    DataverseCLI cache (platform-specific). Never raises -- returns [] on any issue.
    On Linux this is libsecret-first (desktop) then the plaintext MSAL v3 file
    (headless), matching the CLI's WithLinuxUnprotectedFile fallback.
    """
    persistences = []
    try:
        if sys.platform == "win32":
            from msal_extensions import FilePersistenceWithDataProtection
            cache_path = (
                Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
                / "Microsoft" / "DataverseCli" / "tokencache_msalv3.dat"
            )
            if cache_path.exists():
                persistences.append(FilePersistenceWithDataProtection(str(cache_path)))
        elif sys.platform == "darwin":
            from msal_extensions import KeychainPersistence
            # Fallback file path is required by msal-extensions but unused on
            # macOS -- the Keychain service/account match DataverseCLI's
            # PacAuthApplicationFactory constants exactly.
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            persistences.append(
                KeychainPersistence(fallback, "dataverse_cli_service", "dataverse_cli_account")
            )
        else:
            fallback = str(Path.home() / ".dataverse_cli_msal_cache")
            try:
                from msal_extensions import LibsecretPersistence
                persistences.append(
                    LibsecretPersistence(
                        fallback,
                        schema_name="com.microsoft.dataversecli",
                        attributes={"Version": "1", "ProductGroup": "DataverseCli"},
                    )
                )
            except Exception:
                pass  # libsecret backend unavailable on this host -- skip it.
            from msal_extensions import FilePersistence
            xdg_data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
            plaintext_path = Path(xdg_data) / "Microsoft" / "DataverseCli" / "tokencache_msalv3.dat"
            if plaintext_path.exists():
                persistences.append(FilePersistence(str(plaintext_path)))
    except Exception:
        return []
    return persistences


def _build_shared_msal_cache():
    """Open the DataverseCLI MSAL cache for silent reuse, probing it at build time.

    Returns ``(msal.PublicClientApplication, list[account])`` only when a silent
    token actually comes back -- probed against BOTH the tenant-specific and the
    ``organizations`` authority, because ``dataverse auth create`` may have written
    the cache under a different authority than TENANT_ID (issue #108, defect 2).
    Returns ``None`` on any miss so the caller falls through to the next tier --
    the shared-cache path can never break auth.
    """
    try:
        import msal
        from msal_extensions import PersistedTokenCache
    except ImportError:
        return None

    tenant_id = os.environ.get("TENANT_ID")
    if not tenant_id:
        return None

    scope = _dataverse_scope()
    authorities = [
        f"https://login.microsoftonline.com/{tenant_id}",
        "https://login.microsoftonline.com/organizations",
    ]
    for persistence in _shared_cache_persistences():
        for authority in authorities:
            try:
                app = msal.PublicClientApplication(
                    client_id=_DATAVERSE_CLI_CLIENT_ID,
                    authority=authority,
                    token_cache=PersistedTokenCache(persistence),
                )
                accounts = app.get_accounts()
                if not accounts:
                    continue
                if scope is None:
                    # No DATAVERSE_URL to probe with -- trust account presence.
                    return app, accounts
                probe = app.acquire_token_silent([scope], account=accounts[0])
                if probe and "access_token" in probe:
                    return app, accounts  # this authority actually yields a token
            except Exception:
                continue  # never let the shared-cache path break auth
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
        from azure.identity import CredentialUnavailableError
        # Single-account is the common case. If the shared cache happens to
        # contain multiple accounts, the first one wins -- deterministic and
        # matches what `dataverse auth select` would surface as active.
        # Forward a CAE / Conditional-Access claims challenge when azure-core
        # passes one -- CA-hardened tenants are this plugin's target scenario.
        # A None claims_challenge is a harmless no-op.
        result = self._app.acquire_token_silent(
            list(scopes), account=self._accounts[0],
            claims_challenge=kwargs.get("claims"),
        )
        if not result or "access_token" not in result:
            # Fall through, do NOT hard-fail: a cached account can exist while
            # silent acquisition fails (authority mismatch, expired refresh
            # token). Raising CredentialUnavailableError lets the chain try the
            # next tier instead of stranding the user. (Issue #108, defect 1.)
            raise CredentialUnavailableError(
                "Shared DataverseCLI cache present but silent token acquisition "
                "failed (often an authority mismatch or expired refresh token)."
            )
        expires_on = int(time.time()) + int(result.get("expires_in", 3600))
        return AccessToken(result["access_token"], expires_on)

    def close(self):  # pragma: no cover — parity with azure-identity credentials
        pass


# Default workspace cache dir used on headless/ephemeral hosts when the user has not
# set DATAVERSE_TOKEN_CACHE_DIR (see _workspace_token_cache_path).
_DEFAULT_WORKSPACE_CACHE_DIRNAME = ".dataverse"

# Explicit opt-out values for DATAVERSE_TOKEN_CACHE_DIR: keep the OS default cache
# (do not write a plaintext refresh token into the workspace).
_CACHE_DIR_OPT_OUT = frozenset({"off", "0", "false", "no", "none", "disable", "disabled"})


def _should_use_workspace_cache():
    """Pure decision (no I/O): whether the persisted workspace token cache is used,
    and via which source. This is the SINGLE source of truth so
    _workspace_token_cache_path (which builds the path) and _run_diagnose (which
    reports the tier) can never drift. Returns:
      "explicit" -- DATAVERSE_TOKEN_CACHE_DIR is set to a usable path.
      "default"  -- unset on a HEADLESS, non-CI host -> auto-default to <workspace>/.dataverse.
      None       -- keep the OS default cache (desktop, CI, or an explicit opt-out).
    """
    cache_dir = os.environ.get("DATAVERSE_TOKEN_CACHE_DIR")
    if cache_dir is not None and cache_dir.strip().lower() in _CACHE_DIR_OPT_OUT:
        return None  # explicit opt-out -- keep the per-process OS default cache
    if cache_dir:
        return "explicit"
    # No explicit setting: auto-default ONLY where the OS cache will not survive --
    # a headless, non-CI host. Desktop hosts keep their secure default cache; CI
    # never reaches an interactive tier (service principal is terminal earlier).
    if _host_has_browser() or _is_ci():
        return None
    return "default"


def _workspace_token_cache_path():
    """Return the MSAL v3 cache file path used to persist the device-code refresh
    token across separate Python processes, or None to keep the OS default cache.
    The use/skip decision is _should_use_workspace_cache(); this function only turns
    a positive decision into a concrete, git-ignored, owner-only file path.

    Resolution (see _should_use_workspace_cache):
      - DATAVERSE_TOKEN_CACHE_DIR set to a path -> use it (a relative dir is anchored
        to the workspace root, matching how load_env finds .env).
      - opt-out value (off/false/0/no/none) -> None.
      - unset on a HEADLESS, non-CI host (ChatGPT web / Codex sandbox / SSH / container)
        -> DEFAULT to ``<workspace>/.dataverse`` (the OS cache lives under $HOME, which
        the sandbox wipes between Python processes, so device code would re-prompt every
        process; the persisted workspace cache makes sign-in once per conversation).
      - unset on a desktop host -> None (keep the secure OS cache: Windows DPAPI /
        macOS Keychain / Linux desktop keyring -- no behavior change).

    Security: on non-Windows hosts (Linux, and macOS over SSH) the cache holds a
    PLAINTEXT refresh token (no keyring; Windows uses DPAPI). The directory is created
    owner-only (0700 on POSIX) with a self-contained `.gitignore` (`*`) so the token is
    excluded from version control, and an ephemeral sandbox is torn down after the
    session. To keep the OS default cache instead, set DATAVERSE_TOKEN_CACHE_DIR=off.
    """
    decision = _should_use_workspace_cache()
    if decision is None:
        return None
    cache_dir = (
        os.environ.get("DATAVERSE_TOKEN_CACHE_DIR")
        if decision == "explicit"
        else _DEFAULT_WORKSPACE_CACHE_DIRNAME
    )
    try:
        path = Path(cache_dir)
        if not path.is_absolute():
            # Anchor a relative dir to the workspace root (this file's parent dir's
            # parent -- the deployed <project>/scripts/auth.py layout), NOT the
            # current working directory, so the cache location is stable no matter
            # where the process is launched from (matches how load_env finds .env).
            path = Path(__file__).resolve().parent.parent / path
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
        claims = kwargs.get("claims")  # CAE / Conditional-Access challenge, if any
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(
                scope_list, account=accounts[0], claims_challenge=claims,
            )
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
            _expiry_min = max(1, int(flow.get("expires_in", 900)) // 60)
            print(
                f"(Waiting for you to complete the login in your browser -- "
                f"this code expires in ~{_expiry_min} min...)\n",
                flush=True,
            )
            result = self._app.acquire_token_by_device_flow(
                flow, claims_challenge=claims,
            )  # blocks until complete
        if not result or "access_token" not in result:
            detail = result.get("error_description", result) if result else "no response"
            raise RuntimeError(f"Device-code authentication failed: {detail}")
        expires_on = int(time.time()) + int(result.get("expires_in", 3600))
        return AccessToken(result["access_token"], expires_on)

    def close(self):  # pragma: no cover
        pass


def _is_ci():
    """True on CI / build agents (no interactive user), even on win32/darwin --
    GitHub Actions, ADO agents, containerized Windows. Treats only genuinely-
    truthy values as set (avoids the CI="false" trap).
    """
    def _flag(name):
        return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "no")

    return _flag("CI") or _flag("GITHUB_ACTIONS") or _flag("TF_BUILD") or _flag("BUILD_BUILDID")


def _host_has_browser():
    """True if an interactive system browser is likely available.

    CI / build agents are headless even when sys.platform is win32/darwin --
    launching a browser there crashes with no user session, so they route to the
    device-code tier instead. After the CI gate: a Windows console or RDP session
    has a browser, but a Windows service / headless container has an empty or
    "Services" SESSIONNAME; macOS (non-CI) always has a session browser; Linux
    needs a display server (DISPLAY / WAYLAND_DISPLAY) -- headless Linux (SSH /
    container / ChatGPT web) has neither and uses device-code.
    """
    if _is_ci():
        return False
    if sys.platform == "win32":
        session = os.environ.get("SESSIONNAME", "").strip().lower()
        return session not in ("", "services")
    if sys.platform == "darwin":
        # An SSH / remote macOS session has no local browser -- use device-code.
        if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
            return False
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


class _SilentChain:
    """Try each silent tier in order; skip any that is unavailable OR errors, so a
    convenience tier (e.g. az CLI logged into another tenant) can never strand the
    fall-through to the interactive tier. Raises CredentialUnavailableError only
    when every tier is exhausted.
    """

    def __init__(self, tiers):
        self._tiers = tiers  # list[(name, credential)]
        self.last_reasons = []  # why each tier was skipped -- surfaced before a prompt

    def get_token(self, *scopes, **kwargs):
        from azure.identity import CredentialUnavailableError
        reasons = []
        for tier_name, cred in self._tiers:
            try:
                return cred.get_token(*scopes, **kwargs)
            except CredentialUnavailableError:
                reasons.append(f"{tier_name}: unavailable")
            except Exception as e:  # noqa: BLE001 -- a silent tier must never strand the chain
                reasons.append(f"{tier_name}: {type(e).__name__}")
        self.last_reasons = reasons
        raise CredentialUnavailableError(
            "no silent credential available (" + "; ".join(reasons) + ")"
        )

    def close(self):  # pragma: no cover
        pass


class _FallbackCredential:
    """Silent tiers first; if all are unavailable, build and use the single
    host-appropriate interactive tier ON DEMAND -- so an interactive prompt
    happens ONLY when no silent path works. (Issue #108: never strand, never
    prompt when a silent tier would do.)
    """

    def __init__(self, silent, interactive_builder):
        self._silent = silent
        self._interactive_builder = interactive_builder
        self._interactive = None

    def get_token(self, *scopes, **kwargs):
        from azure.identity import CredentialUnavailableError
        if self._silent is not None:
            try:
                return self._silent.get_token(*scopes, **kwargs)
            except CredentialUnavailableError as e:
                # Surface WHY every silent tier was skipped so a sudden interactive
                # prompt is explicable ("it just prompted me and I don't know why").
                reasons = getattr(self._silent, "last_reasons", None)
                detail = "; ".join(reasons) if reasons else str(e)
                print(
                    f"No silent credential available ({detail}); "
                    f"falling back to interactive sign-in.",
                    flush=True,
                )
        if self._interactive is None:
            self._interactive = self._interactive_builder()
        return self._interactive.get_token(*scopes, **kwargs)

    def close(self):  # pragma: no cover
        pass


def _build_workspace_device_code_credential(cache_path, tenant_id):
    """Build the opt-in workspace-cache device-code credential, or None if msal
    is unavailable. The MSAL cache (incl. refresh token) lives at cache_path in
    the persisted workspace, so device code is once per conversation, not per turn.
    """
    try:
        import msal
        from msal_extensions import PersistedTokenCache
        if sys.platform == "win32":
            from msal_extensions import FilePersistenceWithDataProtection
            persistence = FilePersistenceWithDataProtection(str(cache_path))
        else:
            from msal_extensions import FilePersistence
            persistence = FilePersistence(str(cache_path))
        app = msal.PublicClientApplication(
            client_id=_DATAVERSE_CLI_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=PersistedTokenCache(persistence),
        )
        return _MsalDeviceCodeCredential(app)
    except ImportError:
        return None


def _build_interactive_tier(tenant_id):
    """Build ``(credential, kind)`` for the single interactive tier this host uses.

    kind is one of ``workspace-device-code`` / ``interactive-browser`` /
    ``device-code``. Selection:
      - workspace cache available (DATAVERSE_TOKEN_CACHE_DIR set, or auto-defaulted on
        a headless non-CI host) -> workspace-cache device-code (self-persisting).
      - desktop host with a browser -> InteractiveBrowserCredential (system browser).
      - headless host with no buildable workspace cache -> DeviceCodeCredential (legacy).
    The azure-identity interactive tiers persist an AuthenticationRecord on first
    login so a later process refreshes silently. Called ONLY after every silent
    tier is exhausted, so the eager first-login prompt here is never premature.
    """
    # CI / unattended host: no interactive tier can succeed (no browser; a device
    # code just blocks ~15 min then expires into a log nobody reads). Service
    # principal is a terminal tier BEFORE we reach here, so being here under CI
    # means no SP is configured -- fail fast with an actionable message instead of
    # a guaranteed hang.
    if _is_ci():
        raise RuntimeError(
            "Unattended/CI host detected with no working silent credential "
            "(service principal, shared cache, or az login). Interactive sign-in "
            "cannot succeed here -- set CLIENT_ID + CLIENT_SECRET for a service "
            "principal, or run `python scripts/auth.py --diagnose` to see which "
            "tier failed."
        )
    workspace_cache = _workspace_token_cache_path()
    if workspace_cache is not None:
        cred = _build_workspace_device_code_credential(workspace_cache, tenant_id)
        if cred is not None:
            return cred, "workspace-device-code"

    from azure.identity import (
        AuthenticationRecord,
        DeviceCodeCredential,
        InteractiveBrowserCredential,
        TokenCachePersistenceOptions,
    )

    cache_opts = TokenCachePersistenceOptions(
        name="dataverse_cli", allow_unencrypted_storage=True
    )
    record = None
    if _AUTH_RECORD_PATH.exists():
        try:
            record = AuthenticationRecord.deserialize(
                _AUTH_RECORD_PATH.read_text(encoding="utf-8")
            )
        except Exception:
            record = None  # corrupt/stale record -- re-authenticate

    if _host_has_browser():
        cred = InteractiveBrowserCredential(
            tenant_id=tenant_id,
            client_id=_DATAVERSE_CLI_CLIENT_ID,
            cache_persistence_options=cache_opts,
            authentication_record=record,
        )
        kind = "interactive-browser"
    else:
        def _prompt_callback(verification_uri, user_code, _expires_on):
            print(f"\nTo sign in, visit {verification_uri} and enter code: {user_code}", flush=True)
            print("(Waiting for you to complete the login in your browser...)\n", flush=True)

        cred = DeviceCodeCredential(
            tenant_id=tenant_id,
            client_id=_DATAVERSE_CLI_CLIENT_ID,
            prompt_callback=_prompt_callback,
            cache_persistence_options=cache_opts,
            authentication_record=record,
        )
        kind = "device-code"

    # First login: capture + persist the AuthenticationRecord so later processes
    # refresh silently. authenticate() performs the one interactive flow; because
    # we are here only after the silent tiers failed, it is never premature.
    if record is None:
        try:
            scope = _dataverse_scope()
            new_record = cred.authenticate(scopes=[scope] if scope else None)
            _AUTH_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
            _AUTH_RECORD_PATH.write_text(new_record.serialize(), encoding="utf-8")
        except KeyboardInterrupt:
            raise  # user cancelled sign-in -- honor it, don't fall through to a 2nd prompt
        except Exception as e:  # noqa: BLE001 -- non-fatal: get_token still works, may reprompt
            print(
                f"NOTE: first interactive sign-in did not persist a record "
                f"({type(e).__name__}); a later token request may reprompt.",
                flush=True,
            )

    return cred, kind


def _get_credential():
    """
    Return a TokenCredential, creating one on first call.

    The credential is cached for the lifetime of the process. Resolution
    order: service principal or certificate (terminal) -> silent chain (shared
    DataverseCLI cache, then az CLI) -> single host-gated interactive tier,
    used only when every silent tier is unavailable (issue #108).
    """
    global _credential
    if _credential is not None:
        return _credential

    load_env()

    tenant_id = os.environ.get("TENANT_ID")
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    certificate_path = os.environ.get("CLIENT_CERTIFICATE_PATH")
    certificate_password = os.environ.get("CLIENT_CERTIFICATE_PASSWORD")

    if not tenant_id or not dataverse_url:
        missing = [k for k, v in [("TENANT_ID", tenant_id), ("DATAVERSE_URL", dataverse_url)] if not v]
        print(f"ERROR: .env is missing required values: {', '.join(missing)}", flush=True)
        print("  Run the init sequence (/dataverse:init) to create .env.", flush=True)
        sys.exit(1)

    try:
        from azure.identity import (
            AzureCliCredential,
            CertificateCredential,
            ClientSecretCredential,
        )
    except ImportError:
        print("ERROR: azure-identity not installed. Run: pip install --upgrade azure-identity", flush=True)
        sys.exit(1)

    # Tier 1: Service principal. Terminal -- CI must fail fast, never fall to an
    # interactive prompt that would hang an unattended run.
    if client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        return _credential

    # Tier 2: Certificate-based service principal. Terminal for the same reason.
    if client_id and certificate_path:
        path = Path(certificate_path)
        if not path.exists():
            print(
                f"ERROR: CLIENT_CERTIFICATE_PATH does not exist: {certificate_path}",
                flush=True,
            )
            sys.exit(1)
        if not path.is_file() or not os.access(path, os.R_OK):
            print(
                f"ERROR: CLIENT_CERTIFICATE_PATH is not a readable file: {certificate_path}",
                flush=True,
            )
            sys.exit(1)

        try:
            _credential = CertificateCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                certificate_path=str(path),
                password=certificate_password,
                send_certificate_chain=(
                    os.environ.get("CLIENT_SEND_CERTIFICATE_CHAIN") == "1"
                ),
            )
        except ValueError as exc:
            print(
                "ERROR: Could not load CLIENT_CERTIFICATE_PATH. Verify the "
                "certificate format and CLIENT_CERTIFICATE_PASSWORD.",
                flush=True,
            )
            print(f"  {exc}", flush=True)
            sys.exit(1)
        return _credential

    if client_id and not client_secret and not certificate_path:
        print(
            "WARNING: CLIENT_ID is set without CLIENT_SECRET or "
            "CLIENT_CERTIFICATE_PATH.",
            flush=True,
        )
        print(
            "  Falling back to shared cache / device code flow.",
            flush=True,
        )

    if not client_id and (client_secret or certificate_path):
        configured = (
            "CLIENT_SECRET" if client_secret else "CLIENT_CERTIFICATE_PATH"
        )
        print(
            f"WARNING: {configured} is set without CLIENT_ID.",
            flush=True,
        )
        print(
            "  Falling back to shared cache / device code flow.",
            flush=True,
        )

    # No service principal -> silent tiers, then a single host-gated interactive
    # tier used ONLY if every silent tier is unavailable (issue #108: never
    # strand, and never prompt when a silent path works).
    silent_tiers = []

    # Tier 3: Shared DataverseCLI MSAL cache (populated by `dataverse auth
    # create`; same client ID as the @microsoft/dataverse MCP proxy). Probed at
    # build time so it is only selected when it actually yields a token.
    shared = _build_shared_msal_cache()
    if shared is not None:
        app, accounts = shared
        silent_tiers.append(("shared-cache", _MsalSharedCacheCredential(app, accounts)))

    # Tier 4: Azure CLI (`az login`). Scoped to TENANT_ID; AzureCliCredential
    # raises CredentialUnavailableError when az is absent / not logged in, so it
    # is free when unused and a high-value silent win when present.
    silent_tiers.append(("azure-cli", AzureCliCredential(tenant_id=tenant_id)))

    silent = _SilentChain(silent_tiers)

    def _interactive_builder():
        cred, _kind = _build_interactive_tier(tenant_id)
        return cred

    _credential = _FallbackCredential(silent, _interactive_builder)
    return _credential


_auth_record_saved = False


def get_token(scope=None):
    """
    Acquire a raw access token string for the Dataverse environment.

    Resolution order is set by ``_get_credential()``: service principal, then
    the silent chain (shared DataverseCLI cache, then az CLI), then a single
    host-gated interactive tier used only if every silent tier is unavailable.
    The interactive tier persists an AuthenticationRecord on first login so
    subsequent processes refresh silently.

    :param scope: OAuth2 scope. Defaults to "{DATAVERSE_URL}/.default".
    :returns: Access token string suitable for a Bearer Authorization header.
    """
    load_env()
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not scope:
        scope = f"{dataverse_url}/.default"

    credential = _get_credential()

    try:
        token = credential.get_token(scope)
    except Exception as e:
        print(f"ERROR: Failed to acquire access token: {e}", flush=True)
        print("  Check your network connection, credentials, and .env configuration.", flush=True)
        print("  Tip: run `python scripts/auth.py --diagnose` to see which credential", flush=True)
        print("  tiers are available, or `dataverse auth create --environment "
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
    """Return the plugin version for telemetry attribution.

    Sourced from DATAVERSE_PLUGIN_VERSION, which dv-connect writes into .env from
    the live plugin manifest on every connect (Step 0 / Step 3). The deployed
    layout copies this file to <project>/scripts/auth.py -- away from the plugin
    manifest -- so a manifest path relative to __file__ is unreliable here; the
    env var, refreshed at connect, is the source of truth.
    """
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


def _run_diagnose():
    """Print a per-tier credential availability matrix WITHOUT triggering any
    interactive prompt. Turns an auth hang / bare exit-1 into a self-service
    report of which tiers are available and which one would serve the next call.
    (Issue #108: give stranded users a diagnosis, not a dead end.)
    """
    load_env()
    tenant_id = os.environ.get("TENANT_ID")
    url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    scope = _dataverse_scope()
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")

    print(f"Dataverse auth diagnosis for {url or '<DATAVERSE_URL unset>'}")
    print(
        f"  tenant={tenant_id or '<TENANT_ID unset>'}  host={sys.platform}  "
        f"browser={_host_has_browser()}  "
        f"workspace-cache={'on' if os.environ.get('DATAVERSE_TOKEN_CACHE_DIR') else 'off'}"
    )
    print("")

    rows = []  # (tier, status, detail)

    if client_id and client_secret:
        rows.append(("service-principal", "CONFIGURED", "terminal -- used exclusively, no interactive fallback"))
    else:
        rows.append(("service-principal", "not set", "set CLIENT_ID + CLIENT_SECRET for unattended auth"))

    try:
        shared = _build_shared_msal_cache()
        if shared is not None:
            rows.append(("shared-cache", "AVAILABLE", "`dataverse auth create` cache yields a silent token"))
        else:
            rows.append(("shared-cache", "unavailable", "no cache / no account / silent miss -- run `dataverse auth create`"))
    except Exception as e:  # noqa: BLE001
        rows.append(("shared-cache", "error", type(e).__name__))

    try:
        from azure.identity import AzureCliCredential, CredentialUnavailableError
        try:
            cred = AzureCliCredential(tenant_id=tenant_id)
            if scope:
                cred.get_token(scope)
                rows.append(("azure-cli", "AVAILABLE", "`az login` yields a silent token for this tenant"))
            else:
                rows.append(("azure-cli", "unknown", "DATAVERSE_URL unset -- cannot probe"))
        except CredentialUnavailableError:
            rows.append(("azure-cli", "unavailable", "az not installed or not logged in -- run `az login`"))
        except Exception as e:  # noqa: BLE001
            rows.append(("azure-cli", "skipped", type(e).__name__))
    except ImportError:
        rows.append(("azure-cli", "n/a", "azure-identity not installed"))

    if _should_use_workspace_cache() is not None:
        kind = "workspace-device-code"
    elif _host_has_browser():
        kind = "interactive-browser"
    else:
        kind = "device-code"
    rows.append(("interactive", kind, "used only if every silent tier above is unavailable"))

    width = max(len(t) for t, _, _ in rows)
    for tier, status, detail in rows:
        print(f"  {tier.ljust(width)}  {status.ljust(12)}  {detail}")

    silent_ok = any(s in ("CONFIGURED", "AVAILABLE") for _, s, _ in rows[:3])
    print("")
    if silent_ok:
        print("Result: a silent tier is available -- normal calls will not prompt.")
    else:
        print(f"Result: no silent tier -- the next call uses the '{kind}' interactive tier.")


def _run_ping():
    """Lightweight reachability check: token + one HTTP call, no SDK import.

    Uses only stdlib (urllib) and the credential chain (which needs msal or
    azure-identity -- at least one is typically installed globally even before
    pip runs in a fresh workspace). Writes .env and copies auth.py to scripts/
    if missing, so a successful ping makes the workspace ready for SDK use
    after pip install.
    """
    import shutil
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    load_env()
    url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    tenant_id = os.environ.get("TENANT_ID")

    if not url or not tenant_id:
        print("PING FAILED: no DATAVERSE_URL or TENANT_ID (no .env, no user-level config).", flush=True)
        sys.exit(1)

    # Acquire a token via the credential chain (shared CLI cache, az, interactive).
    # _get_credential needs azure-identity or msal; if neither is installed, fail cleanly.
    try:
        token = get_token()
    except SystemExit:
        print("PING FAILED: could not acquire a token (azure-identity or msal may not be installed).", flush=True)
        sys.exit(1)

    # One raw HTTP call to verify the org is reachable.
    try:
        req = Request(f"{url}/api/data/v9.2/WhoAmI")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/json")
        resp = urlopen(req, timeout=20)
        resp.read()
    except HTTPError as e:
        print(f"PING FAILED: {url} returned HTTP {e.code}.", flush=True)
        sys.exit(2)
    except (URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        print(f"PING FAILED: {url} unreachable ({reason}).", flush=True)
        sys.exit(2)

    # Workspace bootstrap: write .env and copy auth.py if missing.
    workspace = Path.cwd()
    env_path = workspace / ".env"
    if not env_path.exists():
        env_path.write_text(f"DATAVERSE_URL={url}\nTENANT_ID={tenant_id}\n", encoding="utf-8")
    dest = workspace / "scripts" / "auth.py"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve(), dest)
    gitignore = workspace / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    for entry in (".env", ".dataverse/"):
        if entry not in existing:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write(f"\n{entry}\n")

    _save_user_config()
    print(f"REACHABLE: {url}", flush=True)


def _run_bootstrap(url):
    """One-command workspace setup from a Dataverse org URL.

    Probes the URL for tenant ID via WWW-Authenticate, writes .env, copies
    auth.py to scripts/, and saves to user-level config. Uses only stdlib
    (urllib) so it works before pip install.
    """
    import shutil
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    url = url.rstrip("/")
    if not url.startswith("https://"):
        print(f"ERROR: URL must start with https:// (got: {url})", flush=True)
        sys.exit(1)

    print(f"Probing {url} for tenant ID...", flush=True)
    www_auth = ""
    try:
        req = Request(f"{url}/api/data/v9.2/", method="GET")
        req.add_header("Accept", "application/json")
        urlopen(req, timeout=20)
        print("ERROR: Unexpected 200 from unauthenticated probe.", flush=True)
        sys.exit(1)
    except HTTPError as e:
        www_auth = e.headers.get("WWW-Authenticate", "")
    except URLError as e:
        print(f"ERROR: Cannot reach {url}: {e.reason}", flush=True)
        sys.exit(1)

    match = re.search(r"login\.microsoftonline\.com/([^/,\s]+)", www_auth)
    if not match:
        print(f"ERROR: Could not discover tenant from {url}", flush=True)
        print(f"  WWW-Authenticate: {www_auth[:200]}", flush=True)
        sys.exit(1)
    tenant_id = match.group(1)

    workspace = Path.cwd()
    env_path = workspace / ".env"
    env_path.write_text(
        f"DATAVERSE_URL={url}\nTENANT_ID={tenant_id}\n", encoding="utf-8",
    )

    scripts_dir = workspace / "scripts"
    dest = scripts_dir / "auth.py"
    if not dest.exists():
        scripts_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).resolve(), dest)

    gitignore = workspace / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    missing = [e for e in (".env", ".dataverse/") if e not in existing]
    if missing:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(missing) + "\n")

    os.environ["DATAVERSE_URL"] = url
    os.environ["TENANT_ID"] = tenant_id
    _save_user_config()

    print(f"BOOTSTRAPPED: {url} (tenant {tenant_id})", flush=True)
    print(f"  .env: {env_path}", flush=True)
    print(f"  user config: {_USER_CONFIG_PATH}", flush=True)
    print("  Next: pip install deps (if needed), then: python scripts/auth.py --check", flush=True)


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
    parser.add_argument(
        "--ping",
        action="store_true",
        help="Lightweight reachability check using only stdlib + msal (no SDK import). "
        "Loads user-level config or .env, acquires a token via the credential chain, makes "
        "one raw HTTP call to verify the org is reachable. Exit 0 = reachable + prints the "
        "org URL, 1 = no config or no token, 2 = token OK but org unreachable. Also writes "
        ".env and copies auth.py to scripts/ if missing.",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print which credential tiers (service principal / shared cache / az CLI / "
        "interactive) are available, WITHOUT prompting. Use when auth hangs or fails to see "
        "why and which tier would serve the next call.",
    )
    parser.add_argument(
        "--bootstrap", metavar="URL",
        help="One-shot setup: probe URL for tenant, write .env, copy auth.py to scripts/, "
        "save to user-level config. Does not authenticate -- run --check after pip install.",
    )
    args = parser.parse_args()

    if args.diagnose:
        _run_diagnose()
        sys.exit(0)

    if args.bootstrap:
        _run_bootstrap(args.bootstrap)
        sys.exit(0)

    if args.ping:
        _run_ping()
        sys.exit(0)

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
        _save_user_config()
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

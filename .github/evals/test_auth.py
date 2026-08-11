"""
Unit tests for the auth.py credential chain (issue #108).

Hermetic: fakes azure-identity / azure-core so the tests run with no external
dependencies. Run standalone (`python .github/evals/test_auth.py`) or via pytest.

Guards the #108 invariants:
  - the shared-cache credential FALLS THROUGH (CredentialUnavailableError),
    it does not hard-raise, when silent acquisition misses (defect 1);
  - the silent chain skips unavailable OR errored tiers and only raises when
    every tier is exhausted;
  - the interactive tier is built ONLY when every silent tier is unavailable,
    and is built once;
  - the interactive tier is host-gated (workspace / browser / device-code);
  - a configured service principal is terminal (no interactive fallback -- CI
    must fail fast).
"""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS = Path(__file__).resolve().parent.parent / "plugins" / "dataverse" / "scripts"
sys.path.insert(0, str(_SCRIPTS))
import auth  # noqa: E402  (import after sys.path insert)


# --- fakes for azure-identity / azure-core -------------------------------

class _CredUnavailable(Exception):
    """Stand-in for azure.identity.CredentialUnavailableError."""


class _AccessToken:
    def __init__(self, token, expires_on):
        self.token = token
        self.expires_on = expires_on


class _FakeClientSecret:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_token(self, *scopes, **kwargs):
        return _AccessToken("sp-token", 9999999999)


class _FakeAzureCli:
    # "unavailable" (not logged in) | "token" | "error" (e.g. wrong tenant)
    behavior = "unavailable"

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_token(self, *scopes, **kwargs):
        if _FakeAzureCli.behavior == "token":
            return _AccessToken("azcli-token", 9999999999)
        if _FakeAzureCli.behavior == "error":
            raise RuntimeError("az logged into a different tenant")
        raise _CredUnavailable("az not logged in")


class _FakeRecord:
    def serialize(self):
        return "{}"

    @classmethod
    def deserialize(cls, _s):
        return cls()


class _FakeInteractiveBrowser:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def authenticate(self, **kwargs):
        return _FakeRecord()

    def get_token(self, *scopes, **kwargs):
        return _AccessToken("browser-token", 9999999999)


class _FakeDeviceCode:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def authenticate(self, **kwargs):
        return _FakeRecord()

    def get_token(self, *scopes, **kwargs):
        return _AccessToken("device-code-token", 9999999999)


class _FakeCacheOpts:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _install_azure_fakes():
    """Inject fake azure.* modules into sys.modules (auth imports them lazily)."""
    azure = types.ModuleType("azure")
    azure_core = types.ModuleType("azure.core")
    azure_core_creds = types.ModuleType("azure.core.credentials")
    azure_core_creds.AccessToken = _AccessToken
    azure_identity = types.ModuleType("azure.identity")
    azure_identity.CredentialUnavailableError = _CredUnavailable
    azure_identity.ClientSecretCredential = _FakeClientSecret
    azure_identity.AzureCliCredential = _FakeAzureCli
    azure_identity.InteractiveBrowserCredential = _FakeInteractiveBrowser
    azure_identity.DeviceCodeCredential = _FakeDeviceCode
    azure_identity.AuthenticationRecord = _FakeRecord
    azure_identity.TokenCachePersistenceOptions = _FakeCacheOpts
    azure.core = azure_core
    azure_core.credentials = azure_core_creds
    azure.identity = azure_identity
    return {
        "azure": azure,
        "azure.core": azure_core,
        "azure.core.credentials": azure_core_creds,
        "azure.identity": azure_identity,
    }


class _FakeMsalApp:
    """Minimal msal PublicClientApplication stand-in for _MsalSharedCacheCredential."""

    def __init__(self, silent_result):
        self._silent = silent_result

    def acquire_token_silent(self, scopes, account=None, claims_challenge=None):
        return self._silent


# --- fixtures ------------------------------------------------------------

class _AuthTestBase(unittest.TestCase):
    def setUp(self):
        _FakeAzureCli.behavior = "unavailable"
        self._added = _install_azure_fakes()
        for name, module in self._added.items():
            sys.modules[name] = module
        auth._credential = None

    def tearDown(self):
        for name in self._added:
            sys.modules.pop(name, None)
        auth._credential = None


# --- tier stubs used by chain tests --------------------------------------

class _RaiseUnavailable:
    def get_token(self, *scopes, **kwargs):
        raise _CredUnavailable("unavailable")


class _RaiseGeneric:
    def get_token(self, *scopes, **kwargs):
        raise RuntimeError("boom")


class _ReturnToken:
    def __init__(self, token="ok"):
        self._token = token

    def get_token(self, *scopes, **kwargs):
        return _AccessToken(self._token, 9999999999)


# --- tests ---------------------------------------------------------------

class SharedCacheFallThrough(_AuthTestBase):
    def test_silent_miss_raises_credential_unavailable_not_runtime_error(self):
        # Defect 1: an account can exist while the silent token misses. The
        # credential MUST fall through (CredentialUnavailableError), not raise a
        # terminal RuntimeError that strands the user.
        cred = auth._MsalSharedCacheCredential(_FakeMsalApp(None), ["account"])
        with self.assertRaises(_CredUnavailable):
            cred.get_token("scope")

    def test_silent_hit_returns_access_token(self):
        app = _FakeMsalApp({"access_token": "abc", "expires_in": 60})
        cred = auth._MsalSharedCacheCredential(app, ["account"])
        token = cred.get_token("scope")
        self.assertEqual(token.token, "abc")


class SilentChainSemantics(_AuthTestBase):
    def test_all_unavailable_raises(self):
        chain = auth._SilentChain([("a", _RaiseUnavailable()), ("b", _RaiseUnavailable())])
        with self.assertRaises(_CredUnavailable):
            chain.get_token("scope")

    def test_generic_error_is_skipped_not_fatal(self):
        # A convenience tier that errors (e.g. az on the wrong tenant) must not
        # strand the chain -- the next tier still wins.
        chain = auth._SilentChain([("a", _RaiseGeneric()), ("b", _ReturnToken("second"))])
        self.assertEqual(chain.get_token("scope").token, "second")

    def test_first_success_wins(self):
        chain = auth._SilentChain([("a", _ReturnToken("first")), ("b", _ReturnToken("second"))])
        self.assertEqual(chain.get_token("scope").token, "first")


class FallbackCredentialBehavior(_AuthTestBase):
    def test_interactive_not_built_when_silent_works(self):
        calls = []

        def builder():
            calls.append(1)
            return _ReturnToken("interactive")

        cred = auth._FallbackCredential(_ReturnToken("silent"), builder)
        self.assertEqual(cred.get_token("scope").token, "silent")
        self.assertEqual(calls, [])  # no prompt when a silent tier works

    def test_interactive_built_once_when_silent_exhausted(self):
        calls = []

        def builder():
            calls.append(1)
            return _ReturnToken("interactive")

        silent = auth._SilentChain([("a", _RaiseUnavailable())])
        cred = auth._FallbackCredential(silent, builder)
        self.assertEqual(cred.get_token("scope").token, "interactive")
        cred.get_token("scope")  # second call reuses the built tier
        self.assertEqual(calls, [1])


class HostBrowserDetection(_AuthTestBase):
    def test_windows_console_has_browser(self):
        with mock.patch.object(auth.sys, "platform", "win32"):
            with mock.patch.dict(os.environ, {"SESSIONNAME": "Console"}, clear=True):
                self.assertTrue(auth._host_has_browser())

    def test_windows_rdp_has_browser(self):
        with mock.patch.object(auth.sys, "platform", "win32"):
            with mock.patch.dict(os.environ, {"SESSIONNAME": "RDP-Tcp#0"}, clear=True):
                self.assertTrue(auth._host_has_browser())

    def test_mac_desktop_has_browser(self):
        with mock.patch.object(auth.sys, "platform", "darwin"):
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertTrue(auth._host_has_browser())

    def test_mac_ssh_is_headless(self):
        with mock.patch.object(auth.sys, "platform", "darwin"):
            with mock.patch.dict(os.environ, {"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}, clear=True):
                self.assertFalse(auth._host_has_browser())

    def test_mac_ssh_tty_is_headless(self):
        with mock.patch.object(auth.sys, "platform", "darwin"):
            with mock.patch.dict(os.environ, {"SSH_TTY": "/dev/ttys000"}, clear=True):
                self.assertFalse(auth._host_has_browser())

    def test_ci_env_is_headless_even_on_windows(self):
        # Regression guard (#110 review): a headless CI runner on win/mac has no
        # browser -- must route to device-code, not crash on InteractiveBrowser.
        for platform in ("win32", "darwin"):
            for ci_var in ("CI", "GITHUB_ACTIONS", "TF_BUILD", "BUILD_BUILDID"):
                with mock.patch.object(auth.sys, "platform", platform):
                    with mock.patch.dict(
                        os.environ, {ci_var: "true", "SESSIONNAME": "Console"}, clear=True
                    ):
                        self.assertFalse(auth._host_has_browser())

    def test_ci_false_value_is_not_treated_as_ci(self):
        # CI="false" must not be read as headless (avoid the truthy-string trap).
        with mock.patch.object(auth.sys, "platform", "win32"):
            with mock.patch.dict(
                os.environ, {"CI": "false", "SESSIONNAME": "Console"}, clear=True
            ):
                self.assertTrue(auth._host_has_browser())

    def test_windows_service_session_is_headless(self):
        with mock.patch.object(auth.sys, "platform", "win32"):
            with mock.patch.dict(os.environ, {"SESSIONNAME": "Services"}, clear=True):
                self.assertFalse(auth._host_has_browser())

    def test_headless_linux_has_no_browser(self):
        with mock.patch.object(auth.sys, "platform", "linux"):
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertFalse(auth._host_has_browser())

    def test_linux_with_display_has_browser(self):
        with mock.patch.object(auth.sys, "platform", "linux"):
            with mock.patch.dict(os.environ, {"DISPLAY": ":0"}, clear=True):
                self.assertTrue(auth._host_has_browser())


class InteractiveTierSelection(_AuthTestBase):
    def test_workspace_cache_opt_in_wins(self):
        sentinel = object()
        with mock.patch.object(auth, "_is_ci", lambda: False):
            with mock.patch.object(auth, "_workspace_token_cache_path", lambda: Path("cache.dat")):
                with mock.patch.object(
                    auth, "_build_workspace_device_code_credential", lambda path, tenant: sentinel
                ):
                    cred, kind = auth._build_interactive_tier("tenant")
        self.assertIs(cred, sentinel)
        self.assertEqual(kind, "workspace-device-code")

    def test_desktop_uses_interactive_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "record.json"
            with mock.patch.object(auth, "_is_ci", lambda: False):
                with mock.patch.object(auth, "_workspace_token_cache_path", lambda: None):
                    with mock.patch.object(auth, "_host_has_browser", lambda: True):
                        with mock.patch.object(auth, "_AUTH_RECORD_PATH", record_path):
                            cred, kind = auth._build_interactive_tier("tenant")
        self.assertIsInstance(cred, _FakeInteractiveBrowser)
        self.assertEqual(kind, "interactive-browser")

    def test_device_code_when_no_workspace_cache(self):
        # When no workspace cache can be built (opt-out, or path build failure),
        # a headless host falls back to the legacy device-code credential.
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "record.json"
            with mock.patch.object(auth, "_is_ci", lambda: False):
                with mock.patch.object(auth, "_workspace_token_cache_path", lambda: None):
                    with mock.patch.object(auth, "_host_has_browser", lambda: False):
                        with mock.patch.object(auth, "_AUTH_RECORD_PATH", record_path):
                            cred, kind = auth._build_interactive_tier("tenant")
        self.assertIsInstance(cred, _FakeDeviceCode)
        self.assertEqual(kind, "device-code")


class GetCredentialShape(_AuthTestBase):
    def test_service_principal_is_terminal(self):
        env = {
            "TENANT_ID": "t", "DATAVERSE_URL": "https://x.crm.dynamics.com",
            "CLIENT_ID": "cid", "CLIENT_SECRET": "sec",
        }
        with mock.patch.object(auth, "load_env", lambda: None):
            with mock.patch.dict(os.environ, env, clear=True):
                cred = auth._get_credential()
        self.assertIsInstance(cred, _FakeClientSecret)  # terminal, no fallback wrapper

    def test_no_sp_builds_fallback_with_azure_cli_tier(self):
        env = {"TENANT_ID": "t", "DATAVERSE_URL": "https://x.crm.dynamics.com"}
        with mock.patch.object(auth, "load_env", lambda: None):
            with mock.patch.object(auth, "_build_shared_msal_cache", lambda: None):
                with mock.patch.dict(os.environ, env, clear=True):
                    cred = auth._get_credential()
        self.assertIsInstance(cred, auth._FallbackCredential)
        tier_names = [name for name, _c in cred._silent._tiers]
        self.assertIn("azure-cli", tier_names)

    def test_no_sp_includes_shared_cache_tier_when_present(self):
        env = {"TENANT_ID": "t", "DATAVERSE_URL": "https://x.crm.dynamics.com"}
        fake_shared = (_FakeMsalApp({"access_token": "x", "expires_in": 60}), ["account"])
        with mock.patch.object(auth, "load_env", lambda: None):
            with mock.patch.object(auth, "_build_shared_msal_cache", lambda: fake_shared):
                with mock.patch.dict(os.environ, env, clear=True):
                    cred = auth._get_credential()
        tier_names = [name for name, _c in cred._silent._tiers]
        self.assertEqual(tier_names[0], "shared-cache")
        self.assertIn("azure-cli", tier_names)


class BuildSharedCacheAuthorityProbe(_AuthTestBase):
    """Regression guard for issue #108 defect 2: `dataverse auth create` may write
    the shared cache under the `organizations` authority, so a tenant-only probe
    misses it and strands the user. _build_shared_msal_cache must probe BOTH.
    """

    class _ProbeApp:
        def __init__(self, has_token):
            self._has_token = has_token

        def get_accounts(self):
            return ["account"]

        def acquire_token_silent(self, scopes, account=None, claims_challenge=None):
            if self._has_token:
                return {"access_token": "x", "expires_in": 60}
            return None

    def _run(self, token_authority_substr):
        seen = []

        def _fake_pca(client_id, authority, token_cache):
            seen.append(authority)
            return self._ProbeApp(token_authority_substr in authority)

        fake_msal = types.ModuleType("msal")
        fake_msal.PublicClientApplication = _fake_pca
        fake_msal_ext = types.ModuleType("msal_extensions")
        fake_msal_ext.PersistedTokenCache = lambda persistence: object()

        env = {"TENANT_ID": "t", "DATAVERSE_URL": "https://x.crm.dynamics.com"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(auth, "_shared_cache_persistences", lambda: [object()]):
                with mock.patch.dict(
                    sys.modules, {"msal": fake_msal, "msal_extensions": fake_msal_ext}
                ):
                    result = auth._build_shared_msal_cache()
        return result, seen

    def test_probes_both_authorities_and_finds_organizations_token(self):
        # Cache only yields a token under `organizations`; the dual probe must
        # still find it after the tenant authority misses.
        result, seen = self._run(token_authority_substr="organizations")
        self.assertIsNotNone(result)
        self.assertIn("https://login.microsoftonline.com/t", seen)
        self.assertIn("https://login.microsoftonline.com/organizations", seen)

    def test_tenant_authority_is_tried_first(self):
        # When the tenant authority yields a token, it wins without probing
        # `organizations` (tenant-preferred ordering).
        result, seen = self._run(token_authority_substr="/t")
        self.assertIsNotNone(result)
        self.assertEqual(seen[0], "https://login.microsoftonline.com/t")


class PluginVersionAttribution(_AuthTestBase):
    def test_reads_from_env_in_deployed_layout(self):
        # In the DEPLOYED layout dv-connect copies auth.py to <project>/scripts/,
        # away from the plugin manifest, so _plugin_version reads the env var that
        # dv-connect refreshes on connect -- not a manifest path relative to
        # __file__. Assert the env var is the source of truth.
        with mock.patch.dict(os.environ, {"DATAVERSE_PLUGIN_VERSION": "1.11.0"}, clear=True):
            self.assertEqual(auth._plugin_version(), "1.11.0")

    def test_defaults_to_unknown_when_env_absent(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(auth._plugin_version(), "unknown")


class SilentChainReasons(_AuthTestBase):
    def test_reasons_recorded_on_exhaustion(self):
        chain = auth._SilentChain([("a", _RaiseUnavailable()), ("b", _RaiseGeneric())])
        with self.assertRaises(_CredUnavailable):
            chain.get_token("scope")
        self.assertEqual(len(chain.last_reasons), 2)
        self.assertIn("a: unavailable", chain.last_reasons)


class CiFailFast(_AuthTestBase):
    def test_ci_without_service_principal_raises_before_interactive(self):
        # CI + no SP -> _build_interactive_tier must fail fast, not enter a
        # 15-minute device-code hang.
        with mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True):
            with self.assertRaises(RuntimeError):
                auth._build_interactive_tier("tenant")


class _ClaimsProbeApp:
    """msal app stand-in that records the claims_challenge it receives."""

    def __init__(self, has_account, silent_result):
        self._has_account = has_account
        self._silent = silent_result
        self.seen_claims = "UNSET"

    def get_accounts(self):
        return ["acct"] if self._has_account else []

    def acquire_token_silent(self, scopes, account=None, claims_challenge=None):
        self.seen_claims = claims_challenge
        return self._silent

    def initiate_device_flow(self, scopes=None):
        return {"user_code": "ABC", "verification_uri": "https://x", "expires_in": 900}

    def acquire_token_by_device_flow(self, flow, claims_challenge=None):
        self.seen_claims = claims_challenge
        return {"access_token": "device-tok", "expires_in": 60}


class DeviceCodeCredentialBehavior(_AuthTestBase):
    def test_silent_hit_skips_device_flow(self):
        app = _ClaimsProbeApp(has_account=True, silent_result={"access_token": "s", "expires_in": 60})
        cred = auth._MsalDeviceCodeCredential(app)
        self.assertEqual(cred.get_token("scope").token, "s")

    def test_device_flow_used_when_no_silent(self):
        app = _ClaimsProbeApp(has_account=False, silent_result=None)
        cred = auth._MsalDeviceCodeCredential(app)
        self.assertEqual(cred.get_token("scope").token, "device-tok")

    def test_forwards_claims_challenge_to_silent(self):
        app = _ClaimsProbeApp(has_account=True, silent_result={"access_token": "s", "expires_in": 60})
        cred = auth._MsalDeviceCodeCredential(app)
        cred.get_token("scope", claims="CH")
        self.assertEqual(app.seen_claims, "CH")


class SharedCacheClaimsForwarding(_AuthTestBase):
    def test_forwards_claims_challenge(self):
        app = _ClaimsProbeApp(has_account=True, silent_result={"access_token": "s", "expires_in": 60})
        cred = auth._MsalSharedCacheCredential(app, ["acct"])
        cred.get_token("scope", claims="CH")
        self.assertEqual(app.seen_claims, "CH")


class WorkspaceTokenCachePath(_AuthTestBase):
    def test_relative_cache_dir_is_cwd_independent(self):
        # R2: a relative DATAVERSE_TOKEN_CACHE_DIR resolves to the same path
        # regardless of the current working directory (anchored to the workspace
        # root -- auth.py's parent.parent -- not cwd).
        with tempfile.TemporaryDirectory() as anchor, \
                tempfile.TemporaryDirectory() as d1, \
                tempfile.TemporaryDirectory() as d2:
            fake_auth = str(Path(anchor) / "scripts" / "auth.py")
            results = []
            with mock.patch.object(auth, "__file__", fake_auth):
                for d in (d1, d2):
                    cwd = os.getcwd()
                    try:
                        os.chdir(d)
                        with mock.patch.dict(
                            os.environ, {"DATAVERSE_TOKEN_CACHE_DIR": ".dvcache"}, clear=True
                        ):
                            results.append(auth._workspace_token_cache_path())
                    finally:
                        os.chdir(cwd)
        self.assertIsNotNone(results[0])
        self.assertEqual(results[0], results[1])


class WorkspaceCacheAutoDefault(_AuthTestBase):
    """#117: on a headless, non-CI host with no explicit DATAVERSE_TOKEN_CACHE_DIR,
    the cache auto-defaults into <workspace>/.dataverse so device code is once per
    conversation. Desktop / CI keep the OS default cache; an opt-out value disables it.
    """

    def _resolve(self, env, browser, ci=False):
        with tempfile.TemporaryDirectory() as anchor:
            (Path(anchor) / "scripts").mkdir(parents=True)
            fake_auth = str(Path(anchor) / "scripts" / "auth.py")
            with mock.patch.object(auth, "__file__", fake_auth), \
                    mock.patch.object(auth, "_host_has_browser", lambda: browser), \
                    mock.patch.object(auth, "_is_ci", lambda: ci), \
                    mock.patch.dict(os.environ, env, clear=True):
                return auth._workspace_token_cache_path()

    def test_headless_no_env_defaults_to_workspace(self):
        path = self._resolve({}, browser=False)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent.name, ".dataverse")
        self.assertEqual(path.name, "tokencache_msalv3.dat")

    def test_desktop_no_env_keeps_os_cache(self):
        self.assertIsNone(self._resolve({}, browser=True))

    def test_ci_no_env_keeps_os_cache(self):
        self.assertIsNone(self._resolve({}, browser=False, ci=True))

    def test_opt_out_keeps_os_cache_even_headless(self):
        for val in ("off", "false", "0", "no", "none", "OFF"):
            self.assertIsNone(
                self._resolve({"DATAVERSE_TOKEN_CACHE_DIR": val}, browser=False),
                msg=f"{val!r} should opt out of the workspace cache",
            )

    def test_explicit_env_used_even_on_headless(self):
        path = self._resolve({"DATAVERSE_TOKEN_CACHE_DIR": "mycache"}, browser=False)
        self.assertIsNotNone(path)
        self.assertEqual(path.parent.name, "mycache")


class WorkspaceCacheDecision(_AuthTestBase):
    """The pure _should_use_workspace_cache() predicate is the single source of truth
    for both _workspace_token_cache_path (path building) and _run_diagnose (tier
    reporting), so the two cannot drift.
    """

    def _decide(self, env, browser, ci=False):
        with mock.patch.object(auth, "_host_has_browser", lambda: browser), \
                mock.patch.object(auth, "_is_ci", lambda: ci), \
                mock.patch.dict(os.environ, env, clear=True):
            return auth._should_use_workspace_cache()

    def test_explicit_env_regardless_of_host(self):
        self.assertEqual(self._decide({"DATAVERSE_TOKEN_CACHE_DIR": ".dv"}, browser=True), "explicit")
        self.assertEqual(self._decide({"DATAVERSE_TOKEN_CACHE_DIR": ".dv"}, browser=False), "explicit")

    def test_headless_no_env_defaults(self):
        self.assertEqual(self._decide({}, browser=False), "default")

    def test_desktop_no_env_is_none(self):
        self.assertIsNone(self._decide({}, browser=True))

    def test_ci_no_env_is_none(self):
        self.assertIsNone(self._decide({}, browser=False, ci=True))

    def test_opt_out_is_none_even_headless(self):
        for val in ("off", "false", "0", "no", "none", "OFF"):
            self.assertIsNone(self._decide({"DATAVERSE_TOKEN_CACHE_DIR": val}, browser=False), msg=val)


if __name__ == "__main__":
    unittest.main(verbosity=2)

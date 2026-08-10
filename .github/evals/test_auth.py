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

    def acquire_token_silent(self, scopes, account=None):
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
            with mock.patch.object(auth, "_workspace_token_cache_path", lambda: None):
                with mock.patch.object(auth, "_host_has_browser", lambda: True):
                    with mock.patch.object(auth, "_AUTH_RECORD_PATH", record_path):
                        cred, kind = auth._build_interactive_tier("tenant")
        self.assertIsInstance(cred, _FakeInteractiveBrowser)
        self.assertEqual(kind, "interactive-browser")

    def test_headless_uses_device_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_path = Path(tmp) / "record.json"
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

        def acquire_token_silent(self, scopes, account=None):
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
    def test_reads_manifest_not_stale_env(self):
        # Regression guard: telemetry attribution must reflect the INSTALLED
        # plugin version (from the packaged plugin.json), not a stale
        # DATAVERSE_PLUGIN_VERSION that a previous install left in .env.
        with mock.patch.dict(os.environ, {"DATAVERSE_PLUGIN_VERSION": "1.8.0"}, clear=True):
            version = auth._plugin_version()
        self.assertNotEqual(version, "1.8.0")
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main(verbosity=2)

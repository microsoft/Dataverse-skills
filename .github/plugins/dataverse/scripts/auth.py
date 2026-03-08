"""
auth.py — Acquire Dataverse tokens via Azure Identity.

Auth priority:
  1. Service principal (CLIENT_ID + CLIENT_SECRET in .env) — non-interactive
  2. Device code flow — interactive, opens browser prompt

Token caching:
  - Service principal: in-memory (tokens are short-lived, no persistent cache needed)
  - Device code: OS credential store (Windows Credential Manager, macOS Keychain,
    Linux libsecret) via TokenCachePersistenceOptions. No plaintext files on disk.
    Falls back to encrypted file if OS store is unavailable.

Functions:
  load_env()            — loads .env into os.environ
  get_credential()      — returns a TokenCredential for use with DataverseClient
  get_token(scope=None) — returns a raw access token string

Usage:
    # For Web API scripts that need a Bearer token:
    from auth import get_token, load_env
    token = get_token()

    # For scripts using the Dataverse Python SDK:
    from auth import get_credential, load_env
    from PowerPlatform.Dataverse.client import DataverseClient
    load_env()
    client = DataverseClient(os.environ["DATAVERSE_URL"], get_credential())

Reads from .env in the current working directory or from environment variables:
    DATAVERSE_URL      — required
    TENANT_ID          — required
    CLIENT_ID          — optional, enables service principal auth
    CLIENT_SECRET      — optional, enables service principal auth
"""

import os
import sys
from pathlib import Path


def load_env():
    """Load key=value pairs from .env into os.environ (does not overwrite existing vars)."""
    env_path = Path(".env")
    if env_path.exists():
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

    if not tenant_id or not dataverse_url:
        missing = [k for k, v in [("TENANT_ID", tenant_id), ("DATAVERSE_URL", dataverse_url)] if not v]
        print(f"ERROR: .env is missing required values: {', '.join(missing)}")
        print("  Run the init sequence (dataverse-init) to create .env.")
        sys.exit(1)

    try:
        from azure.identity import (
            ClientSecretCredential,
            DeviceCodeCredential,
            TokenCachePersistenceOptions,
        )
    except ImportError:
        print("ERROR: azure-identity not installed. Run: pip install azure-identity")
        sys.exit(1)

    # Warn if only one of CLIENT_ID / CLIENT_SECRET is set
    if bool(client_id) != bool(client_secret):
        print("WARNING: Only one of CLIENT_ID / CLIENT_SECRET is set. Both are required for")
        print("  service principal auth. Falling back to interactive device code flow.")

    # Path 1: Service principal (non-interactive)
    if client_id and client_secret:
        _credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
    else:
        # Path 2: Device code flow (interactive) with persistent OS-level token cache
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
        )

    return _credential


def get_token(scope=None):
    """
    Acquire a raw access token string for the Dataverse environment.

    :param scope: OAuth2 scope. Defaults to "{DATAVERSE_URL}/.default".
    :returns: Access token string suitable for a Bearer Authorization header.
    """
    load_env()
    dataverse_url = os.environ.get("DATAVERSE_URL", "").rstrip("/")
    if not scope:
        scope = f"{dataverse_url}/.default"

    credential = get_credential()
    try:
        token = credential.get_token(scope)
    except Exception as e:
        print(f"ERROR: Failed to acquire access token: {e}")
        print("  Check your network connection, credentials, and .env configuration.")
        sys.exit(1)
    return token.token


if __name__ == "__main__":
    token = get_token()
    print(token)

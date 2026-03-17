"""Shared authentication module for Power BI MCP server and setup wizard.

Handles Azure AD public client flow, token caching, and credential persistence.
Used by both server.py (MCP server) and wizard.py (setup wizard).
"""

import json
import os
import time
from pathlib import Path
from azure.identity import (
    InteractiveBrowserCredential,
    DeviceCodeCredential,
    TokenCachePersistenceOptions,
    AuthenticationRecord
)

# Directories
CACHE_DIR = Path.home() / ".powerbi-mcp"
CACHE_DIR.mkdir(exist_ok=True)
AUTH_RECORD_PATH = CACHE_DIR / "auth_record.json"
TOKEN_CACHE_PATH = CACHE_DIR / "token_cache.bin"

# OAuth scopes (read-only)
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Singleton credential
_credential = None
_token_cache = {}


def get_credential(device_code: bool = False):
    """Get or create credential with persistent cache.

    Args:
        device_code: Use device code flow (for headless/SSH environments).
    """
    global _credential

    if _credential is not None:
        return _credential

    # Default to encrypted storage. Set POWERBI_MCP_ALLOW_UNENCRYPTED=1
    # if your OS doesn't support encrypted credential storage (e.g., some
    # Linux distros without a keyring, or headless Docker containers).
    allow_unencrypted = os.environ.get("POWERBI_MCP_ALLOW_UNENCRYPTED", "0") == "1"
    cache_options = TokenCachePersistenceOptions(
        name="powerbi-mcp",
        allow_unencrypted_storage=allow_unencrypted
    )

    # Check for existing auth record
    auth_record = None
    if AUTH_RECORD_PATH.exists():
        try:
            with open(AUTH_RECORD_PATH, "r") as f:
                auth_data = json.load(f)
                auth_record = AuthenticationRecord.deserialize(json.dumps(auth_data))
        except Exception:
            pass

    if device_code:
        _credential = DeviceCodeCredential(
            cache_persistence_options=cache_options,
            authentication_record=auth_record
        )
    elif auth_record:
        # Reuse existing authentication — no browser popup
        _credential = InteractiveBrowserCredential(
            cache_persistence_options=cache_options,
            authentication_record=auth_record
        )
    else:
        # First time — browser popup required
        _credential = InteractiveBrowserCredential(
            cache_persistence_options=cache_options
        )

    return _credential


def save_auth_record(credential, scope):
    """Save auth record for reuse across sessions."""
    try:
        record = credential.authenticate(scopes=[scope])
        auth_data = json.loads(record.serialize())
        with open(AUTH_RECORD_PATH, "w") as f:
            json.dump(auth_data, f)
    except Exception:
        pass


def get_token(scope, device_code: bool = False):
    """Get token with in-memory caching and 5-minute buffer."""
    global _token_cache

    cache_key = scope
    if cache_key in _token_cache:
        cached = _token_cache[cache_key]
        if cached["expires_on"] > time.time() + 300:
            return cached["token"]

    credential = get_credential(device_code=device_code)
    token = credential.get_token(scope)

    _token_cache[cache_key] = {
        "token": token.token,
        "expires_on": token.expires_on
    }

    save_auth_record(credential, scope)
    return token.token


def get_powerbi_headers(device_code: bool = False):
    """Authorization headers for Power BI REST API."""
    return {
        "Authorization": f"Bearer {get_token(POWERBI_SCOPE, device_code=device_code)}",
        "Content-Type": "application/json"
    }


def get_fabric_headers(device_code: bool = False):
    """Authorization headers for Microsoft Fabric API."""
    return {
        "Authorization": f"Bearer {get_token(FABRIC_SCOPE, device_code=device_code)}",
        "Content-Type": "application/json"
    }

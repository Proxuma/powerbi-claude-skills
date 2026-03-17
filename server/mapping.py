"""Mapping persistence for anonymization sessions.

Stores alias->real_value mappings locally so reports can be deanonymized.
Files are created with 0600 permissions (owner-only read/write).
"""

import base64
import hashlib
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class MappingStore:
    """Manages per-session mapping files in ~/.powerbi-mcp/sessions/."""

    def __init__(self, base_dir: Optional[Path] = None, retention_days: int = 90, encrypt: bool = False):
        self._base_dir = base_dir or (Path.home() / ".powerbi-mcp" / "sessions")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._encrypt = encrypt
        self._fernet = self._init_fernet() if encrypt else None
        self._session_id: Optional[str] = None
        self._current_path: Optional[Path] = None

    def _init_fernet(self):
        """Get or create encryption key from env var or keyring."""
        key_str = os.environ.get("POWERBI_MCP_ENCRYPTION_KEY")
        if key_str:
            key = hashlib.sha256(key_str.encode()).digest()
            return Fernet(base64.urlsafe_b64encode(key))

        try:
            import keyring
            stored_key = keyring.get_password("powerbi-mcp", "mapping-encryption-key")
            if stored_key:
                return Fernet(stored_key.encode())
            new_key = Fernet.generate_key()
            keyring.set_password("powerbi-mcp", "mapping-encryption-key", new_key.decode())
            return Fernet(new_key)
        except Exception as e:
            raise RuntimeError(
                f"Cannot initialize encryption: {e}\n"
                "Set POWERBI_MCP_ENCRYPTION_KEY env var or install a keyring backend."
            ) from e

    @property
    def current_path(self) -> Optional[Path]:
        return self._current_path

    def new_session(self) -> str:
        """Create a new session directory. Returns session ID (UUID4)."""
        self._session_id = str(uuid.uuid4())
        self._current_path = self._base_dir / self._session_id
        self._current_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self._current_path, 0o700)
        return self._session_id

    def save(self, mapping: dict, stats: dict):
        """Save mapping and stats to the current session directory."""
        if not self._current_path:
            raise RuntimeError("No active session. Call new_session() first.")
        data = json.dumps({
            "session_id": self._session_id,
            "created": datetime.now(timezone.utc).isoformat(),
            "mappings": mapping,
            "stats": stats,
        }, indent=2)

        if self._encrypt and self._fernet:
            file_path = self._current_path / "mapping.json.enc"
            encrypted = self._fernet.encrypt(data.encode())
            file_path.write_bytes(encrypted)
        else:
            file_path = self._current_path / "mapping.json"
            with open(file_path, "w") as f:
                f.write(data)

        os.chmod(file_path, 0o600)

        latest = self._base_dir / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(self._current_path)

    def load(self, session_id: str) -> Optional[dict]:
        """Load mapping data for a given session ID."""
        session_dir = self._base_dir / session_id

        enc_path = session_dir / "mapping.json.enc"
        plain_path = session_dir / "mapping.json"

        if enc_path.exists():
            if not self._fernet:
                logger.error("Encrypted mapping found but encryption not configured")
                return None
            try:
                data = self._fernet.decrypt(enc_path.read_bytes())
                return json.loads(data)
            except InvalidToken:
                logger.error(
                    "Cannot decrypt mapping file — encryption key has changed. "
                    "Previous session mappings are unrecoverable."
                )
                return None
        elif plain_path.exists():
            with open(plain_path) as f:
                return json.load(f)
        return None

    def load_latest(self) -> Optional[dict]:
        """Load the most recently saved mapping, or None if no sessions exist."""
        latest = self._base_dir / "latest" / "mapping.json"
        if latest.exists():
            with open(latest) as f:
                return json.load(f)
        return None

    def cleanup(self):
        """Remove sessions older than retention_days."""
        if self._retention_days < 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        for entry in self._base_dir.iterdir():
            if entry.name == "latest" or not entry.is_dir():
                continue
            if entry == self._current_path:
                continue
            mapping_file = entry / "mapping.json"
            if mapping_file.exists():
                try:
                    with open(mapping_file) as f:
                        data = json.load(f)
                    raw = data["created"]
                    created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if created < cutoff:
                        shutil.rmtree(entry)
                except Exception:
                    pass

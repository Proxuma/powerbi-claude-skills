"""Mapping persistence for anonymization sessions.

Stores alias->real_value mappings locally so reports can be deanonymized.
Files are created with 0600 permissions (owner-only read/write).
"""

import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


class MappingStore:
    """Manages per-session mapping files in ~/.powerbi-mcp/sessions/."""

    def __init__(self, base_dir: Optional[Path] = None, retention_days: int = 90):
        self._base_dir = base_dir or (Path.home() / ".powerbi-mcp" / "sessions")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._session_id: Optional[str] = None
        self._current_path: Optional[Path] = None

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

    def save(self, mapping: dict[str, str], stats: dict):
        """Save mapping and stats to the current session directory."""
        if not self._current_path:
            raise RuntimeError("No active session. Call new_session() first.")
        data = {
            "session_id": self._session_id,
            "created": datetime.utcnow().isoformat() + "Z",
            "mappings": mapping,
            "stats": stats,
        }
        mapping_file = self._current_path / "mapping.json"
        with open(mapping_file, "w") as f:
            json.dump(data, f, indent=2)
        os.chmod(mapping_file, 0o600)

        # Update "latest" symlink
        latest = self._base_dir / "latest"
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(self._current_path)

    def load(self, session_id: str) -> dict:
        """Load mapping data for a given session ID."""
        path = self._base_dir / session_id / "mapping.json"
        if not path.exists():
            raise FileNotFoundError(f"No mapping found for session {session_id}")
        with open(path) as f:
            return json.load(f)

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
        cutoff = datetime.utcnow() - timedelta(days=self._retention_days)
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
                    created = datetime.fromisoformat(data["created"].rstrip("Z"))
                    if created < cutoff:
                        shutil.rmtree(entry)
                except Exception:
                    pass

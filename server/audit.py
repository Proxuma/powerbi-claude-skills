"""Audit logging for MCP tool calls. GDPR Art. 30 processing activities register."""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class AuditLogger:
    """Logs tool calls with sanitized queries. Does NOT log raw data."""

    def __init__(self, log_dir: Path, session_id: str):
        self._session_id = session_id
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._log_dir, 0o700)

        log_path = log_dir / f"audit-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        # Include log_dir in the logger name to guarantee a unique logger per
        # instance. Using only session_id causes test isolation failures because
        # Python's logging registry caches loggers globally: a second
        # AuditLogger with the same session_id would reuse the first instance's
        # handlers (pointing at the old, already-deleted temp dir).
        logger_name = f"powerbi-mcp-audit-{session_id}-{id(self)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = TimedRotatingFileHandler(
                log_path, when="midnight", backupCount=90, utc=True
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

        # Set permissions on current log file
        if log_path.exists():
            os.chmod(log_path, 0o600)

    def log_tool_call(
        self,
        tool_name: str,
        params: dict,
        result_size: int,
        anonymization_stats: dict,
    ) -> None:
        dax_query = params.get("dax_query")
        sanitized = self._sanitize_dax(dax_query) if dax_query else None
        query_hash = hashlib.sha256(dax_query.encode()).hexdigest() if dax_query else None

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "tool_name": tool_name,
            "sanitized_query": sanitized,
            "query_hash": query_hash,
            "result_rows": result_size,
            "anonymization": anonymization_stats,
        }
        self._logger.info(json.dumps(entry))

        # Ensure file permissions after rotation
        for path in self._log_dir.glob("audit-*.jsonl*"):
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    @staticmethod
    def _sanitize_dax(query: str) -> str:
        """Replace string literals in DAX with [...], preserving table references.

        Table references use single quotes: 'TableName'[Column]
        String values use double quotes: "some value"
        Best-effort: edge cases logged as-is.
        """
        return re.sub(r'"[^"]*"', '"[...]"', query)

    def status(self) -> dict:
        log_files = sorted(self._log_dir.glob("audit-*.jsonl*"))
        total_size = sum(f.stat().st_size for f in log_files if f.exists())
        return {
            "log_dir": str(self._log_dir),
            "log_files": len(log_files),
            "total_size_bytes": total_size,
            "last_write": log_files[-1].name if log_files else None,
        }

import json
import os
import tempfile
from pathlib import Path
from server.audit import AuditLogger


def test_log_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call(
            tool_name="execute_dax",
            params={"dax_query": 'EVALUATE SUMMARIZE(Tickets, "Count", COUNTROWS(Tickets))'},
            result_size=42,
            anonymization_stats={"registry_entities": 5, "presidio_detections": 2},
        )
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        assert len(log_files) == 1
        line = log_files[0].read_text().strip()
        entry = json.loads(line)
        assert entry["tool_name"] == "execute_dax"
        assert entry["session_id"] == "test-session"
        assert entry["result_rows"] == 42
        assert "timestamp" in entry


def test_log_sanitizes_dax_strings():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call(
            tool_name="execute_dax",
            params={"dax_query": 'EVALUATE FILTER(Tickets, Tickets[Subject] = "Secret client data")'},
            result_size=10,
            anonymization_stats={},
        )
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        line = log_files[0].read_text().strip()
        entry = json.loads(line)
        assert "Secret client data" not in entry["sanitized_query"]
        assert "[...]" in entry["sanitized_query"]


def test_log_preserves_table_references():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call(
            tool_name="execute_dax",
            params={"dax_query": "EVALUATE SUMMARIZE('Tickets'[Status], 'Tickets'[Priority])"},
            result_size=5,
            anonymization_stats={},
        )
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        line = log_files[0].read_text().strip()
        entry = json.loads(line)
        assert "'Tickets'[Status]" in entry["sanitized_query"]


def test_log_file_permissions():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call("test", {}, 0, {})
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        stat = os.stat(log_files[0])
        assert oct(stat.st_mode & 0o777) == oct(0o600)


def test_log_does_not_store_raw_data():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call(
            tool_name="execute_dax",
            params={"dax_query": "EVALUATE Tickets"},
            result_size=100,
            anonymization_stats={"presidio_detections": 3},
        )
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        content = log_files[0].read_text()
        entry = json.loads(content.strip())
        assert "query_hash" in entry
        assert "result_data" not in entry


def test_log_non_dax_tool():
    with tempfile.TemporaryDirectory() as tmp:
        logger = AuditLogger(log_dir=Path(tmp), session_id="test-session")
        logger.log_tool_call(
            tool_name="list_workspaces",
            params={},
            result_size=3,
            anonymization_stats={},
        )
        log_files = list(Path(tmp).glob("audit-*.jsonl"))
        entry = json.loads(log_files[0].read_text().strip())
        assert entry["tool_name"] == "list_workspaces"
        assert entry["sanitized_query"] is None

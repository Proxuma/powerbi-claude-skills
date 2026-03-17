import json
import os
import tempfile

import pytest
from pathlib import Path

from server.mapping import MappingStore


def test_mapping_store_saves_and_loads():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MappingStore(base_dir=Path(tmpdir))
        session_id = store.new_session()
        mapping = {"Client_A": "Acme Corp", "Resource_1": "Jan de Vries"}
        stats = {"registry_entities": 2, "presidio_detections": 0}
        store.save(mapping, stats)
        loaded = store.load(session_id)
        assert loaded["mappings"] == mapping
        assert loaded["stats"] == stats


def test_mapping_store_latest_symlink():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MappingStore(base_dir=Path(tmpdir))
        store.new_session()
        store.save({"Client_A": "Acme"}, {})
        latest = Path(tmpdir) / "latest"
        assert latest.is_symlink() or latest.is_dir()
        mapping_file = latest / "mapping.json"
        assert mapping_file.exists()


def test_mapping_store_file_permissions():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MappingStore(base_dir=Path(tmpdir))
        store.new_session()
        store.save({"Client_A": "Acme"}, {})
        mapping_file = store.current_path / "mapping.json"
        mode = oct(mapping_file.stat().st_mode)[-3:]
        assert mode == "600"


def test_mapping_store_cleanup():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = MappingStore(base_dir=Path(tmpdir), retention_days=0)
        old_id = store.new_session()
        store.save({"old": "data"}, {})
        new_id = store.new_session()
        store.save({"new": "data"}, {})
        store.cleanup()
        old_path = Path(tmpdir) / old_id
        assert not old_path.exists()


def test_encrypted_save_and_load(tmp_path):
    """S2: Encrypted mapping can be saved and loaded."""
    os.environ["POWERBI_MCP_ENCRYPTION_KEY"] = "test-key-for-unit-tests-only-32ch"
    try:
        store = MappingStore(base_dir=tmp_path, encrypt=True)
        store.new_session()
        mapping = {"Client_A": "Acme Corp", "<PERSON_1>": "Jan de Vries"}
        stats = {"registry_entities": 1, "presidio_detections": 1}
        store.save(mapping, stats)

        mapping_file = list(tmp_path.rglob("mapping.json.enc"))[0]
        raw = mapping_file.read_bytes()
        assert b"Acme Corp" not in raw
        assert b"Jan de Vries" not in raw

        loaded = store.load(store._session_id)
        assert loaded["mappings"]["Client_A"] == "Acme Corp"
    finally:
        del os.environ["POWERBI_MCP_ENCRYPTION_KEY"]


def test_encrypted_wrong_key_starts_fresh(tmp_path):
    """S2: Wrong key logs error and starts fresh session."""
    os.environ["POWERBI_MCP_ENCRYPTION_KEY"] = "original-key-32-chars-long-here"
    try:
        store = MappingStore(base_dir=tmp_path, encrypt=True)
        store.new_session()
        store.save({"Client_A": "Acme Corp"}, {})
        session_id = store._session_id
    finally:
        del os.environ["POWERBI_MCP_ENCRYPTION_KEY"]

    os.environ["POWERBI_MCP_ENCRYPTION_KEY"] = "different-key-32-chars-long-now"
    try:
        store2 = MappingStore(base_dir=tmp_path, encrypt=True)
        loaded = store2.load(session_id)
        assert loaded is None
    finally:
        del os.environ["POWERBI_MCP_ENCRYPTION_KEY"]


def test_plaintext_still_loads_when_encryption_off(tmp_path):
    """S2: Existing plaintext files still load when encrypt=False."""
    store = MappingStore(base_dir=tmp_path, encrypt=False)
    store.new_session()
    store.save({"Client_A": "Acme Corp"}, {})
    loaded = store.load(store._session_id)
    assert loaded["mappings"]["Client_A"] == "Acme Corp"

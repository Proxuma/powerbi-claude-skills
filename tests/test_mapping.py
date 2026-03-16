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

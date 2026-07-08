"""Tests for the non-interactive wizard modes' missing-detection warning
and the removal of the dead free_text_columns config key."""

import inspect
import json
from pathlib import Path

from server import wizard


def _write_config(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_warns_when_config_has_no_anonymization(tmp_path, monkeypatch, capsys):
    path = _write_config(tmp_path, {"default_workspace_id": "ws"})
    monkeypatch.setattr(wizard, "CONFIG_PATH", path)
    assert wizard.warn_if_detection_skipped() is True
    out = capsys.readouterr().out
    assert "auto-detection did NOT run" in out
    assert "sensitive_columns" in out


def test_warns_when_sensitive_columns_are_empty_lists(tmp_path, monkeypatch, capsys):
    path = _write_config(tmp_path, {
        "anonymization": {
            "enabled": True,
            "sensitive_columns": {"client": [], "resource": [], "contact": []},
        }
    })
    monkeypatch.setattr(wizard, "CONFIG_PATH", path)
    assert wizard.warn_if_detection_skipped() is True


def test_silent_when_sensitive_columns_present(tmp_path, monkeypatch, capsys):
    path = _write_config(tmp_path, {
        "anonymization": {
            "sensitive_columns": {"client": ["'Companies'[company_name]"]},
        }
    })
    monkeypatch.setattr(wizard, "CONFIG_PATH", path)
    assert wizard.warn_if_detection_skipped() is False
    assert capsys.readouterr().out == ""


def test_warns_when_config_file_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wizard, "CONFIG_PATH", tmp_path / "missing.json")
    assert wizard.warn_if_detection_skipped() is True


def test_free_text_columns_key_removed():
    """free_text_columns was written by the wizard but read by nothing."""
    assert "free_text_columns" not in inspect.getsource(wizard)
    example = Path(wizard.__file__).parent / "config.example.json"
    assert "free_text_columns" not in example.read_text()

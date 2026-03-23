"""Tests for adjutant.config."""

from pathlib import Path

from adjutant.config import AdjutantConfig, save_config, CONFIG_DIR


def test_config_defaults():
    """AdjutantConfig has sensible defaults."""
    config = AdjutantConfig(notebook_root=Path("/tmp/notes"))
    assert config.ai_tool == "claude"
    assert config.ai_model == ""
    assert config.notebook_root == Path("/tmp/notes")


def test_config_save_load(tmp_path, monkeypatch):
    """Config can be saved and loaded."""
    config_path = tmp_path / "config.toml"
    config_dir = tmp_path

    monkeypatch.setattr("adjutant.config.CONFIG_PATH", config_path)
    monkeypatch.setattr("adjutant.config.CONFIG_DIR", config_dir)

    config = AdjutantConfig(
        notebook_root=Path("/tmp/notes"),
        ai_tool="gemini",
        ai_model="gemini-pro",
    )
    save_config(config)

    assert config_path.is_file()
    content = config_path.read_text()
    assert "/tmp/notes" in content
    assert "gemini" in content

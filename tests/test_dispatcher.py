"""Tests for adjutant.core.dispatcher."""

from pathlib import Path

from adjutant.core.dispatcher import Dispatcher


def test_build_command_claude():
    cmd = Dispatcher.build_command("claude", "hello", Path("/tmp"))
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "hello" in cmd


def test_build_command_claude_with_model():
    cmd = Dispatcher.build_command("claude", "hello", Path("/tmp"), model="opus")
    assert "--model" in cmd
    assert "opus" in cmd


def test_build_command_gemini():
    cmd = Dispatcher.build_command("gemini", "hello", Path("/tmp"))
    assert cmd[0] == "gemini"
    assert "-p" in cmd


def test_build_command_codex():
    cmd = Dispatcher.build_command("codex", "hello", Path("/tmp"))
    assert cmd[0] == "codex"
    assert "-C" in cmd
    assert "exec" in cmd


def test_get_cwd_claude():
    assert Dispatcher.get_cwd("claude", Path("/tmp")) == Path("/tmp")


def test_get_cwd_codex():
    assert Dispatcher.get_cwd("codex", Path("/tmp")) is None


def test_build_command_unknown():
    import pytest
    with pytest.raises(ValueError, match="Unknown AI tool"):
        Dispatcher.build_command("unknown", "hello", Path("/tmp"))

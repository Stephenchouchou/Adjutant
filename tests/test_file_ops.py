"""Tests for adjutant.core.file_ops."""

import pytest
from pathlib import Path

from adjutant.core.file_ops import (
    FileOutsideRootError,
    FileTooLargeError,
    glob_files,
    make_diff,
    read_file,
    resolve_safe,
    write_file,
)


def test_resolve_safe_within_root(tmp_path):
    f = tmp_path / "test.md"
    f.touch()
    assert resolve_safe(f, tmp_path) == f.resolve()


def test_resolve_safe_outside_root(tmp_path):
    with pytest.raises(FileOutsideRootError):
        resolve_safe(tmp_path / ".." / "etc" / "passwd", tmp_path)


def test_read_file(tmp_path):
    f = tmp_path / "note.md"
    f.write_text("hello world")
    assert read_file(f, tmp_path) == "hello world"


def test_read_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_file(tmp_path / "missing.md", tmp_path)


def test_glob_files(tmp_path):
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "c.md").write_text("c")

    results = glob_files(tmp_path, ["*.md"])
    names = [p.name for p in results]
    assert "a.md" in names
    assert "c.md" in names
    assert "b.txt" not in names


def test_make_diff():
    diff = make_diff("line1\nline2\n", "line1\nline3\n", "test.md")
    assert "-line2" in diff
    assert "+line3" in diff


def test_write_file(tmp_path):
    f = tmp_path / "output.md"
    write_file(f, "new content", tmp_path)
    assert f.read_text() == "new content"


def test_write_file_creates_dirs(tmp_path):
    f = tmp_path / "sub" / "dir" / "output.md"
    write_file(f, "nested", tmp_path)
    assert f.read_text() == "nested"

"""Tests for adjutant.core.sop."""

from pathlib import Path

from adjutant.core.sop import SOPStore, build_sop_prompt, _parse_sop


def test_parse_sop(tmp_path):
    sop_file = tmp_path / "test-sop.md"
    sop_file.write_text(
        '---\nkey: test-sop\nlabel: Test SOP\nicon: "\\U0001F4CB"\n'
        "description: A test SOP\nfiles:\n"
        '  - "inbox.md"\noutput: stdout\n---\n\n'
        "Hello {file_contents}\n"
    )
    sop = _parse_sop(sop_file)
    assert sop is not None
    assert sop.key == "test-sop"
    assert sop.label == "Test SOP"
    assert sop.files == ["inbox.md"]
    assert "{file_contents}" in sop.prompt_template


def test_sop_store_list(tmp_path):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    user = tmp_path / "user"

    (builtin / "alpha.md").write_text("---\nkey: alpha\nlabel: Alpha\n---\n\nAlpha prompt\n")
    (builtin / "beta.md").write_text("---\nkey: beta\nlabel: Beta\n---\n\nBeta prompt\n")

    store = SOPStore(builtin, user)
    sops = store.list_sops()
    assert len(sops) == 2
    keys = [s.key for s in sops]
    assert "alpha" in keys
    assert "beta" in keys


def test_sop_store_user_override(tmp_path):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    user = tmp_path / "user"
    user.mkdir()

    (builtin / "alpha.md").write_text("---\nkey: alpha\nlabel: Alpha Builtin\n---\n\nBuiltin\n")
    (user / "alpha.md").write_text("---\nkey: alpha\nlabel: Alpha User\n---\n\nUser\n")

    store = SOPStore(builtin, user)
    sop = store.get_sop("alpha")
    assert sop is not None
    assert sop.label == "Alpha User"
    assert not sop.is_builtin


def test_build_sop_prompt_with_files(tmp_path):
    # Create a notebook root with a file
    notebook = tmp_path / "notebook"
    notebook.mkdir()
    (notebook / "inbox.md").write_text("- Buy milk\n- Read paper\n")

    sop_file = tmp_path / "test.md"
    sop_file.write_text(
        '---\nkey: test\nlabel: Test\nfiles:\n  - "inbox.md"\noutput: stdout\n---\n\n'
        "Process: {file_contents}\n"
    )

    sop = _parse_sop(sop_file)
    assert sop is not None

    prompt = build_sop_prompt(sop, notebook)
    assert "Buy milk" in prompt
    assert "Read paper" in prompt


def test_build_sop_prompt_no_files(tmp_path):
    notebook = tmp_path / "notebook"
    notebook.mkdir()

    sop_file = tmp_path / "test.md"
    sop_file.write_text(
        "---\nkey: test\nlabel: Test\nfiles:\n"
        '  - "nonexistent.md"\noutput: stdout\n---\n\n'
        "Content: {file_contents}\n"
    )

    sop = _parse_sop(sop_file)
    assert sop is not None

    prompt = build_sop_prompt(sop, notebook)
    assert "(no matching files found)" in prompt


def test_sop_store_save(tmp_path):
    store = SOPStore(tmp_path / "builtin", tmp_path / "user")
    path = store.save_sop(
        key="my-sop",
        label="My SOP",
        description="Custom workflow",
        files=["notes.md"],
        content="Do the thing with {file_contents}",
    )
    assert path.is_file()
    content = path.read_text()
    assert "my-sop" in content
    assert "My SOP" in content


def test_builtin_sops_parse():
    """All built-in SOP templates should parse without errors."""
    builtin_dir = Path(__file__).resolve().parent.parent / "src" / "adjutant" / "sop"
    store = SOPStore(builtin_dir, Path("/nonexistent"))
    sops = store.list_sops()
    assert len(sops) == 4
    keys = {s.key for s in sops}
    assert keys == {"inbox-triage", "daily-summary", "weekly-report", "task-update"}

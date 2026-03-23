"""Tests for adjutant.core.chat."""

from adjutant.core.chat import build_chat_prompt, ADJUTANT_PERSONA
from adjutant.models.session import Session


def test_build_chat_prompt_basic():
    session = Session(name="test")
    prompt = build_chat_prompt("hello", session)
    assert ADJUTANT_PERSONA in prompt
    assert "hello" in prompt


def test_build_chat_prompt_with_history():
    session = Session(name="test")
    session.add_message("user", "first question")
    session.add_message("adjutant", "first answer")

    prompt = build_chat_prompt("second question", session)
    assert "first question" in prompt
    assert "first answer" in prompt
    assert "second question" in prompt


def test_build_chat_prompt_with_file_context():
    session = Session(name="test")
    prompt = build_chat_prompt("analyze this", session, file_context="# My Notes\n\nSome content")
    assert "My Notes" in prompt
    assert "Some content" in prompt
    assert "analyze this" in prompt


def test_build_chat_prompt_truncates_long_history():
    session = Session(name="test")
    # Add more than 20 messages
    for i in range(25):
        session.add_message("user", f"msg {i}")
        session.add_message("adjutant", f"reply {i}")

    prompt = build_chat_prompt("latest", session)
    # Should only include last 20 messages
    assert "msg 0" not in prompt
    assert "msg 24" in prompt

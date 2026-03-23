"""Tests for adjutant.models.session."""

from adjutant.models.session import Message, Session


def test_message_creation():
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp is not None


def test_session_add_message():
    session = Session(name="test")
    msg = session.add_message("user", "hello")
    assert len(session.messages) == 1
    assert msg.role == "user"
    assert msg.content == "hello"


def test_session_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr("adjutant.models.session.SESSIONS_DIR", tmp_path)

    session = Session(name="test")
    session.add_message("user", "hello")
    session.add_message("adjutant", "hi there")
    session.save()

    loaded = Session.load(str(session.id))
    assert loaded is not None
    assert loaded.name == "test"
    assert len(loaded.messages) == 2


def test_session_list(tmp_path, monkeypatch):
    monkeypatch.setattr("adjutant.models.session.SESSIONS_DIR", tmp_path)

    s1 = Session(name="first")
    s1.add_message("user", "a")
    s1.save()

    s2 = Session(name="second")
    s2.add_message("user", "b")
    s2.save()

    sessions = Session.list_sessions()
    assert len(sessions) == 2

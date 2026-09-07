from backend.storage.session_store import SessionStore


def test_append_and_list(tmp_path):
    p = tmp_path / "s.sqlite"
    s = SessionStore(str(p), enabled=True)
    sid = s.start_session()
    s.append("Q?", "A.", timestamp_ms=1, duration_ms=10)
    sessions = s.list_sessions()
    assert sessions[0]["id"] == sid
    entries = s.list_entries(sid)
    assert entries[0].question_text == "Q?"
    assert entries[0].full_answer == "A."
    s.close()


def test_disabled_writes_nothing(tmp_path):
    p = tmp_path / "s.sqlite"
    s = SessionStore(str(p), enabled=False)
    s.start_session()
    s.append("Q?", "A.", timestamp_ms=1, duration_ms=10)
    s.close()
    assert not p.exists() or p.stat().st_size == 0 or SessionStore(str(p), True).list_sessions() == []

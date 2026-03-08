import json

from parsers import (
    _summarize_tool_input,
    load_history,
    load_stats_cache,
    parse_session_file,
)


def _write_jsonl(path, records):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_parse_session_file_basic(tmp_path):
    jfile = tmp_path / "test.jsonl"
    records = [
        {
            "type": "user",
            "timestamp": "2024-01-15T12:00:00.000Z",
            "message": {"content": "Hello world test prompt"},
        },
        {
            "type": "assistant",
            "uuid": "abc-123",
            "timestamp": "2024-01-15T12:00:05.000Z",
            "message": {
                "content": [{"type": "text", "text": "Hi there"}],
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
    ]
    _write_jsonl(jfile, records)
    session = parse_session_file(jfile, "test-sid", "test-project", None)

    assert session is not None
    assert len(session["human_messages"]) == 1
    assert session["human_messages"][0]["text"] == "Hello world test prompt"
    assert session["project"] == "test-project"
    assert "claude-sonnet-4-6" in session["models_used"]


def test_parse_session_file_skips_meta(tmp_path):
    jfile = tmp_path / "test.jsonl"
    records = [
        {
            "type": "user",
            "timestamp": "2024-01-15T12:00:00.000Z",
            "isMeta": True,
            "message": {"content": "meta message"},
        },
        {
            "type": "user",
            "timestamp": "2024-01-15T12:00:01.000Z",
            "message": {"content": "real message"},
        },
    ]
    _write_jsonl(jfile, records)
    session = parse_session_file(jfile, "sid", "proj", None)

    assert len(session["human_messages"]) == 1
    assert session["human_messages"][0]["text"] == "real message"


def test_parse_session_file_deduplicates_uuid(tmp_path):
    jfile = tmp_path / "test.jsonl"
    records = [
        {
            "type": "user",
            "timestamp": "2024-01-15T12:00:00.000Z",
            "message": {"content": "prompt"},
        },
        {
            "type": "assistant",
            "uuid": "same-uuid",
            "timestamp": "2024-01-15T12:00:01.000Z",
            "message": {
                "content": [{"type": "text", "text": "partial"}],
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 50, "output_tokens": 10},
            },
        },
        {
            "type": "assistant",
            "uuid": "same-uuid",
            "timestamp": "2024-01-15T12:00:02.000Z",
            "message": {
                "content": [{"type": "text", "text": "complete"}],
                "model": "claude-sonnet-4-6",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        },
    ]
    _write_jsonl(jfile, records)
    session = parse_session_file(jfile, "sid", "proj", None)

    assert session["total_assistant_blocks"] == 1
    assert session["model_usage"][0]["input_tokens"] == 100


def test_summarize_tool_input_read():
    assert _summarize_tool_input("Read", {"file_path": "/foo/bar.py"}) == "/foo/bar.py"


def test_summarize_tool_input_bash():
    assert _summarize_tool_input("Bash", {"command": "ls -la"}) == "ls -la"


def test_summarize_tool_input_unknown():
    result = _summarize_tool_input("CustomTool", {"key": "value"})
    assert isinstance(result, str)


def test_load_history_empty(tmp_path, monkeypatch):
    import parsers

    monkeypatch.setattr(parsers, "HISTORY_FILE", tmp_path / "nonexistent.jsonl")
    result = load_history(30, None, False)
    assert result == []


def test_load_stats_cache_missing(tmp_path, monkeypatch):
    import parsers

    monkeypatch.setattr(parsers, "STATS_FILE", tmp_path / "nonexistent.json")
    result = load_stats_cache()
    assert result == {}

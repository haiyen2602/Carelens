"""Tests for repository AI logging hooks and submission boundaries."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from scripts import log_hook, set_ai_log_cutoff, submit_log

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def workspace_tmp_dir():
    """Use the writable workspace because the Windows system temp is sandboxed."""
    root = Path.cwd() / ".test-tmp"
    root.mkdir(exist_ok=True)
    path = root / f"ai-log-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _fake_git(command: str) -> str:
    values = {
        "git remote get-url origin": "https://github.com/example/P-067.git",
        "git rev-parse --abbrev-ref HEAD": "chore/ai-log-codex",
        "git rev-parse --short HEAD": "abc1234",
        "git config user.email": "student@example.com",
    }
    return values.get(command, "")


def test_codex_windows_hooks_do_not_nest_powershell():
    """Codex already runs commandWindows in PowerShell; nesting loses $root."""
    config = json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))

    for groups in config["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                command = hook["commandWindows"]
                assert command.startswith("$root = git rev-parse --show-toplevel;")
                assert "powershell" not in command.lower()


def test_codex_post_tool_use_is_logged_and_credentials_are_redacted(monkeypatch):
    monkeypatch.setattr(log_hook, "git", _fake_git)
    raw_secret = "sk-test-secret-1234567890"
    entry = log_hook.normalize(
        {
            "hook_event_name": "PostToolUse",
            "session_id": "thread-1",
            "turn_id": "turn-1",
            "model": "gpt-test",
            "tool_name": "Bash",
            "tool_input": {
                "command": f"AI_LOG_API_KEY={raw_secret} python scripts/example.py",
                "password": "do-not-store",
            },
            "tool_response": f"Authorization: Bearer {raw_secret}",
        },
        "codex",
    )

    assert entry is not None
    serialized = json.dumps(log_hook.redact(entry))
    assert entry["event"] == "PostToolUse"
    assert entry["tool_name"] == "Bash"
    assert raw_secret not in serialized
    assert "do-not-store" not in serialized
    assert serialized.count(log_hook.REDACTED) >= 3


def test_cutoff_is_not_replaced_without_force(workspace_tmp_dir):
    marker = set_ai_log_cutoff.write_cutoff(workspace_tmp_dir)
    original = marker.read_text(encoding="utf-8")

    same_marker = set_ai_log_cutoff.write_cutoff(workspace_tmp_dir)

    assert same_marker == marker
    assert marker.read_text(encoding="utf-8") == original


def test_submit_sends_only_entries_at_or_after_cutoff(monkeypatch, workspace_tmp_dir):
    log_dir = workspace_tmp_dir / ".ai-log"
    log_dir.mkdir()
    log_file = log_dir / "session.jsonl"
    archive_dir = log_dir / "archive"
    cutoff_file = log_dir / "submit-not-before.json"
    cutoff_file.write_text(
        json.dumps({"version": 1, "not_before": "2026-08-27T07:00:00Z"}),
        encoding="utf-8",
    )
    old_entry = {"ts": "2026-08-24T01:00:00+07:00", "tool": "claude", "prompt": "old"}
    boundary_entry = {"ts": "2026-08-27T14:00:00+07:00", "tool": "codex", "prompt": "new"}
    newer_entry = {"ts": "2026-08-27T07:00:01Z", "tool": "codex", "event": "Stop"}
    log_file.write_text(
        "".join(json.dumps(entry) + "\n" for entry in (old_entry, boundary_entry, newer_entry)),
        encoding="utf-8",
    )

    monkeypatch.setattr(submit_log, "SERVER_URL", "https://logs.example.test/ingest")
    monkeypatch.setattr(submit_log, "API_KEY", "test-key")
    monkeypatch.setattr(submit_log, "LOG_DIR", log_dir)
    monkeypatch.setattr(submit_log, "LOG_FILE", log_file)
    monkeypatch.setattr(submit_log, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(submit_log, "CUTOFF_FILE", cutoff_file)
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(submit_log.urllib.request, "urlopen", fake_urlopen)

    submit_log.main()

    assert captured["payload"]["entries"] == [boundary_entry, newer_entry]
    assert captured["authorization"] == "Bearer test-key"
    assert captured["timeout"] == 10
    assert not log_file.exists()
    archived = "".join(path.read_text(encoding="utf-8") for path in archive_dir.iterdir())
    assert '"prompt": "old"' in archived
    assert '"prompt": "new"' in archived


def test_invalid_cutoff_fails_closed_without_http_request(monkeypatch, workspace_tmp_dir):
    log_dir = workspace_tmp_dir / ".ai-log"
    log_dir.mkdir()
    log_file = log_dir / "session.jsonl"
    cutoff_file = log_dir / "submit-not-before.json"
    log_file.write_text('{"ts":"2026-08-27T07:00:01Z"}\n', encoding="utf-8")
    cutoff_file.write_text('{"not_before":"not-a-date"}', encoding="utf-8")

    monkeypatch.setattr(submit_log, "SERVER_URL", "https://logs.example.test/ingest")
    monkeypatch.setattr(submit_log, "LOG_DIR", log_dir)
    monkeypatch.setattr(submit_log, "LOG_FILE", log_file)
    monkeypatch.setattr(submit_log, "ARCHIVE_DIR", log_dir / "archive")
    monkeypatch.setattr(submit_log, "CUTOFF_FILE", cutoff_file)

    def fail_if_called(*args, **kwargs):
        pytest.fail("HTTP must not be called when the cutoff marker is invalid")

    monkeypatch.setattr(submit_log.urllib.request, "urlopen", fail_if_called)

    with pytest.raises(SystemExit) as exc_info:
        submit_log.main()

    assert exc_info.value.code == 0
    assert log_file.exists()
    assert not list(log_dir.glob("session.pending.*.jsonl"))


def test_timestamp_parser_requires_timezone():
    with pytest.raises(submit_log.CutoffError):
        submit_log._parse_timestamp("2026-08-27T07:00:00")

    assert submit_log._parse_timestamp("2026-08-27T14:00:00+07:00") == datetime(2026, 8, 27, 7, 0, tzinfo=UTC)

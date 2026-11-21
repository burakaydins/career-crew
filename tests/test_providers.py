from pathlib import Path

import pytest

from app.providers.base import AgentRequest, ProviderError, parse_envelope
from app.providers.claude_code import ClaudeCodeProvider
from app.registry import Registry


def test_parse_envelope_plain_and_fenced():
    r = parse_envelope('{"message": "Onay.", "data": {"decision": "approve"}, "files": {}}')
    assert r.message == "Onay." and r.data["decision"] == "approve"
    r = parse_envelope('```json\n{"message": "x", "files": {"cv.md": "# CV"}}\n```')
    assert r.files == {"cv.md": "# CV"}


def test_parse_envelope_errors():
    with pytest.raises(ProviderError):
        parse_envelope("JSON yok")
    with pytest.raises(ProviderError):
        parse_envelope('{"message": "x", "files": ["a"]}')


def test_registry_loads_six_cards():
    reg = Registry()
    assert set(reg.cards) == {"job_analyst", "cv_writer", "verifier", "recruiter", "letter_writer", "interviewer"}
    prompt = reg["cv_writer"].system_prompt()
    assert "KONUŞMA KURALLARI" in prompt and "UYDURMA YASAK" in prompt


def test_claude_code_command_is_isolated(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/claude")
    card = Registry()["recruiter"]
    req = AgentRequest(card=card, skill="score", system_prompt="S", user_prompt="U", workdir=Path("."))
    cmd = ClaudeCodeProvider().build_command(req)
    assert cmd[:2] == ["/usr/bin/claude", "-p"]
    for flag, value in [("--setting-sources", ""), ("--tools", ""), ("--model", "haiku"), ("--effort", "low")]:
        assert cmd[cmd.index(flag) + 1] == value
    assert "--strict-mcp-config" in cmd and "--no-session-persistence" in cmd


def test_claude_code_env_drops_api_key_and_parent_session(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:1")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "x")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "keep")
    env = ClaudeCodeProvider.build_env()
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDECODE", "CLAUDE_CODE_SESSION_ID"):
        assert key not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "keep"


def test_parse_envelope_rejects_non_object_data():
    for bad in ('{"message": "x", "data": [1]}', '{"message": "x", "data": "metin"}'):
        with pytest.raises(ProviderError):
            parse_envelope(bad)

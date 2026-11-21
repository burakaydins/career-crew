"""ApiProvider against a fake Anthropic client: request shape, parsing and errors.
No network and no API key needed."""

from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from app.providers.api import ApiProvider
from app.providers.base import AgentRequest, ProviderError
from app.registry import Registry

ENVELOPE = '{"message": "Puan 81.", "data": {"score": 81, "missing": []}, "files": {}}'


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def message(text=ENVELOPE, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=120, output_tokens=40),
    )


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = ApiProvider()
    p.calls = []

    def install(response):
        def stream(**kwargs):
            p.calls.append(kwargs)
            return FakeStream(response)
        p.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))

    p.install = install
    return p


def request(agent):
    card = Registry()[agent]
    return AgentRequest(card, card.skills[0], "SYS", "USER", Path("."))


def test_haiku_request_shape_and_parsing(provider):
    provider.install(message())
    result = provider.run(request("recruiter"))
    (call,) = provider.calls
    assert call["model"] == "claude-haiku-5-5"
    assert call["system"] == "SYS" and call["messages"] == [{"role": "user", "content": "USER"}]
    assert call["output_config"] == {"effort": "low"}
    assert "fallbacks" not in call  # Haiku 5.5 has no server-side fallback
    assert result.data["score"] == 81 and result.usage == {"input_tokens": 120, "output_tokens": 40}


def test_sonnet_gets_refusal_fallback(provider):
    provider.install(message())
    provider.run(request("cv_writer"))
    (call,) = provider.calls
    assert call["model"] == "claude-sonnet-5-5"
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]


@pytest.mark.parametrize("stop_reason, text", [("refusal", "reddetti"), ("max_tokens", "token sınırında")])
def test_bad_stop_reasons(provider, stop_reason, text):
    provider.install(message(stop_reason=stop_reason))
    with pytest.raises(ProviderError, match=text):
        provider.run(request("recruiter"))


def test_api_errors_become_provider_errors(provider):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx.Response(401, request=req)
    provider.install(anthropic.AuthenticationError("bad key", response=resp, body=None))
    with pytest.raises(ProviderError, match="API anahtarı"):
        provider.run(request("recruiter"))
    provider.install(anthropic.APIConnectionError(request=req))
    with pytest.raises(ProviderError, match="bağlanılamadı"):
        provider.run(request("recruiter"))

"""ApiProvider against a fake Anthropic client: request shape, parsing and errors.
No network and no API key needed."""

import base64
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


# ---- image and scanned-PDF reading (never run against the real API) ------------

def test_transcribe_sends_an_image_block(provider):
    provider.install(message(text="Backend Developer\n- Python"))
    text = provider.transcribe("image/png", b"\x89PNGdata", "ilan")
    (call,) = provider.calls
    image, prompt = call["messages"][0]["content"]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert image["source"]["type"] == "base64" and image["source"]["data"] == base64.b64encode(b"\x89PNGdata").decode()
    assert "job posting" in prompt["text"]
    assert "Do not summarize" in call["system"]
    assert call["model"] == "claude-sonnet-5-5"
    assert text == "Backend Developer\n- Python"


def test_transcribe_sends_a_scanned_pdf_as_a_document_block(provider):
    provider.install(message(text="CV metni"))
    provider.transcribe("application/pdf", b"%PDF-1.4", "cv")
    (call,) = provider.calls
    block = call["messages"][0]["content"][0]
    assert block["type"] == "document" and block["source"]["media_type"] == "application/pdf"


def test_transcribe_rejects_huge_images_and_empty_replies(provider):
    provider.install(message())
    with pytest.raises(ProviderError, match="5 MB"):
        provider.transcribe("image/jpeg", b"x" * (5 * 1024 * 1024 + 1), "cv")
    assert provider.calls == []
    provider.install(message(text="  "))
    with pytest.raises(ProviderError, match="metin çıkaramadı"):
        provider.transcribe("image/png", b"x", "cv")


def test_transcribe_maps_api_errors(provider):
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    provider.install(anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=req), body=None))
    with pytest.raises(ProviderError, match="API anahtarı"):
        provider.transcribe("image/png", b"x", "cv")

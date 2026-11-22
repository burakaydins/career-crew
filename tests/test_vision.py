"""Pictures and scanned PDFs: read_input hands them to the provider. No network, no key."""

import json
import subprocess
from types import SimpleNamespace

import pytest
from PIL import Image

from app.inputs import InputError, NeedsVision, read_document, read_input
from app.providers.base import ProviderError
from app.providers.claude_code import ClaudeCodeProvider
from app.providers.mock import MockProvider
from conftest import ROOT

TRANSCRIPT = (ROOT / "examples" / "ilan.md").read_text(encoding="utf-8")


class FakeVision:
    name = "fake"

    def __init__(self, reply=TRANSCRIPT):
        self.reply, self.calls = reply, []

    def transcribe(self, media_type, data, kind):
        self.calls.append((media_type, len(data), kind))
        return self.reply


@pytest.fixture
def png(tmp_path):
    path = tmp_path / "ilan.png"
    Image.new("RGB", (40, 20), "white").save(path)
    return path


@pytest.fixture
def scanned_pdf(tmp_path):
    path = tmp_path / "taranmis.pdf"
    Image.new("RGB", (60, 40), "white").save(path)  # a PDF that holds only a picture
    return path


def test_images_and_scanned_pdfs_need_vision(png, scanned_pdf):
    with pytest.raises(NeedsVision):
        read_document(png)
    with pytest.raises(NeedsVision):
        read_document(scanned_pdf)


def test_read_input_uses_the_provider_for_pictures(png, scanned_pdf):
    provider = FakeVision()
    assert "Backend Developer" in read_input(png, provider, "ilan")
    assert read_input(scanned_pdf, provider, "cv").startswith("# Backend")
    assert [c[0] for c in provider.calls] == ["image/png", "application/pdf"]
    assert [c[2] for c in provider.calls] == ["ilan", "cv"]


def test_read_input_leaves_text_files_to_the_local_readers(tmp_path):
    f = tmp_path / "ilan.md"
    f.write_text(TRANSCRIPT, encoding="utf-8")
    provider = FakeVision()
    assert read_input(f, provider, "ilan").startswith("# Backend")
    assert provider.calls == []


def test_mock_provider_gives_a_clear_error(png):
    with pytest.raises(InputError, match="mock modu görsel okuyamaz"):
        read_input(png, MockProvider(), "ilan")


def test_a_near_empty_transcript_is_rejected(png):
    with pytest.raises(InputError, match="yeterli metin"):
        read_input(png, FakeVision("kısa"), "ilan")


# ---- claude-code: stream-json with an image block -------------------------------

@pytest.fixture
def cc(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/claude")
    return ClaudeCodeProvider()


def test_claude_code_transcribe_command_is_isolated_and_streams_input(cc):
    cmd = cc.build_transcribe_command()
    assert cmd[cmd.index("--input-format") + 1] == "stream-json"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in cmd and "--no-session-persistence" in cmd


def test_claude_code_transcribe_sends_the_image_on_stdin(cc, monkeypatch):
    seen = {}

    def fake_run(cmd, input, **kwargs):
        seen["input"] = input
        out = json.dumps({"type": "result", "is_error": False, "result": "Backend Developer\n- Python"})
        return SimpleNamespace(stdout=out + "\n", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert cc.transcribe("image/jpeg", b"\xff\xd8jpeg", "ilan") == "Backend Developer\n- Python"
    message = json.loads(seen["input"])
    assert message["type"] == "user"
    image = message["message"]["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/jpeg"


def test_claude_code_transcribe_reports_errors(cc, monkeypatch):
    out = json.dumps({"type": "result", "is_error": True, "result": "bad image"})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=out, stderr="", returncode=1))
    with pytest.raises(ProviderError, match="bad image"):
        cc.transcribe("image/png", b"x", "cv")

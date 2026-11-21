"""Real model calls. Run with: CAREER_CREW_LIVE=1 pytest -m live"""

import os
import subprocess
from pathlib import Path

import pytest

from app.providers.base import AgentRequest
from app.providers.claude_code import ClaudeCodeProvider
from app.registry import Registry

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("CAREER_CREW_LIVE") != "1", reason="CAREER_CREW_LIVE=1 değil"),
]


def test_claude_code_isolation_loads_no_plugins_or_mcp(tmp_path):
    """The agent call must see no user plugins, hooks, skills or MCP servers."""
    provider = ClaudeCodeProvider()
    card = Registry()["recruiter"]
    cmd = provider.build_command(AgentRequest(card, "score", "Kısa cevap ver.", "", tmp_path))
    out = subprocess.run(cmd, input="Merhaba", capture_output=True, text=True, cwd=tmp_path,
                         env=provider.build_env(), timeout=300).stdout
    init = next(__import__("json").loads(l) for l in out.splitlines() if '"subtype":"init"' in l.replace(" ", ""))
    assert init.get("mcp_servers") == []
    # No tools at all, so even built-in skills cannot be invoked.
    assert init.get("tools") == []
    # Only plugins that ship inside Claude Code; nothing the user installed.
    assert all(p["source"].endswith("@builtin") for p in init.get("plugins", []))


def test_claude_code_returns_envelope(tmp_path):
    reg = Registry()
    card = reg["recruiter"]
    req = AgentRequest(card, "score", card.system_prompt(),
                       'Görev: score.\n<cv>Python geliştirici</cv>\n<ilan_ozeti>{"title": "Python Developer"}</ilan_ozeti>',
                       tmp_path)
    result = ClaudeCodeProvider().run(req)
    assert isinstance(result.data.get("score"), int)

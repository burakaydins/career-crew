"""Runs agents through the locally installed Claude Code CLI (`claude -p`).

Personal use with your own Pro/Max subscription. Only the official `claude`
binary is called; credentials are never read or copied.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.providers.base import (
    TRANSCRIBE_SYSTEM, AgentRequest, AgentResult, ProviderError, parse_envelope, transcribe_prompt,
)

TIMEOUT_SECONDS = 600


@dataclass
class _TranscriberCard:
    """Just enough of an AgentCard for build_command."""
    model: str = "sonnet"
    effort: str = "low"


class ClaudeCodeProvider:
    name = "claude-code"

    def __init__(self, binary: str = "claude") -> None:
        path = shutil.which(binary)
        if path is None:
            raise ProviderError("'claude' komutu bulunamadı. Claude Code kurulu ve PATH'te olmalı.")
        self.binary = path

    def build_command(self, request: AgentRequest) -> list[str]:
        card = request.card
        return [
            self.binary,
            "-p",
            "--output-format", "stream-json",
            "--verbose",
            "--model", card.model,
            "--effort", card.effort,
            "--system-prompt", request.system_prompt,
            # Isolation: no user/project settings, plugins, hooks or MCP servers.
            "--setting-sources", "",
            "--strict-mcp-config",
            # Inputs arrive inline and the orchestrator writes files: no tools at all.
            "--tools", "",
            "--no-session-persistence",
        ]

    @staticmethod
    def build_env() -> dict[str, str]:
        env = dict(os.environ)
        # An exported API key or gateway would make `claude` bill the API instead of the subscription.
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            env.pop(key, None)
        # When career-crew itself runs inside a Claude Code session, the parent's session
        # variables leak into the child and break its auth. Keep only the user's own token.
        for key in list(env):
            if key == "CLAUDECODE" or (key.startswith("CLAUDE_CODE_") and key != "CLAUDE_CODE_OAUTH_TOKEN"):
                env.pop(key)
        return env

    def _invoke(self, command: list[str], stdin: str, cwd) -> dict:
        try:
            proc = subprocess.run(
                command,
                input=stdin,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=self.build_env(),
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise ProviderError(f"claude {TIMEOUT_SECONDS} sn içinde yanıt vermedi") from e

        final = None
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "result":
                final = event

        if final is None:
            raise ProviderError(f"claude hata verdi (kod {proc.returncode}): {proc.stderr.strip()[:500]}")
        if final.get("is_error"):
            raise ProviderError(f"claude hata verdi: {str(final.get('result'))[:500]}")
        return final

    def run(self, request: AgentRequest) -> AgentResult:
        final = self._invoke(self.build_command(request), request.user_prompt, request.workdir)
        result = parse_envelope(final.get("result", ""))
        result.usage = {
            "cost_usd": final.get("total_cost_usd"),
            "duration_ms": final.get("duration_ms"),
            **(final.get("usage") or {}),
        }
        return result

    def build_transcribe_command(self) -> list[str]:
        # Same isolation as agents; the picture goes in as a stream-json user message.
        command = self.build_command(AgentRequest(
            card=_TranscriberCard(), skill="transcribe", system_prompt=TRANSCRIBE_SYSTEM, user_prompt="", workdir=Path("."),
        ))
        return command + ["--input-format", "stream-json"]

    def transcribe(self, media_type: str, data: bytes, kind: str) -> str:
        """Reads a picture or a scanned PDF through `claude -p` and returns its text."""
        block_type = "document" if media_type == "application/pdf" else "image"
        message = {"type": "user", "message": {"role": "user", "content": [
            {"type": block_type, "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}},
            {"type": "text", "text": transcribe_prompt(kind)},
        ]}}
        final = self._invoke(self.build_transcribe_command(), json.dumps(message) + "\n", Path.cwd())
        text = str(final.get("result", "")).strip()
        if not text:
            raise ProviderError("Model görselden metin çıkaramadı")
        return text

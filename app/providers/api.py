"""Runs agents through the Anthropic API with the user's own key (ANTHROPIC_API_KEY)."""

from __future__ import annotations

import os
from pathlib import Path

from app.providers.base import AgentRequest, AgentResult, ProviderError, parse_envelope

MODELS = {
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
    "opus": "claude-opus-5-5",
}
# Models that support the server-side refusal fallback. Haiku 5.5 has none.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}
MAX_TOKENS = 32000


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip())


class ApiProvider:
    name = "api"

    def __init__(self) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise ProviderError("api modu için: pip install -e '.[api]'") from e
        _load_dotenv()
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()

    def run(self, request: AgentRequest) -> AgentResult:
        card = request.card
        model = MODELS.get(card.model, card.model)
        kwargs = dict(
            model=model,
            max_tokens=MAX_TOKENS,
            system=request.system_prompt,
            messages=[{"role": "user", "content": request.user_prompt}],
            output_config={"effort": card.effort},
        )
        if model in FALLBACK_MODELS:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

        a = self._anthropic
        try:
            with self.client.beta.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        except a.AuthenticationError as e:
            raise ProviderError("API anahtarı geçersiz ya da eksik (ANTHROPIC_API_KEY)") from e
        except a.RateLimitError as e:
            raise ProviderError("API hız limiti aşıldı, biraz sonra tekrar deneyin") from e
        except a.APIStatusError as e:
            raise ProviderError(f"API hatası {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise ProviderError("API'ye bağlanılamadı") from e

        if response.stop_reason == "refusal":
            raise ProviderError("Model isteği reddetti")
        if response.stop_reason == "max_tokens":
            raise ProviderError("Yanıt token sınırında kesildi")

        text = "".join(b.text for b in response.content if b.type == "text")
        result = parse_envelope(text)
        result.usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return result

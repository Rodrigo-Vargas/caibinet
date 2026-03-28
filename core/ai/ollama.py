from typing import List, Optional
import logging
import httpx
from .base import AIProvider, ProviderConfig

log = logging.getLogger(__name__)

# Static fallback table: model name fragment → context window (tokens).
# Used only when /api/show does not return a context_length.
# Keys are matched as substrings of the model name (lowercase).
_CONTEXT_WINDOW_FALLBACK: list[tuple[str, int]] = [
    ("phi4",        16384),
    ("phi3.5",       4096),
    ("phi3",         4096),
    ("llama3.3",   131072),
    ("llama3.2",   131072),
    ("llama3.1",   131072),
    ("llama3",       8192),
    ("llama2",       4096),
    ("mistral",     32768),
    ("mixtral",     32768),
    ("gemma3",     131072),
    ("gemma2",       8192),
    ("gemma",        8192),
    ("qwen2.5",    131072),
    ("qwen2",      131072),
    ("qwen",        32768),
    ("deepseek-r1", 65536),
    ("deepseek",   163840),
    ("command-r",  131072),
    ("codellama",   16384),
    ("starcoder2",  16384),
    ("wizardlm2",    8192),
    ("vicuna",       4096),
]
_DEFAULT_CONTEXT_WINDOW = 4096


class OllamaProvider(AIProvider):
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self._context_window: Optional[int] = None

    def _resolve_context_window(self) -> int:
        """Return the model's context window, querying Ollama /api/show first.

        Resolution order:
        1. Cached value from a previous call.
        2. ``llama.context_length`` (or any ``*.context_length`` key) from
           Ollama's ``/api/show`` → ``model_info`` payload.
        3. Static fallback table keyed by model-name substring.
        4. Hard-coded default of 4096.
        """
        if self._context_window is not None:
            return self._context_window

        # --- Try /api/show ---
        try:
            r = httpx.post(
                f"{self.config.base_url}/api/show",
                json={"name": self.config.model},
                timeout=5,
            )
            r.raise_for_status()
            model_info: dict = r.json().get("model_info", {})
            # Prefer llama.context_length; accept any *.context_length key.
            ctx = model_info.get("llama.context_length")
            if ctx is None:
                for k, v in model_info.items():
                    if k.endswith(".context_length"):
                        ctx = v
                        break
            if isinstance(ctx, int) and ctx > 0:
                log.debug(
                    "CONTEXT WINDOW  model=%s source=api/show context_window=%d",
                    self.config.model, ctx,
                )
                self._context_window = ctx
                return ctx
        except Exception as exc:
            log.debug("Could not fetch context window from /api/show: %s", exc)

        # --- Static fallback table ---
        model_lower = self.config.model.lower()
        for fragment, window in _CONTEXT_WINDOW_FALLBACK:
            if fragment in model_lower:
                log.debug(
                    "CONTEXT WINDOW  model=%s source=fallback_table context_window=%d",
                    self.config.model, window,
                )
                self._context_window = window
                return window

        log.debug(
            "CONTEXT WINDOW  model=%s source=default context_window=%d",
            self.config.model, _DEFAULT_CONTEXT_WINDOW,
        )
        self._context_window = _DEFAULT_CONTEXT_WINDOW
        return _DEFAULT_CONTEXT_WINDOW

    def generate(self, prompt: str) -> str:
        log.debug(
            "LLM REQUEST  model=%s url=%s\n%s\n%s",
            self.config.model,
            self.config.base_url,
            "-" * 60,
            prompt,
        )
        r = httpx.post(
            f"{self.config.base_url}/api/generate",
            json={
                "model": self.config.model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=self.config.timeout,
        )
        r.raise_for_status()
        r_json = r.json()
        response_text = r_json["response"]
        prompt_tokens = r_json.get("prompt_eval_count", 0)
        response_tokens = r_json.get("eval_count", 0)
        total_tokens = prompt_tokens + response_tokens
        log.debug(
            "LLM RESPONSE model=%s tokens=(prompt=%d response=%d total=%d)\n%s\n%s",
            self.config.model,
            prompt_tokens,
            response_tokens,
            total_tokens,
            "-" * 60,
            response_text,
        )
        ctx_window = self._resolve_context_window()
        if prompt_tokens and prompt_tokens >= ctx_window * 0.9:
            log.warning(
                "CONTEXT NEAR LIMIT  model=%s prompt_tokens=%d context_window=%d (%.0f%%)",
                self.config.model,
                prompt_tokens,
                ctx_window,
                prompt_tokens / ctx_window * 100,
            )
        return response_text

    def ping(self) -> bool:
        try:
            httpx.get(f"{self.config.base_url}/api/tags", timeout=5).raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self) -> List[str]:
        r = httpx.get(f"{self.config.base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

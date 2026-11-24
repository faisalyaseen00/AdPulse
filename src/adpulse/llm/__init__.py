from ..config import Settings, get_settings
from .base import LLM, LLMError, Usage


def get_llm(settings: Settings | None = None) -> LLM:
    s = settings or get_settings()
    if s.llm_provider == "anthropic":
        from .anthropic_llm import ClaudeLLM
        return ClaudeLLM(s)
    from .openai_compat import OpenAICompatLLM
    if s.llm_provider == "groq":
        return OpenAICompatLLM(provider="groq", api_key=s.groq_api_key, base_url=s.groq_base_url,
                               model=s.groq_model)
    if s.llm_provider == "openrouter":
        return OpenAICompatLLM(provider="openrouter", api_key=s.openrouter_api_key,
                               base_url=s.openrouter_base_url, model=s.openrouter_model,
                               headers={"X-Title": "AdPulse"})
    raise LLMError(f"Unknown LLM_PROVIDER '{s.llm_provider}' (use anthropic, groq or openrouter)")


__all__ = ["LLM", "LLMError", "Usage", "get_llm"]

from ams_copilot.config import Settings
from ams_copilot.llm.base import LLMClient
from ams_copilot.llm.openai_compat import OpenAICompatibleClient
from ams_copilot.llm.scripted import ScriptedLLM


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "scripted":
        return ScriptedLLM()
    if settings.llm_provider in {"openai", "openai_compatible", "ollama", "vllm"}:
        return OpenAICompatibleClient(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            max_output_tokens=settings.llm_max_output_tokens,
        )
    raise ValueError(f"provedor de LLM desconhecido: {settings.llm_provider}")

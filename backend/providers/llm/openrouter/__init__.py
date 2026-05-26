from providers.llm._base_openai import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(
            api_key_env="OPENROUTER_API_KEY",
            default_base_url="https://openrouter.ai/api/v1",
            provider_name="openrouter",
        )

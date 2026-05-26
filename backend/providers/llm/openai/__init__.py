from providers.llm._base_openai import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(
            api_key_env="OPENAI_API_KEY",
            base_url_env="OPENAI_BASE_URL",
            default_base_url="https://api.openai.com/v1",
            provider_name="openai",
        )

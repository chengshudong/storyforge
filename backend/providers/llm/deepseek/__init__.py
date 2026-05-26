from providers.llm._base_openai import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(
            api_key_env="DEEPSEEK_API_KEY",
            base_url_env="DEEPSEEK_BASE_URL",
            default_base_url="https://api.deepseek.com",
            provider_name="deepseek",
        )

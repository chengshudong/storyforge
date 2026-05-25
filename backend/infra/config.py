from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Novel2Drama"
    app_version: str = "0.1.0"
    debug: bool = True
    secret_key: str = "change-me"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "novel2drama"
    postgres_user: str = "novel2drama"
    postgres_password: str = "novel2drama"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "novel2drama"
    minio_secure: bool = False

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def minio_endpoint(self) -> str:
        return f"{self.minio_host}:{self.minio_port}"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

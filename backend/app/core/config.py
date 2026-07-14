from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "codemind_password"
    mysql_database: str = "codemind"

    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 1
    llm_max_tokens: int = 1200
    llm_enable_thinking: bool | None = None
    llm_thinking_budget: int = 512

    mind_map_model: str = ""
    mind_map_timeout_seconds: float = 120.0
    mind_map_total_timeout_seconds: float = 150.0
    mind_map_max_retries: int = 0
    mind_map_enable_thinking: bool = False
    mind_map_batch_max_tokens: int = 1600
    mind_map_merge_max_tokens: int = 4096
    mind_map_retry_max_tokens: int = 6400

    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_timeout_seconds: float = 30.0
    embedding_max_retries: int = 1

    # JWT
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 3  # 3 hours

    upload_dir: str = "storage/uploads"
    max_upload_size_mb: int = 50
    chroma_persist_dir: str = "storage/chroma"
    backend_cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def upload_dir_path(self) -> Path:
        return self._resolve_project_path(self.upload_dir)

    @property
    def chroma_persist_path(self) -> Path:
        return self._resolve_project_path(self.chroma_persist_dir)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    def _resolve_project_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


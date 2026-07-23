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
    chat_total_timeout_seconds: float = 60.0

    # Per-user LLM presets. The encryption key must be configured separately
    # from JWT_SECRET_KEY so credentials can be rotated independently.
    llm_config_encryption_key: str = ""
    llm_config_max_presets: int = 5
    llm_config_test_cooldown_seconds: int = 30
    llm_config_test_timeout_seconds: float = 30.0
    llm_openai_compatible_allowed_hosts: str = ""
    llm_allow_proxy_fake_ip: bool = False

    mind_map_model: str = ""
    mind_map_timeout_seconds: float = 600.0
    mind_map_total_timeout_seconds: float = 900.0
    mind_map_max_retries: int = 0
    mind_map_enable_thinking: bool = False
    mind_map_batch_max_tokens: int = 1600
    mind_map_merge_max_tokens: int = 4096
    mind_map_retry_max_tokens: int = 6400

    # Temporary AI quiz generation. Sessions are deleted after submission and
    # periodically removed after the TTL when abandoned.
    quiz_timeout_seconds: float = 300.0
    quiz_max_tokens: int = 12000
    quiz_structure_max_retries: int = 1
    quiz_enable_thinking: bool = False
    quiz_worker_concurrency: int = 2
    quiz_session_ttl_minutes: int = 60
    quiz_cleanup_interval_seconds: int = 60
    quiz_context_max_chunks: int = 24
    quiz_context_max_tokens: int = 8000
    quiz_context_max_chars: int = 30000
    quiz_context_max_chars_per_chunk: int = 1600
    quiz_min_context_chars_per_question: int = 40

    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_timeout_seconds: float = 30.0
    embedding_max_retries: int = 1
    retrieval_score_threshold: float = 0.45
    retrieval_hybrid_enabled: bool = True
    retrieval_dense_candidate_k: int = 12
    retrieval_lexical_candidate_k: int = 12
    retrieval_fusion_candidate_k: int = 20
    retrieval_lexical_max_chunks: int = 3000
    retrieval_rrf_k: int = 60

    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = "Qwen/Qwen3-Reranker-8B"
    rerank_timeout_seconds: float = 30.0
    rerank_max_retries: int = 1
    rerank_score_threshold: float = 0.55
    rerank_fail_open: bool = True
    rerank_instruction: str = (
        "判断候选资料是否包含直接回答查询所需的明确事实或解释。"
        "仅主题相关但没有给出所问具体信息、数值、版本、路径或结论时应给低分。"
    )

    document_worker_concurrency: int = 2

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

    @property
    def effective_rerank_api_key(self) -> str:
        return self.rerank_api_key or self.llm_api_key

    @property
    def effective_rerank_base_url(self) -> str:
        return self.rerank_base_url or self.llm_base_url

    def _resolve_project_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


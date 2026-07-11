import logging
import math

from app.core.config import settings


logger = logging.getLogger(__name__)


class EmbeddingServiceError(RuntimeError):
    """可安全返回给用户的 Embedding 服务异常。"""


class EmbeddingAuthenticationError(EmbeddingServiceError):
    """Embedding 服务认证失败。"""


class EmbeddingClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not settings.embedding_api_key or not settings.embedding_model:
            raise EmbeddingServiceError(
                "Embedding 在线服务未配置，请检查服务端的 API Key 和模型名称。"
            )

        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise EmbeddingServiceError("待向量化文本为空，无法调用 Embedding 在线服务。")

        try:
            vectors = self._embed_with_api(texts)
            if len(vectors) != len(texts):
                raise EmbeddingServiceError(
                    "Embedding 服务返回的向量数量不正确，请检查模型配置后重试。"
                )
            dimensions = {len(vector) for vector in vectors}
            if dimensions == {0} or len(dimensions) != 1:
                raise EmbeddingServiceError(
                    "Embedding 服务返回了无效或维度不一致的向量。"
                )
            if any(not math.isfinite(value) for vector in vectors for value in vector):
                raise EmbeddingServiceError("Embedding 服务返回的向量包含无效数值。")
            return vectors
        except EmbeddingServiceError:
            raise
        except Exception as exc:
            logger.exception("Embedding API request failed")
            raise EmbeddingServiceError("Embedding 服务调用失败，请稍后重试。") from exc

    def _embed_with_api(self, texts: list[str]) -> list[list[float]]:
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            OpenAI,
            RateLimitError,
        )

        client_kwargs = {
            "api_key": settings.embedding_api_key,
            "timeout": settings.embedding_timeout_seconds,
            "max_retries": settings.embedding_max_retries,
        }
        if settings.embedding_base_url:
            client_kwargs["base_url"] = settings.embedding_base_url

        client = OpenAI(**client_kwargs)
        try:
            response = client.embeddings.create(model=settings.embedding_model, input=texts)
        except AuthenticationError as exc:
            self._log_provider_error(exc)
            raise EmbeddingAuthenticationError(
                "Embedding API Key 无效，请检查服务端配置。"
            ) from exc
        except RateLimitError as exc:
            self._log_provider_error(exc)
            raise EmbeddingServiceError(
                "Embedding 在线服务请求过于频繁，请稍后重试。"
            ) from exc
        except (APITimeoutError, APIConnectionError) as exc:
            self._log_provider_error(exc)
            raise EmbeddingServiceError(
                "Embedding 在线服务连接超时或暂时不可用，请稍后重试。"
            ) from exc
        except APIStatusError as exc:
            self._log_provider_error(exc)
            if exc.status_code in {401, 403}:
                raise EmbeddingAuthenticationError(
                    "Embedding API Key 无效或无权访问当前模型，请检查服务端配置。"
                ) from exc
            raise EmbeddingServiceError(
                "Embedding 在线服务返回异常，请稍后重试。"
            ) from exc

        ordered_data = sorted(response.data, key=lambda item: getattr(item, "index", 0))
        return [list(item.embedding) for item in ordered_data]

    def _log_provider_error(self, exc: Exception) -> None:
        logger.warning(
            "Embedding provider request failed: %s",
            type(exc).__name__,
            exc_info=True,
        )


embedding_client = EmbeddingClient()

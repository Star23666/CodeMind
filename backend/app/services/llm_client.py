import logging

from app.core.config import settings
from app.services.prompt_builder import RAG_SYSTEM_MESSAGE


logger = logging.getLogger(__name__)


class LlmServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlmClient:
    async def generate_answer(self, prompt: str) -> str:
        if not settings.llm_api_key or not settings.llm_model:
            return self.generate_local_fallback(prompt)

        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AsyncOpenAI,
            AuthenticationError,
            RateLimitError,
        )

        client_kwargs = {
            "api_key": settings.llm_api_key,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        }
        if settings.llm_base_url:
            client_kwargs["base_url"] = settings.llm_base_url

        try:
            client = AsyncOpenAI(**client_kwargs)
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": RAG_SYSTEM_MESSAGE},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=settings.llm_max_tokens,
            )
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise LlmServiceError("大模型服务未返回有效回答。", status_code=502)
            return content.strip()
        except LlmServiceError:
            raise
        except AuthenticationError as exc:
            self._log_provider_error(exc)
            raise LlmServiceError("大模型服务认证失败，请检查服务端配置。", status_code=502) from exc
        except RateLimitError as exc:
            self._log_provider_error(exc)
            raise LlmServiceError("大模型服务请求过于频繁，请稍后重试。") from exc
        except (APITimeoutError, APIConnectionError) as exc:
            self._log_provider_error(exc)
            raise LlmServiceError("大模型服务连接超时或暂时不可用，请稍后重试。") from exc
        except APIStatusError as exc:
            self._log_provider_error(exc)
            raise LlmServiceError("大模型服务返回异常，请稍后重试。", status_code=502) from exc
        except Exception as exc:
            self._log_provider_error(exc)
            raise LlmServiceError("大模型服务暂时不可用，请稍后重试。") from exc

    def generate_local_fallback(self, prompt: str) -> str:
        source_lines = [line for line in prompt.splitlines() if line.startswith("内容：")]
        if not source_lines:
            return "知识库中未找到足够依据。"

        answer_parts = ["当前未配置在线 LLM API，以下为基于检索片段生成的本地演示回答："]
        for index, line in enumerate(source_lines, start=1):
            answer_parts.append(f"{index}. {line.removeprefix('内容：')} [来源{index}]")
        return "\n".join(answer_parts)

    def _log_provider_error(self, exc: Exception) -> None:
        logger.warning("LLM provider request failed: %s", type(exc).__name__, exc_info=True)


llm_client = LlmClient()

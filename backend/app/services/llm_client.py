import asyncio
import inspect
import logging
from collections.abc import AsyncIterator

from app.core.config import settings
from app.services.prompt_builder import RAG_SYSTEM_MESSAGE


logger = logging.getLogger(__name__)


class LlmServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlmClient:
    def _build_client_kwargs(
        self,
        *,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> dict[str, object]:
        client_kwargs: dict[str, object] = {
            "api_key": settings.llm_api_key,
            "timeout": timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds,
            "max_retries": max_retries if max_retries is not None else settings.llm_max_retries,
        }
        if settings.llm_base_url:
            client_kwargs["base_url"] = settings.llm_base_url
        return client_kwargs

    async def _close_client(self, client: object | None) -> None:
        if client is None:
            return
        close = getattr(client, "close", None)
        if close is None:
            return
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.debug("Failed to close LLM client", exc_info=True)

    async def generate_answer(
        self,
        prompt: str,
        *,
        system_message: str = RAG_SYSTEM_MESSAGE,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        model: str | None = None,
        enable_thinking: bool | None = None,
        response_format: dict[str, str] | None = None,
    ) -> str:
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

        client_kwargs = self._build_client_kwargs(
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

        client = None
        try:
            client = AsyncOpenAI(**client_kwargs)
            request_kwargs = {}
            if enable_thinking is not None:
                request_kwargs["extra_body"] = {"enable_thinking": enable_thinking}
            if response_format is not None:
                request_kwargs["response_format"] = response_format
            response = await client.chat.completions.create(
                model=model or settings.llm_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else settings.llm_max_tokens,
                **request_kwargs,
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
        finally:
            await self._close_client(client)

    async def stream_answer(
        self,
        prompt: str,
        *,
        system_message: str = RAG_SYSTEM_MESSAGE,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        model: str | None = None,
        enable_thinking: bool | None = None,
        response_format: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        """Yield answer deltas while preserving the same provider error contract."""
        if not settings.llm_api_key or not settings.llm_model:
            fallback = self.generate_local_fallback(prompt)
            for start in range(0, len(fallback), 32):
                await asyncio.sleep(0)
                yield fallback[start : start + 32]
            return

        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AsyncOpenAI,
            AuthenticationError,
            RateLimitError,
        )

        client = None
        try:
            client = AsyncOpenAI(
                **self._build_client_kwargs(
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                )
            )
            request_kwargs = {}
            if enable_thinking is not None:
                request_kwargs["extra_body"] = {"enable_thinking": enable_thinking}
            if response_format is not None:
                request_kwargs["response_format"] = response_format
            stream = await client.chat.completions.create(
                model=model or settings.llm_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else settings.llm_max_tokens,
                stream=True,
                **request_kwargs,
            )
            finish_reason = None
            async for chunk in stream:
                if not chunk.choices:
                    continue
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
            if finish_reason == "length":
                raise LlmServiceError(
                    "大模型输出达到长度上限，未能生成完整回答。",
                    status_code=502,
                )
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
        finally:
            await self._close_client(client)

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

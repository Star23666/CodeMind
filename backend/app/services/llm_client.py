import asyncio
import inspect
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.config import settings
from app.services.llm_destination_validator import (
    LlmDestinationError,
    validate_llm_destination,
)
from app.services.prompt_builder import RAG_SYSTEM_MESSAGE


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmRuntimeConfig:
    api_key: str
    base_url: str
    model: str
    source: str = "system"
    name: str = "系统默认模型"
    provider: str = "system"

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


def system_llm_runtime_config() -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


AUTO_DISABLE_THINKING_MODEL_PREFIXES = (
    "qwen/qwen3.5-",
    "qwen/qwen3.6-",
)


class LlmServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlmClient:
    async def _validate_destination(self, runtime_config: LlmRuntimeConfig) -> None:
        try:
            await validate_llm_destination(
                base_url=runtime_config.base_url,
                provider=runtime_config.provider,
                source=runtime_config.source,
            )
        except LlmDestinationError as exc:
            raise LlmServiceError(str(exc), status_code=400) from exc

    def _supports_thinking_toggle(self, model: str) -> bool:
        normalized_model = model.strip().casefold()
        return normalized_model.startswith(AUTO_DISABLE_THINKING_MODEL_PREFIXES)

    def _resolve_enable_thinking(
        self,
        *,
        model: str,
        enable_thinking: bool | None,
    ) -> bool | None:
        if enable_thinking is not None:
            return enable_thinking
        if self._supports_thinking_toggle(model):
            return False
        return None

    def _build_completion_request_kwargs(
        self,
        *,
        enable_thinking: bool | None,
        thinking_budget: int | None,
        response_format: dict[str, str] | None,
    ) -> dict[str, object]:
        request_kwargs: dict[str, object] = {}
        if enable_thinking is not None:
            extra_body: dict[str, object] = {"enable_thinking": enable_thinking}
            if enable_thinking:
                extra_body["thinking_budget"] = max(
                    128,
                    thinking_budget
                    if thinking_budget is not None
                    else settings.llm_thinking_budget,
                )
            request_kwargs["extra_body"] = extra_body
        if response_format is not None:
            request_kwargs["response_format"] = response_format
        return request_kwargs

    def _build_client_kwargs(
        self,
        *,
        runtime_config: LlmRuntimeConfig,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
    ) -> dict[str, object]:
        client_kwargs: dict[str, object] = {
            "api_key": runtime_config.api_key,
            "timeout": timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds,
            "max_retries": max_retries if max_retries is not None else settings.llm_max_retries,
        }
        if runtime_config.base_url:
            client_kwargs["base_url"] = runtime_config.base_url
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
        thinking_budget: int | None = None,
        response_format: dict[str, str] | None = None,
        runtime_config: LlmRuntimeConfig | None = None,
    ) -> str:
        selected_config = runtime_config or system_llm_runtime_config()
        if not selected_config.configured:
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
            runtime_config=selected_config,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )

        client = None
        try:
            client = AsyncOpenAI(**client_kwargs)
            selected_model = model or selected_config.model
            selected_enable_thinking = self._resolve_enable_thinking(
                model=selected_model,
                enable_thinking=enable_thinking,
            )
            thinking_attempts = [selected_enable_thinking]
            if (
                selected_enable_thinking is True
                and self._supports_thinking_toggle(selected_model)
            ):
                thinking_attempts.append(False)

            for attempt_index, attempt_enable_thinking in enumerate(thinking_attempts):
                await self._validate_destination(selected_config)
                request_started = time.perf_counter()
                request_kwargs = self._build_completion_request_kwargs(
                    enable_thinking=attempt_enable_thinking,
                    thinking_budget=thinking_budget,
                    response_format=response_format,
                )
                response = await client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=(
                        max_tokens if max_tokens is not None else settings.llm_max_tokens
                    ),
                    **request_kwargs,
                )
                choice = response.choices[0]
                logger.info(
                    "LLM request completed "
                    "(mode=non_stream, model=%s, finish_reason=%s, total_ms=%.1f)",
                    selected_model,
                    getattr(choice, "finish_reason", None),
                    (time.perf_counter() - request_started) * 1000,
                )
                if getattr(choice, "finish_reason", None) == "length":
                    if attempt_index + 1 < len(thinking_attempts):
                        logger.warning(
                            "LLM thinking output reached the token limit; retrying with "
                            "thinking disabled (model=%s)",
                            selected_model,
                        )
                        continue
                    raise LlmServiceError(
                        "大模型输出达到长度上限，未能生成完整回答。",
                        status_code=502,
                    )

                content = choice.message.content
                if not content or not content.strip():
                    raise LlmServiceError("大模型服务未返回有效回答。", status_code=502)
                return content.strip()

            raise LlmServiceError("大模型服务未返回有效回答。", status_code=502)
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
        thinking_budget: int | None = None,
        response_format: dict[str, str] | None = None,
        runtime_config: LlmRuntimeConfig | None = None,
    ) -> AsyncIterator[str]:
        """Yield answer deltas while preserving the same provider error contract."""
        selected_config = runtime_config or system_llm_runtime_config()
        if not selected_config.configured:
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
                    runtime_config=selected_config,
                    timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                )
            )
            selected_model = model or selected_config.model
            selected_enable_thinking = self._resolve_enable_thinking(
                model=selected_model,
                enable_thinking=enable_thinking,
            )
            thinking_attempts = [selected_enable_thinking]
            if (
                selected_enable_thinking is True
                and self._supports_thinking_toggle(selected_model)
            ):
                thinking_attempts.append(False)

            for attempt_index, attempt_enable_thinking in enumerate(thinking_attempts):
                await self._validate_destination(selected_config)
                request_started = time.perf_counter()
                first_token_ms: float | None = None
                request_kwargs = self._build_completion_request_kwargs(
                    enable_thinking=attempt_enable_thinking,
                    thinking_budget=thinking_budget,
                    response_format=response_format,
                )
                stream = await client.chat.completions.create(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=temperature,
                    max_tokens=(
                        max_tokens if max_tokens is not None else settings.llm_max_tokens
                    ),
                    stream=True,
                    **request_kwargs,
                )
                finish_reason = None
                content_chars = 0
                reasoning_chars = 0
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    reasoning_delta = getattr(choice.delta, "reasoning_content", None)
                    if reasoning_delta:
                        reasoning_chars += len(reasoning_delta)
                    content_delta = choice.delta.content
                    if content_delta:
                        if first_token_ms is None:
                            first_token_ms = (time.perf_counter() - request_started) * 1000
                        content_chars += len(content_delta)
                        yield content_delta

                logger.info(
                    "LLM request completed "
                    "(mode=stream, model=%s, finish_reason=%s, first_token_ms=%.1f, total_ms=%.1f)",
                    selected_model,
                    finish_reason,
                    first_token_ms or 0.0,
                    (time.perf_counter() - request_started) * 1000,
                )

                if finish_reason != "length":
                    return
                if content_chars == 0 and attempt_index + 1 < len(thinking_attempts):
                    logger.warning(
                        "LLM thinking output reached the token limit before answer content; "
                        "retrying with thinking disabled (model=%s, reasoning_chars=%s)",
                        selected_model,
                        reasoning_chars,
                    )
                    continue
                logger.warning(
                    "LLM output reached the token limit "
                    "(model=%s, thinking=%s, content_chars=%s, reasoning_chars=%s)",
                    selected_model,
                    attempt_enable_thinking,
                    content_chars,
                    reasoning_chars,
                )
                raise LlmServiceError(
                    "大模型输出达到长度上限，未能生成完整回答。",
                    status_code=502,
                )

            raise LlmServiceError("大模型服务未返回有效回答。", status_code=502)
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

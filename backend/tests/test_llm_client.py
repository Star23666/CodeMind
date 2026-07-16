import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from openai import (
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm_client import LlmClient, LlmServiceError


def run_async(coro):
    return asyncio.run(coro)


class FailingCompletions:
    async def create(self, **kwargs):
        raise RuntimeError("provider unavailable")


class FailingClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": FailingCompletions()})()


class ProviderErrorCompletions:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def create(self, **kwargs):
        raise self.error


class ProviderErrorClient:
    def __init__(self, error: Exception) -> None:
        self.chat = SimpleNamespace(completions=ProviderErrorCompletions(error))


class RecordingCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="基于资料的回答。[来源1]")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class RecordingClient:
    def __init__(self) -> None:
        self.completions = RecordingCompletions()
        self.chat = SimpleNamespace(completions=self.completions)
        self.closed = False

    async def close(self):
        self.closed = True


class StreamingResponse:
    def __init__(self, values: list[str], finish_reason: str | None = None) -> None:
        self.values = values
        self.finish_reason = finish_reason

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for index, value in enumerate(self.values):
            yield SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=value),
                        finish_reason=(
                            self.finish_reason if index == len(self.values) - 1 else None
                        ),
                    )
                ]
            )


class StreamingCompletions:
    def __init__(self, finish_reason: str | None = None) -> None:
        self.kwargs = None
        self.finish_reason = finish_reason

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return StreamingResponse(["第一段", "第二段"], self.finish_reason)


class StreamingClient:
    def __init__(self, finish_reason: str | None = None) -> None:
        self.completions = StreamingCompletions(finish_reason)
        self.chat = SimpleNamespace(completions=self.completions)


class ThinkingLengthResponse:
    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        reasoning_content="思考过程耗尽输出额度",
                    ),
                    finish_reason="length",
                )
            ]
        )


class ThinkingFallbackCompletions:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return ThinkingLengthResponse()
        return StreamingResponse(["降级后的完整回答"])


class ThinkingFallbackClient:
    def __init__(self) -> None:
        self.completions = ThinkingFallbackCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


class LlmClientTest(unittest.TestCase):
    def setUp(self):
        self.destination_validator = AsyncMock()
        self.destination_patch = patch(
            "app.services.llm_client.validate_llm_destination",
            new=self.destination_validator,
        )
        self.destination_patch.start()

    def tearDown(self):
        self.destination_patch.stop()

    def test_provider_uses_configured_timeout_retries_and_output_limit(self):
        client = LlmClient()
        recording_client = RecordingClient()
        constructor_kwargs = {}

        def make_client(**kwargs):
            constructor_kwargs.update(kwargs)
            return recording_client

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch("app.services.llm_client.settings.llm_model", "test-model"),
            patch("app.services.llm_client.settings.llm_base_url", "https://example.test/v1"),
            patch("app.services.llm_client.settings.llm_timeout_seconds", 12.0),
            patch("app.services.llm_client.settings.llm_max_retries", 1),
            patch("app.services.llm_client.settings.llm_max_tokens", 345),
            patch("openai.AsyncOpenAI", side_effect=make_client),
        ):
            answer = run_async(client.generate_answer("test prompt"))

        self.assertEqual(answer, "基于资料的回答。[来源1]")
        self.assertEqual(constructor_kwargs["timeout"], 12.0)
        self.assertEqual(constructor_kwargs["max_retries"], 1)
        self.assertEqual(recording_client.completions.kwargs["max_tokens"], 345)
        self.assertTrue(recording_client.closed)
        self.destination_validator.assert_awaited_once()

    def test_provider_failure_becomes_controlled_service_error(self):
        client = LlmClient()

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch("app.services.llm_client.settings.llm_model", "test-model"),
            patch("openai.AsyncOpenAI", return_value=FailingClient()),
            patch("app.services.llm_client.logger.warning"),
        ):
            with self.assertRaises(LlmServiceError) as context:
                run_async(client.generate_answer("test prompt"))

        self.assertIn("大模型服务", str(context.exception))

    def test_provider_error_logging_does_not_include_exception_detail(self):
        client = LlmClient()
        error = RuntimeError("provider echoed secret sk-user-secret-1234")

        with patch("app.services.llm_client.logger.warning") as warning:
            client._log_provider_error(error)

        warning.assert_called_once_with(
            "LLM provider request failed (type=%s, status=%s)",
            "RuntimeError",
            None,
        )
        self.assertNotIn("sk-user-secret-1234", repr(warning.call_args))

    def _assert_provider_error_message(
        self,
        error: Exception,
        expected: str,
        *,
        status_code: int = 502,
    ) -> None:
        client = LlmClient()
        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch("app.services.llm_client.settings.llm_model", "test-model"),
            patch("openai.AsyncOpenAI", return_value=ProviderErrorClient(error)),
            patch("app.services.llm_client.logger.warning"),
        ):
            with self.assertRaises(LlmServiceError) as context:
                run_async(client.generate_answer("test prompt"))

        self.assertEqual(context.exception.status_code, status_code)
        self.assertIn(expected, str(context.exception))

    def test_authentication_failure_has_specific_message(self):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        response = httpx.Response(401, request=request)
        error = AuthenticationError(
            "invalid api key",
            response=response,
            body={"error": {"code": "invalid_api_key"}},
        )

        self._assert_provider_error_message(error, "认证失败")

    def test_timeout_has_specific_message(self):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")

        self._assert_provider_error_message(
            APITimeoutError(request=request),
            "连接超时",
            status_code=503,
        )

    def test_not_found_status_identifies_model_or_base_url(self):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        response = httpx.Response(404, request=request)
        error = NotFoundError(
            "not found",
            response=response,
            body={"error": {"code": "not_found"}},
        )

        self._assert_provider_error_message(error, "模型或 API 接口不存在")

    def test_model_not_found_body_is_identified_for_bad_request(self):
        request = httpx.Request("POST", "https://example.test/v1/chat/completions")
        response = httpx.Response(400, request=request)
        error = BadRequestError(
            "request rejected",
            response=response,
            body={"error": {"code": "model_not_found"}},
        )

        self._assert_provider_error_message(error, "模型不存在")

    def test_qwen36_automatically_disables_thinking_when_setting_is_unset(self):
        client = LlmClient()
        recording_client = RecordingClient()

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch(
                "app.services.llm_client.settings.llm_model",
                "Qwen/Qwen3.6-35B-A3B",
            ),
            patch("openai.AsyncOpenAI", return_value=recording_client),
        ):
            answer = run_async(client.generate_answer("test prompt"))

        self.assertEqual(answer, "基于资料的回答。[来源1]")
        self.assertEqual(
            recording_client.completions.kwargs["extra_body"],
            {"enable_thinking": False},
        )

    def test_stream_provider_yields_deltas_and_sets_stream_flag(self):
        client = LlmClient()
        streaming_client = StreamingClient()

        async def collect():
            return [
                token
                async for token in client.stream_answer(
                    "test prompt",
                    enable_thinking=False,
                    response_format={"type": "json_object"},
                )
            ]

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch("app.services.llm_client.settings.llm_model", "test-model"),
            patch("openai.AsyncOpenAI", return_value=streaming_client),
        ):
            tokens = run_async(collect())

        self.assertEqual(tokens, ["第一段", "第二段"])
        self.assertTrue(streaming_client.completions.kwargs["stream"])
        self.assertEqual(
            streaming_client.completions.kwargs["extra_body"],
            {"enable_thinking": False},
        )
        self.assertEqual(
            streaming_client.completions.kwargs["response_format"],
            {"type": "json_object"},
        )
        self.destination_validator.assert_awaited_once()

    def test_stream_preserves_output_limit_error(self):
        client = LlmClient()
        streaming_client = StreamingClient(finish_reason="length")

        async def collect():
            return [token async for token in client.stream_answer("test prompt")]

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch("app.services.llm_client.settings.llm_model", "test-model"),
            patch("openai.AsyncOpenAI", return_value=streaming_client),
        ):
            with self.assertRaises(LlmServiceError) as context:
                run_async(collect())

        self.assertEqual(context.exception.status_code, 502)
        self.assertIn("长度上限", str(context.exception))

    def test_stream_retries_qwen36_without_thinking_when_reasoning_hits_limit(self):
        client = LlmClient()
        fallback_client = ThinkingFallbackClient()

        async def collect():
            return [
                token
                async for token in client.stream_answer(
                    "test prompt",
                    enable_thinking=True,
                    thinking_budget=256,
                )
            ]

        with (
            patch("app.services.llm_client.settings.llm_api_key", "test-key"),
            patch(
                "app.services.llm_client.settings.llm_model",
                "Qwen/Qwen3.6-35B-A3B",
            ),
            patch("openai.AsyncOpenAI", return_value=fallback_client),
            patch("app.services.llm_client.logger.warning"),
        ):
            tokens = run_async(collect())

        self.assertEqual(tokens, ["降级后的完整回答"])
        self.assertEqual(len(fallback_client.completions.calls), 2)
        self.assertEqual(
            fallback_client.completions.calls[0]["extra_body"],
            {"enable_thinking": True, "thinking_budget": 256},
        )
        self.assertEqual(
            fallback_client.completions.calls[1]["extra_body"],
            {"enable_thinking": False},
        )

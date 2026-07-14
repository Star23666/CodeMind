import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


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


class LlmClientTest(unittest.TestCase):
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

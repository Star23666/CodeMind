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

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.main import create_app
from app.schemas.contracts import (
    MindMapExpandRequest,
    MindMapGenerateRequest,
    MindMapHistoryUpdate,
    MindMapNode,
    MindMapQuestionRequest,
    MindMapResponse,
    UserRead,
)
from app.services.llm_client import LlmRuntimeConfig, LlmServiceError
from app.services.mind_map_history_service import MindMapHistoryService
from app.services.mind_map_job_service import MindMapJobService
from app.services.mind_map_service import MindMapGenerationError, MindMapService


def run_async(coro):
    return asyncio.run(coro)


class FakeLlmClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt = None
        self.prompts = []
        self.last_system_message = None
        self.last_kwargs = None

    async def generate_answer(self, prompt: str, **kwargs) -> str:
        self.last_prompt = prompt
        self.prompts.append(prompt)
        self.last_system_message = kwargs.get("system_message")
        self.last_kwargs = kwargs
        return self.response


class StreamingLlmClient(FakeLlmClient):
    def __init__(self, response: str) -> None:
        super().__init__(response)
        self.stream_calls = 0
        self.generate_calls = 0
        self.last_kwargs = None

    async def generate_answer(self, prompt: str, **kwargs) -> str:
        self.generate_calls += 1
        raise AssertionError("mind map generation should use the streaming client")

    async def stream_answer(self, prompt: str, **kwargs):
        self.stream_calls += 1
        self.last_kwargs = kwargs
        self.last_prompt = prompt
        self.prompts.append(prompt)
        self.last_system_message = kwargs.get("system_message")
        for start in range(0, len(self.response), 5):
            await asyncio.sleep(0)
            yield self.response[start : start + 5]


class ConcurrencyTrackingLlmClient:
    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0

    async def generate_answer(self, prompt: str, **kwargs) -> str:
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(0.01)
            return """{
              "title": "操作系统",
              "summary": "课程知识结构",
              "source_chunk_ids": [],
              "children": [{
                "title": "进程与线程",
                "summary": "并发基础",
                "source_chunk_ids": [11],
                "children": []
              }]
            }"""
        finally:
            self.active_calls -= 1


class FailingBatchLlmClient:
    def __init__(self) -> None:
        self.calls = 0
        self.cancelled_calls = 0

    async def generate_answer(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(0.01)
            raise LlmServiceError("provider failed", status_code=503)
        try:
            await asyncio.sleep(10)
            return "unused"
        except asyncio.CancelledError:
            self.cancelled_calls += 1
            raise


class LengthThenSuccessStreamingLlmClient:
    def __init__(self) -> None:
        self.max_tokens = []

    async def stream_answer(self, prompt: str, **kwargs):
        self.max_tokens.append(kwargs.get("max_tokens"))
        if len(self.max_tokens) == 1:
            raise LlmServiceError(
                "大模型输出达到长度上限，未能生成完整回答。",
                status_code=502,
            )
        yield '{"title":"重试成功"}'


class TricklingStreamingLlmClient:
    def __init__(self, *, normal_delay: float = 0.02) -> None:
        self.normal_delay = normal_delay
        self.active_calls = 0
        self.max_active_calls = 0
        self.cancelled_calls = 0

    async def stream_answer(self, prompt: str, **kwargs):
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            if prompt.startswith("stuck"):
                try:
                    while True:
                        yield "x"
                        await asyncio.sleep(0.002)
                except asyncio.CancelledError:
                    self.cancelled_calls += 1
                    raise

            await asyncio.sleep(self.normal_delay)
            yield '{"title":"正常完成"}'
        finally:
            self.active_calls -= 1


class MindMapServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._create_schema()
        self.db = self.SessionLocal()
        self._seed_completed_document(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_ai_tree_keeps_only_real_source_ids(self) -> None:
        client = FakeLlmClient(
            """```json
            {
              "title": "操作系统",
              "summary": "核心知识结构",
              "node_type": "overview",
              "key_points": ["先理解资源管理"],
              "learning_tip": "先浏览章节",
              "source_chunk_ids": [],
              "children": [
                {
                  "title": "进程与线程",
                  "summary": "并发执行的基本抽象",
                  "node_type": "concept",
                  "key_points": ["进程隔离资源", "线程共享资源", "比较切换成本", "该项应被截断"],
                  "learning_tip": "画表比较两者",
                  "source_chunk_ids": [11, 999],
                  "children": []
                }
              ]
            }
            ```"""
        )
        service = MindMapService(client=client)

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
        ):
            response = run_async(
                service.generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10),
                )
            )

        self.assertEqual(response.generation_mode, "ai")
        self.assertEqual(response.node_count, 2)
        self.assertEqual([item.chunk_id for item in response.root.children[0].sources], [11])
        self.assertEqual(response.root.node_type.value, "overview")
        self.assertEqual(response.root.children[0].node_type.value, "concept")
        self.assertEqual(len(response.root.children[0].key_points), 3)
        self.assertEqual(response.root.children[0].learning_tip, "画表比较两者")
        self.assertTrue(any("chunk_id=11" in prompt for prompt in client.prompts))
        self.assertIn("严格返回 JSON", client.last_system_message)
        self.assertIn("learning_tip", client.last_prompt)

    def test_missing_model_returns_explicit_error(self) -> None:
        service = MindMapService(client=FakeLlmClient("unused"))

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", ""),
            patch("app.services.mind_map_service.settings.llm_model", ""),
        ):
            with self.assertRaises(MindMapGenerationError) as context:
                run_async(
                    service.generate(
                        self.db,
                        owner_id=1,
                        request=MindMapGenerateRequest(
                            knowledge_base_id=10,
                            document_id=20,
                            max_nodes=8,
                        ),
                    )
                )

        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("必须经过大模型分析", str(context.exception))

    def test_generation_uses_the_owners_personal_model_config(self) -> None:
        client = FakeLlmClient(
            """{
              "title": "个人模型生成的知识地图",
              "children": [{
                "title": "测试概念",
                "summary": "来自个人模型的内容",
                "source_chunk_ids": [11],
                "children": []
              }]
            }"""
        )
        service = MindMapService(client=client)
        personal_config = LlmRuntimeConfig(
            api_key="personal-key",
            base_url="https://api.siliconflow.cn/v1",
            model="personal-model",
            source="personal",
            name="个人模型",
            provider="siliconflow",
        )

        with patch(
            "app.services.mind_map_service.llm_config_service.resolve_runtime",
            return_value=personal_config,
        ) as resolve_runtime:
            response = run_async(
                service.generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10),
                )
            )

        resolve_runtime.assert_called_once_with(self.db, user_id=1)
        self.assertEqual(response.generation_mode, "ai")
        self.assertIs(client.last_kwargs["runtime_config"], personal_config)
        self.assertEqual(client.last_kwargs["model"], "personal-model")

    def test_generation_limits_parallel_llm_calls(self) -> None:
        for chunk_id in range(13, 26):
            self.db.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(id, document_id, chunk_index, chunk_text, page_no) "
                    "VALUES (:id, 20, :chunk_index, :chunk_text, 1)"
                ),
                {
                    "id": chunk_id,
                    "chunk_index": chunk_id - 11,
                    "chunk_text": f"并发控制资料片段 {chunk_id}",
                },
            )
        self.db.commit()
        client = ConcurrencyTrackingLlmClient()

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
        ):
            run_async(
                MindMapService(client=client).generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10),
                )
            )

        self.assertEqual(client.max_active_calls, 3)

    def test_generation_uses_streaming_llm_path(self) -> None:
        client = StreamingLlmClient(
            """{
              "title": "操作系统",
              "summary": "课程知识结构",
              "source_chunk_ids": [],
              "children": [{
                "title": "进程与线程",
                "summary": "并发基础",
                "source_chunk_ids": [11],
                "children": []
              }]
            }"""
        )

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
            patch(
                "app.services.mind_map_service.settings.llm_base_url",
                "https://api.siliconflow.cn/v1",
            ),
        ):
            run_async(
                MindMapService(client=client).generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10),
                )
            )

        self.assertEqual(client.generate_calls, 0)
        self.assertEqual(client.stream_calls, 1)
        self.assertFalse(client.last_kwargs["enable_thinking"])

    def test_service_limits_concurrency_across_operations(self) -> None:
        client = ConcurrencyTrackingLlmClient()
        service = MindMapService(client=client)

        async def call_many() -> None:
            await asyncio.gather(
                *(service._generate_answer(f"prompt-{index}") for index in range(8))
            )

        run_async(call_many())

        self.assertEqual(client.max_active_calls, 3)

    def test_llm_total_timeout_bounds_streaming_generation(self) -> None:
        service = MindMapService(client=ConcurrencyTrackingLlmClient())

        with self.assertRaises(LlmServiceError) as context:
            run_async(
                service._generate_answer(
                    "slow prompt",
                    total_timeout_seconds=0.001,
                )
            )

        self.assertEqual(context.exception.status_code, 504)

    def test_non_positive_total_timeout_allows_slow_generation_to_finish(self) -> None:
        service = MindMapService(client=ConcurrencyTrackingLlmClient())

        answer = run_async(
            service._generate_answer(
                "slow prompt",
                total_timeout_seconds=0,
            )
        )

        self.assertIn('"title": "操作系统"', answer)

    def test_trickling_stream_timeout_releases_slots_for_follow_up_request(self) -> None:
        client = TricklingStreamingLlmClient()
        service = MindMapService(client=client)

        async def run_stuck_then_normal():
            timed_out = await asyncio.gather(
                *(
                    service._generate_answer(
                        f"stuck-{index}",
                        total_timeout_seconds=0.03,
                    )
                    for index in range(service.llm_concurrency)
                ),
                return_exceptions=True,
            )
            follow_up = await asyncio.wait_for(
                service._generate_answer(
                    "normal-follow-up",
                    total_timeout_seconds=0.2,
                ),
                timeout=0.3,
            )
            return timed_out, follow_up

        timed_out, follow_up = run_async(run_stuck_then_normal())

        self.assertEqual(client.max_active_calls, service.llm_concurrency)
        self.assertEqual(client.cancelled_calls, service.llm_concurrency)
        self.assertEqual(client.active_calls, 0)
        self.assertTrue(all(isinstance(error, LlmServiceError) for error in timed_out))
        self.assertTrue(all(error.status_code == 504 for error in timed_out))
        self.assertIn('"title":"正常完成"', follow_up)

    def test_slow_stream_completes_within_total_timeout(self) -> None:
        client = TricklingStreamingLlmClient(normal_delay=0.04)
        service = MindMapService(client=client)

        answer = run_async(
            service._generate_answer(
                "normal-slow",
                total_timeout_seconds=0.2,
            )
        )

        self.assertIn('"title":"正常完成"', answer)
        self.assertEqual(client.cancelled_calls, 0)
        self.assertEqual(client.active_calls, 0)

    def test_structured_generation_retries_once_with_larger_output_budget(self) -> None:
        client = LengthThenSuccessStreamingLlmClient()
        service = MindMapService(client=client)

        with (
            patch(
                "app.services.mind_map_service.settings.mind_map_retry_max_tokens",
                2400,
            ),
            patch("app.services.mind_map_service.logger.warning"),
        ):
            answer = run_async(
                service._generate_answer(
                    "structured prompt",
                    max_tokens=1000,
                    response_format={"type": "json_object"},
                )
            )

        self.assertEqual(answer, '{"title":"重试成功"}')
        self.assertEqual(client.max_tokens, [1000, 2000])

    def test_generation_cancels_remaining_batches_after_failure(self) -> None:
        for chunk_id in range(13, 26):
            self.db.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(id, document_id, chunk_index, chunk_text, page_no) "
                    "VALUES (:id, 20, :chunk_index, :chunk_text, 1)"
                ),
                {
                    "id": chunk_id,
                    "chunk_index": chunk_id - 11,
                    "chunk_text": f"失败取消测试片段 {chunk_id}",
                },
            )
        self.db.commit()
        client = FailingBatchLlmClient()

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
            self.assertRaises(MindMapGenerationError),
        ):
            run_async(
                MindMapService(client=client).generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10),
                )
            )

        self.assertGreaterEqual(client.cancelled_calls, 1)

    def test_document_must_be_completed(self) -> None:
        self.db.execute(text("UPDATE documents SET parse_status = 'processing' WHERE id = 20"))
        self.db.commit()

        with self.assertRaises(MindMapGenerationError) as context:
            run_async(
                MindMapService().generate(
                    self.db,
                    owner_id=1,
                    request=MindMapGenerateRequest(knowledge_base_id=10, document_id=20),
                )
            )

        self.assertIn("尚未完成解析", str(context.exception))

    def test_node_question_uses_only_bound_source_chunks(self) -> None:
        client = FakeLlmClient("进程拥有独立地址空间【来源1】")
        service = MindMapService(client=client)

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
        ):
            response = run_async(
                service.answer_node_question(
                    self.db,
                    owner_id=1,
                    request=MindMapQuestionRequest(
                        knowledge_base_id=10,
                        node_title="进程与线程",
                        question="两者有什么区别？",
                        source_chunk_ids=[11],
                    ),
                )
            )

        self.assertEqual([source.chunk_id for source in response.sources], [11])
        self.assertIn("进程与线程", client.last_prompt)
        self.assertIn("【来源1】", response.answer)

    def test_node_question_rejects_unknown_source_chunk(self) -> None:
        with self.assertRaises(ValueError):
            run_async(
                MindMapService(client=FakeLlmClient("unused")).answer_node_question(
                    self.db,
                    owner_id=1,
                    request=MindMapQuestionRequest(
                        knowledge_base_id=10,
                        node_title="进程",
                        question="请解释",
                        source_chunk_ids=[999],
                    ),
                )
            )

    def test_expand_node_requires_config_after_source_validation(self) -> None:
        request = MindMapExpandRequest(
            knowledge_base_id=10,
            node_title="进程",
            source_chunk_ids=[11],
        )
        with (
            patch("app.services.mind_map_service.settings.llm_api_key", ""),
            patch("app.services.mind_map_service.settings.llm_model", ""),
            self.assertRaises(MindMapGenerationError) as context,
        ):
            run_async(MindMapService().expand_node(self.db, owner_id=1, request=request))

        self.assertEqual(context.exception.status_code, 503)

    def test_expand_node_maps_invalid_model_json_to_502(self) -> None:
        request = MindMapExpandRequest(
            knowledge_base_id=10,
            node_title="进程",
            source_chunk_ids=[11],
        )
        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
            self.assertRaises(MindMapGenerationError) as context,
        ):
            run_async(
                MindMapService(client=FakeLlmClient("not-json")).expand_node(
                    self.db,
                    owner_id=1,
                    request=request,
                )
            )

        self.assertEqual(context.exception.status_code, 502)

    def test_history_insert_and_embedded_id_are_atomic(self) -> None:
        self.db.execute(
            text(
                """
                CREATE TRIGGER fail_history_update
                BEFORE UPDATE ON mind_map_histories
                BEGIN
                    SELECT RAISE(FAIL, 'update failed');
                END
                """
            )
        )
        result = MindMapResponse(
            knowledge_base_id=10,
            generation_mode="ai",
            node_count=1,
            message="done",
            root=MindMapNode(id="root", title="操作系统"),
        )

        with self.assertRaises(Exception):
            MindMapHistoryService().save_generated(self.db, owner_id=1, result=result)

        count = self.db.execute(text("SELECT COUNT(*) FROM mind_map_histories")).scalar_one()
        self.assertEqual(count, 0)

    def test_history_update_preserves_view_state_when_omitted(self) -> None:
        result = MindMapResponse(
            history_id=1,
            knowledge_base_id=10,
            generation_mode="ai",
            node_count=1,
            message="done",
            root=MindMapNode(id="root", title="操作系统"),
        )
        self.db.execute(
            text(
                """
                INSERT INTO mind_map_histories (
                    id, user_id, knowledge_base_id, title, node_count,
                    result_json, view_state_json
                ) VALUES (1, 1, 10, '操作系统', 1, :result, :view_state)
                """
            ),
            {
                "result": result.model_dump_json(),
                "view_state": '{"zoom": 1.5, "x": 20}',
            },
        )
        self.db.commit()

        updated = MindMapHistoryService().update(
            self.db,
            history_id=1,
            owner_id=1,
            payload=MindMapHistoryUpdate(title="操作系统复习版"),
        )

        self.assertEqual(updated.title, "操作系统复习版")
        self.assertEqual(updated.view_state, {"zoom": 1.5, "x": 20})

    def test_background_job_persists_progress_and_result(self) -> None:
        service = MindMapJobService()
        queued = service.create_job(
            self.db,
            owner_id=1,
            request=MindMapGenerateRequest(knowledge_base_id=10),
        )
        result = MindMapResponse(
            knowledge_base_id=10,
            document_id=None,
            generation_mode="ai",
            node_count=1,
            message="done",
            root=MindMapNode(id="root", title="操作系统"),
        )

        with (
            patch("app.services.mind_map_job_service.SessionLocal", self.SessionLocal),
            patch(
                "app.services.mind_map_job_service.mind_map_service.generate",
                new=AsyncMock(return_value=result),
            ),
        ):
            run_async(service.process_job(queued.job_id))

        completed = service.get_job(self.db, job_id=queued.job_id, owner_id=1)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.progress, 100)
        self.assertEqual(completed.result.root.title, "操作系统")

    def test_job_completion_and_generated_history_are_atomic(self) -> None:
        service = MindMapJobService()
        queued = service.create_job(
            self.db,
            owner_id=1,
            request=MindMapGenerateRequest(knowledge_base_id=10),
        )
        self.db.execute(
            text(
                """
                CREATE TRIGGER fail_job_completion
                BEFORE UPDATE ON mind_map_jobs
                WHEN NEW.status = 'completed'
                BEGIN
                    SELECT RAISE(FAIL, 'completion failed');
                END
                """
            )
        )
        result = MindMapResponse(
            knowledge_base_id=10,
            generation_mode="ai",
            node_count=1,
            message="done",
            root=MindMapNode(id="root", title="操作系统"),
        )

        with (
            patch("app.services.mind_map_job_service.SessionLocal", self.SessionLocal),
            patch(
                "app.services.mind_map_job_service.mind_map_service.generate",
                new=AsyncMock(return_value=result),
            ),
            patch("app.services.mind_map_job_service.logger.exception"),
        ):
            run_async(service.process_job(queued.job_id))

        history_count = self.db.execute(
            text("SELECT COUNT(*) FROM mind_map_histories")
        ).scalar_one()
        failed = service.get_job(self.db, job_id=queued.job_id, owner_id=1)
        self.assertEqual(history_count, 0)
        self.assertEqual(failed.status, "failed")

    def test_start_requeues_interrupted_jobs(self) -> None:
        service = MindMapJobService()
        queued = service.create_job(
            self.db,
            owner_id=1,
            request=MindMapGenerateRequest(knowledge_base_id=10),
        )
        self.db.execute(
            text(
                """
                UPDATE mind_map_jobs
                SET status = 'processing', stage = 'merging', progress = 72
                WHERE id = :job_id
                """
            ),
            {"job_id": queued.job_id},
        )
        self.db.commit()

        with (
            patch("app.services.mind_map_job_service.SessionLocal", self.SessionLocal),
            patch.object(service, "enqueue") as enqueue,
        ):
            run_async(service.start())

        recovered = service.get_job(self.db, job_id=queued.job_id, owner_id=1)
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.stage, "queued")
        self.assertEqual(recovered.progress, 0)
        enqueue.assert_called_once_with(queued.job_id)

    def test_completed_job_is_not_processed_again(self) -> None:
        service = MindMapJobService()
        queued = service.create_job(
            self.db,
            owner_id=1,
            request=MindMapGenerateRequest(knowledge_base_id=10),
        )
        self.db.execute(
            text(
                """
                UPDATE mind_map_jobs
                SET status = 'completed', stage = 'completed', progress = 100
                WHERE id = :job_id
                """
            ),
            {"job_id": queued.job_id},
        )
        self.db.commit()

        generate = AsyncMock()
        with (
            patch("app.services.mind_map_job_service.SessionLocal", self.SessionLocal),
            patch("app.services.mind_map_job_service.mind_map_service.generate", new=generate),
        ):
            run_async(service.process_job(queued.job_id))

        generate.assert_not_awaited()
        completed = service.get_job(self.db, job_id=queued.job_id, owner_id=1)
        self.assertEqual(completed.status, "completed")

    def _create_schema(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    """
                    CREATE TABLE knowledge_bases (
                        id INTEGER PRIMARY KEY,
                        owner_id INTEGER NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        visibility VARCHAR(20) NOT NULL DEFAULT 'private'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE mind_map_histories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        knowledge_base_id INTEGER NOT NULL,
                        document_id INTEGER,
                        title VARCHAR(120) NOT NULL,
                        node_count INTEGER NOT NULL,
                        result_json TEXT NOT NULL,
                        view_state_json TEXT NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE mind_map_jobs (
                        id VARCHAR(32) PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        knowledge_base_id INTEGER NOT NULL,
                        document_id INTEGER,
                        max_depth INTEGER NOT NULL DEFAULT 3,
                        max_nodes INTEGER NOT NULL DEFAULT 28,
                        status VARCHAR(20) NOT NULL,
                        stage VARCHAR(30) NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        message VARCHAR(255) NOT NULL,
                        result_json TEXT,
                        error_message TEXT,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE documents (
                        id INTEGER PRIMARY KEY,
                        knowledge_base_id INTEGER NOT NULL,
                        owner_id INTEGER NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        file_type VARCHAR(20) NOT NULL DEFAULT 'txt',
                        file_size INTEGER NOT NULL DEFAULT 0,
                        parse_status VARCHAR(20) NOT NULL,
                        error_message TEXT,
                        chunk_count INTEGER NOT NULL DEFAULT 0
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE document_chunks (
                        id INTEGER PRIMARY KEY,
                        document_id INTEGER NOT NULL,
                        chunk_index INTEGER NOT NULL,
                        chunk_text TEXT NOT NULL,
                        page_no INTEGER
                    )
                    """
                )
            )

    def _seed_completed_document(self, db) -> None:
        db.execute(text("INSERT INTO users (id) VALUES (1)"))
        db.execute(
            text(
                "INSERT INTO knowledge_bases (id, owner_id, name, description, visibility) "
                "VALUES (10, 1, '操作系统', NULL, 'private')"
            )
        )
        db.execute(
            text(
                "INSERT INTO documents (id, knowledge_base_id, owner_id, file_name, parse_status) "
                "VALUES (20, 10, 1, '操作系统笔记.txt', 'completed')"
            )
        )
        db.execute(
            text(
                "INSERT INTO document_chunks (id, document_id, chunk_index, chunk_text, page_no) VALUES "
                "(11, 20, 0, '进程拥有独立地址空间，线程共享进程资源。', 1), "
                "(12, 20, 1, '互斥锁和信号量用于协调并发访问。', 2)"
            )
        )
        db.commit()


class MindMapApiTest(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=engine)
        helper = MindMapServiceTest(methodName="runTest")
        helper.engine = engine
        helper._create_schema()
        with self.SessionLocal() as db:
            helper._seed_completed_document(db)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app = create_app()
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: UserRead(
            id=1,
            username="alice",
            email="alice@example.com",
        )
        self.client = TestClient(app)

    def test_generate_endpoint_returns_canvas_contract(self) -> None:
        model_response = """{
          "title": "操作系统",
          "summary": "课程知识结构",
          "source_chunk_ids": [],
          "children": [{
            "title": "进程与线程",
            "summary": "并发基础",
            "source_chunk_ids": [11],
            "children": []
          }]
        }"""

        async def stream_model_response(prompt: str, **kwargs):
            yield model_response

        with (
            patch("app.services.mind_map_service.settings.llm_api_key", "test-key"),
            patch("app.services.mind_map_service.settings.llm_model", "test-model"),
            patch(
                "app.services.mind_map_service.mind_map_service.client.stream_answer",
                new=stream_model_response,
            ),
        ):
            response = self.client.post(
                "/api/mind-maps/generate",
                json={"knowledge_base_id": 10, "max_depth": 3, "max_nodes": 20},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["generation_mode"], "ai")
        self.assertEqual(payload["root"]["title"], "操作系统")
        self.assertGreater(payload["node_count"], 1)

    def test_generate_endpoint_explains_empty_scope(self) -> None:
        with self.SessionLocal() as db:
            db.execute(text("DELETE FROM document_chunks"))
            db.commit()

        response = self.client.post(
            "/api/mind-maps/generate",
            json={"knowledge_base_id": 10},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("已解析片段", response.json()["detail"])

    def test_delete_history_returns_action_status(self) -> None:
        with self.SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO mind_map_histories (
                        id, user_id, knowledge_base_id, document_id, title,
                        node_count, result_json, view_state_json
                    ) VALUES (1, 1, 10, 20, '操作系统', 1, '{}', '{}')
                    """
                )
            )
            db.commit()

        response = self.client.delete("/api/mind-maps/histories/1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "accepted", "message": "思维导图历史记录已删除。"},
        )

    def test_create_history_rejects_document_from_another_knowledge_base(self) -> None:
        with self.SessionLocal() as db:
            db.execute(
                text(
                    "INSERT INTO knowledge_bases (id, owner_id, name, description, visibility) "
                    "VALUES (11, 1, '计算机网络', NULL, 'private')"
                )
            )
            db.commit()

        response = self.client.post(
            "/api/mind-maps/histories",
            json={
                "knowledge_base_id": 11,
                "document_id": 20,
                "title": "错误归属",
                "generation_mode": "ai",
                "root": {"id": "root", "title": "错误归属"},
                "view_state": {},
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "知识库或文档不存在。")

    def test_create_history_accepts_owned_document_in_same_knowledge_base(self) -> None:
        response = self.client.post(
            "/api/mind-maps/histories",
            json={
                "knowledge_base_id": 10,
                "document_id": 20,
                "title": "操作系统",
                "generation_mode": "ai",
                "root": {"id": "root", "title": "操作系统"},
                "view_state": {},
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["document_id"], 20)


if __name__ == "__main__":
    unittest.main()

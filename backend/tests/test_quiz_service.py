import asyncio
import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
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
from app.schemas.contracts import UserRead
from app.schemas.quiz import (
    GeneratedQuizPayload,
    GeneratedQuizQuestion,
    QuizAnswerSubmission,
    QuizCreateRequest,
    QuizQuestionType,
    QuizSubmitRequest,
)
from app.main import create_app
from app.services.llm_client import LlmRuntimeConfig, LlmServiceError
from app.services.quiz_service import QuizService, QuizServiceError


def run_async(coro):
    return asyncio.run(coro)


class QuizServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.execute(text("PRAGMA foreign_keys = ON"))
        self._create_schema()
        self._seed_data()
        self.client = AsyncMock()
        self.service = QuizService(client=self.client)
        self.runtime = LlmRuntimeConfig(
            api_key="personal-key",
            base_url="https://api.siliconflow.cn/v1",
            model="test-model",
            source="personal",
            name="个人测试模型",
            provider="siliconflow",
        )
        self.setting_patches = [
            patch("app.services.quiz_service.settings.quiz_context_max_chunks", 6),
            patch("app.services.quiz_service.settings.quiz_context_max_tokens", 1800),
            patch("app.services.quiz_service.settings.quiz_context_max_chars", 2400),
            patch("app.services.quiz_service.settings.quiz_context_max_chars_per_chunk", 600),
            patch("app.services.quiz_service.settings.quiz_min_context_chars_per_question", 20),
            patch("app.services.quiz_service.settings.quiz_structure_max_retries", 1),
            patch("app.services.quiz_service.settings.quiz_max_tokens", 4000),
        ]
        for setting_patch in self.setting_patches:
            setting_patch.start()

    def tearDown(self) -> None:
        for setting_patch in reversed(self.setting_patches):
            setting_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_private_and_public_bases_are_selectable_but_other_private_base_is_not(self) -> None:
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([11, 100]),
        )
        self.assertEqual(session.knowledge_base_ids, [11, 100])
        self.assertEqual(session.status.value, "queued")

        with self.assertRaises(QuizServiceError) as context:
            self.service.create_session(
                self.db,
                owner_id=1,
                request=self._request([12]),
            )
        self.assertEqual(context.exception.status_code, 404)

    def test_generation_rechecks_access_after_a_public_base_becomes_private(self) -> None:
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([100]),
        )
        self.db.execute(
            text(
                "UPDATE knowledge_bases SET visibility = 'private', owner_id = 2 "
                "WHERE id = 100"
            )
        )
        self.db.commit()

        with self.assertRaises(QuizServiceError) as context:
            run_async(
                self.service.generate_session(
                    self.db,
                    session_id=session.session_id,
                )
            )

        self.assertEqual(context.exception.status_code, 404)
        self.client.generate_answer.assert_not_awaited()

    def test_empty_or_insufficient_content_returns_an_explicit_error(self) -> None:
        with self.assertRaises(QuizServiceError) as empty_context:
            self.service.create_session(
                self.db,
                owner_id=1,
                request=self._request([13]),
            )
        self.assertIn("没有可用于出题", str(empty_context.exception))

        self.db.execute(
            text("UPDATE document_chunks SET chunk_text = '短' WHERE knowledge_base_id = 11")
        )
        self.db.commit()
        with self.assertRaises(QuizServiceError) as short_context:
            self.service.create_session(
                self.db,
                owner_id=1,
                request=self._request([11]),
            )
        self.assertIn("内容不足", str(short_context.exception))

    def test_context_sampling_is_balanced_and_bounded(self) -> None:
        chunks = self.service._collect_context_chunks(self.db, self._request([11, 100]))
        base_ids = [chunk["source"].knowledge_base_id for chunk in chunks]
        self.assertIn(11, base_ids)
        self.assertIn(100, base_ids)
        self.assertLessEqual(len(chunks), 6)
        self.assertLessEqual(sum(len(chunk["source_text"]) for chunk in chunks), 2400)
        self.assertLessEqual(sum(len(chunk["source_text"]) for chunk in chunks), 1800)

    def test_context_sampling_round_robins_documents_inside_one_base(self) -> None:
        request = self._request([11]).model_copy(update={"topic": None})
        chunks = self.service._collect_context_chunks(self.db, request)
        document_ids = [chunk["source"].document_id for chunk in chunks]

        self.assertGreaterEqual(len(document_ids), 2)
        self.assertEqual(set(document_ids[:2]), {21, 24})

    def test_topic_context_only_keeps_directly_matching_material(self) -> None:
        self.db.execute(
            text(
                "INSERT INTO documents (id, knowledge_base_id, owner_id, file_name, parse_status) "
                "VALUES (25, 11, 1, 'network-tcp.txt', 'completed')"
            )
        )
        self.db.execute(
            text(
                "INSERT INTO document_chunks "
                "(id, document_id, knowledge_base_id, chunk_index, chunk_text) "
                "VALUES (38, 25, 11, 1, 'TCP 通过三次握手建立连接，属于计算机网络传输层内容。')"
            )
        )
        self.db.commit()

        request = self._request([11]).model_copy(update={"topic": "TCP 与计算机网络"})
        chunks = self.service._collect_context_chunks(self.db, request)

        self.assertTrue(chunks)
        self.assertTrue(
            all(
                "tcp" in (chunk["source_text"] + chunk["source"].file_name).casefold()
                or "计算机网络" in (chunk["source_text"] + chunk["source"].file_name)
                for chunk in chunks
            )
        )

    def test_specified_types_are_generated_in_small_type_batches(self) -> None:
        request = QuizCreateRequest(
            knowledge_base_ids=[11],
            question_count=6,
            question_types=list(QuizQuestionType),
            random_mix=False,
            topic="操作系统",
        )
        chunks = self.service._collect_context_chunks(self.db, request)
        templates = {
            question["question_type"]: question
            for question in self._valid_payload()["questions"]
        }
        templates["scenario"] = {
            "question_type": "scenario",
            "cognitive_level": "analyze",
            "prompt": "操作系统负载升高时应如何分析调度问题？",
            "options": [],
            "correct_answer": None,
            "accepted_answers": [],
            "keywords": [],
            "reference_answer": "检查运行队列、上下文切换和调度策略。",
            "explanation": "资料说明调度状态和资源竞争需要结合观察。",
            "source_ids": ["S1"],
        }
        payloads = []
        for index, question_type in enumerate(QuizQuestionType, start=1):
            question = json.loads(json.dumps(templates[question_type.value], ensure_ascii=False))
            question["prompt"] = f"操作系统题型验证 {index}：{question['prompt']}"
            payloads.append(json.dumps({"questions": [question]}, ensure_ascii=False))
        self.client.generate_answer.side_effect = payloads

        payload = run_async(
            self.service._generate_payload(
                request=request,
                context_chunks=chunks,
                runtime_config=self.runtime,
            )
        )

        self.assertEqual(self.client.generate_answer.await_count, len(QuizQuestionType))
        self.assertEqual(
            {question.question_type for question in payload.questions},
            set(QuizQuestionType),
        )

    def test_generation_requires_document_coverage_without_a_topic(self) -> None:
        request = self._request([11]).model_copy(update={"topic": None})
        chunks = self.service._collect_context_chunks(self.db, request)
        payload = self._valid_payload()

        with self.assertRaisesRegex(ValueError, "资料覆盖不足"):
            self.service._validate_generated_payload(
                self._payload_model(payload),
                request,
                chunks,
            )

        second_document_source = next(
            chunk["source_id"]
            for chunk in chunks
            if chunk["source"].document_id == 24
        )
        payload["questions"][0]["source_ids"] = [second_document_source]
        self.service._validate_generated_payload(
            self._payload_model(payload),
            request,
            chunks,
        )

    def test_quiz_api_contract_exposes_jobs_and_never_places_answers_in_get_schema(self) -> None:
        schema = create_app().openapi()
        self.assertIn("/api/quizzes/sessions", schema["paths"])
        self.assertIn("/api/quizzes/sessions/{session_id}", schema["paths"])
        self.assertIn("/api/quizzes/sessions/{session_id}/submit", schema["paths"])
        question_properties = schema["components"]["schemas"]["QuizQuestionRead"]["properties"]
        self.assertNotIn("correct_answer", question_properties)
        self.assertNotIn("explanation", question_properties)
        self.assertNotIn("sources", question_properties)

    def test_api_hides_answers_enforces_owner_and_deletes_after_submit(self) -> None:
        def override_get_db():
            db = self.Session()
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
        client = TestClient(app)

        with patch("app.api.routes.quiz_job_service.enqueue") as enqueue:
            created = client.post(
                "/api/quizzes/sessions",
                json=self._request([11, 100]).model_dump(mode="json"),
            )
        self.assertEqual(created.status_code, 202)
        session_id = created.json()["session_id"]
        enqueue.assert_called_once_with(session_id)

        self.client.generate_answer.return_value = json.dumps(
            self._valid_payload(),
            ensure_ascii=False,
        )
        with patch(
            "app.services.quiz_service.llm_config_service.resolve_runtime",
            return_value=self.runtime,
        ):
            run_async(
                self.service.generate_session(
                    self.db,
                    session_id=session_id,
                )
            )

        ready = client.get(f"/api/quizzes/sessions/{session_id}")
        self.assertEqual(ready.status_code, 200)
        for question in ready.json()["questions"]:
            self.assertNotIn("correct_answer", question)
            self.assertNotIn("explanation", question)
            self.assertNotIn("sources", question)

        app.dependency_overrides[get_current_user] = lambda: UserRead(
            id=2,
            username="bob",
            email="bob@example.com",
        )
        self.assertEqual(
            client.get(f"/api/quizzes/sessions/{session_id}").status_code,
            404,
        )

        app.dependency_overrides[get_current_user] = lambda: UserRead(
            id=1,
            username="alice",
            email="alice@example.com",
        )
        submitted = client.post(
            f"/api/quizzes/sessions/{session_id}/submit",
            json={"answers": []},
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertTrue(
            all("correct_answer" in item for item in submitted.json()["results"])
        )
        self.assertEqual(
            client.get(f"/api/quizzes/sessions/{session_id}").status_code,
            404,
        )

    def test_scenario_questions_are_supported_without_forced_scoring(self) -> None:
        question = GeneratedQuizQuestion(
            question_type="scenario",
            cognitive_level="analyze",
            prompt="服务器负载升高时，你会如何分析进程调度问题？",
            reference_answer="检查运行队列、上下文切换和调度策略。",
            explanation="资料给出了进程调度的主要观察指标。",
            source_ids=["S1"],
        )
        self.assertEqual(question.question_type, QuizQuestionType.SCENARIO)
        self.assertIsNone(
            self.service._grade(
                QuizQuestionType.SCENARIO,
                "学生分析",
                {"reference_answer": question.reference_answer},
            )
        )

    def test_model_null_optional_lists_and_duplicate_answers_are_canonicalized(self) -> None:
        question = GeneratedQuizQuestion.model_validate(
            {
                "question_type": "fill_blank",
                "cognitive_level": "remember",
                "prompt": "操作系统使用什么结构记录进程信息？",
                "options": None,
                "correct_answer": None,
                "accepted_answers": ["进程控制块", "进程控制块"],
                "keywords": None,
                "reference_answer": None,
                "explanation": "资料说明进程控制块保存进程信息。",
                "source_ids": ["S1", "S1"],
            }
        )
        self.assertEqual(question.options, [])
        self.assertEqual(question.accepted_answers, ["进程控制块"])
        self.assertEqual(question.keywords, [])
        self.assertEqual(question.source_ids, ["S1"])

    def test_fill_blank_supports_keyword_scoring(self) -> None:
        self.assertTrue(
            self.service._grade(
                QuizQuestionType.FILL_BLANK,
                "线程共享地址空间，但拥有独立栈",
                {"accepted_answers": [], "keywords": ["地址空间", "独立栈"]},
            )
        )

    def test_internal_source_labels_are_removed_from_user_facing_text(self) -> None:
        cleaned = self.service._clean_generated_text(
            "根据资料 S4 和 S6，可以得到结论；请再核对片段 S10。"
        )
        self.assertEqual(cleaned, "根据引用资料，可以得到结论；请再核对引用资料。")

    def test_generation_hides_answers_and_preserves_verifiable_sources(self) -> None:
        session = self._create_and_generate()
        ready = self.service.get_session(
            self.db,
            session_id=session.session_id,
            owner_id=1,
        )
        serialized = ready.model_dump_json()
        self.assertEqual(ready.status.value, "ready")
        self.assertEqual(len(ready.questions), 5)
        self.assertNotIn("correct_answer", serialized)
        self.assertNotIn("accepted_answers", serialized)
        self.assertNotIn("reference_answer", serialized)
        self.assertNotIn("依据资料", serialized)
        self.assertTrue(all(question.source_count >= 1 for question in ready.questions))

    def test_invalid_structured_output_is_retried_and_never_persisted(self) -> None:
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([11]),
        )
        self.client.generate_answer.side_effect = [
            "not-json",
            json.dumps({"questions": []}),
        ]
        with patch(
            "app.services.quiz_service.llm_config_service.resolve_runtime",
            return_value=self.runtime,
        ):
            with self.assertRaises(QuizServiceError):
                run_async(
                    self.service.generate_session(
                        self.db,
                        session_id=session.session_id,
                    )
                )

        count = self.db.execute(
            text("SELECT COUNT(*) FROM quiz_questions WHERE session_id = :id"),
            {"id": session.session_id},
        ).scalar_one()
        self.assertEqual(count, 0)
        self.assertEqual(self.client.generate_answer.await_count, 2)
        self.assertTrue(
            all(
                call.kwargs["runtime_config"] is self.runtime
                for call in self.client.generate_answer.await_args_list
            )
        )

    def test_source_id_retry_lists_allowed_ids_and_recovers(self) -> None:
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([11]),
        )
        invalid_payload = self._valid_payload()
        invalid_payload["questions"][0]["source_ids"] = ["S999"]
        self.client.generate_answer.side_effect = [
            json.dumps(invalid_payload, ensure_ascii=False),
            json.dumps(self._valid_payload(), ensure_ascii=False),
        ]

        with patch(
            "app.services.quiz_service.llm_config_service.resolve_runtime",
            return_value=self.runtime,
        ):
            run_async(
                self.service.generate_session(
                    self.db,
                    session_id=session.session_id,
                )
            )

        ready = self.service.get_session(
            self.db,
            session_id=session.session_id,
            owner_id=1,
        )
        self.assertEqual(ready.status.value, "ready")
        self.assertEqual(self.client.generate_answer.await_count, 2)
        first_prompt = self.client.generate_answer.await_args_list[0].args[0]
        retry_prompt = self.client.generate_answer.await_args_list[1].args[0]
        self.assertIn("可用来源编号：S1", first_prompt)
        self.assertIn("不存在的资料来源：S999", retry_prompt)
        self.assertIn("允许使用的来源编号只有：S1", retry_prompt)

    def test_personal_and_system_runtime_are_forwarded_without_fallback(self) -> None:
        for source in ("personal", "system"):
            with self.subTest(source=source):
                runtime = LlmRuntimeConfig(
                    api_key=f"{source}-key",
                    base_url="https://api.siliconflow.cn/v1",
                    model=f"{source}-model",
                    source=source,
                    name=source,
                    provider="siliconflow" if source == "personal" else "system",
                )
                session = self.service.create_session(
                    self.db,
                    owner_id=1,
                    request=self._request([11]),
                )
                self.client.generate_answer.reset_mock()
                self.client.generate_answer.return_value = json.dumps(
                    self._valid_payload(),
                    ensure_ascii=False,
                )
                with patch(
                    "app.services.quiz_service.llm_config_service.resolve_runtime",
                    return_value=runtime,
                ):
                    run_async(
                        self.service.generate_session(
                            self.db,
                            session_id=session.session_id,
                        )
                    )
                forwarded = self.client.generate_answer.await_args.kwargs["runtime_config"]
                self.assertIs(forwarded, runtime)

        failing_session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([11]),
        )
        self.client.generate_answer.reset_mock()
        self.client.generate_answer.side_effect = LlmServiceError("个人模型调用失败")
        with patch(
            "app.services.quiz_service.llm_config_service.resolve_runtime",
            return_value=self.runtime,
        ):
            with self.assertRaises(LlmServiceError):
                run_async(
                    self.service.generate_session(
                        self.db,
                        session_id=failing_session.session_id,
                    )
                )
        self.assertEqual(self.client.generate_answer.await_count, 1)

    def test_objective_and_fill_questions_are_scored_and_subjective_answer_is_returned(self) -> None:
        session = self._create_and_generate()
        question_rows = self.db.execute(
            text(
                "SELECT id, question_type FROM quiz_questions "
                "WHERE session_id = :id ORDER BY order_no"
            ),
            {"id": session.session_id},
        ).all()
        submitted_by_type = {
            "single_choice": "A",
            "multiple_choice": ["A", "C"],
            "true_false": True,
            "fill_blank": "进程控制块",
            "short_answer": "学生自己的概括",
        }
        result = self.service.submit(
            self.db,
            session_id=session.session_id,
            owner_id=1,
            request=QuizSubmitRequest(
                answers=[
                    QuizAnswerSubmission(
                        question_id=int(question_id),
                        answer=submitted_by_type[str(question_type)],
                    )
                    for question_id, question_type in question_rows
                ]
            ),
        )

        self.assertEqual(result.auto_scored_count, 4)
        self.assertEqual(result.correct_count, 4)
        self.assertEqual(result.manual_review_count, 1)
        self.assertEqual(result.score_percent, 100.0)
        subjective = next(
            item
            for item in result.results
            if item.question_type == QuizQuestionType.SHORT_ANSWER
        )
        self.assertIsNone(subjective.is_correct)
        self.assertEqual(subjective.reference_answer, "进程与线程的主要差异包括资源和调度单位。")
        self.assertTrue(all(item.explanation for item in result.results))
        self.assertTrue(all(item.sources for item in result.results))
        remaining = self.db.execute(
            text("SELECT COUNT(*) FROM quiz_sessions WHERE id = :id"),
            {"id": session.session_id},
        ).scalar_one()
        self.assertEqual(remaining, 0)

    def test_result_can_hide_explanations_and_sources(self) -> None:
        request = self._request([11]).model_copy(
            update={"show_explanations_and_sources": False}
        )
        session = self._create_and_generate(request=request)
        result = self.service.submit(
            self.db,
            session_id=session.session_id,
            owner_id=1,
            request=QuizSubmitRequest(),
        )
        self.assertTrue(all(item.explanation is None for item in result.results))
        self.assertTrue(all(not item.sources for item in result.results))

    def test_session_is_owner_only_and_expired_sessions_are_removed(self) -> None:
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=self._request([11]),
        )
        with self.assertRaises(QuizServiceError) as context:
            self.service.get_session(
                self.db,
                session_id=session.session_id,
                owner_id=2,
            )
        self.assertEqual(context.exception.status_code, 404)

        self.db.execute(
            text("UPDATE quiz_sessions SET expires_at = :expired WHERE id = :id"),
            {
                "id": session.session_id,
                "expired": datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1),
            },
        )
        self.db.commit()
        removed = self.service.cleanup_expired(self.db)
        self.assertEqual(removed, 1)

    def _request(self, knowledge_base_ids: list[int]) -> QuizCreateRequest:
        return QuizCreateRequest(
            knowledge_base_ids=knowledge_base_ids,
            question_count=5,
            random_mix=True,
            topic="操作系统",
        )

    def _create_and_generate(self, request: QuizCreateRequest | None = None):
        session = self.service.create_session(
            self.db,
            owner_id=1,
            request=request or self._request([11, 100]),
        )
        self.client.generate_answer.return_value = json.dumps(
            self._valid_payload(),
            ensure_ascii=False,
        )
        with patch(
            "app.services.quiz_service.llm_config_service.resolve_runtime",
            return_value=self.runtime,
        ):
            run_async(
                self.service.generate_session(
                    self.db,
                    session_id=session.session_id,
                )
            )
        return session

    def _valid_payload(self) -> dict:
        source_ids = ["S1"]
        return {
            "questions": [
                {
                    "question_type": "single_choice",
                    "cognitive_level": "remember",
                    "prompt": "进程调度的基本单位是什么？",
                    "options": [
                        {"id": "A", "text": "线程"},
                        {"id": "B", "text": "文件"},
                    ],
                    "correct_answer": "A",
                    "accepted_answers": [],
                    "keywords": [],
                    "reference_answer": None,
                    "explanation": "依据资料，线程是处理器调度的基本单位。",
                    "source_ids": source_ids,
                },
                {
                    "question_type": "multiple_choice",
                    "cognitive_level": "apply",
                    "prompt": "进程控制块通常记录哪些内容？",
                    "options": [
                        {"id": "A", "text": "进程状态"},
                        {"id": "B", "text": "显示器型号"},
                        {"id": "C", "text": "寄存器信息"},
                    ],
                    "correct_answer": ["A", "C"],
                    "accepted_answers": [],
                    "keywords": [],
                    "reference_answer": None,
                    "explanation": "PCB 保存进程状态和处理器现场。",
                    "source_ids": source_ids,
                },
                {
                    "question_type": "true_false",
                    "cognitive_level": "understand",
                    "prompt": "同一进程中的线程通常共享地址空间。",
                    "options": [],
                    "correct_answer": True,
                    "accepted_answers": [],
                    "keywords": [],
                    "reference_answer": None,
                    "explanation": "资料明确说明线程共享进程资源。",
                    "source_ids": source_ids,
                },
                {
                    "question_type": "fill_blank",
                    "cognitive_level": "remember",
                    "prompt": "操作系统使用____记录进程运行信息。",
                    "options": [],
                    "correct_answer": None,
                    "accepted_answers": ["进程控制块", "PCB"],
                    "keywords": [],
                    "reference_answer": None,
                    "explanation": "进程控制块用于保存进程上下文。",
                    "source_ids": source_ids,
                },
                {
                    "question_type": "short_answer",
                    "cognitive_level": "analyze",
                    "prompt": "简述进程和线程的主要区别。",
                    "options": [],
                    "correct_answer": None,
                    "accepted_answers": [],
                    "keywords": [],
                    "reference_answer": "进程与线程的主要差异包括资源和调度单位。",
                    "explanation": "可从资源所有权和调度单位两个方面回答。",
                    "source_ids": source_ids,
                },
            ]
        }

    def _payload_model(self, payload: dict):
        return GeneratedQuizPayload.model_validate(payload)

    def _create_schema(self) -> None:
        statements = [
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username TEXT NOT NULL,
                email TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user'
            )
            """,
            """
            CREATE TABLE knowledge_bases (
                id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT NOT NULL,
                description TEXT, visibility TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY, knowledge_base_id INTEGER NOT NULL,
                owner_id INTEGER NOT NULL, file_name TEXT NOT NULL,
                parse_status TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE document_chunks (
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
                knowledge_base_id INTEGER NOT NULL, chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL, page_no INTEGER
            )
            """,
            """
            CREATE TABLE quiz_sessions (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                knowledge_base_ids_json TEXT NOT NULL, config_json TEXT NOT NULL,
                status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL,
                message TEXT NOT NULL, error_message TEXT, expires_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE quiz_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                order_no INTEGER NOT NULL, question_type TEXT NOT NULL,
                prompt TEXT NOT NULL, options_json TEXT NOT NULL,
                answer_json TEXT NOT NULL, explanation TEXT NOT NULL,
                sources_json TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES quiz_sessions(id) ON DELETE CASCADE
            )
            """,
        ]
        for statement in statements:
            self.db.execute(text(statement))
        self.db.commit()

    def _seed_data(self) -> None:
        self.db.execute(
            text(
                "INSERT INTO users (id, username, email, role) VALUES "
                "(1, 'alice', 'alice@example.com', 'user'), "
                "(2, 'bob', 'bob@example.com', 'user')"
            )
        )
        self.db.execute(
            text(
                "INSERT INTO knowledge_bases (id, owner_id, name, visibility) VALUES "
                "(11, 1, 'Alice 私人库', 'private'), "
                "(12, 2, 'Bob 私人库', 'private'), "
                "(13, 1, '空知识库', 'private'), "
                "(100, NULL, '公共知识库', 'public')"
            )
        )
        self.db.execute(
            text(
                "INSERT INTO documents (id, knowledge_base_id, owner_id, file_name, parse_status) VALUES "
                "(21, 11, 1, 'alice-os.txt', 'completed'), "
                "(22, 12, 2, 'bob-private.txt', 'completed'), "
                "(23, 100, 2, 'public-os.txt', 'completed'), "
                "(24, 11, 1, 'alice-database.txt', 'completed')"
            )
        )
        base_text = (
            "操作系统通过进程控制块记录进程状态、寄存器和调度信息。"
            "进程是资源分配的基本单位，线程是处理器调度的基本单位。"
            "同一进程内的线程共享地址空间和打开的文件，但拥有独立栈与寄存器。"
        ) * 4
        for chunk_id, document_id, knowledge_base_id in (
            (31, 21, 11),
            (32, 21, 11),
            (33, 23, 100),
            (34, 23, 100),
            (35, 22, 12),
            (36, 24, 11),
            (37, 24, 11),
        ):
            self.db.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(id, document_id, knowledge_base_id, chunk_index, chunk_text) "
                    "VALUES (:id, :document_id, :knowledge_base_id, :chunk_index, :text)"
                ),
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "knowledge_base_id": knowledge_base_id,
                    "chunk_index": chunk_id,
                    "text": base_text,
                },
            )
        self.db.commit()


if __name__ == "__main__":
    unittest.main()

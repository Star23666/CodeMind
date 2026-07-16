import asyncio
import sys
import unittest
from pathlib import Path
import socket
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.contracts import LlmConfigCreate, LlmConfigUpdate
from app.services.llm_config_service import (
    LlmConfigError,
    LlmConfigRateLimitError,
    LlmConfigService,
)


def run_async(coro):
    return asyncio.run(coro)


class LlmConfigServiceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        self.session = sessionmaker(bind=engine)()
        self.session.execute(text("PRAGMA foreign_keys = ON"))
        self.session.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL
                );
                """
            )
        )
        self.session.execute(
            text(
                """
                CREATE TABLE user_llm_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    model TEXT NOT NULL,
                    api_key_ciphertext TEXT NOT NULL,
                    api_key_last4 TEXT NOT NULL,
                    test_status TEXT NOT NULL DEFAULT 'untested',
                    test_message TEXT,
                    last_tested_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, name),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
        )
        self.session.execute(
            text(
                """
                CREATE TABLE user_llm_preferences (
                    user_id INTEGER PRIMARY KEY,
                    active_config_id INTEGER,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (active_config_id) REFERENCES user_llm_configs(id) ON DELETE SET NULL
                );
                """
            )
        )
        self.session.execute(
            text("INSERT INTO users (id, username) VALUES (1, 'alice'), (2, 'bob')")
        )
        self.session.commit()
        self.service = LlmConfigService()
        self.setting_patches = [
            patch(
                "app.services.llm_config_service.settings.llm_config_encryption_key",
                "test-encryption-key-with-at-least-32-characters",
            ),
            patch("app.services.llm_config_service.settings.llm_config_max_presets", 5),
            patch("app.services.llm_client.settings.llm_api_key", "system-key"),
            patch("app.services.llm_client.settings.llm_base_url", "https://system.example/v1"),
            patch("app.services.llm_client.settings.llm_model", "env-system-model"),
        ]
        for setting_patch in self.setting_patches:
            setting_patch.start()

    def tearDown(self):
        for setting_patch in reversed(self.setting_patches):
            setting_patch.stop()
        self.session.close()

    def _create(self):
        return self.service.create(
            self.session,
            user_id=1,
            payload=LlmConfigCreate(
                name="学习模型",
                provider="siliconflow",
                base_url="https://api.siliconflow.cn/v1",
                model="deepseek-ai/DeepSeek-V4-Flash",
                api_key="sk-user-secret-1234",
            ),
        )

    def test_api_key_is_encrypted_and_system_model_name_is_exposed(self):
        created = self._create()
        stored = self.session.execute(
            text(
                """
                SELECT api_key_ciphertext, api_key_last4
                FROM user_llm_configs WHERE id = :config_id
                """
            ),
            {"config_id": created.id},
        ).mappings().one()

        self.assertNotIn("sk-user-secret-1234", stored["api_key_ciphertext"])
        self.assertEqual(stored["api_key_last4"], "1234")
        self.assertEqual(created.masked_api_key, "••••••••1234")

        overview = self.service.list_overview(self.session, user_id=1)
        self.assertEqual(overview.system_default.model, "env-system-model")
        self.assertEqual(overview.effective_model, "env-system-model")
        self.assertNotIn("sk-user-secret-1234", overview.model_dump_json())

    def test_only_successfully_tested_owned_config_can_be_activated(self):
        created = self._create()
        with self.assertRaises(LlmConfigError):
            self.service.activate(self.session, user_id=1, config_id=created.id)

        self.session.execute(
            text(
                "UPDATE user_llm_configs SET test_status = 'success' WHERE id = :config_id"
            ),
            {"config_id": created.id},
        )
        self.session.commit()
        overview = self.service.activate(self.session, user_id=1, config_id=created.id)
        runtime = self.service.resolve_runtime(self.session, user_id=1)

        self.assertEqual(overview.active_config_id, created.id)
        self.assertEqual(runtime.source, "personal")
        self.assertEqual(runtime.api_key, "sk-user-secret-1234")
        self.assertEqual(runtime.model, "deepseek-ai/DeepSeek-V4-Flash")
        self.assertEqual(self.service.resolve_runtime(self.session, user_id=2).source, "system")

        with self.assertRaises(LlmConfigError):
            self.service.get(self.session, user_id=2, config_id=created.id)
        with self.assertRaises(LlmConfigError):
            self.service.activate(self.session, user_id=2, config_id=created.id)
        with self.assertRaises(LlmConfigError):
            self.service.delete(self.session, user_id=2, config_id=created.id)

    def test_deleting_active_config_returns_to_system_default(self):
        created = self._create()
        self.session.execute(
            text("UPDATE user_llm_configs SET test_status = 'success' WHERE id = :id"),
            {"id": created.id},
        )
        self.session.commit()
        self.service.activate(self.session, user_id=1, config_id=created.id)

        self.service.delete(self.session, user_id=1, config_id=created.id)

        overview = self.service.list_overview(self.session, user_id=1)
        self.assertIsNone(overview.active_config_id)
        self.assertEqual(overview.effective_source, "system")
        self.assertEqual(self.service.resolve_runtime(self.session, user_id=1).model, "env-system-model")

    def test_changing_active_connection_requires_retest_and_falls_back_to_system(self):
        created = self._create()
        self.session.execute(
            text("UPDATE user_llm_configs SET test_status = 'success' WHERE id = :id"),
            {"id": created.id},
        )
        self.session.commit()
        self.service.activate(self.session, user_id=1, config_id=created.id)

        updated = self.service.update(
            self.session,
            user_id=1,
            config_id=created.id,
            payload=LlmConfigUpdate(model="another-model"),
        )

        self.assertEqual(updated.test_status.value, "untested")
        self.assertFalse(updated.is_active)
        self.assertEqual(
            self.service.resolve_runtime(self.session, user_id=1).model,
            "env-system-model",
        )

    def test_connection_test_is_rate_limited_and_marks_success(self):
        created = self._create()
        with (
            patch.object(self.service, "_ensure_public_destination", new=AsyncMock()),
            patch(
                "app.services.llm_config_service.llm_client.generate_answer",
                new=AsyncMock(return_value="连接成功"),
            ),
            patch(
                "app.services.llm_config_service.settings.llm_config_test_cooldown_seconds",
                30,
            ),
        ):
            result = run_async(
                self.service.test_config(self.session, user_id=1, config_id=created.id)
            )
            with self.assertRaises(LlmConfigRateLimitError):
                run_async(
                    self.service.test_config(self.session, user_id=1, config_id=created.id)
                )

        refreshed = self.service.get(self.session, user_id=1, config_id=created.id)
        self.assertTrue(result.success)
        self.assertEqual(refreshed.test_status.value, "success")

    def test_proxy_fake_ip_requires_explicit_development_setting(self):
        fake_ip_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.1.248", 0))
        ]

        with (
            patch(
                "app.services.llm_destination_validator.socket.getaddrinfo",
                return_value=fake_ip_result,
            ),
            patch(
                "app.services.llm_destination_validator.settings.llm_allow_proxy_fake_ip",
                False,
            ),
        ):
            with self.assertRaises(LlmConfigError):
                run_async(
                    self.service._ensure_public_destination(
                        "https://api.siliconflow.cn/v1",
                        provider="siliconflow",
                    )
                )

        with (
            patch(
                "app.services.llm_destination_validator.socket.getaddrinfo",
                return_value=fake_ip_result,
            ),
            patch(
                "app.services.llm_destination_validator.settings.llm_allow_proxy_fake_ip",
                True,
            ),
        ):
            run_async(
                self.service._ensure_public_destination(
                    "https://api.siliconflow.cn/v1",
                    provider="siliconflow",
                )
            )

    def test_private_ipv4_and_ipv6_dns_results_are_rejected(self):
        for family, address in (
            (socket.AF_INET, "10.0.0.8"),
            (socket.AF_INET6, "fd00::8"),
        ):
            dns_result = [(family, socket.SOCK_STREAM, 6, "", (address, 443))]
            with patch(
                "app.services.llm_destination_validator.socket.getaddrinfo",
                return_value=dns_result,
            ):
                with self.assertRaises(LlmConfigError):
                    run_async(
                        self.service._ensure_public_destination(
                            "https://api.siliconflow.cn/v1",
                            provider="siliconflow",
                        )
                    )

    def test_destination_is_resolved_again_for_each_request(self):
        public_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        private_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
        with patch(
            "app.services.llm_destination_validator.socket.getaddrinfo",
            side_effect=[public_result, private_result],
        ) as resolver:
            run_async(
                self.service._ensure_public_destination(
                    "https://api.siliconflow.cn/v1",
                    provider="siliconflow",
                )
            )
            with self.assertRaises(LlmConfigError):
                run_async(
                    self.service._ensure_public_destination(
                        "https://api.siliconflow.cn/v1",
                        provider="siliconflow",
                    )
                )

        self.assertEqual(resolver.call_count, 2)

    def test_openai_compatible_host_requires_server_allowlist(self):
        public_result = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        with patch(
            "app.services.llm_destination_validator.settings.llm_openai_compatible_allowed_hosts",
            "",
        ):
            with self.assertRaises(LlmConfigError):
                run_async(
                    self.service._ensure_public_destination(
                        "https://gateway.example/v1",
                        provider="openai_compatible",
                    )
                )

        with (
            patch(
                "app.services.llm_destination_validator.settings.llm_openai_compatible_allowed_hosts",
                "gateway.example",
            ),
            patch(
                "app.services.llm_destination_validator.socket.getaddrinfo",
                return_value=public_result,
            ),
        ):
            run_async(
                self.service._ensure_public_destination(
                    "https://gateway.example/v1",
                    provider="openai_compatible",
                )
            )

    def test_rate_limiter_has_no_hourly_attempt_cap(self):
        limiter = self.service._test_rate_limiter
        with (
            patch(
                "app.services.llm_config_service.settings.llm_config_test_cooldown_seconds",
                1,
            ),
            patch("app.services.llm_config_service.time.monotonic") as monotonic,
        ):
            for attempt in range(12):
                monotonic.return_value = float(attempt * 2)
                limiter.acquire(user_id=1)
                limiter.release(user_id=1)


if __name__ == "__main__":
    unittest.main()

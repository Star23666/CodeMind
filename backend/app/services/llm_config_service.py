import asyncio
import base64
import hashlib
import ipaddress
import logging
import socket
import threading
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.contracts import (
    LlmConfigCreate,
    LlmConfigOverview,
    LlmConfigRead,
    LlmConfigTestResult,
    LlmConfigUpdate,
    LlmProvider,
    LlmSystemDefaultRead,
    LlmTestStatus,
)
from app.services.llm_client import (
    LlmRuntimeConfig,
    LlmServiceError,
    llm_client,
    system_llm_runtime_config,
)


logger = logging.getLogger(__name__)

# Clash and similar local proxies commonly synthesize DNS records from the
# RFC 2544 benchmarking range, then route requests by the original hostname.
# Only DNS results may use this range; a user-entered literal IP is still denied.
PROXY_FAKE_IP_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)


class LlmConfigError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class LlmConfigRateLimitError(LlmConfigError):
    def __init__(self, message: str, *, retry_after: int) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = max(1, retry_after)


class _TestRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_attempt: dict[int, float] = {}
        self._active_users: set[int] = set()

    def acquire(self, user_id: int) -> None:
        now = time.monotonic()
        cooldown = max(1, settings.llm_config_test_cooldown_seconds)
        with self._lock:
            if user_id in self._active_users:
                raise LlmConfigRateLimitError(
                    "已有模型连接测试正在进行，请等待完成后再试。",
                    retry_after=cooldown,
                )
            last_attempt = self._last_attempt.get(user_id)
            if last_attempt is not None and now - last_attempt < cooldown:
                retry_after = int(cooldown - (now - last_attempt) + 0.999)
                raise LlmConfigRateLimitError(
                    f"测试过于频繁，请在 {retry_after} 秒后重试。",
                    retry_after=retry_after,
                )

            self._last_attempt[user_id] = now
            self._active_users.add(user_id)

    def release(self, user_id: int) -> None:
        with self._lock:
            self._active_users.discard(user_id)

    def reset(self) -> None:
        with self._lock:
            self._last_attempt.clear()
            self._active_users.clear()


class LlmConfigService:
    def __init__(self) -> None:
        self._test_rate_limiter = _TestRateLimiter()

    def list_overview(self, db: Session, *, user_id: int) -> LlmConfigOverview:
        active_config_id = self._active_config_id(db, user_id=user_id)
        rows = db.execute(
            text(
                """
                SELECT id, name, provider, base_url, model, api_key_last4,
                       test_status, test_message, last_tested_at,
                       created_at, updated_at
                FROM user_llm_configs
                WHERE user_id = :user_id
                ORDER BY updated_at DESC, id DESC
                """
            ),
            {"user_id": user_id},
        ).mappings()
        configs = [
            self._to_read(row, active_config_id=active_config_id) for row in rows
        ]
        active_config = next(
            (config for config in configs if config.id == active_config_id),
            None,
        )
        system_config = system_llm_runtime_config()
        if active_config is None:
            effective_source = "system"
            effective_name = "系统默认模型"
            effective_model = system_config.model or "未配置"
            active_config_id = None
        else:
            effective_source = "personal"
            effective_name = active_config.name
            effective_model = active_config.model

        return LlmConfigOverview(
            configs=configs,
            active_config_id=active_config_id,
            effective_source=effective_source,
            effective_name=effective_name,
            effective_model=effective_model,
            system_default=LlmSystemDefaultRead(
                configured=system_config.configured,
                model=system_config.model or "未配置",
            ),
            max_presets=max(1, settings.llm_config_max_presets),
            test_cooldown_seconds=max(1, settings.llm_config_test_cooldown_seconds),
        )

    def create(
        self,
        db: Session,
        *,
        user_id: int,
        payload: LlmConfigCreate,
    ) -> LlmConfigRead:
        count = db.execute(
            text("SELECT COUNT(*) FROM user_llm_configs WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).scalar_one()
        if int(count) >= max(1, settings.llm_config_max_presets):
            raise LlmConfigError(
                f"每位用户最多保存 {max(1, settings.llm_config_max_presets)} 套模型配置。",
                status_code=409,
            )

        encrypted_key, last4 = self._encrypt_api_key(payload.api_key)
        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO user_llm_configs (
                        user_id, name, provider, base_url, model,
                        api_key_ciphertext, api_key_last4
                    ) VALUES (
                        :user_id, :name, :provider, :base_url, :model,
                        :api_key_ciphertext, :api_key_last4
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "name": payload.name,
                    "provider": payload.provider.value,
                    "base_url": payload.base_url,
                    "model": payload.model,
                    "api_key_ciphertext": encrypted_key,
                    "api_key_last4": last4,
                },
            )
            config_id = int(result.lastrowid)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return self.get(db, user_id=user_id, config_id=config_id)

    def get(self, db: Session, *, user_id: int, config_id: int) -> LlmConfigRead:
        row = self._owned_row(db, user_id=user_id, config_id=config_id)
        return self._to_read(
            row,
            active_config_id=self._active_config_id(db, user_id=user_id),
        )

    def update(
        self,
        db: Session,
        *,
        user_id: int,
        config_id: int,
        payload: LlmConfigUpdate,
    ) -> LlmConfigRead:
        self._owned_row(db, user_id=user_id, config_id=config_id)
        values = {
            key: value
            for key, value in payload.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if not values:
            return self.get(db, user_id=user_id, config_id=config_id)

        assignments: list[str] = []
        params: dict[str, object] = {
            "config_id": config_id,
            "user_id": user_id,
        }
        resets_test = False
        for field_name in ("name", "provider", "base_url", "model"):
            if field_name not in values:
                continue
            value = values[field_name]
            if isinstance(value, LlmProvider):
                value = value.value
            assignments.append(f"{field_name} = :{field_name}")
            params[field_name] = value
            resets_test = resets_test or field_name != "name"

        if "api_key" in values:
            encrypted_key, last4 = self._encrypt_api_key(str(values["api_key"]))
            assignments.extend(
                [
                    "api_key_ciphertext = :api_key_ciphertext",
                    "api_key_last4 = :api_key_last4",
                ]
            )
            params["api_key_ciphertext"] = encrypted_key
            params["api_key_last4"] = last4
            resets_test = True

        if resets_test:
            assignments.extend(
                [
                    "test_status = 'untested'",
                    "test_message = NULL",
                    "last_tested_at = NULL",
                ]
            )

        if not assignments:
            return self.get(db, user_id=user_id, config_id=config_id)
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        try:
            db.execute(
                text(
                    f"""
                    UPDATE user_llm_configs
                    SET {', '.join(assignments)}
                    WHERE id = :config_id AND user_id = :user_id
                    """
                ),
                params,
            )
            if resets_test:
                db.execute(
                    text(
                        """
                        UPDATE user_llm_preferences
                        SET active_config_id = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id AND active_config_id = :config_id
                        """
                    ),
                    {"user_id": user_id, "config_id": config_id},
                )
            db.commit()
        except Exception:
            db.rollback()
            raise
        return self.get(db, user_id=user_id, config_id=config_id)

    def delete(self, db: Session, *, user_id: int, config_id: int) -> None:
        self._owned_row(db, user_id=user_id, config_id=config_id)
        try:
            db.execute(
                text(
                    """
                    UPDATE user_llm_preferences
                    SET active_config_id = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND active_config_id = :config_id
                    """
                ),
                {"user_id": user_id, "config_id": config_id},
            )
            db.execute(
                text(
                    """
                    DELETE FROM user_llm_configs
                    WHERE id = :config_id AND user_id = :user_id
                    """
                ),
                {"user_id": user_id, "config_id": config_id},
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

    def activate(
        self,
        db: Session,
        *,
        user_id: int,
        config_id: int,
    ) -> LlmConfigOverview:
        row = self._owned_row(db, user_id=user_id, config_id=config_id)
        if row["test_status"] != LlmTestStatus.SUCCESS.value:
            raise LlmConfigError("请先测试连接，测试成功后才能启用该配置。", status_code=409)
        self._set_active_config(db, user_id=user_id, config_id=config_id)
        return self.list_overview(db, user_id=user_id)

    def use_system_default(self, db: Session, *, user_id: int) -> LlmConfigOverview:
        self._set_active_config(db, user_id=user_id, config_id=None)
        return self.list_overview(db, user_id=user_id)

    async def test_config(
        self,
        db: Session,
        *,
        user_id: int,
        config_id: int,
    ) -> LlmConfigTestResult:
        row = self._owned_row(db, user_id=user_id, config_id=config_id)
        self._test_rate_limiter.acquire(user_id)
        started_at = time.perf_counter()
        try:
            await self._ensure_public_destination(str(row["base_url"]))
            runtime_config = self._runtime_from_row(row)
            answer = await llm_client.generate_answer(
                "请只回复：连接成功",
                system_message="你正在执行模型 API 连接测试，请简短回答。",
                temperature=0,
                max_tokens=32,
                max_retries=0,
                timeout_seconds=max(1.0, settings.llm_config_test_timeout_seconds),
                runtime_config=runtime_config,
            )
            latency_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            self._store_test_result(
                db,
                user_id=user_id,
                config_id=config_id,
                status_value=LlmTestStatus.SUCCESS.value,
                message="连接测试成功。",
            )
            return LlmConfigTestResult(
                success=True,
                message="连接测试成功。",
                model=runtime_config.model,
                latency_ms=latency_ms,
            )
        except LlmConfigRateLimitError:
            raise
        except Exception as exc:
            safe_message = self._safe_test_error(exc)
            self._store_test_result(
                db,
                user_id=user_id,
                config_id=config_id,
                status_value=LlmTestStatus.FAILED.value,
                message=safe_message,
            )
            if isinstance(exc, LlmConfigError):
                raise
            if isinstance(exc, LlmServiceError):
                raise
            raise LlmServiceError(safe_message, status_code=502) from exc
        finally:
            self._test_rate_limiter.release(user_id)

    def resolve_runtime(self, db: Session, *, user_id: int) -> LlmRuntimeConfig:
        try:
            row = db.execute(
                text(
                    """
                    SELECT c.id, c.name, c.provider, c.base_url, c.model,
                           c.api_key_ciphertext
                    FROM user_llm_preferences p
                    JOIN user_llm_configs c
                      ON c.id = p.active_config_id AND c.user_id = p.user_id
                    WHERE p.user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
        except OperationalError as exc:
            error_text = str(exc).casefold()
            if "user_llm_preferences" in error_text and (
                "no such table" in error_text or "doesn't exist" in error_text
            ):
                logger.info("User LLM preference table is not migrated; using system model")
                return system_llm_runtime_config()
            raise LlmServiceError("读取个人模型配置失败，请稍后重试。") from exc

        if row is None:
            return system_llm_runtime_config()
        try:
            return self._runtime_from_row(row)
        except LlmConfigError as exc:
            raise LlmServiceError(
                "当前个人模型配置无法解密，请重新保存 API Key。",
                status_code=503,
            ) from exc

    def _owned_row(self, db: Session, *, user_id: int, config_id: int):
        row = db.execute(
            text(
                """
                SELECT id, user_id, name, provider, base_url, model,
                       api_key_ciphertext, api_key_last4, test_status,
                       test_message, last_tested_at, created_at, updated_at
                FROM user_llm_configs
                WHERE id = :config_id AND user_id = :user_id
                """
            ),
            {"config_id": config_id, "user_id": user_id},
        ).mappings().first()
        if row is None:
            raise LlmConfigError("模型配置不存在。", status_code=404)
        return row

    def _active_config_id(self, db: Session, *, user_id: int) -> int | None:
        value = db.execute(
            text(
                """
                SELECT active_config_id
                FROM user_llm_preferences
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        ).scalar_one_or_none()
        return int(value) if value is not None else None

    def _set_active_config(
        self,
        db: Session,
        *,
        user_id: int,
        config_id: int | None,
    ) -> None:
        exists = db.execute(
            text(
                "SELECT user_id FROM user_llm_preferences WHERE user_id = :user_id"
            ),
            {"user_id": user_id},
        ).first()
        try:
            if exists is None:
                db.execute(
                    text(
                        """
                        INSERT INTO user_llm_preferences (user_id, active_config_id)
                        VALUES (:user_id, :config_id)
                        """
                    ),
                    {"user_id": user_id, "config_id": config_id},
                )
            else:
                db.execute(
                    text(
                        """
                        UPDATE user_llm_preferences
                        SET active_config_id = :config_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id
                        """
                    ),
                    {"user_id": user_id, "config_id": config_id},
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _store_test_result(
        self,
        db: Session,
        *,
        user_id: int,
        config_id: int,
        status_value: str,
        message: str,
    ) -> None:
        try:
            db.execute(
                text(
                    """
                    UPDATE user_llm_configs
                    SET test_status = :test_status,
                        test_message = :test_message,
                        last_tested_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :config_id AND user_id = :user_id
                    """
                ),
                {
                    "test_status": status_value,
                    "test_message": message[:255],
                    "config_id": config_id,
                    "user_id": user_id,
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to persist LLM connection test result")

    def _runtime_from_row(self, row) -> LlmRuntimeConfig:
        return LlmRuntimeConfig(
            api_key=self._decrypt_api_key(str(row["api_key_ciphertext"])),
            base_url=str(row["base_url"]),
            model=str(row["model"]),
            source="personal",
            name=str(row["name"]),
            provider=str(row["provider"]),
        )

    def _to_read(self, row, *, active_config_id: int | None) -> LlmConfigRead:
        last4 = str(row["api_key_last4"] or "")
        return LlmConfigRead(
            id=int(row["id"]),
            name=str(row["name"]),
            provider=str(row["provider"]),
            base_url=str(row["base_url"]),
            model=str(row["model"]),
            masked_api_key=f"••••••••{last4}",
            test_status=str(row["test_status"]),
            test_message=row["test_message"],
            last_tested_at=row["last_tested_at"],
            is_active=int(row["id"]) == active_config_id,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _fernet(self) -> Fernet:
        raw_key = settings.llm_config_encryption_key.strip()
        if (
            len(raw_key) < 32
            or raw_key
            == "replace_with_a_separate_random_secret_at_least_32_chars"
        ):
            raise LlmConfigError(
                "服务端尚未配置 LLM_CONFIG_ENCRYPTION_KEY，暂时无法保存个人 API Key。",
                status_code=503,
            )
        derived_key = base64.urlsafe_b64encode(
            hashlib.sha256(raw_key.encode("utf-8")).digest()
        )
        return Fernet(derived_key)

    def _encrypt_api_key(self, api_key: str) -> tuple[str, str]:
        ciphertext = self._fernet().encrypt(api_key.encode("utf-8")).decode("ascii")
        return ciphertext, api_key[-4:]

    def _decrypt_api_key(self, ciphertext: str) -> str:
        try:
            return self._fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
            raise LlmConfigError("API Key 解密失败，请重新保存。", status_code=503) from exc

    async def _ensure_public_destination(self, base_url: str) -> None:
        hostname = urlsplit(base_url).hostname
        if not hostname:
            raise LlmConfigError("API Base URL 无效。")
        try:
            literal_ip = ipaddress.ip_address(hostname)
        except ValueError:
            literal_ip = None
        if literal_ip is not None:
            if not literal_ip.is_global:
                raise LlmConfigError("模型测试地址不能指向本机或内网地址。")
            return

        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                None,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise LlmConfigError("无法解析模型服务域名，请检查 API Base URL。") from exc
        resolved_ips = {item[4][0] for item in addresses}
        if not resolved_ips or any(
            not self._is_safe_resolved_address(address) for address in resolved_ips
        ):
            raise LlmConfigError("模型测试地址不能解析到本机或内网地址。")

    def _is_safe_resolved_address(self, address: str) -> bool:
        parsed_address = ipaddress.ip_address(address)
        return parsed_address.is_global or any(
            parsed_address in network for network in PROXY_FAKE_IP_NETWORKS
        )

    def _safe_test_error(self, exc: Exception) -> str:
        if isinstance(exc, (LlmConfigError, LlmServiceError)):
            return str(exc)[:255]
        return "模型连接测试失败，请检查地址、模型名称与 API Key。"


llm_config_service = LlmConfigService()

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class RerankerServiceError(RuntimeError):
    """Safe provider error that never contains credentials or response bodies."""


class RerankerAuthenticationError(RerankerServiceError):
    pass


@dataclass(frozen=True)
class RerankResult:
    index: int
    relevance_score: float


class RerankerClient:
    def is_configured(self) -> bool:
        return bool(
            settings.effective_rerank_api_key
            and settings.effective_rerank_base_url
            and settings.rerank_model
        )

    def rerank(
        self,
        *,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []
        if not self.is_configured():
            raise RerankerServiceError("Reranker 在线服务未配置。")
        requested_top_n = min(max(1, top_n or len(documents)), len(documents))
        payload: dict[str, object] = {
            "model": settings.rerank_model,
            "query": query.strip(),
            "documents": documents,
            "top_n": requested_top_n,
            "return_documents": False,
        }
        if "qwen3-reranker" in settings.rerank_model.casefold():
            payload["instruction"] = settings.rerank_instruction

        url = settings.effective_rerank_base_url.rstrip("/") + "/rerank"
        headers = {"Authorization": f"Bearer {settings.effective_rerank_api_key}"}
        attempts = max(0, settings.rerank_max_retries) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with httpx.Client(
                    timeout=settings.rerank_timeout_seconds,
                    follow_redirects=False,
                ) as client:
                    response = client.post(url, headers=headers, json=payload)
                if response.status_code in {401, 403}:
                    raise RerankerAuthenticationError(
                        "Reranker API Key 无效或无权访问当前模型。"
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        "retryable reranker response",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 400:
                    logger.warning(
                        "Reranker provider rejected request (model=%s, status=%s)",
                        settings.rerank_model,
                        response.status_code,
                    )
                    raise RerankerServiceError("Reranker 在线服务返回异常。")
                return self._parse_results(response.json(), document_count=len(documents))
            except RerankerAuthenticationError:
                raise
            except RerankerServiceError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(min(2**attempt, 2))
                    continue
                logger.warning(
                    "Reranker provider unavailable (model=%s, error=%s)",
                    settings.rerank_model,
                    type(exc).__name__,
                )
            except (TypeError, ValueError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "Reranker provider returned invalid data (model=%s)",
                    settings.rerank_model,
                )
                break
        raise RerankerServiceError("Reranker 在线服务连接失败，请稍后重试。") from last_error

    def _parse_results(
        self,
        payload: object,
        *,
        document_count: int,
    ) -> list[RerankResult]:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("missing reranker results")
        parsed: list[RerankResult] = []
        seen: set[int] = set()
        for item in payload["results"]:
            if not isinstance(item, dict):
                raise ValueError("invalid reranker result")
            index = int(item["index"])
            score = float(item["relevance_score"])
            if index in seen or not 0 <= index < document_count or not math.isfinite(score):
                raise ValueError("invalid reranker result fields")
            seen.add(index)
            parsed.append(
                RerankResult(
                    index=index,
                    relevance_score=max(-1.0, min(1.0, score)),
                )
            )
        parsed.sort(key=lambda item: item.relevance_score, reverse=True)
        return parsed


reranker_client = RerankerClient()

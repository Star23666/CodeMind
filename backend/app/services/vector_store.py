from dataclasses import dataclass
from typing import Any

from app.core.config import settings


@dataclass(frozen=True)
class VectorSearchHit:
    vector_id: str
    text: str
    metadata: dict[str, Any]
    score: float


class VectorStore:
    collection_name = "document_chunks"

    def __init__(self) -> None:
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少 chromadb 依赖，请先安装 backend/requirements.txt。") from exc

        settings.chroma_persist_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        *,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return

        self.collection.upsert(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete_ids(self, ids: list[str]) -> None:
        if ids:
            self.collection.delete(ids=ids)

    def update_metadatas(
        self,
        *,
        ids: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not ids:
            return
        if len(ids) != len(metadatas):
            raise ValueError("向量编号和 metadata 数量不一致。")
        self.collection.update(ids=ids, metadatas=metadatas)
        result = self.collection.get(ids=ids, include=["metadatas"])
        stored = {
            vector_id: dict(metadata or {})
            for vector_id, metadata in zip(
                result.get("ids", []),
                result.get("metadatas", []) or [],
                strict=False,
            )
        }
        for vector_id, expected in zip(ids, metadatas, strict=True):
            actual = stored.get(vector_id)
            if actual is None or any(actual.get(key) != value for key, value in expected.items()):
                raise RuntimeError(f"向量 metadata 更新后校验失败：{vector_id}")

    def get_metadatas(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ids:
            return {}
        result = self.collection.get(ids=ids, include=["metadatas"])
        return {
            str(vector_id): dict(metadata or {})
            for vector_id, metadata in zip(
                result.get("ids", []),
                result.get("metadatas", []) or [],
                strict=False,
            )
        }

    def search(
        self,
        *,
        embedding: list[float],
        knowledge_base_id: int,
        owner_id: int | None,
        top_k: int,
    ) -> list[VectorSearchHit]:
        where = {"knowledge_base_id": knowledge_base_id}
        if owner_id is not None:
            where = {
                "$and": [
                    {"knowledge_base_id": knowledge_base_id},
                    {"owner_id": owner_id},
                ]
            }
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0] or []
        documents = result.get("documents", [[]])[0] or []
        metadatas = result.get("metadatas", [[]])[0] or []
        distances = result.get("distances", [[]])[0] or []

        hits: list[VectorSearchHit] = []
        for index, vector_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            score = max(-1.0, min(1.0, 1.0 - distance))
            metadata = dict(metadatas[index] or {}) if index < len(metadatas) else {}
            text = documents[index] if index < len(documents) else ""
            hits.append(VectorSearchHit(vector_id=vector_id, text=text, metadata=metadata, score=score))

        return hits


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store

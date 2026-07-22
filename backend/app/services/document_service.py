import logging
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.contracts import DocumentChunkRead, DocumentRead
from app.services.document_parser import DocumentParseError, document_parser
from app.services.embedding_client import EmbeddingServiceError, embedding_client
from app.services.embedding_text import build_embedding_text
from app.services.knowledge_base_service import (
    KnowledgeBasePermissionError,
    knowledge_base_service,
)
from app.services.text_splitter import text_splitter
from app.services.vector_store import get_vector_store


logger = logging.getLogger(__name__)


class DocumentBusyError(ValueError):
    pass


class DocumentNotProcessingError(ValueError):
    pass


class DocumentProcessingCancelled(RuntimeError):
    pass


class DocumentPermissionError(ValueError):
    pass


class DocumentMoveError(ValueError):
    pass


class DocumentMoveConsistencyError(RuntimeError):
    pass


class DocumentService:
    allowed_file_types = {"pdf", "docx", "md", "markdown", "txt"}

    async def save_upload(
        self,
        *,
        db: Session,
        owner_id: int,
        knowledge_base_id: int,
        file: UploadFile,
    ) -> DocumentRead:
        knowledge_base_service.get_uploadable(db, knowledge_base_id, owner_id)

        original_name = Path(file.filename or "").name
        file_type = self._detect_file_type(original_name)
        target_path, file_size = await self._save_file(owner_id, knowledge_base_id, original_name, file)

        try:
            result = db.execute(
                text(
                    """
                    INSERT INTO documents (
                        knowledge_base_id, owner_id, file_name, file_type,
                        file_size, file_path, parse_status, chunk_count
                    )
                    VALUES (
                        :knowledge_base_id, :owner_id, :file_name, :file_type,
                        :file_size, :file_path, 'pending', 0
                    )
                    """
                ),
                {
                    "knowledge_base_id": knowledge_base_id,
                    "owner_id": owner_id,
                    "file_name": original_name,
                    "file_type": file_type,
                    "file_size": file_size,
                    "file_path": str(target_path),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            self._unlink_file(target_path)
            raise

        return self.get_owned_document(db, int(result.lastrowid), owner_id)

    def list_documents(
        self,
        db: Session,
        *,
        owner_id: int,
        knowledge_base_id: int | None = None,
        parse_status: str | None = None,
    ) -> list[DocumentRead]:
        if knowledge_base_id is not None:
            knowledge_base_service.get_readable(db, knowledge_base_id, owner_id)

        conditions = ["(kb.visibility = 'public' OR d.owner_id = :owner_id)"]
        params: dict[str, object] = {"owner_id": owner_id}

        if knowledge_base_id is not None:
            conditions.append("d.knowledge_base_id = :knowledge_base_id")
            params["knowledge_base_id"] = knowledge_base_id

        if parse_status is not None:
            conditions.append("d.parse_status = :parse_status")
            params["parse_status"] = parse_status

        rows = db.execute(
            text(
                f"""
                SELECT d.id, d.knowledge_base_id, d.owner_id, d.file_name,
                       d.file_type, d.file_size, d.parse_status, d.error_message,
                       d.chunk_count, u.username AS uploader_username,
                       kb.visibility AS knowledge_base_visibility
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                JOIN users u ON u.id = d.owner_id
                WHERE {" AND ".join(conditions)}
                ORDER BY d.created_at DESC, d.id DESC
                """
            ),
            params,
        ).mappings()
        is_admin = self._is_admin(db, owner_id)
        return [
            self._to_document_read(
                row,
                can_manage=(
                    int(row["owner_id"]) == owner_id
                    or (row["knowledge_base_visibility"] == "public" and is_admin)
                ),
            )
            for row in rows
        ]

    def get_owned_document(self, db: Session, document_id: int, owner_id: int) -> DocumentRead:
        row = self._get_accessible_document_row(db, document_id, owner_id)
        if row is None:
            raise ValueError("Document not found")
        return self._to_document_read(
            row,
            can_manage=self._can_manage_document(db, row, owner_id),
        )

    def get_owned_file(self, db: Session, *, document_id: int, owner_id: int) -> dict[str, object]:
        row = self._get_accessible_document_row(
            db,
            document_id,
            owner_id,
            include_path=True,
        )
        if row is None:
            raise ValueError("Document not found")

        upload_root = settings.upload_dir_path.resolve()
        file_path = Path(row["file_path"]).resolve()
        if not file_path.is_relative_to(upload_root) or not file_path.is_file():
            raise ValueError("Document file not found")

        return {
            "path": file_path,
            "file_name": row["file_name"],
            "file_type": row["file_type"],
        }

    def list_chunks(self, db: Session, *, document_id: int, owner_id: int) -> list[DocumentChunkRead]:
        self.get_owned_document(db, document_id, owner_id)
        rows = db.execute(
            text(
                """
                SELECT id, document_id, knowledge_base_id, chunk_index, chunk_text,
                       page_no, start_offset, end_offset, vector_id
                FROM document_chunks
                WHERE document_id = :document_id
                ORDER BY chunk_index ASC
                """
            ),
            {"document_id": document_id},
        ).mappings()
        return [self._to_chunk_read(row) for row in rows]

    def get_owned_chunk(
        self,
        db: Session,
        *,
        chunk_id: int,
        owner_id: int,
        document_id: int | None = None,
    ) -> DocumentChunkRead:
        conditions = [
            "c.id = :chunk_id",
            "(kb.visibility = 'public' OR d.owner_id = :owner_id)",
        ]
        params: dict[str, object] = {"chunk_id": chunk_id, "owner_id": owner_id}

        if document_id is not None:
            conditions.append("c.document_id = :document_id")
            params["document_id"] = document_id

        row = db.execute(
            text(
                f"""
                SELECT c.id, c.document_id, c.knowledge_base_id, c.chunk_index,
                       c.chunk_text, c.page_no, c.start_offset, c.end_offset, c.vector_id
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE {" AND ".join(conditions)}
                """
            ),
            params,
        ).mappings().first()
        if row is None:
            raise ValueError("Chunk not found")
        return self._to_chunk_read(row)

    def queue_reindex(self, db: Session, *, document_id: int, owner_id: int) -> None:
        row = self._get_manageable_document_row(db, document_id, owner_id)
        document = self._to_document_read(row, can_manage=True)
        if document.parse_status in {"pending", "processing"}:
            raise DocumentBusyError("Document is already queued or processing")
        result = db.execute(
            text(
                """
                UPDATE documents
                SET parse_status = 'pending', error_message = NULL
                WHERE id = :document_id
                  AND parse_status = :previous_status
                """
            ),
            {
                "document_id": document_id,
                "previous_status": document.parse_status.value,
            },
        )
        db.commit()
        if result.rowcount != 1:
            raise DocumentBusyError("Document state changed while queuing reindex")

    def cancel_processing(self, db: Session, *, document_id: int, owner_id: int) -> None:
        self._get_manageable_document_row(db, document_id, owner_id)
        result = db.execute(
            text(
                """
                UPDATE documents
                SET parse_status = 'cancelled', error_message = '文档处理已由用户取消。'
                WHERE id = :document_id
                  AND parse_status IN ('pending', 'processing')
                """
            ),
            {"document_id": document_id},
        )
        db.commit()
        if result.rowcount != 1:
            raise DocumentNotProcessingError("Document is not queued or processing")

    def recover_incomplete_documents(self, db: Session) -> list[int]:
        db.execute(
            text(
                """
                UPDATE documents
                SET parse_status = 'pending',
                    error_message = '上次处理因服务重启中断，正在自动恢复。'
                WHERE parse_status = 'processing'
                """
            )
        )
        rows = db.execute(
            text(
                """
                SELECT id
                FROM documents
                WHERE parse_status = 'pending'
                ORDER BY created_at ASC, id ASC
                """
            )
        ).mappings()
        document_ids = [int(row["id"]) for row in rows]
        db.commit()
        return document_ids

    def move_document(
        self,
        db: Session,
        *,
        document_id: int,
        target_knowledge_base_id: int,
        owner_id: int,
    ) -> DocumentRead:
        lock_clause = "" if db.bind is not None and db.bind.dialect.name == "sqlite" else " FOR UPDATE"
        document = db.execute(
            text(
                """
                SELECT d.id, d.knowledge_base_id, d.owner_id, d.file_name,
                       d.file_type, d.file_size, d.parse_status, d.error_message,
                       d.chunk_count, kb.visibility AS knowledge_base_visibility
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                WHERE d.id = :document_id AND d.owner_id = :owner_id
                """ + lock_clause
            ),
            {"document_id": document_id, "owner_id": owner_id},
        ).mappings().first()
        if document is None:
            raise ValueError("Document not found")
        if document["parse_status"] != "completed":
            raise DocumentMoveError("仅已完成处理的文档可以调整所属知识库。")
        if document["knowledge_base_visibility"] != "private":
            raise DocumentMoveError("公共资料不能直接移动；请删除后重新投稿并确认公开范围。")

        target = knowledge_base_service.get_readable(db, target_knowledge_base_id, owner_id)
        if target.visibility.value != "private" or target.owner_id != owner_id:
            raise DocumentMoveError("目标必须是当前用户拥有的私人知识库。")
        if int(document["knowledge_base_id"]) == target_knowledge_base_id:
            return self.get_owned_document(db, document_id, owner_id)

        chunks = db.execute(
            text(
                """
                SELECT id, vector_id, chunk_index, page_no, start_offset, end_offset
                FROM document_chunks
                WHERE document_id = :document_id
                ORDER BY chunk_index ASC
                """
            ),
            {"document_id": document_id},
        ).mappings().all()
        vector_ids = [str(row["vector_id"]) for row in chunks]

        def metadata_for(row, knowledge_base_id: int) -> dict[str, object]:
            return {
                "owner_id": int(document["owner_id"]),
                "knowledge_base_id": knowledge_base_id,
                "document_id": int(document_id),
                "chunk_id": int(row["id"]),
                "chunk_index": int(row["chunk_index"]),
                "file_name": document["file_name"],
                "page_no": int(row["page_no"]) if row["page_no"] is not None else 0,
                "start_offset": int(row["start_offset"] or 0),
                "end_offset": int(row["end_offset"] or 0),
            }

        source_knowledge_base_id = int(document["knowledge_base_id"])
        old_metadatas = [metadata_for(row, source_knowledge_base_id) for row in chunks]
        new_metadatas = [metadata_for(row, target_knowledge_base_id) for row in chunks]
        vector_store = get_vector_store()
        vector_update_attempted = False

        try:
            db.execute(
                text(
                    """
                    UPDATE documents
                    SET knowledge_base_id = :target_knowledge_base_id
                    WHERE id = :document_id AND owner_id = :owner_id
                    """
                ),
                {
                    "target_knowledge_base_id": target_knowledge_base_id,
                    "document_id": document_id,
                    "owner_id": owner_id,
                },
            )
            db.execute(
                text(
                    """
                    UPDATE document_chunks
                    SET knowledge_base_id = :target_knowledge_base_id
                    WHERE document_id = :document_id
                    """
                ),
                {
                    "target_knowledge_base_id": target_knowledge_base_id,
                    "document_id": document_id,
                },
            )
            db.execute(
                text(
                    """
                    UPDATE mind_map_histories
                    SET knowledge_base_id = :target_knowledge_base_id
                    WHERE document_id = :document_id AND user_id = :owner_id
                    """
                ),
                {
                    "target_knowledge_base_id": target_knowledge_base_id,
                    "document_id": document_id,
                    "owner_id": owner_id,
                },
            )
            vector_update_attempted = True
            vector_store.update_metadatas(ids=vector_ids, metadatas=new_metadatas)
            db.commit()
        except Exception as exc:
            db.rollback()
            if vector_update_attempted:
                try:
                    vector_store.update_metadatas(ids=vector_ids, metadatas=old_metadatas)
                except Exception:
                    logger.critical(
                        "Failed to restore vector metadata after document move failure "
                        "(document_id=%s, vector_count=%s)",
                        document_id,
                        len(vector_ids),
                        exc_info=True,
                    )
                    raise DocumentMoveConsistencyError(
                        "文档迁移失败，向量 metadata 回滚也失败，请立即检查服务日志。"
                    ) from exc
            raise DocumentMoveConsistencyError("文档迁移失败，数据库和向量数据已回滚。") from exc

        return self.get_owned_document(db, document_id, owner_id)

    def delete_document(self, db: Session, *, document_id: int, owner_id: int) -> None:
        row = self._get_manageable_document_row(
            db,
            document_id,
            owner_id,
            include_path=True,
        )

        vector_ids = self._list_vector_ids(db, document_id)
        get_vector_store().delete_ids(vector_ids)

        db.execute(
            text("DELETE FROM documents WHERE id = :document_id"),
            {"document_id": document_id},
        )
        db.commit()
        self._unlink_file(Path(row["file_path"]))

    def delete_vectors_for_knowledge_base(self, db: Session, *, knowledge_base_id: int, owner_id: int) -> None:
        rows = db.execute(
            text(
                """
                SELECT c.vector_id
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.knowledge_base_id = :knowledge_base_id AND d.owner_id = :owner_id
                """
            ),
            {"knowledge_base_id": knowledge_base_id, "owner_id": owner_id},
        ).mappings()
        get_vector_store().delete_ids([row["vector_id"] for row in rows])

    def delete_knowledge_base(self, db: Session, *, knowledge_base_id: int, owner_id: int) -> None:
        knowledge_base = knowledge_base_service.get_readable(
            db,
            knowledge_base_id,
            owner_id,
        )
        if not knowledge_base.can_delete:
            raise KnowledgeBasePermissionError("全局公共知识库不能删除。")
        file_rows = db.execute(
            text(
                """
                SELECT file_path
                FROM documents
                WHERE knowledge_base_id = :knowledge_base_id AND owner_id = :owner_id
                """
            ),
            {"knowledge_base_id": knowledge_base_id, "owner_id": owner_id},
        ).mappings()
        file_paths = [Path(row["file_path"]) for row in file_rows]

        self.delete_vectors_for_knowledge_base(
            db,
            knowledge_base_id=knowledge_base_id,
            owner_id=owner_id,
        )
        db.execute(
            text("DELETE FROM knowledge_bases WHERE id = :id AND owner_id = :owner_id"),
            {"id": knowledge_base_id, "owner_id": owner_id},
        )
        db.commit()

        for file_path in file_paths:
            self._unlink_file(file_path)
        self._remove_empty_upload_directory(owner_id, knowledge_base_id)

    def process_document(self, document_id: int) -> None:
        db = SessionLocal()
        inserted_vector_ids: list[str] = []
        old_vector_ids: list[str] = []

        try:
            if not self._claim_pending_document(db, document_id):
                return
            document = self._get_document_row(db, document_id, include_path=True)
            if document is None:
                return
            document = dict(document)
            db.rollback()

            blocks = document_parser.parse(document["file_path"], document["file_type"])
            chunks = text_splitter.split_blocks(blocks)
            if not chunks:
                raise DocumentParseError("文档解析失败：未提取到可用文字。")

            embeddings = embedding_client.embed_texts(
                [
                    build_embedding_text(
                        file_name=str(document["file_name"]),
                        text=chunk.text,
                        section_title=getattr(chunk, "section_title", None),
                    )
                    for chunk in chunks
                ]
            )
            if not self._lock_processing_document(db, document_id):
                db.rollback()
                raise DocumentProcessingCancelled()

            old_vector_ids = self._list_vector_ids(db, document_id)
            db.execute(
                text("DELETE FROM document_chunks WHERE document_id = :document_id"),
                {"document_id": document_id},
            )
            metadatas = []
            texts = []
            run_id = uuid4().hex[:12]

            for chunk in chunks:
                vector_id = (
                    f"kb{document['knowledge_base_id']}-doc{document_id}"
                    f"-run{run_id}-chunk{chunk.chunk_index}"
                )
                result = db.execute(
                    text(
                        """
                        INSERT INTO document_chunks (
                            document_id, knowledge_base_id, chunk_index, chunk_text,
                            page_no, start_offset, end_offset, vector_id
                        )
                        VALUES (
                            :document_id, :knowledge_base_id, :chunk_index, :chunk_text,
                            :page_no, :start_offset, :end_offset, :vector_id
                        )
                        """
                    ),
                    {
                        "document_id": document_id,
                        "knowledge_base_id": document["knowledge_base_id"],
                        "chunk_index": chunk.chunk_index,
                        "chunk_text": chunk.text,
                        "page_no": chunk.page_no,
                        "start_offset": chunk.start_offset,
                        "end_offset": chunk.end_offset,
                        "vector_id": vector_id,
                    },
                )
                chunk_id = int(result.lastrowid)
                inserted_vector_ids.append(vector_id)
                texts.append(chunk.text)
                metadatas.append(
                    {
                        "owner_id": int(document["owner_id"]),
                        "knowledge_base_id": int(document["knowledge_base_id"]),
                        "document_id": int(document_id),
                        "chunk_id": chunk_id,
                        "chunk_index": int(chunk.chunk_index),
                        "file_name": document["file_name"],
                        "page_no": int(chunk.page_no) if chunk.page_no is not None else 0,
                        "start_offset": int(chunk.start_offset),
                        "end_offset": int(chunk.end_offset),
                        "section_title": str(
                            getattr(chunk, "section_title", None) or ""
                        ),
                    }
                )

            get_vector_store().upsert_chunks(
                ids=inserted_vector_ids,
                texts=texts,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            self._mark_status(
                db,
                document_id,
                "completed",
                chunk_count=len(chunks),
                error_message=None,
                commit=False,
            )
            db.commit()
            self._safe_delete_vectors(old_vector_ids)
        except DocumentProcessingCancelled:
            db.rollback()
            self._safe_delete_vectors(inserted_vector_ids)
            logger.info("Document %s processing was cancelled", document_id)
        except (DocumentParseError, EmbeddingServiceError) as exc:
            db.rollback()
            self._safe_delete_vectors(inserted_vector_ids)
            logger.warning("Document %s processing failed: %s", document_id, exc)
            self._mark_status(
                db,
                document_id,
                "failed",
                error_message=str(exc),
                required_current_status="processing",
            )
        except Exception:
            db.rollback()
            self._safe_delete_vectors(inserted_vector_ids)
            logger.exception("Unexpected error while processing document %s", document_id)
            self._mark_status(
                db,
                document_id,
                "failed",
                error_message="文档处理失败，请稍后重试；若问题持续，请检查后端日志。",
                required_current_status="processing",
            )
        finally:
            db.close()

    async def _save_file(
        self,
        owner_id: int,
        knowledge_base_id: int,
        original_name: str,
        file: UploadFile,
    ) -> tuple[Path, int]:
        file_type = self._detect_file_type(original_name)
        safe_name = self._safe_file_name(original_name)
        target_dir = settings.upload_dir_path / str(owner_id) / str(knowledge_base_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{uuid4().hex}_{safe_name}"

        file_size = 0
        try:
            with target_path.open("wb") as target:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break

                    file_size += len(chunk)
                    if file_size > settings.max_upload_size_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"文件过大，最大允许 {settings.max_upload_size_mb} MB。",
                        )
                    target.write(chunk)
        except Exception:
            self._unlink_file(target_path)
            raise

        if file_size == 0:
            self._unlink_file(target_path)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空。")

        return target_path, file_size

    def _detect_file_type(self, file_name: str) -> str:
        file_type = Path(file_name).suffix.lower().lstrip(".")
        if not file_name or not file_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件名缺少扩展名。")

        if file_type not in self.allowed_file_types:
            allowed = "、".join(sorted(self.allowed_file_types))
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"仅支持 {allowed} 文件。")

        return file_type

    def _safe_file_name(self, file_name: str) -> str:
        blocked = '<>:"/\\|?*'
        return "".join("_" if char in blocked else char for char in file_name).strip() or "upload.bin"

    def _get_document_row(
        self,
        db: Session,
        document_id: int,
        owner_id: int | None = None,
        *,
        include_path: bool = False,
    ):
        columns = (
            "id, knowledge_base_id, owner_id, file_name, file_type, file_size, "
            "file_path, parse_status, error_message, chunk_count"
            if include_path
            else "id, knowledge_base_id, owner_id, file_name, file_type, file_size, parse_status, error_message, chunk_count"
        )
        conditions = ["id = :document_id"]
        params: dict[str, object] = {"document_id": document_id}

        if owner_id is not None:
            conditions.append("owner_id = :owner_id")
            params["owner_id"] = owner_id

        return db.execute(
            text(f"SELECT {columns} FROM documents WHERE {' AND '.join(conditions)}"),
            params,
        ).mappings().first()

    def _get_accessible_document_row(
        self,
        db: Session,
        document_id: int,
        owner_id: int,
        *,
        include_path: bool = False,
    ):
        path_column = ", d.file_path" if include_path else ""
        return db.execute(
            text(
                f"""
                SELECT d.id, d.knowledge_base_id, d.owner_id, d.file_name,
                       d.file_type, d.file_size, d.parse_status, d.error_message,
                       d.chunk_count, u.username AS uploader_username,
                       kb.visibility AS knowledge_base_visibility{path_column}
                FROM documents d
                JOIN knowledge_bases kb ON kb.id = d.knowledge_base_id
                JOIN users u ON u.id = d.owner_id
                WHERE d.id = :document_id
                  AND (kb.visibility = 'public' OR d.owner_id = :owner_id)
                """
            ),
            {"document_id": document_id, "owner_id": owner_id},
        ).mappings().first()

    def _get_manageable_document_row(
        self,
        db: Session,
        document_id: int,
        owner_id: int,
        *,
        include_path: bool = False,
    ):
        row = self._get_document_row(
            db,
            document_id,
            owner_id,
            include_path=include_path,
        )
        if row is not None:
            return row

        row = self._get_accessible_document_row(
            db,
            document_id,
            owner_id,
            include_path=include_path,
        )
        if row is None:
            raise ValueError("Document not found")
        if not self._can_manage_document(db, row, owner_id):
            raise DocumentPermissionError("只能管理自己上传的公共文档。")
        return row

    def _can_manage_document(self, db: Session, row, owner_id: int) -> bool:
        if int(row["owner_id"]) == owner_id:
            return True
        return (
            row["knowledge_base_visibility"] == "public"
            and self._is_admin(db, owner_id)
        )

    def _is_admin(self, db: Session, user_id: int) -> bool:
        role = db.execute(
            text("SELECT role FROM users WHERE id = :user_id"),
            {"user_id": user_id},
        ).scalar_one_or_none()
        return role == "admin"

    def _list_vector_ids(self, db: Session, document_id: int) -> list[str]:
        rows = db.execute(
            text("SELECT vector_id FROM document_chunks WHERE document_id = :document_id"),
            {"document_id": document_id},
        ).mappings()
        return [row["vector_id"] for row in rows]

    def _claim_pending_document(self, db: Session, document_id: int) -> bool:
        result = db.execute(
            text(
                """
                UPDATE documents
                SET parse_status = 'processing', error_message = NULL
                WHERE id = :document_id AND parse_status = 'pending'
                """
            ),
            {"document_id": document_id},
        )
        db.commit()
        return result.rowcount == 1

    def _lock_processing_document(self, db: Session, document_id: int) -> bool:
        lock_clause = "" if db.bind is not None and db.bind.dialect.name == "sqlite" else " FOR UPDATE"
        row = db.execute(
            text(
                "SELECT parse_status FROM documents "
                "WHERE id = :document_id" + lock_clause
            ),
            {"document_id": document_id},
        ).mappings().first()
        return row is not None and row["parse_status"] == "processing"

    def _safe_delete_vectors(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return
        for attempt in range(1, 4):
            try:
                get_vector_store().delete_ids(vector_ids)
                return
            except Exception:
                if attempt == 3:
                    logger.exception(
                        "Failed to delete %s stale document vectors after %s attempts",
                        len(vector_ids),
                        attempt,
                    )
                    return
                logger.warning(
                    "Retrying stale vector cleanup (attempt=%s, vector_count=%s)",
                    attempt,
                    len(vector_ids),
                    exc_info=True,
                )
                time.sleep(0.1 * attempt)

    def _mark_status(
        self,
        db: Session,
        document_id: int,
        parse_status: str,
        *,
        chunk_count: int | None = None,
        error_message: str | None = None,
        commit: bool = True,
        required_current_status: str | None = None,
    ) -> bool:
        assignments = ["parse_status = :parse_status", "error_message = :error_message"]
        params: dict[str, object] = {
            "document_id": document_id,
            "parse_status": parse_status,
            "error_message": error_message,
        }

        if chunk_count is not None:
            assignments.append("chunk_count = :chunk_count")
            params["chunk_count"] = chunk_count

        status_condition = ""
        if required_current_status is not None:
            status_condition = " AND parse_status = :required_current_status"
            params["required_current_status"] = required_current_status

        result = db.execute(
            text(
                f"UPDATE documents SET {', '.join(assignments)} "
                f"WHERE id = :document_id{status_condition}"
            ),
            params,
        )
        if commit:
            db.commit()
        return result.rowcount == 1

    def _unlink_file(self, path: Path) -> None:
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass

    def _remove_empty_upload_directory(self, owner_id: int, knowledge_base_id: int) -> None:
        target_dir = settings.upload_dir_path / str(owner_id) / str(knowledge_base_id)
        try:
            target_dir.rmdir()
        except OSError:
            pass

    def _to_document_read(self, row, *, can_manage: bool = False) -> DocumentRead:
        return DocumentRead(
            id=int(row["id"]),
            knowledge_base_id=int(row["knowledge_base_id"]),
            owner_id=int(row["owner_id"]),
            file_name=row["file_name"],
            file_type=row["file_type"],
            file_size=int(row["file_size"] or 0),
            parse_status=row["parse_status"],
            error_message=row["error_message"],
            chunk_count=int(row["chunk_count"] or 0),
            uploader_username=row.get("uploader_username"),
            knowledge_base_visibility=row.get(
                "knowledge_base_visibility",
                "private",
            ),
            can_manage=can_manage,
        )

    def _to_chunk_read(self, row) -> DocumentChunkRead:
        return DocumentChunkRead(
            id=int(row["id"]),
            document_id=int(row["document_id"]),
            knowledge_base_id=int(row["knowledge_base_id"]),
            chunk_index=int(row["chunk_index"]),
            chunk_text=row["chunk_text"],
            page_no=int(row["page_no"]) if row["page_no"] is not None else None,
            start_offset=int(row["start_offset"]) if row["start_offset"] is not None else None,
            end_offset=int(row["end_offset"]) if row["end_offset"] is not None else None,
            vector_id=row["vector_id"],
        )


document_service = DocumentService()

-- Preserve historical answer sources after their original document is deleted.
-- Run this once on databases created before 2026-07-11.
-- MySQL DDL statements auto-commit, so back up the database before applying it.

SET NAMES utf8mb4;

ALTER TABLE qa_sources
  ADD COLUMN file_name VARCHAR(255) NULL AFTER source_text,
  ADD COLUMN chunk_index INT UNSIGNED NULL AFTER file_name,
  ADD COLUMN page_no INT UNSIGNED NULL AFTER chunk_index;

UPDATE qa_sources AS source
JOIN documents AS document ON document.id = source.document_id
JOIN document_chunks AS chunk ON chunk.id = source.chunk_id
SET source.file_name = document.file_name,
    source.chunk_index = chunk.chunk_index,
    source.page_no = chunk.page_no;

ALTER TABLE qa_sources
  DROP FOREIGN KEY fk_qa_sources_document,
  DROP FOREIGN KEY fk_qa_sources_chunk;

ALTER TABLE qa_sources
  MODIFY COLUMN document_id BIGINT UNSIGNED NULL,
  MODIFY COLUMN chunk_id BIGINT UNSIGNED NULL,
  MODIFY COLUMN file_name VARCHAR(255) NOT NULL,
  MODIFY COLUMN chunk_index INT UNSIGNED NOT NULL;

ALTER TABLE qa_sources
  ADD CONSTRAINT fk_qa_sources_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE SET NULL,
  ADD CONSTRAINT fk_qa_sources_chunk
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
    ON DELETE SET NULL;

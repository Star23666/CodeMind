-- Add persistent JWT revocation and the document cancellation state required
-- by Issue #13. Run once on databases created before 2026-07-15.

SET NAMES utf8mb4;

ALTER TABLE users
  ADD COLUMN token_version INT UNSIGNED NOT NULL DEFAULT 0 AFTER status;

ALTER TABLE documents
  DROP CHECK chk_documents_parse_status,
  ADD CONSTRAINT chk_documents_parse_status
    CHECK (parse_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled'));

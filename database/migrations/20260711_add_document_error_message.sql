-- Add the document processing error message introduced on 2026-07-11.
-- Run this once on databases created before the column was added to schema.sql.

SET NAMES utf8mb4;

ALTER TABLE documents
  ADD COLUMN error_message VARCHAR(500) NULL AFTER parse_status;

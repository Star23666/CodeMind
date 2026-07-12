-- Create the persistent tables required by the mind map feature.
-- Run this once on databases created before the mind map tables were added to schema.sql.
-- MySQL DDL statements auto-commit, so back up the database before applying it.

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS mind_map_histories (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  document_id BIGINT UNSIGNED NULL,
  title VARCHAR(120) NOT NULL,
  node_count INT UNSIGNED NOT NULL,
  result_json LONGTEXT NOT NULL,
  view_state_json LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- The MODIFY clauses also upgrade tables previously created by the old
-- request-time _ensure_table() fallback, whose integer types were signed and
-- whose updated_at column did not update automatically.
ALTER TABLE mind_map_histories
  MODIFY COLUMN id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  MODIFY COLUMN user_id BIGINT UNSIGNED NOT NULL,
  MODIFY COLUMN knowledge_base_id BIGINT UNSIGNED NOT NULL,
  MODIFY COLUMN document_id BIGINT UNSIGNED NULL,
  MODIFY COLUMN node_count INT UNSIGNED NOT NULL,
  MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD KEY idx_mind_map_history_user_updated (user_id, updated_at),
  ADD CONSTRAINT fk_mind_map_history_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  ADD CONSTRAINT fk_mind_map_history_kb
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE,
  ADD CONSTRAINT fk_mind_map_history_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS mind_map_jobs (
  id VARCHAR(32) PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  document_id BIGINT UNSIGNED NULL,
  max_depth INT UNSIGNED NOT NULL DEFAULT 3,
  max_nodes INT UNSIGNED NOT NULL DEFAULT 28,
  status VARCHAR(20) NOT NULL,
  stage VARCHAR(30) NOT NULL,
  progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
  message VARCHAR(255) NOT NULL,
  result_json LONGTEXT NULL,
  error_message TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE mind_map_jobs
  MODIFY COLUMN user_id BIGINT UNSIGNED NOT NULL,
  MODIFY COLUMN knowledge_base_id BIGINT UNSIGNED NOT NULL,
  MODIFY COLUMN document_id BIGINT UNSIGNED NULL,
  MODIFY COLUMN max_depth INT UNSIGNED NOT NULL DEFAULT 3,
  MODIFY COLUMN max_nodes INT UNSIGNED NOT NULL DEFAULT 28,
  MODIFY COLUMN progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
  MODIFY COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD KEY idx_mind_map_jobs_user_created (user_id, created_at),
  ADD KEY idx_mind_map_jobs_status (status),
  ADD CONSTRAINT fk_mind_map_jobs_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  ADD CONSTRAINT fk_mind_map_jobs_knowledge_base
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE,
  ADD CONSTRAINT fk_mind_map_jobs_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE SET NULL,
  ADD CONSTRAINT chk_mind_map_jobs_status
    CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
  ADD CONSTRAINT chk_mind_map_jobs_progress
    CHECK (progress BETWEEN 0 AND 100)
;

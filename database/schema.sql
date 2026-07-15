SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(50) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  email VARCHAR(120) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'user',
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  token_version INT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_users_username (username),
  UNIQUE KEY uk_users_email (email),
  KEY idx_users_status (status),
  CONSTRAINT chk_users_role CHECK (role IN ('user', 'admin')),
  CONSTRAINT chk_users_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_bases (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  owner_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  description TEXT NULL,
  visibility VARCHAR(20) NOT NULL DEFAULT 'private',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_knowledge_bases_owner_name (owner_id, name),
  KEY idx_knowledge_bases_owner_id (owner_id),
  KEY idx_knowledge_bases_visibility (visibility),
  CONSTRAINT fk_knowledge_bases_owner
    FOREIGN KEY (owner_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_knowledge_bases_visibility CHECK (visibility IN ('private', 'public'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documents (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  owner_id BIGINT UNSIGNED NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_type VARCHAR(50) NOT NULL,
  file_size BIGINT UNSIGNED NOT NULL DEFAULT 0,
  file_path VARCHAR(500) NOT NULL,
  parse_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  error_message VARCHAR(500) NULL,
  chunk_count INT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_documents_owner_id (owner_id),
  KEY idx_documents_knowledge_base_id (knowledge_base_id),
  KEY idx_documents_parse_status (parse_status),
  CONSTRAINT fk_documents_owner
    FOREIGN KEY (owner_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_documents_knowledge_base
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_documents_parse_status
    CHECK (parse_status IN ('pending', 'processing', 'completed', 'failed', 'cancelled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_chunks (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  document_id BIGINT UNSIGNED NOT NULL,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  chunk_index INT UNSIGNED NOT NULL,
  chunk_text MEDIUMTEXT NOT NULL,
  page_no INT UNSIGNED NULL,
  start_offset INT UNSIGNED NULL,
  end_offset INT UNSIGNED NULL,
  vector_id VARCHAR(128) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_document_chunks_doc_index (document_id, chunk_index),
  UNIQUE KEY uk_document_chunks_vector_id (vector_id),
  KEY idx_document_chunks_document_id (document_id),
  KEY idx_document_chunks_knowledge_base_id (knowledge_base_id),
  CONSTRAINT fk_document_chunks_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_document_chunks_knowledge_base
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qa_records (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  knowledge_base_id BIGINT UNSIGNED NOT NULL,
  question TEXT NOT NULL,
  rewritten_question TEXT NULL,
  answer MEDIUMTEXT NOT NULL,
  source_count INT UNSIGNED NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_qa_records_user_id (user_id),
  KEY idx_qa_records_knowledge_base_id (knowledge_base_id),
  KEY idx_qa_records_created_at (created_at),
  CONSTRAINT fk_qa_records_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_qa_records_knowledge_base
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS qa_sources (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  qa_record_id BIGINT UNSIGNED NOT NULL,
  document_id BIGINT UNSIGNED NULL,
  chunk_id BIGINT UNSIGNED NULL,
  rank_no INT UNSIGNED NOT NULL,
  score DECIMAL(7,6) NULL,
  source_text TEXT NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  chunk_index INT UNSIGNED NOT NULL,
  page_no INT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_qa_sources_record_chunk (qa_record_id, chunk_id),
  KEY idx_qa_sources_qa_record_id (qa_record_id),
  KEY idx_qa_sources_document_id (document_id),
  KEY idx_qa_sources_chunk_id (chunk_id),
  CONSTRAINT fk_qa_sources_qa_record
    FOREIGN KEY (qa_record_id) REFERENCES qa_records(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_qa_sources_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_qa_sources_chunk
    FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
    ON DELETE SET NULL,
  CONSTRAINT chk_qa_sources_score CHECK (score IS NULL OR (score >= -1 AND score <= 1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feedbacks (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  qa_record_id BIGINT UNSIGNED NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  rating TINYINT UNSIGNED NOT NULL,
  comment TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_feedbacks_record_user (qa_record_id, user_id),
  KEY idx_feedbacks_qa_record_id (qa_record_id),
  KEY idx_feedbacks_user_id (user_id),
  CONSTRAINT fk_feedbacks_qa_record
    FOREIGN KEY (qa_record_id) REFERENCES qa_records(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_feedbacks_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_feedbacks_rating CHECK (rating BETWEEN 1 AND 5)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_mind_map_history_user_updated (user_id, updated_at),
  CONSTRAINT fk_mind_map_history_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_mind_map_history_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  CONSTRAINT fk_mind_map_history_document FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_mind_map_jobs_user_created (user_id, created_at),
  KEY idx_mind_map_jobs_status (status),
  CONSTRAINT fk_mind_map_jobs_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_mind_map_jobs_knowledge_base
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_mind_map_jobs_document
    FOREIGN KEY (document_id) REFERENCES documents(id)
    ON DELETE SET NULL,
  CONSTRAINT chk_mind_map_jobs_status
    CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
  CONSTRAINT chk_mind_map_jobs_progress
    CHECK (progress BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

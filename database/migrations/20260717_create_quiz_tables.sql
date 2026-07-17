-- Add short-lived AI quiz sessions for Issue #18.
-- Submitted sessions are deleted by the application; expired sessions are
-- periodically removed by the quiz cleanup worker.

CREATE TABLE IF NOT EXISTS quiz_sessions (
  id VARCHAR(32) PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  knowledge_base_ids_json TEXT NOT NULL,
  config_json TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'queued',
  stage VARCHAR(30) NOT NULL DEFAULT 'queued',
  progress TINYINT UNSIGNED NOT NULL DEFAULT 0,
  message VARCHAR(255) NOT NULL,
  error_message TEXT NULL,
  expires_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_quiz_sessions_user_created (user_id, created_at),
  KEY idx_quiz_sessions_status (status),
  KEY idx_quiz_sessions_expires_at (expires_at),
  CONSTRAINT fk_quiz_sessions_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_quiz_sessions_status
    CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
  CONSTRAINT chk_quiz_sessions_progress
    CHECK (progress BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_questions (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(32) NOT NULL,
  order_no INT UNSIGNED NOT NULL,
  question_type VARCHAR(30) NOT NULL,
  prompt TEXT NOT NULL,
  options_json TEXT NOT NULL,
  answer_json TEXT NOT NULL,
  explanation TEXT NOT NULL,
  sources_json LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_quiz_questions_session_order (session_id, order_no),
  KEY idx_quiz_questions_session (session_id),
  CONSTRAINT fk_quiz_questions_session
    FOREIGN KEY (session_id) REFERENCES quiz_sessions(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_quiz_questions_type CHECK (
    question_type IN (
      'single_choice', 'multiple_choice', 'true_false',
      'fill_blank', 'short_answer', 'scenario'
    )
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

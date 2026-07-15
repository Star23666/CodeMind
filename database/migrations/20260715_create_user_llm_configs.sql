SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS user_llm_configs (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(80) NOT NULL,
  provider VARCHAR(30) NOT NULL DEFAULT 'openai_compatible',
  base_url VARCHAR(500) NOT NULL,
  model VARCHAR(200) NOT NULL,
  api_key_ciphertext TEXT NOT NULL,
  api_key_last4 VARCHAR(8) NOT NULL,
  test_status VARCHAR(20) NOT NULL DEFAULT 'untested',
  test_message VARCHAR(255) NULL,
  last_tested_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_llm_configs_user_name (user_id, name),
  KEY idx_user_llm_configs_user_id (user_id),
  KEY idx_user_llm_configs_test_status (test_status),
  CONSTRAINT fk_user_llm_configs_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT chk_user_llm_configs_provider
    CHECK (provider IN ('siliconflow', 'openai', 'openai_compatible')),
  CONSTRAINT chk_user_llm_configs_test_status
    CHECK (test_status IN ('untested', 'success', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_llm_preferences (
  user_id BIGINT UNSIGNED PRIMARY KEY,
  active_config_id BIGINT UNSIGNED NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_user_llm_preferences_active_config (active_config_id),
  CONSTRAINT fk_user_llm_preferences_user
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_user_llm_preferences_active_config
    FOREIGN KEY (active_config_id) REFERENCES user_llm_configs(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

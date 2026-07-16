-- Add the single global public knowledge base required by Issue #15.
-- Apply this migration once to databases created before 2026-07-16.

ALTER TABLE knowledge_bases
  MODIFY COLUMN owner_id BIGINT UNSIGNED NULL;

-- The application previously rejected public knowledge bases, so production data
-- should contain none. This normalization still keeps the oldest row if someone
-- inserted public rows manually before applying the migration.
SET @global_public_id = (
  SELECT MIN(id) FROM knowledge_bases WHERE visibility = 'public'
);

UPDATE knowledge_bases
SET visibility = 'private'
WHERE visibility = 'public'
  AND @global_public_id IS NOT NULL
  AND id <> @global_public_id;

UPDATE knowledge_bases
SET owner_id = NULL
WHERE id = @global_public_id;

ALTER TABLE knowledge_bases
  ADD COLUMN global_public_key TINYINT
    GENERATED ALWAYS AS (CASE WHEN visibility = 'public' THEN 1 ELSE NULL END) STORED,
  ADD UNIQUE KEY uk_knowledge_bases_global_public (global_public_key),
  ADD CONSTRAINT chk_knowledge_bases_scope CHECK (
    (visibility = 'private' AND owner_id IS NOT NULL)
    OR (visibility = 'public' AND owner_id IS NULL)
  );

INSERT INTO knowledge_bases (owner_id, name, description, visibility)
SELECT NULL,
       CONVERT(0xE585ACE585B1E79FA5E8AF86E5BA93 USING utf8mb4),
       CONVERT(0xE68980E69C89E799BBE5BD95E794A8E688B7E585B1E5908CE7BBB4E68AA4E5928CE6A380E7B4A2E79A84E585ACE585B1E8AEA1E7AE97E69CBAE79FA5E8AF86E8B584E69699E38082 USING utf8mb4),
       'public'
WHERE NOT EXISTS (
  SELECT 1 FROM knowledge_bases WHERE visibility = 'public'
);

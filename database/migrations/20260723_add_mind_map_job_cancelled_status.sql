-- 允许用户主动取消仍在等待或生成中的知识地图任务。
ALTER TABLE mind_map_jobs
  DROP CHECK chk_mind_map_jobs_status;

ALTER TABLE mind_map_jobs
  ADD CONSTRAINT chk_mind_map_jobs_status
  CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled'));

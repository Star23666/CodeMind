# CodeMind Database

CodeMind 使用 MySQL 保存结构化业务数据，使用 Chroma 保存文档片段向量。两者承担不同职责，不能互相替代。

## MySQL 表

| 表 | 用途 |
| --- | --- |
| `users` | 用户、密码哈希、角色和状态 |
| `knowledge_bases` | 私人知识库和用户归属 |
| `documents` | 文件信息、处理状态、错误和片段数量 |
| `document_chunks` | 文本片段、位置、页码和 `vector_id` |
| `qa_records` | 问题、重写问题、回答和来源数量 |
| `qa_sources` | 历史来源快照和可空的原文关联 |
| `feedbacks` | 反馈目标表；当前业务接口尚未持久化 |
| `mind_map_histories` | 地图结果 JSON、节点数和画布状态 |
| `mind_map_jobs` | 地图后台任务、阶段、进度、结果和错误 |

新数据库由 `schema.sql` 初始化。Docker 中该脚本只会在 `mysql_data` 数据卷第一次创建时运行。

## 已有数据库迁移

| 脚本 | 用途 |
| --- | --- |
| `migrations/20260711_add_document_error_message.sql` | 增加文档处理失败原因 |
| `migrations/20260711_preserve_qa_source_snapshots.sql` | 删除原文后保留问答来源快照 |
| `migrations/20260712_create_mind_map_tables.sql` | 创建地图历史和后台任务表 |

生产数据库执行迁移前必须备份。迁移脚本按说明执行一次，不要通过删除 Docker 数据卷来替代迁移。

Linux、macOS 或 WSL 示例：

```bash
docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
  < database/migrations/<migration>.sql
```

Windows PowerShell 示例：

```powershell
Get-Content -Raw database\migrations\<migration>.sql |
  docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
```

## Chroma 关联

`document_chunks.vector_id` 与 Chroma 记录 ID 一一对应。Chroma metadata 至少包含用户、知识库、文档、片段序号、文件名、页码和偏移信息，以便权限过滤和来源反查。

更换 Embedding 模型或向量维度后，旧向量不能与新向量混用。应停止写入、备份数据、清空或重建 Chroma 索引，并对现有文档重新入库；MySQL 用户和业务记录不应随向量重建一起删除。

## 知识地图字段兼容

`node_type`、`key_points` 和 `learning_tip` 位于 `mind_map_histories.result_json`，不是独立数据库列。新增字段由后端模型提供默认值，因此 PR #11 不需要额外数据库迁移，旧地图历史可以继续读取。

# CodeMind Backend

FastAPI 后端负责认证、知识库与文档管理、Embedding 入库、Chroma 检索、RAG 问答、问答历史、知识地图和 AI 定制练习服务。

## 模块结构

| 目录或文件 | 职责 |
| --- | --- |
| `app/api/routes.py` | REST API 与 HTTP 错误转换 |
| `app/core/config.py` | `.env` 配置读取和路径解析 |
| `app/db/session.py` | SQLAlchemy Engine 与 Session |
| `app/services/document_service.py` | 上传、后台解析、入库、重建、私人库间迁移和删除 |
| `app/services/knowledge_base_service.py` | 公共/私人知识库作用域和读取、上传、管理权限 |
| `app/services/document_job_service.py` | 文档任务并发调度、启动恢复和实例内防重 |
| `app/services/feedback_service.py` | 问答反馈持久化、归属校验和管理员筛选 |
| `app/services/admin_service.py` | 管理员概览、用户启停、公共文档治理和私人数据脱敏 |
| `app/services/health_service.py` | MySQL 与 Chroma 就绪检查 |
| `app/services/retrieval_service.py` | 问题重写、Dense/BM25 召回、RRF 融合、在线 rerank 与降级 |
| `app/services/reranker_client.py` | OpenAI 兼容根地址下的在线 Rerank 调用、重试和安全错误分类 |
| `app/services/retrieval_scoring.py` | BM25、RRF 和回退关键词评分 |
| `app/services/rag_service.py` | 检索、Prompt、LLM、SSE 流式输出和历史保存的问答编排 |
| `app/services/mind_map_service.py` | 知识地图结构生成、节点追问和分支扩展 |
| `app/services/mind_map_job_service.py` | 异步任务状态、进度和结果持久化 |
| `app/services/mind_map_history_service.py` | 地图历史版本和画布状态持久化 |
| `app/services/quiz_service.py` | 多知识库抽样、结构化出题、来源校验、评分和临时会话清理 |
| `app/services/quiz_job_service.py` | 出题后台任务、进度、启动恢复和过期清理 |
| `scripts/promote_admin.py` | 将已注册用户安全提升为管理员 |
| `scripts/evaluate_quality.py` | 固定 RAG 阈值、拒答与 AI 出题质量评估 |
| `tests/` | 后端自动化测试 |

## 环境配置

在 `backend/` 下创建 `.env`。字段模板位于仓库根目录 `.env.example`，至少配置：

```dotenv
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=replace_with_database_password
MYSQL_DATABASE=codemind

LLM_API_KEY=replace_with_llm_key
LLM_BASE_URL=https://provider.example.com/v1
LLM_MODEL=replace_with_chat_model
CHAT_TOTAL_TIMEOUT_SECONDS=60

# 独立用于加密用户保存的模型 API Key，至少 32 个随机字符
LLM_CONFIG_ENCRYPTION_KEY=replace_with_a_separate_random_secret

# 可选：知识地图单独使用更快的纯文本指令模型
MIND_MAP_MODEL=replace_with_structured_text_model
MIND_MAP_TIMEOUT_SECONDS=600
# 每次模型调用（含结构化输出重试）的墙钟总时限
MIND_MAP_TOTAL_TIMEOUT_SECONDS=900
MIND_MAP_ENABLE_THINKING=false

QUIZ_TIMEOUT_SECONDS=300
QUIZ_MAX_TOKENS=12000
QUIZ_ENABLE_THINKING=false
QUIZ_SESSION_TTL_MINUTES=60
QUIZ_CONTEXT_MAX_TOKENS=8000

EMBEDDING_API_KEY=replace_with_embedding_key
EMBEDDING_BASE_URL=https://provider.example.com/v1
EMBEDDING_MODEL=replace_with_embedding_model
EMBEDDING_BATCH_SIZE=64
RERANK_API_KEY=
RERANK_BASE_URL=
RERANK_MODEL=Qwen/Qwen3-Reranker-8B
RERANK_SCORE_THRESHOLD=0.55
RETRIEVAL_SCORE_THRESHOLD=0.45

DOCUMENT_WORKER_CONCURRENCY=2
MAX_UPLOAD_SIZE_MB=50
DOCUMENT_MAX_EXPANDED_SIZE_MB=100
DOCUMENT_MAX_PARSED_CHARS=3500000
DOCUMENT_MAX_CHUNKS=5000

JWT_SECRET_KEY=replace_with_a_long_random_secret
```

Embedding 未配置时，文档入库和检索会明确失败。`RERANK_API_KEY`/`RERANK_BASE_URL` 留空时复用系统 `LLM_*`；正常检索使用 `RERANK_SCORE_THRESHOLD=0.55`，reranker 不可用且 `RERANK_FAIL_OPEN=true` 时回退到向量链路及 `RETRIEVAL_SCORE_THRESHOLD=0.45`。普通 RAG 问答在 LLM 未配置时保留本地演示回答；知识地图和 AI 出题依赖结构化 LLM 输出，因此必须配置在线 LLM。

## 原生开发

Windows PowerShell：

```powershell
cd backend
E:\Python\python.exe -m pip install -r requirements.txt
E:\Python\python.exe -m uvicorn app.main:app --reload
```

Linux、macOS 或 WSL：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

默认地址：

- API：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`
- 存活检查：`http://localhost:8000/api/health/live`
- 就绪检查：`http://localhost:8000/api/health/ready`

除健康检查、注册和登录外，业务接口需要：

```http
Authorization: Bearer <access_token>
```

RAG 问答提供两个接口：`POST /api/chat` 返回完整 JSON；`POST /api/chat/stream` 返回
`text/event-stream`。流式接口依次发送 `meta`、多个 `token` 和 `done` 事件，只有生成完成并发送
`done` 后才保存问答历史；处理异常时发送 `error` 事件。客户端断开或生成失败时，不应把未完成回答当作已保存记录。

用户可在“我的 → AI 模型设置”中最多保存 5 套 OpenAI 兼容模型预设。API Key
使用 `LLM_CONFIG_ENCRYPTION_KEY` 加密后写入数据库，接口只返回末四位；预设必须测试成功后才能启用。
测试由后端限制为单用户单并发、至少间隔 30 秒。未启用个人预设时，
系统默认项会展示并使用 `.env` 中的 `LLM_MODEL`。
连接失败会区分 API Key 认证失败、连接超时、模型不存在以及模型/API 接口不存在；安全提示会写回
`test_message`，供应商原始响应和完整密钥不会返回前端。
硅基流动和 OpenAI 预设只能使用各自官方域名，其他兼容域名需要服务端通过
`LLM_OPENAI_COMPATIBLE_ALLOWED_HOSTS` 显式放行。测试连接、普通问答、SSE 和知识地图的
每次实际请求前都会重新检查 DNS 解析结果，拒绝本机、私网、链路本地和保留地址。
启用个人预设后，问答、知识地图和 AI 出题不会在调用失败时自动回退到系统模型。AI 出题的首次生成和结构重试显式复用同一个 `llm_config_service.resolve_runtime` 结果；未启用个人预设时才使用系统模型。Embedding 继续使用服务器统一配置。

知识库分为两种作用域：私人库按 `knowledge_base_id + owner_id` 隔离；唯一的全局公共库按
`knowledge_base_id` 聚合所有上传者的文档。所有登录用户可读取、上传和检索公共资料，上传者可管理
自己的公共文档，管理员可编辑公共库信息并管理全部公共文档。公共库没有固定 ID，也不能删除。

已有数据库需要先执行 `database/migrations/20260716_create_global_public_knowledge_base.sql`。管理员通过
`python scripts/promote_admin.py --username <用户名>` 或 `--email <邮箱>` 初始化；脚本不创建默认账号，
普通注册接口也不能指定管理员角色。

非流式回答受 `CHAT_TOTAL_TIMEOUT_SECONDS` 硬生成时限约束。检索和生成日志分别记录 Embedding/LLM 模型、检索耗时、首 Token、总耗时和 `finish_reason`。

## 文档任务说明

- 上传和重建只写入 `pending` 状态，由受并发限制的后台 Worker 原子领取。
- 上传文件会校验实际 PDF/DOCX 结构；DOCX 解压体积、解析字符数和切片数都有独立上限，防止小压缩包放大后耗尽内存。
- 文件写盘不占用 FastAPI 事件循环；Embedding 按 `EMBEDDING_BATCH_SIZE` 分批调用，避免大文档一次请求过载供应商。
- Markdown 解析保留标题和段落换行，切片时不会把整篇文档压成一行。
- 同一文档不能重复入队；重建中的再次提交返回 `409`。
- 后端启动时会将中断的 `processing` 文档恢复为 `pending` 并重新调度。
- 新片段和新向量成功后才替换旧索引；解析、Embedding 或写入失败时保留旧索引。
- `POST /api/documents/{id}/cancel` 可以取消等待中或处理中的任务。

## 知识地图说明

- `POST /api/mind-maps/jobs` 创建后台任务，`GET /api/mind-maps/jobs/{job_id}` 查询进度。
- 相同用户、知识库和文档范围已有活动任务时复用原任务；`POST /api/mind-maps/jobs/{job_id}/cancel` 可主动取消。
- 1～3 个资料片段会单次生成；更大范围先按文档均衡采样、分批提炼，再按资料顺序合并为总览、章节、概念和细节节点。
- 结构生成通过 LLM 流式响应收集文本，并受每次模型调用的墙钟总时限约束；首次生成和结构化输出长度重试共享该时限，超时会取消流并释放全局 LLM 并发槽位。
- `MIND_MAP_TOTAL_TIMEOUT_SECONDS=0` 仅作为管理员显式关闭保护的特殊选项；异常上游持续零星输出但不结束时可能永久占用 3 个全局槽位，生产环境应保留有限值。
- 后端重启时，处于等待或处理中的知识地图任务会自动重新排队，客户端可继续查询原任务 ID。
- 每个节点可包含 `key_points`、`learning_tip`、原文来源和子节点。
- 模型只能引用本次实际提供的片段；无真实来源、同级同名的重复节点会在保存前剔除。
- 长时间等待模型前会释放只读数据库事务，避免生成期间占住连接池。
- 同一后端实例的知识地图 LLM 调用并发上限为 3；分批调用失败时会取消剩余请求。
- 自动生成结果会保存历史版本；前端也可创建、更新和删除版本。
- 新增节点学习字段位于历史 JSON 中，旧数据可使用默认值读取，不需要数据库迁移。

## AI 出题说明

- `POST /api/quizzes/sessions` 创建后台任务，支持同时选择 1～5 个有读取权的私人或公共知识库。
- 后端先在每个知识库内按文档轮询、再在知识库之间轮询抽取已完成片段，并受片段数、字符数和保守 Token 上限约束；任务真正执行前会再次校验权限。
- 题目由 Pydantic 校验数量、六类题型、选项、答案和真实来源编号；未限定主题时还会校验整套题的文档覆盖度，避免长文档垄断题目。
- 每题带内部认知层级；进阶题至少 40% 达到应用或分析，挑战题至少 70% 达到应用或分析且至少 40% 为分析。无效结构只有限重试，整批验证通过后才入库。
- `GET /api/quizzes/sessions/{id}` 只返回题干、选项和来源数量，不返回答案、解析或来源正文。
- `POST /api/quizzes/sessions/{id}/submit` 自动评分单选、多选、判断和填空，主观题返回参考答案供自评；结果返回后立即删除会话和题目。
- `DELETE /api/quizzes/sessions/{id}` 清理放弃的练习，过期会话由后台任务定期清理。所有会话接口只允许创建者访问。
- 已有数据库必须先执行 `database/migrations/20260717_create_quiz_tables.sql`。
- 在线模型生成耗时与语义质量、真实依赖测试自动化等后续事项见 [已知问题与后续计划](../docs/已知问题与后续计划.md)。

固定质量数据位于 `../testdata/eval/`。先运行 `python scripts/evaluate_quality.py validate` 校验语料与标注；当前完整检索使用 `python scripts/evaluate_quality.py rag-hybrid --output <path> --with-generation` 评估，在线阈值、拒答、出题和人工评分说明见 [RAG 与 AI 出题质量评估](../docs/RAG与AI出题质量评估.md)。在线命令会消耗 API 额度，不加入普通 PR CI。

## 运行测试

```bash
cd backend
python -m pytest -q
```

当前基线以本分支完整测试结果为准。测试使用 SQLite 和替身服务覆盖主要业务，其中包括全局公共库唯一性、跨用户公共文档访问和管理、私人库隔离、管理员初始化与用户启停、私人数据脱敏、删除清理、个人模型配置、连接错误分类、敏感日志与 SSRF 防护、问答和知识地图个人模型路由、知识地图流式总超时、均衡采样、来源过滤、任务取消和并发槽位释放、文档格式与体积校验、Embedding 分批、重启恢复、重复入队、取消、私人库间迁移与 MySQL/Chroma 补偿、索引补偿和陈旧向量过滤、Dense/BM25/RRF/reranker 与权限化词法召回、反馈持久化、越权与管理员筛选，JWT 注销撤销，MySQL/Chroma 就绪探针，固定质量数据校验、指标计算与基线产物，以及 AI 出题的多库权限、文档轮询、覆盖度、难度结构、输入预算、来源编号白名单、答案隔离、评分、BYOK 与临时清理；Docker 端到端测试另外验证真实 MySQL、Chroma、在线 Embedding/LLM、Issue #28 角色流程、公共库跨用户检索、AI 六类题型、来源反查、权限按钮和数据同步清理。

## Docker 运行

完整环境建议从仓库根目录启动：

```bash
docker compose up -d --build
docker compose logs -f backend
```

已有数据库升级时还需按根目录 README 执行 `database/migrations/` 中尚未应用的脚本。


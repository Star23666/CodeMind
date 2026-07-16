# CodeMind Backend

FastAPI 后端负责认证、知识库与文档管理、Embedding 入库、Chroma 检索、RAG 问答、问答历史和知识地图服务。

## 模块结构

| 目录或文件 | 职责 |
| --- | --- |
| `app/api/routes.py` | REST API 与 HTTP 错误转换 |
| `app/core/config.py` | `.env` 配置读取和路径解析 |
| `app/db/session.py` | SQLAlchemy Engine 与 Session |
| `app/services/document_service.py` | 上传、后台解析、入库、重建和删除 |
| `app/services/document_job_service.py` | 文档任务并发调度、启动恢复和实例内防重 |
| `app/services/feedback_service.py` | 问答反馈持久化、归属校验和管理员筛选 |
| `app/services/health_service.py` | MySQL 与 Chroma 就绪检查 |
| `app/services/retrieval_service.py` | 问题重写、Embedding、Chroma 召回、过滤与 rerank |
| `app/services/rag_service.py` | 检索、Prompt、LLM、SSE 流式输出和历史保存的问答编排 |
| `app/services/mind_map_service.py` | 知识地图结构生成、节点追问和分支扩展 |
| `app/services/mind_map_job_service.py` | 异步任务状态、进度和结果持久化 |
| `app/services/mind_map_history_service.py` | 地图历史版本和画布状态持久化 |
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
# 设为 0 表示关闭整体耗时上限，真实的模型或网络异常仍会报错
MIND_MAP_TOTAL_TIMEOUT_SECONDS=0
MIND_MAP_ENABLE_THINKING=false

EMBEDDING_API_KEY=replace_with_embedding_key
EMBEDDING_BASE_URL=https://provider.example.com/v1
EMBEDDING_MODEL=replace_with_embedding_model
RETRIEVAL_SCORE_THRESHOLD=0.45

DOCUMENT_WORKER_CONCURRENCY=2

JWT_SECRET_KEY=replace_with_a_long_random_secret
```

Embedding 未配置时，文档入库和检索会明确失败；普通 RAG 问答在 LLM 未配置时保留本地演示回答。知识地图依赖结构化 LLM 输出，因此必须配置在线 LLM。

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
硅基流动和 OpenAI 预设只能使用各自官方域名，其他兼容域名需要服务端通过
`LLM_OPENAI_COMPATIBLE_ALLOWED_HOSTS` 显式放行。测试连接、普通问答、SSE 和知识地图的
每次实际请求前都会重新检查 DNS 解析结果，拒绝本机、私网、链路本地和保留地址。

非流式回答受 `CHAT_TOTAL_TIMEOUT_SECONDS` 硬生成时限约束。检索和生成日志分别记录 Embedding/LLM 模型、检索耗时、首 Token、总耗时和 `finish_reason`。

## 文档任务说明

- 上传和重建只写入 `pending` 状态，由受并发限制的后台 Worker 原子领取。
- 同一文档不能重复入队；重建中的再次提交返回 `409`。
- 后端启动时会将中断的 `processing` 文档恢复为 `pending` 并重新调度。
- 新片段和新向量成功后才替换旧索引；解析、Embedding 或写入失败时保留旧索引。
- `POST /api/documents/{id}/cancel` 可以取消等待中或处理中的任务。

## 知识地图说明

- `POST /api/mind-maps/jobs` 创建后台任务，`GET /api/mind-maps/jobs/{job_id}` 查询进度。
- 1～3 个资料片段会单次生成；更大范围先分批提炼，再合并为总览、章节、概念和细节节点。
- 结构生成通过 LLM 流式响应收集文本，并受每次请求总时限约束；知识地图可单独配置纯文本模型和关闭思考模式。
- 后端重启时，处于等待或处理中的知识地图任务会自动重新排队，客户端可继续查询原任务 ID。
- 每个节点可包含 `key_points`、`learning_tip`、原文来源和子节点。
- 同一后端实例的知识地图 LLM 调用并发上限为 3；分批调用失败时会取消剩余请求。
- 自动生成结果会保存历史版本；前端也可创建、更新和删除版本。
- 新增节点学习字段位于历史 JSON 中，旧数据可使用默认值读取，不需要数据库迁移。

## 运行测试

```bash
cd backend
python -m pytest -q
```

当前基线为 `90 passed`。测试使用 SQLite 和替身服务覆盖主要业务，其中包括个人模型配置与 SSRF 防护、文档重启恢复、重复入队、取消、索引补偿和陈旧向量过滤，反馈持久化与越权，JWT 注销撤销，以及 MySQL/Chroma 就绪探针；Docker 端到端测试另外验证真实 MySQL、Chroma、在线 Embedding/LLM、Nginx SSE 代理和知识地图任务恢复、多批次任务链路。

## Docker 运行

完整环境建议从仓库根目录启动：

```bash
docker compose up -d --build
docker compose logs -f backend
```

已有数据库升级时还需按根目录 README 执行 `database/migrations/` 中尚未应用的脚本。


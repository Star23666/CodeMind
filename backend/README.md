# CodeMind Backend

FastAPI 后端负责认证、知识库与文档管理、Embedding 入库、Chroma 检索、RAG 问答、问答历史和知识地图服务。

## 模块结构

| 目录或文件 | 职责 |
| --- | --- |
| `app/api/routes.py` | REST API 与 HTTP 错误转换 |
| `app/core/config.py` | `.env` 配置读取和路径解析 |
| `app/db/session.py` | SQLAlchemy Engine 与 Session |
| `app/services/document_service.py` | 上传、后台解析、入库、重建和删除 |
| `app/services/retrieval_service.py` | 问题重写、Embedding、Chroma 召回、过滤与 rerank |
| `app/services/rag_service.py` | 检索、Prompt、LLM、历史保存的问答编排 |
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

EMBEDDING_API_KEY=replace_with_embedding_key
EMBEDDING_BASE_URL=https://provider.example.com/v1
EMBEDDING_MODEL=replace_with_embedding_model

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
- 健康检查：`http://localhost:8000/api/health`

除健康检查、注册和登录外，业务接口需要：

```http
Authorization: Bearer <access_token>
```

## 知识地图说明

- `POST /api/mind-maps/jobs` 创建后台任务，`GET /api/mind-maps/jobs/{job_id}` 查询进度。
- 任务会分批提炼资料，再合并为总览、章节、概念和细节节点。
- 每个节点可包含 `key_points`、`learning_tip`、原文来源和子节点。
- 同一后端实例的知识地图 LLM 调用并发上限为 3；分批调用失败时会取消剩余请求。
- 自动生成结果会保存历史版本；前端也可创建、更新和删除版本。
- 新增节点学习字段位于历史 JSON 中，旧数据可使用默认值读取，不需要数据库迁移。

## 运行测试

```bash
cd backend
python -m pytest -q
```

当前基线为 `53 passed`。测试使用 SQLite 和替身服务覆盖主要业务，不等同于真实 MySQL、Chroma 和在线模型端到端验证。

## Docker 运行

完整环境建议从仓库根目录启动：

```bash
docker compose up -d --build
docker compose logs -f backend
```

已有数据库升级时还需按根目录 README 执行 `database/migrations/` 中尚未应用的脚本。


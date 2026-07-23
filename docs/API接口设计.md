# CodeMind API 接口设计

## 1. 通用约定

- 基础路径：`/api`
- 数据格式：除文件上传外，请求和响应均使用 `application/json`
- 文件上传：`multipart/form-data`
- 认证：除健康检查、注册和登录外，受保护接口使用 `Authorization: Bearer <token>`
- 时间格式：ISO 8601 字符串
- 检索分数：启用 rerank 时返回 0 到 1 的证据相关度，默认阈值为 `0.55`；关闭 rerank 时为 `[-1, 1]` 的余弦相似度

通用错误响应：

```json
{
  "detail": "错误说明"
}
```

## 2. 接口总览

| 模块     | 方法   | 路径                                             | 说明                   |
| -------- | ------ | ------------------------------------------------ | ---------------------- |
| 健康检查 | GET    | `/api/health/live`                               | 检查 API 进程存活      |
| 健康检查 | GET    | `/api/health/ready`                              | 检查 MySQL、Chroma 就绪 |
| 健康检查 | GET    | `/api/health`                                    | 兼容的就绪检查别名     |
| 认证     | POST   | `/api/auth/register`                             | 用户注册               |
| 认证     | POST   | `/api/auth/login`                                | 用户登录               |
| 认证     | POST   | `/api/auth/logout`                               | 用户退出               |
| 认证     | GET    | `/api/auth/me`                                   | 获取当前用户           |
| 个人模型 | GET    | `/api/me/llm-configs`                            | 查询配置与当前模型     |
| 个人模型 | POST   | `/api/me/llm-configs`                            | 新增个人模型配置       |
| 个人模型 | PUT    | `/api/me/llm-configs/{config_id}`                | 更新个人模型配置       |
| 个人模型 | DELETE | `/api/me/llm-configs/{config_id}`                | 删除个人模型配置       |
| 个人模型 | POST   | `/api/me/llm-configs/{config_id}/test`           | 测试模型连接           |
| 个人模型 | POST   | `/api/me/llm-configs/{config_id}/activate`       | 启用个人模型配置       |
| 个人模型 | POST   | `/api/me/llm-configs/use-system-default`         | 切换到系统默认模型     |
| 知识库   | GET    | `/api/knowledge-bases`                           | 查询知识库列表         |
| 知识库   | POST   | `/api/knowledge-bases`                           | 创建知识库             |
| 知识库   | PATCH  | `/api/knowledge-bases/{knowledge_base_id}`       | 更新知识库             |
| 知识库   | DELETE | `/api/knowledge-bases/{knowledge_base_id}`       | 删除知识库             |
| 文档     | GET    | `/api/documents`                                 | 查询文档列表           |
| 文档     | POST   | `/api/documents/upload`                          | 上传文档               |
| 文档     | GET    | `/api/documents/{document_id}`                   | 查询文档详情           |
| 文档     | GET    | `/api/documents/{document_id}/content`           | 内联读取原始文档       |
| 文档     | DELETE | `/api/documents/{document_id}`                   | 删除文档和向量索引     |
| 文档     | POST   | `/api/documents/{document_id}/reindex`           | 重新入库文档           |
| 文档     | POST   | `/api/documents/{document_id}/cancel`            | 取消文档处理任务       |
| 文档     | PATCH  | `/api/documents/{document_id}/knowledge-base`    | 在本人私人库间移动文档 |
| 文档     | GET    | `/api/documents/{document_id}/chunks`            | 查询文档片段           |
| 文档     | GET    | `/api/documents/{document_id}/chunks/{chunk_id}` | 按文档定位查询单个片段 |
| 文档     | GET    | `/api/chunks/{chunk_id}`                         | 查询单个片段           |
| 检索     | POST   | `/api/search`                                    | 语义检索或文档直接检索 |
| 问答     | POST   | `/api/chat`                                      | RAG 问答               |
| 问答     | POST   | `/api/chat/stream`                               | SSE 流式 RAG 问答      |
| 知识地图 | POST   | `/api/mind-maps/generate`                        | 同步生成地图（调试）   |
| 知识地图 | POST   | `/api/mind-maps/jobs`                            | 创建后台生成任务       |
| 知识地图 | GET    | `/api/mind-maps/jobs/{job_id}`                   | 查询任务进度和结果     |
| 知识地图 | POST   | `/api/mind-maps/jobs/{job_id}/cancel`            | 取消后台生成任务       |
| 知识地图 | POST   | `/api/mind-maps/ask`                             | 针对节点来源提问       |
| 知识地图 | POST   | `/api/mind-maps/expand`                          | 根据来源扩展节点       |
| 知识地图 | GET    | `/api/mind-maps/histories`                       | 查询地图历史           |
| 知识地图 | POST   | `/api/mind-maps/histories`                       | 保存地图历史           |
| 知识地图 | GET    | `/api/mind-maps/histories/{history_id}`          | 查询地图历史详情       |
| 知识地图 | PUT    | `/api/mind-maps/histories/{history_id}`          | 更新地图和画布状态     |
| 知识地图 | DELETE | `/api/mind-maps/histories/{history_id}`          | 删除地图历史           |
| AI 出题  | POST   | `/api/quizzes/sessions`                         | 创建临时出题会话       |
| AI 出题  | GET    | `/api/quizzes/sessions/{session_id}`            | 查询进度或获取题目     |
| AI 出题  | POST   | `/api/quizzes/sessions/{session_id}/submit`     | 提交、评分并清理会话   |
| AI 出题  | DELETE | `/api/quizzes/sessions/{session_id}`            | 放弃并清理临时会话     |
| 历史     | GET    | `/api/qa-records`                                | 查询问答历史           |
| 历史     | GET    | `/api/qa-records/{qa_record_id}`                 | 查询问答详情           |
| 反馈     | POST   | `/api/qa-records/{qa_record_id}/feedback`        | 提交回答反馈           |
| 反馈     | GET    | `/api/qa-records/{qa_record_id}/feedback`        | 查询本人已提交反馈     |
| 管理     | GET    | `/api/admin/overview`                            | 就绪状态与异常概览     |
| 管理     | GET    | `/api/admin/users`                               | 筛选用户列表           |
| 管理     | PATCH  | `/api/admin/users/{user_id}/status`              | 启用或停用用户         |
| 管理     | GET    | `/api/admin/documents`                           | 脱敏查询文档与任务     |
| 管理     | GET    | `/api/admin/feedbacks`                           | 筛选反馈和问答详情     |

健康检查不调用在线 LLM 或 Embedding。`/health/live` 只要进程可响应就返回 `200`；`/health/ready` 和兼容路径 `/health` 会分别探测 MySQL 与 Chroma，任一不可用时返回 `503` 和具体 `checks`。Docker 后端健康检查使用 readiness。

## 3. 认证接口

### 3.1 用户注册

```text
POST /api/auth/register
```

请求：

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "password123"
}
```

响应：

```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "role": "user",
  "status": "active"
}
```

### 3.2 用户登录

```text
POST /api/auth/login
```

请求：

```json
{
  "username": "alice",
  "password": "password123"
}
```

响应：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

### 3.3 获取当前用户

```text
GET /api/auth/me
```

响应字段同用户注册响应。

### 3.4 用户退出

```text
POST /api/auth/logout
```

退出会持久化递增当前用户的 `token_version`。本次登录签发的 JWT 以及同版本的其他 JWT 会立即失效，再次访问受保护接口返回 `401`；重新登录后获取新版本 Token。

## 3.5 个人大模型配置

个人模型接口均要求 JWT，且只能访问当前用户自己的配置。新增配置请求包含 `name`、`provider`、
`base_url`、`model` 和 `api_key`；查询响应仅返回 `masked_api_key`，不会返回完整密钥。

配置需要先调用测试接口并成功，才能启用。测试失败时返回受控错误并保存 `test_status=failed`：

- API Key 无效或无权限：提示认证失败。
- 上游连接或读取超时：提示连接超时。
- 模型名错误或无权使用模型：提示模型不存在或无权访问。
- HTTP 404 但供应商未提供明确错误码：提示检查模型名称与 API Base URL。

当前用户启用个人配置后，RAG 问答、SSE 和知识地图都传递同一个用户运行时配置；个人模型调用失败时
不会自动使用系统模型。停用或删除个人配置后使用 `.env` 中的系统模型。Embedding 不属于 BYOK 范围。
AI 出题同样复用用户运行时配置解析。个人配置启用时，首次出题和结构重试均使用同一配置且失败不回退；没有个人配置时使用系统模型。

## 4. 知识库接口

### 4.1 创建知识库

```text
POST /api/knowledge-bases
```

请求：

```json
{
  "name": "操作系统复习资料",
  "description": "课程讲义、实验说明和复习笔记",
  "visibility": "private",
  "can_read": true,
  "can_upload": true,
  "can_manage": true,
  "can_edit": true,
  "can_delete": true
}
```

响应：

```json
{
  "id": 1,
  "owner_id": 1,
  "name": "操作系统复习资料",
  "description": "课程讲义、实验说明和复习笔记",
  "visibility": "private"
}
```

### 4.2 查询知识库列表

```text
GET /api/knowledge-bases
```

响应：

```json
[
  {
    "id": 42,
    "owner_id": null,
    "name": "公共知识库",
    "description": "所有登录用户共同维护和检索的公共计算机知识资料。",
    "visibility": "public",
    "can_read": true,
    "can_upload": true,
    "can_manage": false,
    "can_edit": false,
    "can_delete": false
  },
  {
    "id": 1,
    "owner_id": 1,
    "name": "操作系统复习资料",
    "description": "课程讲义、实验说明和复习笔记",
    "visibility": "private",
    "can_read": true,
    "can_upload": true,
    "can_manage": true,
    "can_edit": true,
    "can_delete": true
  }
]
```

列表始终返回当前用户的私人知识库和全站唯一公共知识库，公共库 ID 由数据库动态生成。客户端必须使用
返回值，不能硬编码 `1`。普通用户可读写公共资料但不能编辑或删除公共库；管理员的公共库
`can_manage/can_edit` 为 `true`，`can_delete` 仍为 `false`。

### 4.3 更新和删除知识库

```text
PATCH  /api/knowledge-bases/{knowledge_base_id}
DELETE /api/knowledge-bases/{knowledge_base_id}
```

- 私人库只允许所有者更新和删除。
- 公共库只允许管理员更新名称和描述。
- 公共库对普通用户更新返回 `403`，对任何角色删除都返回 `403`。

## 5. 文档接口

### 5.1 上传文档

```text
POST /api/documents/upload
```

请求类型：`multipart/form-data`

| 字段                | 类型   | 必填 | 说明                            |
| ------------------- | ------ | ---- | ------------------------------- |
| `knowledge_base_id` | number | 是   | 所属知识库编号                  |
| `file`              | file   | 是   | PDF、DOCX、Markdown、TXT 等资料 |

响应：

```json
{
  "id": 1,
  "knowledge_base_id": 1,
  "owner_id": 1,
  "file_name": "操作系统笔记.pdf",
  "file_type": "pdf",
  "file_size": 204800,
  "parse_status": "pending",
  "error_message": null,
  "chunk_count": 0,
  "uploader_username": "alice",
  "knowledge_base_visibility": "public",
  "can_manage": true
}
```

当后台解析、Embedding 或向量入库失败时，`parse_status` 为 `failed`，
`error_message` 返回可直接展示给用户的失败原因；其他状态下该字段为 `null`。

后端不会只相信扩展名：PDF 必须包含有效文件头，DOCX 必须包含标准文档结构，TXT/Markdown
不得伪装为二进制文件。DOCX 解压体积、解析字符数和切片数量分别受配置上限约束；
Embedding 按批次调用。超出限制时返回受控的 `400` 或 `413`，不会进入后台解析队列。

所有登录用户都可以向公共库上传。公共文档对全部登录用户可见，`uploader_username` 标识上传者；
只有上传者和管理员获得 `can_manage=true`，并可调用取消、重建和删除接口。私人文档仍只对所有者可见。

已有 MySQL 数据库需要在升级代码后执行一次：

```sql
ALTER TABLE documents
ADD COLUMN error_message VARCHAR(500) NULL AFTER parse_status;
```

新建数据库会由 `database/schema.sql` 自动创建该字段，不需要重复执行。

### 5.2 查询文档列表

```text
GET /api/documents?knowledge_base_id=1&parse_status=completed
```

查询参数：

| 参数                | 必填 | 说明                                                                  |
| ------------------- | ---- | --------------------------------------------------------------------- |
| `knowledge_base_id` | 否   | 按知识库过滤                                                          |
| `parse_status`      | 否   | 按处理状态过滤，取值为 `pending`、`processing`、`completed`、`failed`、`cancelled` |

响应为 `DocumentRead[]`，字段同上传文档响应。

### 5.3 查询文档详情和原文件

```text
GET /api/documents/{document_id}
GET /api/documents/{document_id}/content
```

第一个接口返回 `DocumentRead`。第二个接口校验文档归属后以内联方式返回原文件，支持 PDF、DOCX、Markdown 和 TXT；原文件不存在时返回 `404`。前端文档预览页使用该接口，不应绕过 JWT 直接访问上传目录。

### 5.4 重新入库文档

```text
POST /api/documents/{document_id}/reindex
```

响应：

```json
{
  "status": "processing",
  "message": "Document 1 entered the ingest pipeline."
}
```

同一文档处于 `pending` 或 `processing` 时再次重建返回 `409`。重建会先完成新内容解析和向量化，再原子替换 MySQL 片段并清理旧向量；失败或取消时保留上一次已完成索引。

### 5.5 取消文档处理

```text
POST /api/documents/{document_id}/cancel
```

仅 `pending` 或 `processing` 状态可以取消，成功后状态变为 `cancelled`；其他状态返回 `409`。后端重启会把中断的 `processing` 文档恢复为 `pending` 并重新入队。

### 5.6 查询文档片段

```text
GET /api/documents/{document_id}/chunks
GET /api/documents/{document_id}/chunks/{chunk_id}
GET /api/chunks/{chunk_id}
```

片段响应：

```json
{
  "id": 10,
  "document_id": 1,
  "knowledge_base_id": 1,
  "chunk_index": 3,
  "chunk_text": "进程拥有独立地址空间，线程共享进程资源……",
  "page_no": 12,
  "start_offset": 1800,
  "end_offset": 2100,
  "vector_id": "kb1-doc1-chunk3"
}
```

### 5.7 移动私人文档

```text
PATCH /api/documents/{document_id}/knowledge-base
```

请求：

```json
{
  "knowledge_base_id": 2
}
```

仅文档所有者可以移动 `completed` 状态的私人文档，源库和目标库都必须是当前用户的私人知识库；公共资料、跨用户目标和私人/公共范围互转返回 `403` 或 `409`。成功响应为更新后的 `DocumentRead`。

后端在同一事务中更新 `documents`、`document_chunks` 和文档级知识地图归属，再更新 Chroma metadata。Chroma 或数据库提交失败时执行数据库回滚和向量 metadata 补偿；`qa_records` 与 `qa_sources` 历史快照不随文档移动而改变。

## 6. 检索接口

```text
POST /api/search
```

请求：

```json
{
  "knowledge_base_id": 1,
  "query": "进程和线程有什么区别？",
  "top_k": 4,
  "score_threshold": 0.55,
  "rerank_top_n": 2,
  "enable_rewrite": true,
  "enable_rerank": true
}
```

响应：

```json
{
  "knowledge_base_id": 1,
  "query": "进程和线程有什么区别？",
  "rewritten_query": "操作系统中进程与线程的区别是什么？",
  "message": null,
  "results": [
    {
      "document_id": 1,
      "chunk_id": 10,
      "file_name": "操作系统笔记.pdf",
      "chunk_index": 3,
      "page_no": 12,
      "score": 0.864321,
      "source_text": "进程拥有独立地址空间，线程共享进程资源……",
      "jump_url": "/documents/1/chunks/10"
    }
  ]
}
```

## 7. RAG 问答接口

```text
POST /api/chat
```

请求字段与检索接口保持一致，将 `query` 改为 `question`：

```json
{
  "knowledge_base_id": 1,
  "question": "操作系统中的进程和线程有什么区别？",
  "top_k": 4,
  "score_threshold": 0.55,
  "rerank_top_n": 2,
  "enable_rewrite": true,
  "enable_rerank": true
}
```

处理流程：

1. 根据上下文可选重写问题。
2. 调用 Embedding API 生成问题向量。
3. 从 Chroma 取得至少 12 个 Dense 候选，同时从 MySQL 片段取得 12 个 BM25 候选。
4. 通过 RRF 融合为最多 20 个候选，在线 reranker 按直接证据相关性重新评分。
5. 按 `score_threshold=0.55` 过滤后，默认保留前 `rerank_top_n=2` 个片段进入 prompt；reranker 故障时按服务器配置降级到 `0.45` 向量阈值。
6. 调用在线 LLM API 生成回答。
7. 将回答写入 `qa_records`，来源写入 `qa_sources`。

文档入库和问题检索均强制使用在线 Embedding API，不提供本地向量降级。
服务端必须配置 `EMBEDDING_API_KEY` 和 `EMBEDDING_MODEL`；连接失败、认证失败或
响应向量无效时，本次入库或检索立即失败并返回明确错误，不会写入模拟向量。

响应：

```json
{
  "qa_record_id": 1001,
  "knowledge_base_id": 1,
  "question": "操作系统中的进程和线程有什么区别？",
  "rewritten_question": "操作系统中进程与线程的区别是什么？",
  "answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位……",
  "sources": [
    {
      "document_id": 1,
      "chunk_id": 10,
      "file_name": "操作系统笔记.pdf",
      "chunk_index": 3,
      "page_no": 12,
      "score": 0.864321,
      "source_text": "进程拥有独立地址空间，线程共享进程资源……",
      "jump_url": "/documents/1/chunks/10"
    }
  ]
}
```

### 7.1 SSE 流式问答

```text
POST /api/chat/stream
Accept: text/event-stream
```

请求体与 `POST /api/chat` 完全相同。响应使用 Server-Sent Events（SSE），响应头为
`Content-Type: text/event-stream`，事件之间使用空行分隔：

```text
event: meta
data: {"knowledge_base_id":1,"question":"...","rewritten_question":null,"sources":[...]}

event: token
data: {"delta":"进程是"}

event: token
data: {"delta":"资源分配的基本单位。"}

event: done
data: {"qa_record_id":1002,"knowledge_base_id":1,"question":"...","rewritten_question":null,"answer":"...","sources":[...]}
```

事件约定：

1. `meta`：检索完成后发送，包含改写问题和来源列表，便于前端先展示引用。
2. `token`：每个事件的 `delta` 是回答的一段文本，前端按顺序拼接即可。
3. `done`：回答完成并成功保存问答历史后发送，字段与普通 `/api/chat` 响应一致。
4. `error`：处理失败时发送，包含 `status_code` 和 `detail`；流式响应建立后 HTTP 状态通常已经是 `200`，客户端必须同时处理该事件。

前端通过 Nginx 代理时必须关闭响应缓冲；本项目的 `frontend/nginx.conf` 已配置
`proxy_buffering off`、`proxy_cache off` 和 960 秒读取超时。

## 8. 知识地图接口

知识地图必须配置在线 LLM。前端正式流程使用后台任务接口，避免长时间同步请求阻塞页面；同步接口主要用于 Swagger 调试和后端联调。

### 8.1 创建并查询生成任务

```text
POST /api/mind-maps/jobs
GET /api/mind-maps/jobs/{job_id}
POST /api/mind-maps/jobs/{job_id}/cancel
```

创建请求：

```json
{
  "knowledge_base_id": 1,
  "document_id": null,
  "max_depth": 3,
  "max_nodes": 38
}
```

- `document_id=null` 表示使用知识库内全部已完成解析的文档。
- 私人库只使用当前用户文档；公共库使用同一公共库内所有上传者的文档。
- `max_depth` 范围为 2 至 4。
- `max_nodes` 范围为 8 至 60。

创建成功返回 `202 Accepted`：

```json
{
  "job_id": "e1f0b8f4d6d84dbe8db3f8cf15a1f08b",
  "status": "queued",
  "stage": "queued",
  "progress": 0,
  "message": "任务已创建，正在等待处理",
  "result": null,
  "error_message": null,
  "created_at": "2026-07-13T10:00:00",
  "updated_at": "2026-07-13T10:00:00"
}
```

任务状态为 `queued`、`processing`、`completed`、`failed` 或 `cancelled`。处理中可出现 `collecting`、`preparing`、`extracting`、`merging`、`validating` 和 `assembling` 阶段。完成后 `result` 为 `MindMapResponse`；失败时读取 `error_message`。

同一用户对相同知识库和文档范围重复创建活动任务时返回原任务，避免重复消耗模型额度。
取消接口只接受 `queued` 或 `processing` 任务；任务结束后再次取消返回 `409`。

`GET /api/mind-maps/histories` 不传 `knowledge_base_id` 时返回当前用户全部知识库的地图摘要，
前端据此统一展示和筛选，不依赖当前生成范围。

同步接口使用同一请求模型：

```text
POST /api/mind-maps/generate
```

### 8.2 地图节点结构

`MindMapResponse.root` 是递归节点：

```json
{
  "id": "mind-node-0-0",
  "title": "进程与线程",
  "summary": "说明两种并发抽象的定义、作用和关系。",
  "node_type": "concept",
  "key_points": ["进程拥有独立资源", "线程共享进程资源"],
  "learning_tip": "画表比较资源、调度和切换成本",
  "depth": 2,
  "sources": [
    {
      "chunk_id": 10,
      "document_id": 1,
      "file_name": "操作系统笔记.pdf",
      "chunk_index": 3,
      "page_no": 12,
      "source_text": "进程拥有独立地址空间……",
      "jump_url": "/documents/1/chunks/10"
    }
  ],
  "children": []
}
```

`node_type` 只能为 `overview`、`chapter`、`concept` 或 `detail`；`key_points` 最多 3 条。新增字段都有兼容默认值，旧历史 JSON 可以继续读取。

### 8.3 节点提问

```text
POST /api/mind-maps/ask
```

```json
{
  "knowledge_base_id": 1,
  "node_title": "进程与线程",
  "question": "两者最容易混淆的地方是什么？",
  "source_chunk_ids": [10, 11]
}
```

后端最多接受 8 个已完成解析片段。私人库要求片段属于当前用户和当前知识库；公共库允许同一公共库
中不同上传者的片段。响应包含回答和实际使用的来源列表。

### 8.4 节点扩展

```text
POST /api/mind-maps/expand
```

```json
{
  "knowledge_base_id": 1,
  "node_title": "进程与线程",
  "node_summary": "并发执行的基本抽象",
  "source_chunk_ids": [10, 11],
  "child_count": 4
}
```

`child_count` 范围为 2 至 8。后端根据给定真实来源生成子结构，并返回一个 `MindMapNode`。无效来源返回 `404`；缺少 LLM 配置返回 `503`；模型未返回有效 JSON 返回 `502`。

### 8.5 地图历史

```text
GET    /api/mind-maps/histories?knowledge_base_id=1
POST   /api/mind-maps/histories
GET    /api/mind-maps/histories/{history_id}
PUT    /api/mind-maps/histories/{history_id}
DELETE /api/mind-maps/histories/{history_id}
```

- 列表响应不携带完整 `result`，详情响应包含完整地图。
- 创建和更新时可传 `view_state`，用于保存节点坐标及折叠状态。
- 私人 `document_id` 必须属于当前用户和同一知识库；公共文档允许所有登录用户使用。
- 自动生成成功后后端会保存一个历史版本。
- 节点掌握状态当前保存在浏览器 `localStorage`，不属于历史接口字段。

## 9. AI 出题接口

AI 出题使用短期后台会话，不保存历史试卷或答题记录。所有接口都要求 JWT，并把不存在和不属于当前用户的会话统一返回为 `404`。

### 9.1 创建出题会话

```text
POST /api/quizzes/sessions
```

```json
{
  "knowledge_base_ids": [3, 9],
  "question_count": 5,
  "difficulty": "intermediate",
  "question_types": ["single_choice", "multiple_choice", "true_false"],
  "random_mix": true,
  "topic": "进程与线程",
  "show_explanations_and_sources": true
}
```

- `knowledge_base_ids` 必须包含 1 至 5 个不重复且当前用户可读的私人/公共知识库。
- `question_count` 范围为 5 至 20；难度为 `basic`、`intermediate` 或 `challenge`。
- 题型可选 `single_choice`、`multiple_choice`、`true_false`、`fill_blank`、`short_answer` 和 `scenario`。
- 随机混合模式下 `question_types=[]` 表示使用全部六类题型；显式传入时至少选择两种。指定模式至少选择一种，且生成结果覆盖所选题型。
- 任一知识库没有已解析资料或总内容不足时返回 `409` 和明确提示；越权知识库返回 `404`。

成功返回 `202 Accepted` 和 `QuizSessionRead`，初始状态为 `queued`。状态为 `queued`、`processing`、`ready` 或 `failed`，进度范围为 0 至 100。

### 9.2 查询进度和题目

```text
GET /api/quizzes/sessions/{session_id}
```

任务未完成时 `questions` 为空；完成后题目示例：

```json
{
  "id": 81,
  "order_no": 1,
  "question_type": "single_choice",
  "prompt": "根据资料，处理器调度的基本单位是什么？",
  "options": [
    {"id": "A", "text": "线程"},
    {"id": "B", "text": "文件"}
  ],
  "source_count": 1
}
```

该响应模型没有正确答案、标准答案、参考答案、解析和来源正文，不能通过未提交接口提前取得答案。

### 9.3 提交并评分

```text
POST /api/quizzes/sessions/{session_id}/submit
```

```json
{
  "answers": [
    {"question_id": 81, "answer": "A"},
    {"question_id": 82, "answer": ["A", "C"]},
    {"question_id": 83, "answer": true},
    {"question_id": 84, "answer": "进程控制块"}
  ]
}
```

单选、多选、判断和填空题返回 `is_correct=true/false`；填空题匹配标准答案，或要求答案包含全部关键词。简答和情景题返回 `is_correct=null` 与 `reference_answer`，不强制精确自动评分。启用显示选项时，每题同时返回解析、来源快照和 `/documents/{document_id}/chunks/{chunk_id}` 跳转地址。

响应返回后，服务端立即删除本会话及全部题目。因此再次查询或提交同一 `session_id` 返回 `404`。

### 9.4 放弃会话

```text
DELETE /api/quizzes/sessions/{session_id}
```

用于取消生成或离开未完成练习。未主动放弃的会话到达 `expires_at` 后由后台清理任务删除。

## 10. 历史与反馈接口

### 10.1 查询问答历史

```text
GET /api/qa-records?knowledge_base_id=1
```

响应：

```json
[
  {
    "id": 1001,
    "user_id": 1,
    "knowledge_base_id": 1,
    "question": "操作系统中的进程和线程有什么区别？",
    "rewritten_question": "操作系统中进程与线程的区别是什么？",
    "answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位……",
    "source_count": 1,
    "sources": [],
    "created_at": "2026-07-08T10:00:00"
  }
]
```

### 10.2 查询问答详情

```text
GET /api/qa-records/{qa_record_id}
```

响应为单个 `QaRecordRead`，应包含完整 `sources` 列表。

历史来源中的 `document_id` 和 `chunk_id` 可以为空。删除原文后仍返回文件名、片段序号、页码、分数和文本快照，但 `jump_url` 为 `null`。

### 10.3 提交反馈

```text
POST /api/qa-records/{qa_record_id}/feedback
```

请求：

```json
{
  "rating": 5,
  "comment": "回答依据清楚，来源可核对。"
}
```

查询本人对该回答的已提交反馈：

```text
GET /api/qa-records/{qa_record_id}/feedback
```

未提交时返回 `200` 和 `null`；已提交时返回同一 `FeedbackRead`。前端在回答结果和历史详情中据此恢复只读状态，评分和文字反馈提交后不可修改。

后端只允许当前用户对本人问答记录提交反馈，并写入 `feedbacks` 表。同一用户对同一问答只能提交一次，重复提交返回 `409`；不存在或不属于当前用户的问答返回 `404`。

响应：

```json
{
  "id": 1,
  "qa_record_id": 1001,
  "user_id": 1,
  "rating": 5,
  "comment": "回答依据清楚，来源可核对。",
  "created_at": "2026-07-08T10:05:00"
}
```

### 10.4 管理员查询反馈

```text
GET /api/admin/feedbacks?rating=5&user_id=1&knowledge_base_id=1
```

仅 `admin` 角色可以访问，普通用户返回 `403`。`rating`、`user_id` 和 `knowledge_base_id` 均为可选筛选条件，响应按创建时间和编号倒序排列。公共库反馈包含知识库名称、问题、回答和来源数量；私人库反馈设置 `content_redacted=true`，并将知识库名称、问题和回答置为 `null`，只展示用户主动提交的评分和文字说明。

### 10.5 管理员中心

```text
GET   /api/admin/overview
GET   /api/admin/users?query=&role=&status=
PATCH /api/admin/users/{user_id}/status
GET   /api/admin/documents?query=&owner_id=&knowledge_base_id=&parse_status=&visibility=
```

- `overview` 返回用户、文档、反馈统计，MySQL/Chroma 就绪状态，以及最近失败任务的安全摘要；私人文档、私人知识地图和出题任务的具体错误会被隐藏。
- 用户状态请求体为 `{"status":"active"}` 或 `{"status":"disabled"}`。管理员不能停用自己或最后一个有效管理员；停用管理员时会锁定有效管理员集合，避免并发操作留下零个可用管理员。停用会递增目标用户的 `token_version`，使现有 JWT 失效。
- 文档查询对公共资料返回文件名、知识库名称和管理权限；私人资料只返回脱敏编号、所有者和状态，具体错误使用固定脱敏文案，且 `can_manage=false`，不能借管理员接口读取或管理私人内容。

## 11. 字段一致性要求

| API 字段               | MySQL 字段或 Chroma metadata                                         | 说明                                     |
| ---------------------- | -------------------------------------------------------------------- | ---------------------------------------- |
| `knowledge_base_id`    | `knowledge_bases.id`、`documents.knowledge_base_id`、Chroma metadata | 限定检索和问答范围                       |
| `owner_id` / `user_id` | `users.id`、Chroma metadata `owner_id`                               | 私人库用于隔离；公共库用于标识上传者     |
| `parse_status`         | `documents.parse_status`                                             | 文档处理状态                             |
| `chunk_id`             | `document_chunks.id`、Chroma metadata `chunk_id`                     | 引用跳转和 MySQL 反查                    |
| `vector_id`            | `document_chunks.vector_id`、Chroma id                               | 向量记录唯一编号                         |
| `qa_record_id`         | `qa_records.id`、`qa_sources.qa_record_id`                           | 问答历史和来源引用关联                   |
| `source_text`          | `qa_sources.source_text`、Chroma document                            | 来源片段快照                             |
| `score`                | `qa_sources.score`                                                   | 正常链路为 0 到 1 的 reranker 证据相关度；降级或关闭 rerank 时为 `[-1, 1]` 的向量相似度 |
| `job_id`               | `mind_map_jobs.id`                                                   | 地图后台任务编号                         |
| `history_id`           | `mind_map_histories.id`                                              | 地图历史版本编号                         |
| `node_type`            | `mind_map_histories.result_json`                                     | 地图节点类型，不单独占数据库列           |
| `session_id`           | `quiz_sessions.id`                                                   | AI 出题临时会话编号                      |
| `question_id`          | `quiz_questions.id`                                                  | 临时题目编号，随会话级联删除             |

后端实现位于 `backend/app/api/routes.py`、`backend/app/services/` 和 `backend/app/schemas/`。当前已接入可撤销 JWT、唯一全局公共知识库、私人隔离、管理员中心、MySQL、Chroma、Embedding、在线 LLM、问答历史、反馈闭环、可靠文档任务、私人文档迁移、知识地图和 AI 出题。真实 Docker 已验证默认私人库、公共上传确认、语义检索、反馈详情、管理员隐私边界，以及文档迁移后的 MySQL/Chroma/历史快照一致性；固定测试集、模型质量与耗时记录仍需持续完善。

---

文档状态：已按 Issue #28 角色流程补全同步，更新时间为 2026-07-18。当前限制见 [已知问题与后续计划](已知问题与后续计划.md)。

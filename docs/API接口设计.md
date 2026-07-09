# CodeMind API 接口设计

## 1. 通用约定

- 基础路径：`/api`
- 数据格式：除文件上传外，请求和响应均使用 `application/json`
- 文件上传：`multipart/form-data`
- 正式认证：受保护接口使用 `Authorization: Bearer <token>`
- 当前后端参考代码：临时使用 `X-User-Id` 表示当前用户，后续由 JWT 鉴权替换
- 时间格式：ISO 8601 字符串
- 相似度分数：余弦相似度范围为 `[-1, 1]`，默认过滤阈值为 `0.77`

通用错误响应：

```json
{
  "detail": "错误说明"
}
```

## 2. 接口总览

| 模块     | 方法   | 路径                                             | 说明                   |
| -------- | ------ | ------------------------------------------------ | ---------------------- |
| 健康检查 | GET    | `/api/health`                                    | 检查后端服务状态       |
| 认证     | POST   | `/api/auth/register`                             | 用户注册               |
| 认证     | POST   | `/api/auth/login`                                | 用户登录               |
| 认证     | POST   | `/api/auth/logout`                               | 用户退出               |
| 认证     | GET    | `/api/auth/me`                                   | 获取当前用户           |
| 知识库   | GET    | `/api/knowledge-bases`                           | 查询知识库列表         |
| 知识库   | POST   | `/api/knowledge-bases`                           | 创建知识库             |
| 知识库   | PATCH  | `/api/knowledge-bases/{knowledge_base_id}`       | 更新知识库             |
| 知识库   | DELETE | `/api/knowledge-bases/{knowledge_base_id}`       | 删除知识库             |
| 文档     | GET    | `/api/documents`                                 | 查询文档列表           |
| 文档     | POST   | `/api/documents/upload`                          | 上传文档               |
| 文档     | GET    | `/api/documents/{document_id}`                   | 查询文档详情           |
| 文档     | DELETE | `/api/documents/{document_id}`                   | 删除文档和向量索引     |
| 文档     | POST   | `/api/documents/{document_id}/reindex`           | 重新入库文档           |
| 文档     | GET    | `/api/documents/{document_id}/chunks`            | 查询文档片段           |
| 文档     | GET    | `/api/documents/{document_id}/chunks/{chunk_id}` | 按文档定位查询单个片段 |
| 文档     | GET    | `/api/chunks/{chunk_id}`                         | 查询单个片段           |
| 检索     | POST   | `/api/search`                                    | 语义检索或文档直接检索 |
| 问答     | POST   | `/api/chat`                                      | RAG 问答               |
| 历史     | GET    | `/api/qa-records`                                | 查询问答历史           |
| 历史     | GET    | `/api/qa-records/{qa_record_id}`                 | 查询问答详情           |
| 反馈     | POST   | `/api/qa-records/{qa_record_id}/feedback`        | 提交回答反馈           |
| 管理     | GET    | `/api/admin/feedbacks`                           | 管理端查看反馈         |

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
  "visibility": "private"
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
    "id": 1,
    "owner_id": 1,
    "name": "操作系统复习资料",
    "description": "课程讲义、实验说明和复习笔记",
    "visibility": "private"
  }
]
```

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
  "chunk_count": 0
}
```

### 5.2 查询文档列表

```text
GET /api/documents?knowledge_base_id=1&parse_status=completed
```

查询参数：

| 参数                | 必填 | 说明                                                                  |
| ------------------- | ---- | --------------------------------------------------------------------- |
| `knowledge_base_id` | 否   | 按知识库过滤                                                          |
| `parse_status`      | 否   | 按处理状态过滤，取值为 `pending`、`processing`、`completed`、`failed` |

响应为 `DocumentRead[]`，字段同上传文档响应。

### 5.3 重新入库文档

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

### 5.4 查询文档片段

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
  "score_threshold": 0.77,
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
  "score_threshold": 0.77,
  "rerank_top_n": 2,
  "enable_rewrite": true,
  "enable_rerank": true
}
```

处理流程：

1. 根据上下文可选重写问题。
2. 调用 Embedding API 生成问题向量。
3. 在 Chroma 中召回 `top_k=4` 个候选片段。
4. 按 `score_threshold=0.77` 过滤低相似度片段。
5. 可选 rerank，并默认保留前 `rerank_top_n=2` 个片段进入 prompt。
6. 调用在线 LLM API 生成回答。
7. 将回答写入 `qa_records`，来源写入 `qa_sources`。

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

## 8. 历史与反馈接口

### 8.1 查询问答历史

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

### 8.2 查询问答详情

```text
GET /api/qa-records/{qa_record_id}
```

响应为单个 `QaRecordRead`，应包含完整 `sources` 列表。

### 8.3 提交反馈

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

## 9. 字段一致性要求

| API 字段               | MySQL 字段或 Chroma metadata                                         | 说明                                     |
| ---------------------- | -------------------------------------------------------------------- | ---------------------------------------- |
| `knowledge_base_id`    | `knowledge_bases.id`、`documents.knowledge_base_id`、Chroma metadata | 限定检索和问答范围                       |
| `owner_id` / `user_id` | `users.id`、Chroma metadata `owner_id`                               | 用于权限隔离                             |
| `parse_status`         | `documents.parse_status`                                             | 文档处理状态                             |
| `chunk_id`             | `document_chunks.id`、Chroma metadata `chunk_id`                     | 引用跳转和 MySQL 反查                    |
| `vector_id`            | `document_chunks.vector_id`、Chroma id                               | 向量记录唯一编号                         |
| `qa_record_id`         | `qa_records.id`、`qa_sources.qa_record_id`                           | 问答历史和来源引用关联                   |
| `source_text`          | `qa_sources.source_text`、Chroma document                            | 来源片段快照                             |
| `score`                | `qa_sources.score`                                                   | 检索相似度或 rerank 分数，范围 `[-1, 1]` |

后端参考代码位于 `backend/app/api/routes.py` 和 `backend/app/schemas/contracts.py`。当前代码只提供接口合同与占位响应，真实的数据库访问、Chroma 调用、Embedding、rerank 和 LLM 调用由后端开发人员继续实现。

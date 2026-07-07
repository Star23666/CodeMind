# CodeMind API 接口设计

## 1. 健康检查

```text
GET /api/health
```

用于检查后端服务是否正常运行。

## 2. 文档上传

```text
POST /api/documents/upload
```

请求类型：`multipart/form-data`

字段：

```text
file: 上传文件
```

## 3. 文档列表

```text
GET /api/documents
```

返回已上传文档列表和处理状态。

## 4. 文档删除

```text
DELETE /api/documents/{document_id}
```

删除文档记录及对应向量索引。

## 5. RAG 问答

```text
POST /api/chat
```

请求示例：

```json
{
  "question": "操作系统中的进程和线程有什么区别？",
  "session_id": 1,
  "top_k": 5
}
```

响应示例：

```json
{
  "answer": "进程是资源分配的基本单位，线程是 CPU 调度的基本单位……",
  "sources": [
    {
      "document_id": 1,
      "document_name": "操作系统笔记.pdf",
      "chunk_index": 3,
      "page_number": 12,
      "content": "进程拥有独立地址空间，线程共享进程资源……"
    }
  ]
}
```


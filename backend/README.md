# CodeMind Backend

FastAPI 后端负责提供文档管理、RAG 问答、问答历史和系统管理接口。

## 开发命令

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认服务地址：

```text
http://localhost:8000
```

接口文档地址：

```text
http://localhost:8000/docs
```


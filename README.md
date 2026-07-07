# CodeMind

CodeMind 是一个面向计算机知识学习场景的 RAG 知识库问答系统。系统支持导入计算机相关资料，构建向量知识库，并基于用户问题检索相关知识片段，结合在线大模型 API 生成带来源依据的回答。

## 技术栈

- 前端：Vue 3 + Vite
- 后端：FastAPI
- 业务数据库：MySQL
- 向量数据库：Chroma
- 大模型能力：在线 LLM API + Embedding API

## 核心功能

- 文档上传与知识库管理
- 文档解析、文本切分与向量化
- 基于 Chroma 的语义检索
- 基于在线大模型 API 的 RAG 问答
- 答案来源引用与问答历史记录
- 用户反馈与测试评估扩展

## 项目结构

```text
CodeMind/
├─ backend/          FastAPI 后端服务
├─ frontend/         Vue 3 前端项目
├─ database/         MySQL 建表脚本
├─ docs/             实训文档与设计资料
├─ scripts/          辅助脚本
└─ storage/          本地上传文件和 Chroma 持久化目录
```

## 快速开始

1. 复制环境变量文件：

```bash
cp .env.example .env
```

2. 启动 MySQL：

```bash
docker compose up -d mysql
```

3. 初始化数据库：

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p codemind < database/schema.sql
```

4. 启动后端：

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

5. 启动前端：

```bash
cd frontend
npm install
npm run dev
```

## 当前状态

当前仓库处于初始化阶段，已确定项目方向、技术选型和基础工程结构。后续将优先完成文档上传、知识库构建、RAG 问答和来源引用这条核心闭环。


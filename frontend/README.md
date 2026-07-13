# CodeMind Frontend

Vue 3 前端提供认证、知识库管理、文档处理、RAG 问答、问答历史和知识地图界面。

## 技术栈

- Vue 3 与 Vue Router
- Vite
- Element Plus
- Axios
- AntV G6 知识地图画布
- Mammoth、Marked 与 DOMPurify 文档预览

## 页面路由

| 路径 | 页面 | 说明 |
| --- | --- | --- |
| `/` | `HomeView` | RAG 问答和来源展示 |
| `/documents` | `DocumentUploadView` | 上传、进度和处理状态 |
| `/library` | `DocumentLibraryView` | 文档筛选、重建和删除 |
| `/documents/:id/view` | `DocumentViewerView` | 原始文档预览 |
| `/documents/:id/chunks/:chunkId` | `DocumentDetailView` | 片段查看和定位 |
| `/history` | `QaHistoryView` | 问答历史和来源快照 |
| `/mind-map` | `MindMapView` | 知识地图生成与学习 |
| `/me` | `MeView` | 用户和知识库管理 |
| `/login`、`/register` | 认证页面 | 登录和注册 |

除首页和认证页面的公开外观外，业务路由通过用户 Store 和 JWT 状态保护；后端仍会独立校验所有资源归属。

## 本地开发

```bash
cd frontend
npm ci
npm run dev
```

默认开发地址为 `http://localhost:5173`。接口根地址由 `VITE_API_BASE_URL` 控制；Docker 前端通过 Nginx 将 `/api` 代理到后端。

生产构建：

```bash
npm run build
```

当前构建可以完成，但 AntV G6、Element Plus 和文档预览相关产物仍会触发大于 500 kB 的 chunk 警告，后续可通过更细的动态导入和 `manualChunks` 优化。

## 知识地图交互

当前 `MindMapView` 与 `MindMapCanvas` 已支持：

- 创建后台生成任务、显示阶段和逐步降频轮询。
- 页面切换后恢复同一知识库中的未完成任务，并丢弃旧任务迟到响应。
- 展示节点类型、摘要、关键记忆点、学习建议、知识路径和来源。
- 节点相关资料检索、针对性提问和 AI 分支扩展。
- 搜索标题、摘要和关键记忆点并定位节点。
- 画布缩放、适应、重新布局、撤销重做、拖拽锁定、折叠和全屏。
- 地图历史创建、更新、打开和删除。
- PNG、SVG、JSON 和 Markdown 导出。
- 使用 `localStorage` 保存本机节点掌握状态；该状态不会跨浏览器或设备同步。

知识地图正式生成流程调用 `/api/mind-maps/jobs` 和 `/api/mind-maps/jobs/{job_id}`。节点追问和扩展接口最长可等待 300 秒，前端请求超时设置为 6 分钟。

## 文档上传与预览

- 上传接口超时为 5 分钟，并通过 Axios 事件显示真实上传进度。
- 若上传响应超时，先到文档库确认是否已创建记录，避免重复提交。
- 状态轮询遇到临时网络错误会继续重试。
- 原文预览通过受保护的 `/api/documents/{id}/content` 获取，不直接公开上传目录。

## 安全注意事项

- 不在前端环境变量中放置 LLM、Embedding、数据库或 JWT 签名密钥。
- `VITE_` 变量会进入浏览器构建产物，只能用于公开配置。
- 文档预览生成的 HTML 必须经过 DOMPurify 清理。

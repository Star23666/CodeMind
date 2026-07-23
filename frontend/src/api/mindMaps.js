import { request } from "./request";

// 节点问答 / 展开默认受后端 900 秒墙钟总时限保护；前端多留 1 分钟，
// 避免慢模型仍在正常收尾时被浏览器先判定为失败。
const SLOW_TIMEOUT = 960_000;

export function createMindMapJob(payload) {
  return request.post("/mind-maps/jobs", payload);
}

export function getMindMapJob(jobId) {
  return request.get(`/mind-maps/jobs/${jobId}`);
}

export function cancelMindMapJob(jobId) {
  return request.post(`/mind-maps/jobs/${jobId}/cancel`);
}

export function askMindMapNode(payload) {
  return request.post("/mind-maps/ask", payload, { timeout: SLOW_TIMEOUT });
}

export function listMindMapHistories(knowledgeBaseId) {
  const config = knowledgeBaseId
    ? { params: { knowledge_base_id: knowledgeBaseId } }
    : undefined;
  return request.get("/mind-maps/histories", config);
}

export function getMindMapHistory(historyId) {
  return request.get(`/mind-maps/histories/${historyId}`);
}

export function createMindMapHistory(payload) {
  return request.post("/mind-maps/histories", payload);
}

export function updateMindMapHistory(historyId, payload) {
  return request.put(`/mind-maps/histories/${historyId}`, payload);
}

export function deleteMindMapHistory(historyId) {
  return request.delete(`/mind-maps/histories/${historyId}`);
}

export function expandMindMapNode(payload) {
  return request.post("/mind-maps/expand", payload, { timeout: SLOW_TIMEOUT });
}

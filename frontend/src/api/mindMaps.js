import { request } from "./request";

// 生成 / 问答 / 展开类接口后端最长 300 秒，这里放宽到 6 分钟，
// 避免前端先超时、把仍在正常处理的请求误判为失败。
const SLOW_TIMEOUT = 360_000;

export function createMindMapJob(payload) {
  return request.post("/mind-maps/jobs", payload);
}

export function getMindMapJob(jobId) {
  return request.get(`/mind-maps/jobs/${jobId}`);
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

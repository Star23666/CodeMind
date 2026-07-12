import { request } from "./request";

export function createMindMapJob(payload) {
  return request.post("/mind-maps/jobs", payload);
}

export function getMindMapJob(jobId) {
  return request.get(`/mind-maps/jobs/${jobId}`);
}

export function askMindMapNode(payload) {
  return request.post("/mind-maps/ask", payload, {
    timeout: 90000,
  });
}

export function listMindMapHistories(knowledgeBaseId) {
  return request.get("/mind-maps/histories", { params: { knowledge_base_id: knowledgeBaseId } });
}

export function getMindMapHistory(historyId) {
  return request.get(`/mind-maps/histories/${historyId}`);
}

export function updateMindMapHistory(historyId, payload) {
  return request.put(`/mind-maps/histories/${historyId}`, payload);
}

export function deleteMindMapHistory(historyId) {
  return request.delete(`/mind-maps/histories/${historyId}`);
}

export function expandMindMapNode(payload) {
  return request.post("/mind-maps/expand", payload, { timeout: 90000 });
}

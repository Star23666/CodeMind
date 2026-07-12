import { request } from "./request";

export function listKnowledgeBases() {
  return request.get("/knowledge-bases");
}

export function createKnowledgeBase(payload) {
  return request.post("/knowledge-bases", payload);
}

export function updateKnowledgeBase(knowledgeBaseId, payload) {
  return request.patch(`/knowledge-bases/${knowledgeBaseId}`, payload);
}

export function deleteKnowledgeBase(knowledgeBaseId) {
  return request.delete(`/knowledge-bases/${knowledgeBaseId}`);
}

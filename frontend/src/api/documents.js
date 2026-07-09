import { request } from "./request";

export function listDocuments(params = {}) {
  return request.get("/documents", { params });
}

export function getDocument(documentId) {
  return request.get(`/documents/${documentId}`);
}

export function uploadDocument({ knowledgeBaseId = 1, file }) {
  const formData = new FormData();
  formData.append("knowledge_base_id", knowledgeBaseId);
  formData.append("file", file);

  return request.post("/documents/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
}

export function deleteDocument(documentId) {
  return request.delete(`/documents/${documentId}`);
}

export function reindexDocument(documentId) {
  return request.post(`/documents/${documentId}/reindex`);
}

export function listDocumentChunks(documentId) {
  return request.get(`/documents/${documentId}/chunks`);
}

export function getDocumentChunk(documentId, chunkId) {
  return request.get(`/documents/${documentId}/chunks/${chunkId}`);
}

export function getChunk(chunkId) {
  return request.get(`/chunks/${chunkId}`);
}

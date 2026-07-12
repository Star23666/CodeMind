import { request } from "./request";

// 上传需要把整个文件传到服务器并写入磁盘，不能沿用普通接口的 20 秒超时。
const UPLOAD_TIMEOUT = 300_000;

export function listDocuments(params = {}) {
  return request.get("/documents", { params });
}

export function getDocument(documentId) {
  return request.get(`/documents/${documentId}`);
}

export function getDocumentContent(documentId) {
  return request.get(`/documents/${documentId}/content`, {
    responseType: "arraybuffer",
    timeout: 60000,
  });
}

export function uploadDocument({ knowledgeBaseId = 1, file }) {
  const formData = new FormData();
  formData.append("knowledge_base_id", knowledgeBaseId);
  formData.append("file", file);

  return request.post("/documents/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
    timeout: UPLOAD_TIMEOUT,
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

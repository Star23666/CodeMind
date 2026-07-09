import { request } from "./request";

export function listDocuments(params = {}) {
  return request.get("/documents", { params });
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

import { request } from "./request";

export function listQaRecords(params = {}) {
  return request.get("/qa-records", { params });
}

export function getQaRecord(qaRecordId) {
  return request.get(`/qa-records/${qaRecordId}`);
}

export function getQaFeedback(qaRecordId) {
  return request.get(`/qa-records/${qaRecordId}/feedback`);
}

export function submitQaFeedback(qaRecordId, payload) {
  return request.post(`/qa-records/${qaRecordId}/feedback`, payload);
}

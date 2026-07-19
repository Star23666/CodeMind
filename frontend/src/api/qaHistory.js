import { request } from "./request";

export function listQaRecords(params = {}) {
  return request.get("/qa-records", { params });
}

export function getQaRecord(qaRecordId) {
  return request.get(`/qa-records/${qaRecordId}`);
}

export function deleteQaRecord(qaRecordId) {
  return request.delete(`/qa-records/${qaRecordId}`);
}

export function deleteQaRecords(qaRecordIds) {
  return request.delete("/qa-records", {
    data: { qa_record_ids: qaRecordIds },
  });
}

export function getQaFeedback(qaRecordId) {
  return request.get(`/qa-records/${qaRecordId}/feedback`);
}

export function submitQaFeedback(qaRecordId, payload) {
  return request.post(`/qa-records/${qaRecordId}/feedback`, payload);
}

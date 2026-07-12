import { request } from "./request";

export function listQaRecords(params = {}) {
  return request.get("/qa-records", { params });
}

export function getQaRecord(qaRecordId) {
  return request.get(`/qa-records/${qaRecordId}`);
}

import { request } from "./request";

export function getAdminOverview() {
  return request.get("/admin/overview");
}

export function listAdminUsers(params = {}) {
  return request.get("/admin/users", { params });
}

export function updateAdminUserStatus(userId, status) {
  return request.patch(`/admin/users/${userId}/status`, { status });
}

export function listAdminDocuments(params = {}) {
  return request.get("/admin/documents", { params });
}

export function listAdminFeedbacks(params = {}) {
  return request.get("/admin/feedbacks", { params });
}

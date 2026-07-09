import { request } from "./request";

export function registerUser(payload) {
  return request.post("/auth/register", payload);
}

export function loginUser(payload) {
  return request.post("/auth/login", payload);
}

export function logoutUser() {
  return request.post("/auth/logout");
}

export function getCurrentUser() {
  return request.get("/auth/me");
}

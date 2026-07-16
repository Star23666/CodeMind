import { request } from "./request";

export function getLlmConfigOverview() {
  return request.get("/me/llm-configs");
}

export function createLlmConfig(payload) {
  return request.post("/me/llm-configs", payload);
}

export function updateLlmConfig(configId, payload) {
  return request.put(`/me/llm-configs/${configId}`, payload);
}

export function deleteLlmConfig(configId) {
  return request.delete(`/me/llm-configs/${configId}`);
}

export function testLlmConfig(configId) {
  return request.post(`/me/llm-configs/${configId}/test`);
}

export function activateLlmConfig(configId) {
  return request.post(`/me/llm-configs/${configId}/activate`);
}

export function useSystemDefaultLlm() {
  return request.post("/me/llm-configs/use-system-default");
}

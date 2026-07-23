import { request } from "./request";

// 检索要经过 Embedding + 向量库，给足时间，避免慢响应被前端误判为失败。
const SEARCH_TIMEOUT = 120_000;

export function searchKnowledge(payload, options = {}) {
  return request.post("/search", payload, {
    timeout: SEARCH_TIMEOUT,
    signal: options.signal,
  });
}

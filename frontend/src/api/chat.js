import { request } from "./request";

export function sendChatQuestion(payload) {
  return request.post(
    "/chat",
    {
      knowledge_base_id: payload.knowledge_base_id || 1,
      question: payload.question,
      top_k: payload.top_k ?? 4,
      score_threshold: payload.score_threshold ?? 0.77,
      rerank_top_n: payload.rerank_top_n ?? 2,
      enable_rewrite: payload.enable_rewrite ?? true,
      enable_rerank: payload.enable_rerank ?? true,
    },
    { timeout: 120000 },
  );
}

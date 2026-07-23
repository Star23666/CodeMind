import { request } from "./request";
import { TOKEN_KEY } from "../stores/user";

export const DEFAULT_SCORE_THRESHOLD = 0.55;

export function sendChatQuestion(payload) {
  return request.post(
    "/chat",
    {
      knowledge_base_id: payload.knowledge_base_id,
      question: payload.question,
      top_k: payload.top_k ?? 4,
      score_threshold: payload.score_threshold ?? DEFAULT_SCORE_THRESHOLD,
      rerank_top_n: payload.rerank_top_n ?? 2,
      enable_rewrite: payload.enable_rewrite ?? true,
      enable_rerank: payload.enable_rerank ?? true,
    },
    { timeout: 120000 },
  );
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];

  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) return null;

  return {
    event,
    data: JSON.parse(dataLines.join("\n")),
  };
}

async function parseErrorResponse(response) {
  try {
    const payload = await response.json();
    return payload.detail || `请求失败（${response.status}）`;
  } catch {
    return `请求失败（${response.status}）`;
  }
}

export async function streamChatQuestion(payload, { onMeta, onToken, onDone, signal } = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      knowledge_base_id: payload.knowledge_base_id,
      question: payload.question,
      top_k: payload.top_k ?? 4,
      score_threshold: payload.score_threshold ?? DEFAULT_SCORE_THRESHOLD,
      rerank_top_n: payload.rerank_top_n ?? 2,
      enable_rewrite: payload.enable_rewrite ?? true,
      enable_rerank: payload.enable_rerank ?? true,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(await parseErrorResponse(response));
  }

  if (!response.body) {
    throw new Error("浏览器不支持流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  const handleBlock = (block) => {
    const parsed = parseSseBlock(block);
    if (!parsed) return;

    if (parsed.event === "meta") {
      onMeta?.(parsed.data);
      return;
    }

    if (parsed.event === "token") {
      onToken?.(parsed.data.delta || "");
      return;
    }

    if (parsed.event === "done") {
      finalData = parsed.data;
      onDone?.(parsed.data);
      return;
    }

    if (parsed.event === "error") {
      const error = new Error(parsed.data.detail || "流式回答失败，请稍后重试。");
      error.status = parsed.data.status_code;
      throw error;
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || "";
    for (const block of blocks) handleBlock(block);

    if (done) break;
  }

  if (buffer.trim()) handleBlock(buffer);
  if (!finalData) {
    throw new Error("流式回答未正常结束。");
  }
  return finalData;
}

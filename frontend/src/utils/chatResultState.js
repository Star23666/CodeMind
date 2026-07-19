const CHAT_RESULT_KEY_PREFIX = "codemind-chat-result";

function storageKey(userId) {
  const normalizedUserId = Number(userId);
  return Number.isInteger(normalizedUserId) && normalizedUserId > 0
    ? `${CHAT_RESULT_KEY_PREFIX}:${normalizedUserId}`
    : "";
}

export function readChatResultState(userId) {
  const key = storageKey(userId);
  if (!key) return null;

  try {
    const value = JSON.parse(sessionStorage.getItem(key) || "null");
    return value?.version === 1 ? value : null;
  } catch {
    return null;
  }
}

export function saveChatResultState(userId, state) {
  const key = storageKey(userId);
  if (!key) return;

  try {
    sessionStorage.setItem(key, JSON.stringify({
      version: 1,
      ...state,
    }));
  } catch {
    // 浏览器禁用会话存储或空间不足时，不影响正常问答。
  }
}

export function clearChatResultState(userId) {
  const key = storageKey(userId);
  if (!key) return;

  try {
    sessionStorage.removeItem(key);
  } catch {
    // 清理失败时仍允许继续退出或登录。
  }
}

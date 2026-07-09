import axios from "axios";
import { TOKEN_KEY, USER_KEY } from "../stores/user";

export const request = axios.create({
  baseURL: "/api",
  timeout: 20000,
});

function readStoredUserId() {
  try {
    const user = JSON.parse(localStorage.getItem(USER_KEY) || "null");
    return user?.id || 1;
  } catch {
    return 1;
  }
}

request.interceptors.request.use((config) => {
  config.headers = config.headers || {};

  const token = localStorage.getItem(TOKEN_KEY);
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  config.headers["X-User-Id"] = config.headers["X-User-Id"] || String(readStoredUserId());
  return config;
});

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const detail = error.response?.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item.message || String(item)).join("；")
      : detail || error.message || "请求失败，请稍后重试。";

    return Promise.reject(new Error(message));
  },
);

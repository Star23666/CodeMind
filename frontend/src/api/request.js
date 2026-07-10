import axios from "axios";
import { TOKEN_KEY } from "../stores/user";

export const request = axios.create({
  baseURL: "/api",
  timeout: 20000,
});

let unauthorizedHandler = null;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

request.interceptors.request.use((config) => {
  config.headers = config.headers || {};

  const token = localStorage.getItem(TOKEN_KEY);
  if (token && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      unauthorizedHandler?.();
    }

    const detail = error.response?.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item.message || String(item)).join("；")
      : detail || error.message || "请求失败，请稍后重试。";

    const requestError = new Error(message);
    requestError.status = error.response?.status;
    return Promise.reject(requestError);
  },
);

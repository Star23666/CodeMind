import axios from "axios";

export const request = axios.create({
  baseURL: "/api",
  timeout: 20000,
});

request.interceptors.request.use((config) => {
  config.headers["X-User-Id"] = config.headers["X-User-Id"] || "1";
  return config;
});

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.message ||
      "请求失败，请稍后重试。";
    return Promise.reject(new Error(message));
  },
);

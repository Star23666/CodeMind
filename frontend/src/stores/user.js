import { reactive } from "vue";
import { clearChatResultState } from "../utils/chatResultState";

export const TOKEN_KEY = "codemind_token";
export const USER_KEY = "codemind_user";

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

const userStore = reactive({
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: readStoredUser(),
  authNotice: "",
  get isLoggedIn() {
    return Boolean(this.token);
  },
  get displayName() {
    return this.user?.username || "未登录用户";
  },
  get userId() {
    return this.user?.id || null;
  },
  setAuth({ token, user }) {
    this.token = token || "";
    this.user = user || null;

    if (this.token) {
      localStorage.setItem(TOKEN_KEY, this.token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }

    if (this.user) {
      localStorage.setItem(USER_KEY, JSON.stringify(this.user));
    } else {
      localStorage.removeItem(USER_KEY);
    }
  },
  updateUser(user) {
    this.user = user || null;
    this.authNotice = "";
    if (this.user) {
      localStorage.setItem(USER_KEY, JSON.stringify(this.user));
    } else {
      localStorage.removeItem(USER_KEY);
    }
  },
  clearAuth() {
    clearChatResultState(this.userId);
    this.token = "";
    this.user = null;
    this.authNotice = "";
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
  setAuthNotice(message) {
    this.authNotice = message || "";
  },
});

export function useUserStore() {
  return userStore;
}

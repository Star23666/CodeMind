<template>
  <header class="app-header">
    <RouterLink class="brand" to="/">
      <span class="brand-mark">
        <el-icon><Cpu /></el-icon>
      </span>
      <span>CodeMind</span>
    </RouterLink>

    <nav class="nav-links" aria-label="主导航">
      <RouterLink to="/">AI 问答</RouterLink>
      <RouterLink to="/documents">文档上传</RouterLink>
      <RouterLink to="/mind-map">知识地图</RouterLink>
      <RouterLink to="/library">文档库</RouterLink>
      <RouterLink to="/history">问答历史</RouterLink>
      <RouterLink to="/me">我的</RouterLink>
    </nav>

    <div class="actions">
      <el-tag v-if="showHealth" :type="healthOnline ? 'success' : 'info'" effect="light" round>
        {{ healthOnline ? "后端在线" : "后端未连接" }}
      </el-tag>

      <template v-if="userStore.isLoggedIn">
        <RouterLink class="user-link" to="/me">{{ userStore.displayName }}</RouterLink>
        <el-button text @click="logout">退出登录</el-button>
      </template>
      <el-button v-else type="primary" plain @click="goLogin">登录</el-button>

      <el-button
        :aria-label="isDark ? '切换到浅色主题' : '切换到深色主题'"
        :icon="isDark ? Sunny : Moon"
        circle
        @click="toggleTheme"
      />
    </div>
  </header>
</template>

<script setup>
import { Cpu, Moon, Sunny } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import { logoutUser } from "../../api/auth";
import { useTheme } from "../../composables/useTheme";
import { useUserStore } from "../../stores/user";

defineProps({
  healthOnline: {
    type: Boolean,
    default: false,
  },
  showHealth: {
    type: Boolean,
    default: true,
  },
});

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const { isDark, toggleTheme } = useTheme();

function goLogin() {
  router.push({
    name: "login",
    query: route.name === "login" ? {} : { redirect: route.fullPath },
  });
}

async function logout() {
  try {
    await ElMessageBox.confirm(
      "确定要退出当前账号吗？",
      "确认退出登录",
      {
        confirmButtonText: "退出登录",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }

  try {
    await logoutUser();
  } catch {
    // 前端退出不依赖后端登出是否成功。
  } finally {
    userStore.clearAuth();
    router.push({ name: "login" });
  }
}
</script>

<style scoped>
.app-header {
  position: sticky;
  top: 16px;
  z-index: 20;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 20px;
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 12px 14px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: color-mix(in srgb, var(--cm-surface) 88%, transparent);
  box-shadow: var(--cm-shadow);
  backdrop-filter: blur(18px);
}

.brand,
.nav-links,
.actions {
  display: flex;
  align-items: center;
}

.brand {
  gap: 10px;
  color: var(--cm-heading);
  font-size: 19px;
  font-weight: 800;
}

.brand-mark {
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border-radius: var(--cm-radius);
  color: #ffffff;
  background: linear-gradient(135deg, var(--cm-primary), #38bdf8);
}

.nav-links {
  justify-content: center;
  gap: 6px;
  padding: 4px;
  border: 1px solid var(--cm-border);
  border-radius: 999px;
  background: var(--cm-surface-soft);
}

.nav-links a {
  border-radius: 999px;
  padding: 8px 14px;
  color: var(--cm-muted);
  font-size: 14px;
  font-weight: 700;
  transition:
    color 0.18s ease,
    background 0.18s ease;
}

.nav-links a:hover,
.nav-links a.router-link-active {
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
}

.actions {
  justify-content: flex-end;
  gap: 10px;
}

.user-link {
  max-width: 140px;
  overflow: hidden;
  color: var(--cm-heading);
  font-size: 14px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) {
  .app-header {
    grid-template-columns: 1fr;
    top: 8px;
  }

  .nav-links,
  .actions {
    justify-content: flex-start;
  }

  .actions {
    flex-wrap: wrap;
  }
}

@media (max-width: 560px) {
  .nav-links {
    width: 100%;
    overflow-x: auto;
    justify-content: flex-start;
  }
}
</style>

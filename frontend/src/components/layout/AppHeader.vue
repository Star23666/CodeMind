<template>
  <header class="app-header">
    <RouterLink class="brand" to="/" aria-label="CodeMind 首页">
      <img class="brand-logo" :src="codeMindLogo" alt="CodeMind" />
    </RouterLink>

    <el-button
      class="mobile-menu-toggle"
      :icon="mobileMenuOpen ? Close : Menu"
      circle
      :aria-label="mobileMenuOpen ? '收起主导航' : '展开主导航'"
      :aria-expanded="mobileMenuOpen"
      aria-controls="primary-navigation"
      :title="mobileMenuOpen ? '收起主导航' : '展开主导航'"
      @click="mobileMenuOpen = !mobileMenuOpen"
    />

    <nav
      id="primary-navigation"
      class="nav-links"
      :class="{ 'nav-links--open': mobileMenuOpen }"
      aria-label="主导航"
    >
      <RouterLink to="/" @click="mobileMenuOpen = false">AI 问答</RouterLink>
      <RouterLink to="/documents" @click="mobileMenuOpen = false">文档上传</RouterLink>
      <RouterLink to="/search" @click="mobileMenuOpen = false">语义检索</RouterLink>
      <RouterLink to="/mind-map" @click="mobileMenuOpen = false">知识地图</RouterLink>
      <RouterLink to="/quiz" @click="mobileMenuOpen = false">AI 出题</RouterLink>
      <RouterLink to="/library" @click="mobileMenuOpen = false">文档库</RouterLink>
      <RouterLink to="/history" @click="mobileMenuOpen = false">问答历史</RouterLink>
      <RouterLink to="/me" @click="mobileMenuOpen = false">我的</RouterLink>
      <RouterLink v-if="userStore.user?.role === 'admin'" to="/admin" @click="mobileMenuOpen = false">
        管理后台
      </RouterLink>
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

    </div>
  </header>
</template>

<script setup>
import { Close, Menu } from "@element-plus/icons-vue";
import { ElMessageBox } from "element-plus";
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { logoutUser } from "../../api/auth";
import codeMindLogo from "../../assets/codemind-wordmark.png";
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
const mobileMenuOpen = ref(false);

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
  top: 18px;
  z-index: 30;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: clamp(24px, 2.4vw, 42px);
  width: min(1460px, calc(100% - 40px));
  margin: 0 auto;
  padding: 14px 20px;
  border: 1px solid rgba(183, 204, 230, 0.5);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow:
    0 18px 50px rgba(70, 115, 170, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(24px) saturate(135%);
}

.brand,
.nav-links,
.actions {
  display: flex;
  align-items: center;
}

.brand {
  align-self: stretch;
  width: fit-content;
}

.brand-logo {
  display: block;
  width: 164px;
  height: auto;
  object-fit: contain;
  transition:
    filter 0.2s ease,
    transform 0.2s ease;
}

.brand:hover .brand-logo {
  filter: drop-shadow(0 5px 10px rgba(37, 99, 235, 0.2));
  transform: translateY(-1px);
}

.nav-links {
  justify-content: center;
  gap: clamp(20px, 1.65vw, 30px);
  min-width: 0;
}

.nav-links a {
  position: relative;
  flex: 0 0 auto;
  padding: 10px 1px 9px;
  color: #526071;
  font-size: 14px;
  font-weight: 650;
  white-space: nowrap;
  transition:
    color 0.2s ease,
    transform 0.2s ease;
}

.nav-links a::after {
  position: absolute;
  right: 0;
  bottom: 2px;
  left: 0;
  height: 1.5px;
  border-radius: 999px;
  background: linear-gradient(90deg, #1f63d7, #5cb8ff);
  content: "";
  transform: scaleX(0);
  transform-origin: left center;
  transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.nav-links a:hover,
.nav-links a.router-link-active {
  color: #10223e;
}

.nav-links a:hover {
  transform: translateY(-1px);
}

.nav-links a:hover::after,
.nav-links a.router-link-active::after {
  transform: scaleX(1);
}

.actions {
  justify-content: flex-end;
  gap: 10px;
  color: #526071;
  white-space: nowrap;
}

.user-link {
  max-width: 140px;
  overflow: hidden;
  color: #172844;
  font-size: 14px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1240px) {
  .app-header {
    grid-template-columns: minmax(0, 1fr) auto;
    top: 10px;
    gap: 10px 24px;
  }

  .nav-links {
    grid-column: 1 / -1;
    justify-content: flex-start;
    gap: 28px;
    padding: 5px 2px 0;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .nav-links::-webkit-scrollbar {
    display: none;
  }
}

.mobile-menu-toggle {
  display: none;
}

@media (max-width: 700px) {
  .app-header {
    grid-template-columns: minmax(0, 1fr) auto;
    width: min(100% - 20px, 1460px);
    padding: 12px 14px;
  }

  .mobile-menu-toggle {
    display: inline-flex;
  }

  .nav-links {
    display: none;
    grid-column: 1 / -1;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 4px 16px;
    width: 100%;
    padding: 12px;
    border: 1px solid rgba(183, 204, 230, 0.52);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.92);
    overflow: visible;
  }

  .nav-links--open {
    display: grid;
  }

  .nav-links a {
    text-align: center;
  }

  .actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (max-width: 560px) {
  .brand-logo {
    width: 150px;
  }

}
</style>

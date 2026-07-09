<template>
  <div id="app">
    <!-- 顶部导航栏 -->
    <header class="app-header" v-if="userStore.isLoggedIn">
      <div class="brand">CodeMind</div>
      <div class="user-info">
        <span class="username">{{ userStore.user?.username }}</span>
        <span class="email">{{ userStore.user?.email }}</span>
        <el-button type="text" @click="logout">退出登录</el-button>
      </div>
    </header>
    <!-- 路由内容 -->
    <router-view />
  </div>
</template>

<script setup>
import { useUserStore } from './stores/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()

function logout() {
  userStore.clearAuth()
  router.push('/login')
}
</script>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  background: #ffffff;
  border-bottom: 1px solid #e2e7f0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}
.brand {
  font-weight: 700;
  font-size: 20px;
  color: #2f6fed;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
}
.username {
  font-weight: 600;
  font-size: 16px;
}
.email {
  color: #68748a;
}
</style>

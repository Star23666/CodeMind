<template>
  <div v-if="userStore.authNotice" class="auth-notice" role="alert">
    <span>{{ userStore.authNotice }}</span>
    <button type="button" aria-label="关闭服务提示" @click="userStore.setAuthNotice('')">关闭</button>
  </div>
  <RouterView />
</template>

<script setup>
import { useUserStore } from "./stores/user";

const userStore = useUserStore();
</script>

<style>
.auth-notice {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: min(1040px, calc(100% - 32px));
  margin: 12px auto -4px;
  padding: 10px 14px;
  border: 1px solid #e8b36b;
  border-radius: 8px;
  color: #6f4615;
  background: #fff8eb;
  box-shadow: 0 8px 22px rgba(111, 70, 21, 0.1);
  font-size: 14px;
}

.auth-notice button {
  border: 0;
  color: inherit;
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-weight: 700;
}
</style>

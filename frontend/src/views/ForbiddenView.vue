<template>
  <div class="forbidden-view">
    <AppHeader :show-health="false" />
    <main>
      <el-result icon="warning" title="无权访问" sub-title="此页面仅对管理员开放。">
        <template #extra>
          <el-button type="primary" @click="router.push({ name: 'home' })">返回 AI 问答</el-button>
        </template>
      </el-result>
    </main>
  </div>
</template>

<script setup>
import { useRouter } from "vue-router";
import AppHeader from "../components/layout/AppHeader.vue";

const router = useRouter();
</script>

<style scoped>
.forbidden-view { min-height: 100vh; padding: 16px 0 56px; }
.forbidden-view main { width: min(760px, calc(100% - 32px)); margin: 80px auto 0; padding: 32px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
</style>

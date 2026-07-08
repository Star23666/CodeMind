<template>
  <header class="app-header">
    <RouterLink class="brand" to="/">
      <span class="brand-mark">
        <el-icon><Cpu /></el-icon>
      </span>
      <span>CodeMind</span>
    </RouterLink>

    <nav class="nav-links" aria-label="主导航">
      <a href="#chat">问答</a>
      <a href="#documents">文档</a>
      <a href="#sources">来源</a>
    </nav>

    <div class="actions">
      <el-tag :type="healthOnline ? 'success' : 'info'" effect="light" round>
        {{ healthOnline ? "后端在线" : "演示模式" }}
      </el-tag>
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
import { useTheme } from "../../composables/useTheme";

defineProps({
  healthOnline: {
    type: Boolean,
    default: false,
  },
});

const { isDark, toggleTheme } = useTheme();
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

.nav-links a:hover {
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
}

.actions {
  justify-content: flex-end;
  gap: 10px;
}

@media (max-width: 760px) {
  .app-header {
    grid-template-columns: 1fr;
    top: 8px;
  }

  .nav-links,
  .actions {
    justify-content: flex-start;
  }
}
</style>

<template>
  <section class="health-card">
    <div class="status-dot" :class="{ online }"></div>
    <div>
      <p>后端状态</p>
      <strong>{{ online ? "服务可用" : "未连接或未启动" }}</strong>
      <span>{{ message }}</span>
    </div>
  </section>
</template>

<script setup>
defineProps({
  online: {
    type: Boolean,
    default: false,
  },
  message: {
    type: String,
    default: "等待检测",
  },
});
</script>

<style scoped>
.health-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
}

.status-dot {
  width: 12px;
  height: 12px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--cm-warning);
}

.status-dot.online {
  background: var(--cm-success);
}

p {
  margin: 0 0 4px;
  color: var(--cm-muted);
  font-size: 13px;
  font-weight: 700;
}

strong {
  display: block;
  margin-bottom: 6px;
  color: var(--cm-heading);
  font-size: 18px;
}

span {
  color: var(--cm-muted);
  line-height: 1.6;
}
</style>

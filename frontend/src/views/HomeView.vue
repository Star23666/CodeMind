<template>
  <div class="home-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="hero">
        <el-tag effect="plain">个人知识库 AI 助手</el-tag>
        <h1>首页只保留提问入口</h1>
        <p>
          登录后可以基于自己的资料提问，回答会带上可跳转的来源片段。
          文档上传和个人资料放到独立页面里，首页保持干净。
        </p>
      </section>

      <ChatPanel :knowledge-base-id="knowledgeBaseId" />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import ChatPanel from "../components/chat/ChatPanel.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const healthOnline = ref(false);
const knowledgeBaseId = ref(1);

onMounted(() => {
  checkHealth();
  loadDefaultKnowledgeBase();
});

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadDefaultKnowledgeBase() {
  try {
    const bases = await listKnowledgeBases();
    knowledgeBaseId.value = bases[0]?.id || 1;
  } catch {
    knowledgeBaseId.value = 1;
  }
}
</script>

<style scoped>
.home-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  display: grid;
  gap: 22px;
  width: min(920px, calc(100% - 32px));
  margin: 56px auto 0;
}

.hero {
  display: grid;
  gap: 12px;
  text-align: center;
}

.hero :deep(.el-tag) {
  justify-self: center;
}

h1 {
  margin: 0;
  color: var(--cm-heading);
  font-size: clamp(32px, 5vw, 54px);
  line-height: 1.08;
}

p {
  width: min(680px, 100%);
  margin: 0 auto;
  color: var(--cm-muted);
  font-size: 16px;
  line-height: 1.8;
}

@media (max-width: 640px) {
  .home-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 920px);
    margin-top: 32px;
  }
}
</style>

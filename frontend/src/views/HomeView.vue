<template>
  <div class="home-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <HeroSection
        @focus-chat="focusChat"
        @focus-upload="focusUpload"
        @use-prompt="usePrompt"
      />

      <section class="dashboard">
        <KnowledgeBasePanel
          v-model="knowledgeBaseId"
          :bases="knowledgeBases"
          :loaded="knowledgeLoaded"
        />
        <HealthCard :online="healthOnline" :message="healthMessage" />
      </section>

      <section class="workspace">
        <div ref="uploadSection">
          <UploadPanel :knowledge-base-id="knowledgeBaseId" />
        </div>
        <ChatPanel
          ref="chatPanel"
          :knowledge-base-id="knowledgeBaseId"
          :initial-question="selectedPrompt"
        />
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import AppHeader from "../components/layout/AppHeader.vue";
import HeroSection from "../components/home/HeroSection.vue";
import ChatPanel from "../components/chat/ChatPanel.vue";
import UploadPanel from "../components/documents/UploadPanel.vue";
import HealthCard from "../components/status/HealthCard.vue";
import KnowledgeBasePanel from "../components/knowledge/KnowledgeBasePanel.vue";

const knowledgeBaseId = ref(1);
const knowledgeBases = ref([]);
const knowledgeLoaded = ref(false);
const healthOnline = ref(false);
const healthMessage = ref("正在检测后端服务");
const selectedPrompt = ref("");
const chatPanel = ref(null);
const uploadSection = ref(null);

onMounted(() => {
  checkHealth();
  loadKnowledgeBases();
});

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
    healthMessage.value = healthOnline.value ? "FastAPI 已响应 /api/health" : "后端返回了未知状态";
  } catch (error) {
    healthOnline.value = false;
    healthMessage.value = error.message;
  }
}

async function loadKnowledgeBases() {
  try {
    knowledgeBases.value = await listKnowledgeBases();
  } catch {
    knowledgeBases.value = [];
  } finally {
    knowledgeLoaded.value = true;
  }
}

function focusChat() {
  chatPanel.value?.focusQuestion?.();
  document.querySelector("#chat")?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function focusUpload() {
  uploadSection.value?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function usePrompt(prompt) {
  selectedPrompt.value = prompt;
  chatPanel.value?.setQuestion?.(prompt);
  focusChat();
}
</script>

<style scoped>
.home-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
}

.dashboard,
.workspace {
  display: grid;
  gap: 20px;
}

.dashboard {
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
  margin-bottom: 20px;
}

.workspace {
  grid-template-columns: minmax(320px, 0.88fr) minmax(0, 1.12fr);
  align-items: start;
}

@media (max-width: 980px) {
  .dashboard,
  .workspace {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .home-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 1180px);
  }
}
</style>

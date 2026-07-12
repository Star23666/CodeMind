<template>
  <div class="home-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="hero">
        <el-tag effect="plain">你的私人知识库 AI</el-tag>
        <h1>让每一份资料，都成为随时可问的知识</h1>
        <p>
          上传文档，沉淀属于你的知识空间。CodeMind 从资料中寻找依据，
          为你生成清晰、可信、可追溯的回答。
        </p>
      </section>

      <section v-if="userStore.isLoggedIn" class="knowledge-picker">
        <div>
          <p>当前知识库</p>
          <h2>{{ currentKnowledgeBase?.name || "尚未创建知识库" }}</h2>
        </div>
        <el-select
          v-model="knowledgeBaseId"
          placeholder="请选择知识库"
          :disabled="!knowledgeBases.length"
          class="knowledge-select"
        >
          <el-option
            v-for="base in knowledgeBases"
            :key="base.id"
            :label="base.name"
            :value="base.id"
          />
        </el-select>
        <el-button
          v-if="knowledgeBases.length"
          type="primary"
          plain
          :disabled="!knowledgeBaseId"
          @click="openMindMap"
        >
          打开知识地图
        </el-button>
        <el-button v-if="!knowledgeBases.length" type="primary" plain @click="goCreateKnowledgeBase">
          创建知识库
        </el-button>
      </section>

      <ChatPanel
        :knowledge-base-id="knowledgeBaseId"
        :knowledge-base-name="currentKnowledgeBase?.name || ''"
      />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import ChatPanel from "../components/chat/ChatPanel.vue";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const userStore = useUserStore();
const router = useRouter();
const healthOnline = ref(false);
const knowledgeBases = ref([]);
const knowledgeBaseId = ref(null);
const currentKnowledgeBase = computed(() =>
  knowledgeBases.value.find((base) => base.id === knowledgeBaseId.value),
);

onMounted(() => {
  checkHealth();
  if (userStore.isLoggedIn) {
    loadDefaultKnowledgeBase();
  }
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
    knowledgeBases.value = await listKnowledgeBases();
    knowledgeBaseId.value = knowledgeBases.value[0]?.id ?? null;
  } catch {
    knowledgeBases.value = [];
    knowledgeBaseId.value = null;
  }
}

function goCreateKnowledgeBase() {
  router.push({ name: "me" });
}

function openMindMap() {
  router.push({
    name: "mind-map",
    query: { knowledge_base_id: knowledgeBaseId.value },
  });
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

.knowledge-picker {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.knowledge-picker > div {
  min-width: 0;
  flex: 1;
}

.knowledge-picker p {
  width: auto;
  margin: 0 0 5px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.knowledge-picker h2 {
  margin: 0;
  overflow: hidden;
  color: var(--cm-heading);
  font-size: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-select {
  width: min(280px, 100%);
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

  .knowledge-picker {
    align-items: stretch;
    flex-direction: column;
  }

  .knowledge-select {
    width: 100%;
  }
}
</style>

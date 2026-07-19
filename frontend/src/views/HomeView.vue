<template>
  <div class="home-view">
    <HomeParticleBackground />
    <AppHeader :health-online="healthOnline" />

    <main class="home-main">
      <ChatPanel
        :knowledge-base-id="knowledgeBaseId"
        :knowledge-bases="knowledgeBases"
        :initial-question="initialQuestion"
        @update:knowledge-base-id="updateKnowledgeBase"
      >
        <template #intro>
          <section class="hero-copy">
            <p class="eyebrow">CodeMind · Knowledge with evidence</p>
            <h1>让知识可问，<br />让每个答案都有依据</h1>
          </section>
        </template>
      </ChatPanel>
    </main>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import ChatPanel from "../components/chat/ChatPanel.vue";
import HomeParticleBackground from "../components/home/HomeParticleBackground.vue";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";
import { pickDefaultKnowledgeBase } from "../utils/knowledgeBases";

const userStore = useUserStore();
const route = useRoute();
const router = useRouter();
const healthOnline = ref(false);
const knowledgeBases = ref([]);
const knowledgeBaseId = ref(null);
const initialQuestion = ref("");

watch(
  () => route.query.question,
  async (nextQuestion) => {
    if (typeof nextQuestion !== "string" || !nextQuestion.trim()) return;
    initialQuestion.value = nextQuestion.slice(0, 500);
    await nextTick();
    const nextQuery = { ...route.query };
    delete nextQuery.question;
    router.replace({ query: nextQuery });
  },
  { immediate: true },
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
    knowledgeBaseId.value = pickDefaultKnowledgeBase(knowledgeBases.value)?.id ?? null;
  } catch {
    knowledgeBases.value = [];
    knowledgeBaseId.value = null;
  }
}

function updateKnowledgeBase(nextId) {
  knowledgeBaseId.value = nextId;
}
</script>

<style scoped>
.home-view {
  position: relative;
  min-height: 100svh;
  overflow-x: clip;
  padding: 16px 0 0;
  color: #18263a;
}

.home-main {
  position: relative;
  z-index: 1;
  display: grid;
  width: min(1080px, calc(100% - 40px));
  min-height: calc(100svh - 106px);
  margin: 0 auto;
  padding: 14px 0 24px;
  place-items: center;
}

.hero-copy {
  display: grid;
  justify-items: center;
  gap: 13px;
  width: min(890px, 100%);
  text-align: center;
}

.eyebrow {
  margin: 0;
  color: #2b6fca;
  font-family: "DIN Alternate", "Avenir Next", Inter, "PingFang SC", sans-serif;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  color: #11213a;
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(43px, 5.8vw, 68px);
  font-weight: 600;
  letter-spacing: -0.045em;
  line-height: 1.12;
  text-wrap: balance;
}

@media (max-width: 700px) {
  .home-view {
    padding-top: 8px;
  }

  .home-main {
    width: min(100% - 24px, 1080px);
    min-height: calc(100svh - 88px);
    padding: 26px 0 42px;
  }

  .hero-copy {
    gap: 14px;
  }

  h1 {
    font-size: clamp(39px, 12vw, 56px);
    letter-spacing: -0.035em;
  }

}
</style>

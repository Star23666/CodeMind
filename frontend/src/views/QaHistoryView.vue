<template>
  <div class="history-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-tag effect="plain">个人记录</el-tag>
          <h1>问答历史</h1>
          <p>回看过去的问题、AI 回答和当时引用的来源片段。</p>
        </div>
        <el-button :icon="Refresh" :loading="loading" @click="loadHistory">刷新记录</el-button>
      </section>

      <section class="history-layout">
        <aside class="history-sidebar">
          <div class="filters">
            <el-input v-model="keyword" :prefix-icon="Search" clearable placeholder="匹配问题关键词" />
            <el-select v-model="selectedBaseId" placeholder="全部知识库">
              <el-option label="全部知识库" :value="null" />
              <KnowledgeBaseOptions :bases="knowledgeBases" />
            </el-select>
          </div>

          <div v-loading="loading" class="record-list">
            <button
              v-for="record in filteredRecords"
              :key="record.id"
              :class="{ active: selectedRecord?.id === record.id }"
              type="button"
              @click="selectRecord(record)"
            >
              <strong>{{ record.question }}</strong>
              <span>{{ knowledgeBaseName(record.knowledge_base_id) }}</span>
              <small>{{ formatDate(record.created_at) }} · {{ record.source_count }} 个来源</small>
            </button>
            <el-empty v-if="!filteredRecords.length && !loading" description="暂无符合条件的问答记录" />
          </div>
        </aside>

        <article v-loading="detailLoading" class="record-detail">
          <template v-if="selectedRecord">
            <div class="detail-head">
              <div>
                <p>{{ knowledgeBaseName(selectedRecord.knowledge_base_id) }}</p>
                <span>{{ formatDate(selectedRecord.created_at) }}</span>
              </div>
              <el-tag effect="plain">{{ selectedRecord.source_count }} 个来源</el-tag>
            </div>

            <section class="question-block">
              <small>你的问题</small>
              <h2>{{ selectedRecord.question }}</h2>
              <p v-if="selectedRecord.rewritten_question">
                检索改写：{{ selectedRecord.rewritten_question }}
              </p>
            </section>

            <section class="answer-block">
              <small>AI 回答</small>
              <p>{{ selectedRecord.answer }}</p>
            </section>

            <SourceList :sources="selectedRecord.sources || []" />
            <FeedbackPanel :qa-record-id="selectedRecord.id" />
          </template>
          <el-empty v-else description="选择左侧记录查看详情" />
        </article>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Refresh, Search } from "@element-plus/icons-vue";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { getQaRecord, listQaRecords } from "../api/qaHistory";
import SourceList from "../components/chat/SourceList.vue";
import FeedbackPanel from "../components/chat/FeedbackPanel.vue";
import KnowledgeBaseOptions from "../components/knowledge/KnowledgeBaseOptions.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const healthOnline = ref(false);
const loading = ref(false);
const detailLoading = ref(false);
const records = ref([]);
const knowledgeBases = ref([]);
const selectedRecord = ref(null);
const selectedBaseId = ref(null);
const keyword = ref("");

const filteredRecords = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase();
  return records.value.filter((record) => {
    const matchesBase = selectedBaseId.value === null || record.knowledge_base_id === selectedBaseId.value;
    const matchesKeyword = !query || record.question.toLocaleLowerCase().includes(query);
    return matchesBase && matchesKeyword;
  });
});

watch([selectedBaseId, keyword], async () => {
  if (!filteredRecords.value.some((record) => record.id === selectedRecord.value?.id)) {
    await selectRecord(filteredRecords.value[0] || null);
  }
});

onMounted(() => {
  checkHealth();
  loadHistory();
});

async function checkHealth() {
  try { healthOnline.value = (await getHealth()).status === "ok"; }
  catch { healthOnline.value = false; }
}

async function loadHistory() {
  loading.value = true;
  try {
    const [bases, history] = await Promise.all([listKnowledgeBases(), listQaRecords()]);
    knowledgeBases.value = bases;
    records.value = history;
    await selectRecord(history[0] || null);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function selectRecord(record) {
  if (!record) {
    selectedRecord.value = null;
    return;
  }
  if (selectedRecord.value?.id === record.id) {
    return;
  }
  if (record.sources?.length) {
    selectedRecord.value = record;
    return;
  }

  detailLoading.value = true;
  try {
    selectedRecord.value = await getQaRecord(record.id);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    detailLoading.value = false;
  }
}

function knowledgeBaseName(id) {
  return knowledgeBases.value.find((base) => base.id === id)?.name || "已删除的知识库";
}

function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.history-view { min-height: 100vh; padding: 16px 0 56px; }
.page { display: grid; gap: 20px; width: min(1180px, calc(100% - 32px)); margin: 44px auto 0; }
.page-head, .detail-head { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.page-head h1 { margin: 12px 0 8px; color: var(--cm-heading); font-size: 34px; }
.page-head p { margin: 0; color: var(--cm-muted); }
.history-layout { display: grid; grid-template-columns: minmax(300px, .72fr) minmax(0, 1.28fr); gap: 20px; align-items: start; }
.history-sidebar, .record-detail { border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.history-sidebar { overflow: hidden; }
.filters { display: grid; gap: 10px; padding: 16px; border-bottom: 1px solid var(--cm-border); }
.record-list { display: grid; min-height: 280px; max-height: 680px; overflow: auto; }
.record-list button { display: grid; gap: 7px; padding: 16px; border: 0; border-bottom: 1px solid var(--cm-border); color: inherit; background: transparent; text-align: left; cursor: pointer; }
.record-list button:hover, .record-list button.active { background: var(--cm-primary-soft); }
.record-list button.active { box-shadow: inset 3px 0 var(--cm-primary); }
.record-list strong { display: -webkit-box; overflow: hidden; color: var(--cm-heading); line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.record-list span { color: var(--cm-primary); font-size: 13px; font-weight: 700; }
.record-list small { color: var(--cm-muted); }
.record-detail { display: grid; min-height: 520px; gap: 22px; padding: 24px; }
.detail-head p { margin: 0 0 5px; color: var(--cm-primary); font-weight: 800; }
.detail-head span { color: var(--cm-muted); font-size: 13px; }
.question-block, .answer-block { padding: 18px; border-radius: var(--cm-radius); }
.question-block { background: var(--cm-primary-soft); }
.answer-block { border: 1px solid var(--cm-border); background: var(--cm-surface-soft); }
.question-block small, .answer-block small { color: var(--cm-primary); font-weight: 800; }
.question-block h2 { margin: 8px 0 0; color: var(--cm-heading); font-size: 22px; line-height: 1.5; }
.question-block p { margin: 12px 0 0; color: var(--cm-muted); line-height: 1.6; }
.answer-block p { margin: 10px 0 0; color: var(--cm-text); line-height: 1.85; white-space: pre-wrap; }
@media (max-width: 900px) { .history-layout { grid-template-columns: 1fr; } .record-list { max-height: 380px; } }
@media (max-width: 640px) { .history-view { padding-top: 8px; } .page { width: min(100% - 20px, 1180px); margin-top: 32px; } .page-head { align-items: stretch; flex-direction: column; } }
</style>

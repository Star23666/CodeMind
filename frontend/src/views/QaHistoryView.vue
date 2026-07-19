<template>
  <div class="history-view">
    <HomeParticleBackground />
    <AppHeader :health-online="healthOnline" />

    <main class="history-page">
      <header class="page-head">
        <h1>提问历史</h1>
        <el-button :icon="Refresh" :loading="loading" round @click="loadHistory">
          刷新
        </el-button>
      </header>

      <section class="history-workspace">
        <aside class="history-panel">
          <div class="filters">
            <el-input
              v-model="keyword"
              :prefix-icon="Search"
              clearable
              placeholder="搜索提问"
            />
            <el-select v-model="selectedBaseId" placeholder="全部知识库">
              <el-option label="全部知识库" :value="null" />
              <KnowledgeBaseOptions :bases="knowledgeBases" />
            </el-select>
            <span>{{ filteredRecords.length }} / 50</span>
          </div>

          <div class="management-bar">
            <el-button type="primary" plain round @click="toggleManagement">
              {{ managementMode ? "完成" : "管理" }}
            </el-button>
          </div>

          <div v-if="managementMode" class="selection-bar">
            <el-checkbox
              :model-value="allFilteredSelected"
              :indeterminate="someFilteredSelected"
              :disabled="!filteredRecords.length"
              @change="toggleAllFiltered"
            >
              全选当前
            </el-checkbox>
            <div>
              <span v-if="selectedIds.length">已选 {{ selectedIds.length }} 条</span>
              <el-button
                type="danger"
                plain
                :disabled="!selectedIds.length"
                :loading="batchDeleting"
                @click="confirmBatchDelete"
              >
                批量删除
              </el-button>
            </div>
          </div>

          <div v-loading="loading" class="record-list">
            <article
              v-for="record in filteredRecords"
              :key="record.id"
              class="record-item"
              :class="{
                active: selectedRecord?.id === record.id,
                'is-managing': managementMode,
              }"
            >
              <el-checkbox
                v-if="managementMode"
                :model-value="selectedIds.includes(record.id)"
                :aria-label="`选择问题：${record.question}`"
                @click.stop
                @change="(checked) => toggleRecord(record.id, checked)"
              />
              <button class="record-question" type="button" @click="selectRecord(record)">
                <strong>{{ record.question }}</strong>
                <span>
                  {{ knowledgeBaseName(record.knowledge_base_id) }}
                  <i aria-hidden="true">·</i>
                  {{ formatDate(record.created_at) }}
                  <i aria-hidden="true">·</i>
                  {{ record.source_count }} 个来源
                </span>
              </button>
              <el-button
                v-if="managementMode"
                class="delete-button"
                :icon="Delete"
                text
                circle
                type="danger"
                :loading="deletingId === record.id"
                :aria-label="`删除问题：${record.question}`"
                title="删除这条历史"
                @click.stop="confirmDelete(record)"
              />
            </article>

            <el-empty
              v-if="!filteredRecords.length && !loading"
              description="暂无符合条件的提问记录"
            />
          </div>
        </aside>

        <article v-loading="detailLoading" class="record-detail">
          <template v-if="selectedRecord">
            <div class="detail-head">
              <div>
                <strong>{{ knowledgeBaseName(selectedRecord.knowledge_base_id) }}</strong>
                <span>{{ formatDate(selectedRecord.created_at) }}</span>
              </div>
              <el-button type="primary" plain round @click="useQuestion(selectedRecord.question)">
                重新提问
              </el-button>
            </div>

            <section class="question-block">
              <small>你的问题</small>
              <h2>{{ selectedRecord.question }}</h2>
              <p v-if="selectedRecord.rewritten_question">
                检索改写：{{ selectedRecord.rewritten_question }}
              </p>
            </section>

            <AnswerCard
              :answer="selectedRecord.answer"
              status="历史回答"
              :qa-record-id="selectedRecord.id"
              :sources="selectedRecord.sources || []"
            />
          </template>
          <el-empty v-else description="选择左侧记录查看原回答和来源" />
        </article>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Delete, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import {
  deleteQaRecord,
  deleteQaRecords,
  getQaRecord,
  listQaRecords,
} from "../api/qaHistory";
import AnswerCard from "../components/chat/AnswerCard.vue";
import HomeParticleBackground from "../components/home/HomeParticleBackground.vue";
import KnowledgeBaseOptions from "../components/knowledge/KnowledgeBaseOptions.vue";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";
import { clearChatResultStateForQaRecords } from "../utils/chatResultState";

const router = useRouter();
const userStore = useUserStore();
const healthOnline = ref(false);
const loading = ref(false);
const detailLoading = ref(false);
const deletingId = ref(null);
const batchDeleting = ref(false);
const managementMode = ref(false);
const records = ref([]);
const selectedRecord = ref(null);
const selectedIds = ref([]);
const knowledgeBases = ref([]);
const selectedBaseId = ref(null);
const keyword = ref("");

const filteredRecords = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase();
  return records.value.filter((record) => {
    const matchesBase =
      selectedBaseId.value === null || record.knowledge_base_id === selectedBaseId.value;
    const matchesKeyword = !query || record.question.toLocaleLowerCase().includes(query);
    return matchesBase && matchesKeyword;
  });
});

const allFilteredSelected = computed(
  () =>
    filteredRecords.value.length > 0 &&
    filteredRecords.value.every((record) => selectedIds.value.includes(record.id)),
);

const someFilteredSelected = computed(
  () =>
    !allFilteredSelected.value &&
    filteredRecords.value.some((record) => selectedIds.value.includes(record.id)),
);

watch([selectedBaseId, keyword], () => {
  if (!filteredRecords.value.some((record) => record.id === selectedRecord.value?.id)) {
    selectRecord(filteredRecords.value[0] || null);
  }
});

onMounted(() => {
  checkHealth();
  loadHistory();
});

async function checkHealth() {
  try {
    healthOnline.value = (await getHealth()).status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadHistory() {
  loading.value = true;
  try {
    const [bases, history] = await Promise.all([
      listKnowledgeBases(),
      listQaRecords({ limit: 50 }),
    ]);
    knowledgeBases.value = bases;
    records.value = history;
    const availableIds = new Set(history.map((record) => record.id));
    selectedIds.value = selectedIds.value.filter((id) => availableIds.has(id));
    const nextRecord =
      history.find((record) => record.id === selectedRecord.value?.id) ||
      filteredRecords.value[0] ||
      null;
    await selectRecord(nextRecord, { force: true });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function selectRecord(record, { force = false } = {}) {
  if (!record) {
    selectedRecord.value = null;
    return;
  }
  if (!force && selectedRecord.value?.id === record.id) return;

  detailLoading.value = true;
  try {
    selectedRecord.value = await getQaRecord(record.id);
  } catch (error) {
    selectedRecord.value = null;
    ElMessage.error(error.message);
  } finally {
    detailLoading.value = false;
  }
}

function toggleManagement() {
  if (managementMode.value) {
    finishManagement();
    return;
  }
  managementMode.value = true;
}

function finishManagement() {
  managementMode.value = false;
  selectedIds.value = [];
}

function useQuestion(question) {
  router.push({
    name: "home",
    query: { question },
  });
}

async function confirmDelete(record) {
  try {
    await ElMessageBox.confirm(
      "删除后无法恢复，是否继续？",
      "删除这条提问历史",
      {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }

  deletingId.value = record.id;
  try {
    await deleteQaRecord(record.id);
    records.value = records.value.filter((item) => item.id !== record.id);
    selectedIds.value = selectedIds.value.filter((id) => id !== record.id);
    clearChatResultStateForQaRecords(userStore.userId, [record.id]);
    if (selectedRecord.value?.id === record.id) {
      selectedRecord.value = null;
      await selectRecord(filteredRecords.value[0] || null);
    }
    finishManagement();
    ElMessage.success("历史记录已删除");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    deletingId.value = null;
  }
}

function toggleRecord(recordId, checked) {
  const next = new Set(selectedIds.value);
  if (checked) next.add(recordId);
  else next.delete(recordId);
  selectedIds.value = [...next];
}

function toggleAllFiltered(checked) {
  const next = new Set(selectedIds.value);
  for (const record of filteredRecords.value) {
    if (checked) next.add(record.id);
    else next.delete(record.id);
  }
  selectedIds.value = [...next];
}

async function confirmBatchDelete() {
  const ids = [...selectedIds.value];
  if (!ids.length) return;

  try {
    await ElMessageBox.confirm(
      `将永久删除选中的 ${ids.length} 条提问历史，是否继续？`,
      "批量删除提问历史",
      {
        confirmButtonText: "全部删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
  } catch {
    return;
  }

  batchDeleting.value = true;
  try {
    await deleteQaRecords(ids);
    const deletedIds = new Set(ids);
    records.value = records.value.filter((record) => !deletedIds.has(record.id));
    selectedIds.value = [];
    clearChatResultStateForQaRecords(userStore.userId, ids);
    if (selectedRecord.value && deletedIds.has(selectedRecord.value.id)) {
      selectedRecord.value = null;
      await selectRecord(filteredRecords.value[0] || null);
    }
    finishManagement();
    ElMessage.success(`已删除 ${ids.length} 条历史记录`);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    batchDeleting.value = false;
  }
}

function knowledgeBaseName(id) {
  return knowledgeBases.value.find((base) => base.id === id)?.name || "已删除的知识库";
}

function formatDate(value) {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
}
</script>

<style scoped>
.history-view {
  position: relative;
  min-height: 100svh;
  overflow-x: clip;
  padding: 16px 0 56px;
  color: #1c2c42;
}

.history-page {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 28px;
  width: min(1240px, calc(100% - 40px));
  margin: 70px auto 0;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.management-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-height: 54px;
  padding: 8px 18px;
  border-bottom: 1px solid rgba(170, 194, 222, 0.4);
  background: rgba(247, 251, 255, 0.5);
}

.page-head h1 {
  margin: 0;
  color: #13243c;
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(36px, 5vw, 54px);
  font-weight: 600;
  letter-spacing: -0.04em;
}

.history-workspace {
  display: grid;
  grid-template-columns: minmax(340px, 0.72fr) minmax(0, 1.28fr);
  align-items: start;
  gap: 20px;
}

.history-panel,
.detail-head,
.question-block,
.record-detail > :deep(.el-empty) {
  overflow: hidden;
  border: 1px solid rgba(159, 187, 220, 0.52);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow:
    0 28px 80px rgba(62, 112, 168, 0.13),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(24px) saturate(125%);
}

.filters {
  display: grid;
  grid-template-columns: 1fr;
  align-items: center;
  gap: 12px;
  padding: 18px;
  border-bottom: 1px solid rgba(170, 194, 222, 0.4);
}

.filters > span {
  color: #8997a9;
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 11px;
  text-align: right;
  white-space: nowrap;
}

.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 54px;
  padding: 8px 18px;
  border-bottom: 1px solid rgba(170, 194, 222, 0.4);
  background: rgba(247, 251, 255, 0.62);
}

.selection-bar > div {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selection-bar span {
  color: #75859a;
  font-size: 12px;
}

.record-list {
  display: grid;
  min-height: 280px;
  max-height: 720px;
  overflow-y: auto;
}

.record-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  padding: 4px 12px 4px 20px;
  border-bottom: 1px solid rgba(174, 198, 225, 0.34);
  transition: background 0.18s ease;
}

.record-item.is-managing {
  grid-template-columns: auto minmax(0, 1fr) auto;
}

.record-item.active {
  background: rgba(224, 241, 255, 0.78);
  box-shadow: inset 3px 0 #4b91df;
}

.record-item:last-child {
  border-bottom: 0;
}

.record-item:hover {
  background: rgba(235, 246, 255, 0.7);
}

.record-question {
  display: grid;
  gap: 8px;
  min-width: 0;
  border: 0;
  padding: 15px 0;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.record-question strong {
  overflow: hidden;
  color: #263b55;
  font-size: 15px;
  font-weight: 650;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  transition: color 0.18s ease;
}

.record-question:hover strong,
.record-question:focus-visible strong {
  color: #2775c8;
}

.record-question:focus-visible {
  outline: none;
}

.record-question span {
  color: #8795a7;
  font-size: 11px;
}

.record-question i {
  margin: 0 5px;
  color: #b3bdca;
  font-style: normal;
}

.record-detail {
  display: grid;
  min-width: 0;
  min-height: 560px;
  align-content: start;
  gap: 18px;
}

.detail-head,
.question-block {
  background: rgba(255, 255, 255, 0.76);
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
}

.detail-head > div {
  display: grid;
  gap: 4px;
}

.detail-head strong {
  color: #2e6fb9;
  font-size: 13px;
}

.detail-head span {
  color: #8492a5;
  font-size: 11px;
}

.question-block {
  padding: 20px 22px;
}

.question-block small {
  color: #3979c4;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.question-block h2 {
  margin: 8px 0 0;
  color: #203650;
  font-size: 21px;
  line-height: 1.5;
}

.question-block p {
  margin: 12px 0 0;
  color: #74849a;
  font-size: 12px;
  line-height: 1.65;
}

.record-detail > :deep(.el-empty) {
  display: grid;
  min-height: 560px;
  place-items: center;
  background: rgba(255, 255, 255, 0.7);
}

.delete-button {
  opacity: 0.54;
  transition: opacity 0.18s ease;
}

.record-item:hover .delete-button,
.delete-button:focus-visible {
  opacity: 1;
}

@media (max-width: 700px) {
  .history-view {
    padding-top: 8px;
  }

  .history-page {
    width: min(100% - 24px, 1240px);
    margin-top: 48px;
  }

  .page-head {
    align-items: center;
  }

  .page-head .el-button {
    align-self: center;
  }

  .selection-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .selection-bar > div {
    justify-content: space-between;
  }
}

@media (max-width: 980px) {
  .history-workspace {
    grid-template-columns: 1fr;
  }

  .record-list {
    max-height: 440px;
  }
}
</style>

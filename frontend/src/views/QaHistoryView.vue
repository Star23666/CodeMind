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

      <section class="history-panel">
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

        <div class="selection-bar">
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
          <article v-for="record in filteredRecords" :key="record.id" class="record-item">
            <el-checkbox
              :model-value="selectedIds.includes(record.id)"
              :aria-label="`选择问题：${record.question}`"
              @click.stop
              @change="(checked) => toggleRecord(record.id, checked)"
            />
            <button class="record-question" type="button" @click="useQuestion(record.question)">
              <strong>{{ record.question }}</strong>
              <span>
                {{ knowledgeBaseName(record.knowledge_base_id) }}
                <i aria-hidden="true">·</i>
                {{ formatDate(record.created_at) }}
              </span>
            </button>
            <el-button
              class="delete-button"
              :icon="Delete"
              text
              circle
              type="danger"
              :loading="deletingId === record.id"
              :aria-label="`删除问题：${record.question}`"
              title="删除这条历史"
              @click="confirmDelete(record)"
            />
          </article>

          <el-empty
            v-if="!filteredRecords.length && !loading"
            description="暂无符合条件的提问记录"
          />
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Delete, Refresh, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { deleteQaRecord, deleteQaRecords, listQaRecords } from "../api/qaHistory";
import HomeParticleBackground from "../components/home/HomeParticleBackground.vue";
import KnowledgeBaseOptions from "../components/knowledge/KnowledgeBaseOptions.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const router = useRouter();
const healthOnline = ref(false);
const loading = ref(false);
const deletingId = ref(null);
const batchDeleting = ref(false);
const records = ref([]);
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
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
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
  width: min(980px, calc(100% - 40px));
  margin: 70px auto 0;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}

.page-head h1 {
  margin: 0;
  color: #13243c;
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(36px, 5vw, 54px);
  font-weight: 600;
  letter-spacing: -0.04em;
}

.history-panel {
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
  grid-template-columns: minmax(220px, 1fr) minmax(180px, 240px) auto;
  align-items: center;
  gap: 12px;
  padding: 18px;
  border-bottom: 1px solid rgba(170, 194, 222, 0.4);
}

.filters > span {
  color: #8997a9;
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 11px;
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
}

.record-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 4px 12px 4px 20px;
  border-bottom: 1px solid rgba(174, 198, 225, 0.34);
  transition: background 0.18s ease;
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
  text-overflow: ellipsis;
  white-space: nowrap;
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
    width: min(100% - 24px, 980px);
    margin-top: 48px;
  }

  .page-head {
    align-items: center;
  }

  .page-head .el-button {
    align-self: center;
  }

  .filters {
    grid-template-columns: 1fr;
  }

  .filters > span {
    text-align: right;
  }

  .selection-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .selection-bar > div {
    justify-content: space-between;
  }
}
</style>

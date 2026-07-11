<template>
  <div class="document-upload-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <el-alert
        v-if="!userStore.isLoggedIn"
        title="当前为游客浏览模式"
        description="你可以查看页面；上传、刷新文档或访问个人数据时会先跳转到登录页面。"
        type="info"
        show-icon
        :closable="false"
        class="guest-alert"
      />

      <section class="page-head">
        <div>
          <el-tag effect="plain">我的资料</el-tag>
          <h1>文档上传</h1>
          <p>选择当前知识库后上传资料，后端会保存文件、解析文本、切分片段并写入向量库。</p>
        </div>
        <el-button type="primary" plain @click="loadDocuments">刷新文档</el-button>
      </section>

      <section class="upload-layout">
        <aside class="side-stack">
          <KnowledgeBasePanel
            v-model="knowledgeBaseId"
            :bases="knowledgeBases"
            :loaded="knowledgeLoaded"
          />
          <section class="status-card">
            <div>
              <p>后端状态</p>
              <h2>{{ healthOnline ? "在线" : "未连接" }}</h2>
            </div>
            <el-tag :type="healthOnline ? 'success' : 'info'" effect="light">
              /api/health
            </el-tag>
          </section>
        </aside>

        <div class="main-stack">
          <UploadPanel :knowledge-base-id="knowledgeBaseId" @uploaded="afterUpload" />

          <section class="documents-card">
            <div class="card-head">
              <div>
                <p>文档列表</p>
                <h2>当前知识库文件</h2>
              </div>
              <span>{{ documents.length }} 个</span>
            </div>

            <el-table
              v-loading="documentsLoading"
              :data="documents"
              :empty-text="knowledgeBaseId ? '暂无文档，先上传一份资料。' : '请先创建并选择知识库。'"
              class="documents-table"
            >
              <el-table-column label="文件" min-width="220">
                <template #default="{ row }">
                  <strong class="file-name">{{ row.file_name }}</strong>
                  <span class="file-meta">{{ row.file_type }} · {{ formatSize(row.file_size) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="120">
                <template #default="{ row }">
                  <el-tag :type="statusType(row.parse_status)" effect="light">
                    {{ statusText(row.parse_status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="chunk_count" label="片段" width="90" />
              <el-table-column label="处理结果" min-width="280">
                <template #default="{ row }">
                  <span :class="row.error_message ? 'failure-message' : 'result-message'">
                    {{ row.error_message || statusDescription(row.parse_status) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="230" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openDocument(row)">查看</el-button>
                  <el-button
                    link
                    type="primary"
                    :disabled="row.parse_status === 'processing'"
                    @click="rebuildIndex(row)"
                  >
                    重建
                  </el-button>
                  <el-button link type="danger" @click="removeDocument(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { deleteDocument, getDocument, listDocuments, reindexDocument } from "../api/documents";
import UploadPanel from "../components/documents/UploadPanel.vue";
import KnowledgeBasePanel from "../components/knowledge/KnowledgeBasePanel.vue";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const router = useRouter();
const userStore = useUserStore();
const healthOnline = ref(false);
const knowledgeBaseId = ref(null);
const knowledgeBases = ref([]);
const knowledgeLoaded = ref(false);
const documents = ref([]);
const documentsLoading = ref(false);
const processingTimers = new Map();

onMounted(async () => {
  checkHealth();
  if (!userStore.isLoggedIn) {
    knowledgeLoaded.value = true;
    return;
  }
  await loadKnowledgeBases();
  await loadDocuments();
});

watch(knowledgeBaseId, () => {
  if (userStore.isLoggedIn) {
    loadDocuments();
  }
});

onBeforeUnmount(() => {
  processingTimers.forEach((timer) => window.clearTimeout(timer));
  processingTimers.clear();
});

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadKnowledgeBases() {
  try {
    knowledgeBases.value = await listKnowledgeBases();
    const selectionStillExists = knowledgeBases.value.some((base) => base.id === knowledgeBaseId.value);
    knowledgeBaseId.value = selectionStillExists ? knowledgeBaseId.value : (knowledgeBases.value[0]?.id ?? null);
  } catch {
    knowledgeBases.value = [];
    knowledgeBaseId.value = null;
  } finally {
    knowledgeLoaded.value = true;
  }
}

async function loadDocuments() {
  if (!knowledgeBaseId.value) {
    documents.value = [];
    return;
  }

  documentsLoading.value = true;
  try {
    documents.value = await listDocuments({ knowledge_base_id: knowledgeBaseId.value });
  } catch (error) {
    documents.value = [];
    ElMessage.error(error.message);
  } finally {
    documentsLoading.value = false;
  }
}

function afterUpload(document) {
  loadDocuments();
  scheduleProcessingCheck(document.id);
}

function scheduleProcessingCheck(documentId, attempt = 0) {
  const previousTimer = processingTimers.get(documentId);
  if (previousTimer) {
    window.clearTimeout(previousTimer);
  }

  const timer = window.setTimeout(async () => {
    try {
      const latest = await getDocument(documentId);
      const index = documents.value.findIndex((item) => item.id === documentId);
      if (index >= 0) {
        documents.value[index] = latest;
      } else if (latest.knowledge_base_id === knowledgeBaseId.value) {
        documents.value.unshift(latest);
      }

      if (latest.parse_status === "failed") {
        processingTimers.delete(documentId);
        ElMessage.error(latest.error_message || "文档处理失败，请重建索引或重新上传。");
        return;
      }

      if (latest.parse_status === "completed") {
        processingTimers.delete(documentId);
        ElMessage.success(`“${latest.file_name}”已完成解析并写入知识库。`);
        return;
      }

      if (attempt < 29) {
        scheduleProcessingCheck(documentId, attempt + 1);
      } else {
        processingTimers.delete(documentId);
        ElMessage.warning("文档仍在后台处理中，请稍后刷新列表查看结果。");
      }
    } catch {
      processingTimers.delete(documentId);
    }
  }, 2000);

  processingTimers.set(documentId, timer);
}

async function rebuildIndex(row) {
  try {
    await reindexDocument(row.id);
    ElMessage.success("已提交重建索引任务。");
    loadDocuments();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function removeDocument(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档“${row.file_name}”吗？原始文件、文本片段和向量数据都会被删除，且无法恢复。`,
      "确认删除文档",
      {
        confirmButtonText: "确定删除",
        cancelButtonText: "取消",
        type: "warning",
      },
    );
    await deleteDocument(row.id);
    ElMessage.success("文档已删除。");
    await loadDocuments();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.message || "删除文档失败。");
    }
  }
}

function openDocument(row) {
  router.push({ name: "document-detail", params: { documentId: row.id } });
}

function statusText(status) {
  const map = {
    pending: "等待中",
    processing: "处理中",
    completed: "已完成",
    failed: "失败",
  };
  return map[status] || status || "未知";
}

function statusType(status) {
  const map = {
    pending: "info",
    processing: "warning",
    completed: "success",
    failed: "danger",
  };
  return map[status] || "info";
}

function statusDescription(status) {
  const map = {
    pending: "等待后台处理。",
    processing: "正在解析、切分并生成向量。",
    completed: "文档已写入知识库，可用于检索。",
    failed: "处理失败，请重建索引或重新上传。",
  };
  return map[status] || "暂无处理信息。";
}

function formatSize(size) {
  if (!size) {
    return "0 B";
  }

  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<style scoped>
.document-upload-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  width: min(1180px, calc(100% - 32px));
  margin: 44px auto 0;
}

.guest-alert {
  margin-bottom: 20px;
}

.page-head,
.card-head,
.status-card {
  display: flex;
  align-items: center;
}

.page-head {
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 22px;
}

.page-head h1 {
  margin: 12px 0 8px;
  color: var(--cm-heading);
  font-size: 34px;
}

.page-head p {
  margin: 0;
  color: var(--cm-muted);
  line-height: 1.7;
}

.upload-layout {
  display: grid;
  grid-template-columns: minmax(280px, 0.82fr) minmax(0, 1.18fr);
  gap: 20px;
  align-items: start;
}

.side-stack,
.main-stack {
  display: grid;
  gap: 20px;
}

.status-card,
.documents-card {
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.status-card {
  justify-content: space-between;
  gap: 16px;
  padding: 22px;
}

.documents-card {
  display: grid;
  gap: 18px;
  padding: 22px;
}

.status-card p,
.card-head p {
  margin: 0 0 6px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.status-card h2,
.card-head h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 22px;
}

.card-head {
  justify-content: space-between;
  gap: 16px;
}

.card-head span {
  color: var(--cm-muted);
  font-size: 13px;
}

.documents-table {
  width: 100%;
}

.file-name,
.file-meta {
  display: block;
}

.failure-message {
  color: var(--el-color-danger);
  line-height: 1.5;
}

.result-message {
  color: var(--cm-muted);
  line-height: 1.5;
}

.file-name {
  color: var(--cm-heading);
}

.file-meta {
  margin-top: 4px;
  color: var(--cm-muted);
  font-size: 13px;
}

@media (max-width: 980px) {
  .upload-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .document-upload-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 1180px);
    margin-top: 32px;
  }

  .page-head,
  .card-head,
  .status-card {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>

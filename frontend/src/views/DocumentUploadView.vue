<template>
  <div class="document-upload-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
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
              empty-text="暂无文档，先上传一份资料。"
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
              <el-table-column label="操作" width="170" fixed="right">
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
import { onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { listDocuments, reindexDocument } from "../api/documents";
import UploadPanel from "../components/documents/UploadPanel.vue";
import KnowledgeBasePanel from "../components/knowledge/KnowledgeBasePanel.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const router = useRouter();
const healthOnline = ref(false);
const knowledgeBaseId = ref(1);
const knowledgeBases = ref([]);
const knowledgeLoaded = ref(false);
const documents = ref([]);
const documentsLoading = ref(false);

onMounted(async () => {
  checkHealth();
  await loadKnowledgeBases();
  await loadDocuments();
});

watch(knowledgeBaseId, () => {
  loadDocuments();
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
    if (knowledgeBases.value.length) {
      knowledgeBaseId.value = knowledgeBases.value[0].id;
    }
  } catch {
    knowledgeBases.value = [];
  } finally {
    knowledgeLoaded.value = true;
  }
}

async function loadDocuments() {
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

function afterUpload() {
  loadDocuments();
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

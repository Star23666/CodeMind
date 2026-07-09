<template>
  <div class="document-detail-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <el-breadcrumb separator="/" class="breadcrumb">
        <el-breadcrumb-item :to="{ name: 'home' }">AI 问答</el-breadcrumb-item>
        <el-breadcrumb-item :to="{ name: 'documents' }">文档上传</el-breadcrumb-item>
        <el-breadcrumb-item>{{ document?.file_name || "文档详情" }}</el-breadcrumb-item>
      </el-breadcrumb>

      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <section v-loading="loading" class="reader-layout">
        <aside class="chunk-sidebar">
          <div class="document-summary">
            <el-tag :type="statusType(document?.parse_status)" effect="light">
              {{ statusText(document?.parse_status) }}
            </el-tag>
            <h1>{{ document?.file_name || "正在读取文档" }}</h1>
            <p>{{ document?.file_type || "-" }} · {{ document?.chunk_count || 0 }} 个片段</p>
          </div>

          <div class="chunk-list">
            <button
              v-for="chunk in chunks"
              :key="chunk.id"
              :class="{ active: selectedChunk?.id === chunk.id }"
              type="button"
              @click="openChunk(chunk)"
            >
              <strong>片段 {{ chunk.chunk_index }}</strong>
              <span>{{ previewText(chunk.chunk_text) }}</span>
            </button>
          </div>

          <el-empty v-if="!chunks.length && !loading" description="该文档还没有可阅读片段。" />
        </aside>

        <article class="reader">
          <div v-if="selectedChunk" class="reader-head">
            <div>
              <p>chunk {{ selectedChunk.chunk_index }}</p>
              <h2>{{ document?.file_name }}</h2>
            </div>
            <el-tag v-if="selectedChunk.page_no" effect="plain">
              第 {{ selectedChunk.page_no }} 页
            </el-tag>
          </div>

          <p v-if="selectedChunk" class="chunk-text">{{ selectedChunk.chunk_text }}</p>
          <el-empty v-else description="请选择左侧片段查看内容。" />
        </article>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { getDocument, getDocumentChunk, listDocumentChunks } from "../api/documents";
import AppHeader from "../components/layout/AppHeader.vue";

const route = useRoute();
const router = useRouter();
const healthOnline = ref(false);
const loading = ref(false);
const error = ref("");
const document = ref(null);
const chunks = ref([]);
const selectedChunk = ref(null);

onMounted(() => {
  checkHealth();
});

watch(
  () => [route.params.documentId, route.params.chunkId],
  () => {
    loadDocumentDetail();
  },
  { immediate: true },
);

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadDocumentDetail() {
  const documentId = Number(route.params.documentId);
  const chunkId = route.params.chunkId ? Number(route.params.chunkId) : null;

  loading.value = true;
  error.value = "";
  try {
    const [documentData, chunkList] = await Promise.all([
      getDocument(documentId),
      listDocumentChunks(documentId),
    ]);
    document.value = documentData;
    chunks.value = chunkList;

    if (chunkId) {
      selectedChunk.value = await getDocumentChunk(documentId, chunkId);
      return;
    }

    selectedChunk.value = chunkList[0] || null;
  } catch (loadError) {
    error.value = loadError.message;
    document.value = null;
    chunks.value = [];
    selectedChunk.value = null;
  } finally {
    loading.value = false;
  }
}

function openChunk(chunk) {
  router.push({
    name: "document-chunk",
    params: {
      documentId: chunk.document_id,
      chunkId: chunk.id,
    },
  });
}

function previewText(text = "") {
  return text.length > 64 ? `${text.slice(0, 64)}...` : text;
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
</script>

<style scoped>
.document-detail-view {
  min-height: 100vh;
  padding: 16px 0 56px;
}

.page {
  display: grid;
  gap: 18px;
  width: min(1180px, calc(100% - 32px));
  margin: 44px auto 0;
}

.breadcrumb {
  color: var(--cm-muted);
}

.reader-layout {
  display: grid;
  grid-template-columns: minmax(260px, 0.42fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.chunk-sidebar,
.reader {
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.chunk-sidebar {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.document-summary h1 {
  margin: 12px 0 8px;
  color: var(--cm-heading);
  font-size: 24px;
  line-height: 1.25;
}

.document-summary p {
  margin: 0;
  color: var(--cm-muted);
}

.chunk-list {
  display: grid;
  gap: 10px;
  max-height: 620px;
  overflow: auto;
}

.chunk-list button {
  display: grid;
  gap: 6px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  color: var(--cm-text);
  background: var(--cm-surface-soft);
  text-align: left;
  cursor: pointer;
}

.chunk-list button.active,
.chunk-list button:hover {
  border-color: var(--cm-primary);
  background: var(--cm-primary-soft);
}

.chunk-list strong {
  color: var(--cm-heading);
}

.chunk-list span {
  color: var(--cm-muted);
  font-size: 13px;
  line-height: 1.5;
}

.reader {
  display: grid;
  gap: 18px;
  min-height: 520px;
  padding: 24px;
}

.reader-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.reader-head p {
  margin: 0 0 6px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.reader-head h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 24px;
}

.chunk-text {
  margin: 0;
  color: var(--cm-text);
  font-size: 16px;
  line-height: 1.9;
  white-space: pre-wrap;
}

@media (max-width: 880px) {
  .reader-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .document-detail-view {
    padding-top: 8px;
  }

  .page {
    width: min(100% - 20px, 1180px);
    margin-top: 32px;
  }
}
</style>

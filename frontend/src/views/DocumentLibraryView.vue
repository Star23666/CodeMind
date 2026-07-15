<template>
  <div class="library-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-tag effect="plain">文档管理</el-tag>
          <h1>我的文档库</h1>
          <p>通过明确的条件筛选私人文档，点击文档可直接查看原文件。</p>
        </div>
        <div class="head-actions">
          <el-button :icon="Refresh" :loading="loading" @click="loadData">刷新</el-button>
          <el-button type="primary" :icon="Upload" @click="goUpload">上传文档</el-button>
        </div>
      </section>

      <section class="filter-card">
        <div class="filter-row primary-filters">
          <label>
            <span>关键词匹配</span>
            <el-input v-model="keyword" clearable :prefix-icon="Search" placeholder="匹配文件名关键词" />
          </label>
          <label>
            <span>文件类型</span>
            <el-select v-model="selectedTypes" multiple collapse-tags clearable placeholder="全部类型">
              <el-option v-for="type in fileTypes" :key="type" :label="typeLabel(type)" :value="type" />
            </el-select>
          </label>
        </div>

        <div class="kb-filter">
          <div class="filter-title">
            <span>所属知识库</span>
            <div>
              <el-button link type="primary" @click="selectAllBases">全选</el-button>
              <el-button link @click="selectedBaseIds = []">清空</el-button>
            </div>
          </div>
          <el-checkbox-group v-model="selectedBaseIds" class="kb-options">
            <el-checkbox v-for="base in knowledgeBases" :key="base.id" :value="base.id">
              {{ base.name }}
            </el-checkbox>
          </el-checkbox-group>
          <el-empty v-if="!knowledgeBases.length && !loading" description="暂无知识库" :image-size="54" />
        </div>
      </section>

      <section class="documents-card">
        <div class="card-head">
          <div>
            <p>筛选结果</p>
            <h2>{{ filteredDocuments.length }} 个文档</h2>
          </div>
          <span>关键词仅匹配文件名，不进行语义检索</span>
        </div>

        <div v-loading="loading" class="document-list">
          <article
            v-for="document in filteredDocuments"
            :key="document.id"
            class="document-row"
            tabindex="0"
            @click="openDocument(document)"
            @keydown.enter="openDocument(document)"
          >
            <span class="file-icon">{{ fileBadge(document.file_type) }}</span>
            <div class="file-copy">
              <strong>{{ document.file_name }}</strong>
              <span>{{ knowledgeBaseName(document.knowledge_base_id) }} · {{ typeLabel(document.file_type) }} · {{ formatSize(document.file_size) }}</span>
              <small v-if="document.error_message" class="error-message">{{ document.error_message }}</small>
            </div>
            <div class="file-status">
              <el-tag :type="statusType(document.parse_status)" effect="light">{{ statusText(document.parse_status) }}</el-tag>
              <span>{{ document.chunk_count }} 个片段</span>
            </div>
            <div class="row-actions" @click.stop>
              <el-button link type="primary" @click="openDocument(document)">查看文档</el-button>
              <el-button link @click="openChunks(document)">查看切片</el-button>
              <el-button
                v-if="['pending', 'processing'].includes(document.parse_status)"
                link
                type="warning"
                @click="cancelProcessing(document)"
              >取消处理</el-button>
              <el-button
                link
                type="primary"
                :disabled="['pending', 'processing'].includes(document.parse_status)"
                @click="rebuild(document)"
              >重建</el-button>
              <el-button link type="danger" @click="remove(document)">删除</el-button>
            </div>
          </article>

          <el-empty
            v-if="!filteredDocuments.length && !loading"
            :description="documents.length ? '没有符合当前筛选条件的文档' : '暂无文档，先上传一份资料吧'"
          >
            <el-button type="primary" @click="goUpload">去上传</el-button>
          </el-empty>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Refresh, Search, Upload } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import {
  cancelDocumentProcessing,
  deleteDocument,
  listDocuments,
  reindexDocument,
} from "../api/documents";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import AppHeader from "../components/layout/AppHeader.vue";

const router = useRouter();
const healthOnline = ref(false);
const loading = ref(false);
const documents = ref([]);
const knowledgeBases = ref([]);
const keyword = ref("");
const selectedTypes = ref([]);
const selectedBaseIds = ref([]);

const fileTypes = computed(() => [...new Set(documents.value.map((item) => item.file_type))].sort());
const filteredDocuments = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase();
  return documents.value.filter((document) => {
    const matchesKeyword = !query || document.file_name.toLocaleLowerCase().includes(query);
    const matchesType = !selectedTypes.value.length || selectedTypes.value.includes(document.file_type);
    const matchesBase = selectedBaseIds.value.includes(document.knowledge_base_id);
    return matchesKeyword && matchesType && matchesBase;
  });
});

onMounted(() => {
  checkHealth();
  loadData();
});

async function checkHealth() {
  try {
    healthOnline.value = (await getHealth()).status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadData() {
  loading.value = true;
  try {
    const previousSelection = new Set(selectedBaseIds.value);
    const [bases, docs] = await Promise.all([listKnowledgeBases(), listDocuments()]);
    knowledgeBases.value = bases;
    documents.value = docs;
    const retained = bases.filter((base) => previousSelection.has(base.id)).map((base) => base.id);
    selectedBaseIds.value = previousSelection.size ? retained : bases.map((base) => base.id);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function selectAllBases() {
  selectedBaseIds.value = knowledgeBases.value.map((base) => base.id);
}

function knowledgeBaseName(id) {
  return knowledgeBases.value.find((base) => base.id === id)?.name || "未知知识库";
}

function openDocument(document) {
  router.push({ name: "document-viewer", params: { documentId: document.id } });
}

function openChunks(document) {
  router.push({ name: "document-detail", params: { documentId: document.id } });
}

async function rebuild(document) {
  try {
    await reindexDocument(document.id);
    ElMessage.success("已提交重建索引任务。");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function cancelProcessing(document) {
  try {
    await cancelDocumentProcessing(document.id);
    ElMessage.success("已取消文档处理任务。");
    await loadData();
  } catch (error) {
    ElMessage.error(error.message);
  }
}

async function remove(document) {
  try {
    await ElMessageBox.confirm(
      `确定删除文档“${document.file_name}”吗？原文件、文本片段和向量数据都会被删除，且无法恢复。`,
      "确认删除文档",
      { confirmButtonText: "确定删除", cancelButtonText: "取消", type: "warning" },
    );
    await deleteDocument(document.id);
    documents.value = documents.value.filter((item) => item.id !== document.id);
    ElMessage.success("文档已删除。");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.message || "删除文档失败。");
    }
  }
}

function goUpload() { router.push({ name: "documents" }); }
function fileBadge(type) { return (type || "FILE").slice(0, 4).toUpperCase(); }
function typeLabel(type) { return ({ md: "Markdown", markdown: "Markdown", txt: "TXT", pdf: "PDF", docx: "Word" })[type] || String(type).toUpperCase(); }
function statusText(status) { return ({ pending: "等待中", processing: "处理中", completed: "已完成", failed: "失败", cancelled: "已取消" })[status] || status; }
function statusType(status) { return ({ pending: "info", processing: "warning", completed: "success", failed: "danger", cancelled: "info" })[status] || "info"; }
function formatSize(size) {
  if (!size) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<style scoped>
.library-view { min-height: 100vh; padding: 16px 0 56px; }
.page { display: grid; gap: 20px; width: min(1180px, calc(100% - 32px)); margin: 44px auto 0; }
.page-head, .head-actions, .filter-row, .filter-title, .card-head, .document-row, .file-status, .row-actions { display: flex; align-items: center; }
.page-head, .filter-title, .card-head { justify-content: space-between; gap: 18px; }
.page-head h1 { margin: 12px 0 8px; color: var(--cm-heading); font-size: 34px; }
.page-head p { margin: 0; color: var(--cm-muted); }
.head-actions, .row-actions { gap: 8px; }
.filter-card, .documents-card { display: grid; gap: 20px; padding: 22px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.primary-filters { gap: 16px; }
.primary-filters label { display: grid; min-width: 0; flex: 1; gap: 8px; color: var(--cm-heading); font-size: 13px; font-weight: 800; }
.kb-filter { display: grid; gap: 12px; padding-top: 16px; border-top: 1px solid var(--cm-border); }
.filter-title > span { color: var(--cm-heading); font-size: 13px; font-weight: 800; }
.kb-options { display: flex; flex-wrap: wrap; gap: 4px 18px; }
.card-head p { margin: 0 0 5px; color: var(--cm-primary); font-size: 13px; font-weight: 800; }
.card-head h2 { margin: 0; color: var(--cm-heading); }
.card-head > span { color: var(--cm-muted); font-size: 13px; }
.document-list { min-height: 180px; }
.document-row { gap: 16px; padding: 16px 0; border-top: 1px solid var(--cm-border); cursor: pointer; }
.document-row:hover { background: color-mix(in srgb, var(--cm-primary-soft) 52%, transparent); }
.file-icon { display: grid; width: 52px; height: 52px; flex: 0 0 auto; place-items: center; border-radius: var(--cm-radius); color: var(--cm-primary); background: var(--cm-primary-soft); font-size: 12px; font-weight: 900; }
.file-copy { display: grid; min-width: 0; flex: 1; gap: 5px; }
.file-copy strong { overflow: hidden; color: var(--cm-heading); text-overflow: ellipsis; white-space: nowrap; }
.file-copy span, .file-copy small, .file-status span { color: var(--cm-muted); font-size: 13px; }
.file-copy .error-message { color: var(--cm-danger); }
.file-status { min-width: 100px; flex-direction: column; gap: 6px; }
.row-actions { flex-wrap: wrap; justify-content: flex-end; }
@media (max-width: 900px) { .document-row { align-items: flex-start; flex-wrap: wrap; } .file-copy { min-width: calc(100% - 72px); } .file-status { align-items: flex-start; } .row-actions { width: 100%; justify-content: flex-start; padding-left: 68px; } }
@media (max-width: 640px) { .library-view { padding-top: 8px; } .page { width: min(100% - 20px, 1180px); margin-top: 32px; } .page-head, .primary-filters, .card-head { align-items: stretch; flex-direction: column; } .head-actions { flex-wrap: wrap; } .row-actions { padding-left: 0; } }
</style>

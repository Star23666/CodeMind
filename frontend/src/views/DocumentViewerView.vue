<template>
  <div class="viewer-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <el-breadcrumb separator="/" class="breadcrumb">
        <el-breadcrumb-item :to="{ name: 'document-library' }">文档库</el-breadcrumb-item>
        <el-breadcrumb-item>{{ document?.file_name || "文档查看" }}</el-breadcrumb-item>
      </el-breadcrumb>

      <section class="viewer-head">
        <div>
          <el-tag :type="statusType(document?.parse_status)" effect="light">
            {{ statusText(document?.parse_status) }}
          </el-tag>
          <el-tag v-if="document?.knowledge_base_visibility === 'public'" effect="plain">公共资料</el-tag>
          <h1>{{ document?.file_name || "正在读取文档" }}</h1>
          <p v-if="document">{{ typeLabel(document.file_type) }} · {{ formatSize(document.file_size) }}</p>
          <p v-if="document?.knowledge_base_visibility === 'public'">
            上传者：{{ document.uploader_username || `用户 ${document.owner_id}` }}
          </p>
        </div>
        <div class="head-actions">
          <el-button @click="openChunks">查看切片</el-button>
          <el-button type="primary" :icon="Download" :disabled="!fileBuffer" @click="downloadFile">下载原文件</el-button>
        </div>
      </section>

      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />

      <section v-loading="loading" class="viewer-card">
        <iframe v-if="viewerType === 'pdf' && objectUrl" :src="objectUrl" class="pdf-viewer" title="PDF 文档预览" />

        <MarkdownContent
          v-else-if="viewerType === 'markdown'"
          class="rendered-content markdown-body"
          :content="textContent"
        />

        <article v-else-if="viewerType === 'docx'" class="rendered-content docx-body" v-html="renderedHtml" />

        <pre v-else-if="viewerType === 'text'" class="text-viewer">{{ textContent }}</pre>

        <el-empty v-else-if="!loading && !error" description="暂不支持在线预览此文件类型">
          <el-button type="primary" :disabled="!fileBuffer" @click="downloadFile">下载查看</el-button>
        </el-empty>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Download } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";
import DOMPurify from "dompurify";
import * as mammoth from "mammoth";
import { getDocument, getDocumentContent } from "../api/documents";
import { getHealth } from "../api/health";
import MarkdownContent from "../components/common/MarkdownContent.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const route = useRoute();
const router = useRouter();
const healthOnline = ref(false);
const loading = ref(false);
const error = ref("");
const document = ref(null);
const viewerType = ref("");
const renderedHtml = ref("");
const textContent = ref("");
const objectUrl = ref("");
const fileBuffer = ref(null);

onMounted(checkHealth);
watch(() => route.params.documentId, loadDocument, { immediate: true });
onBeforeUnmount(revokeObjectUrl);

async function checkHealth() {
  try { healthOnline.value = (await getHealth()).status === "ok"; }
  catch { healthOnline.value = false; }
}

async function loadDocument() {
  const documentId = Number(route.params.documentId);
  loading.value = true;
  error.value = "";
  resetViewer();

  try {
    const [metadata, buffer] = await Promise.all([
      getDocument(documentId),
      getDocumentContent(documentId),
    ]);
    document.value = metadata;
    fileBuffer.value = buffer;
    await renderFile(metadata.file_type, buffer);
  } catch (loadError) {
    document.value = null;
    error.value = loadError.message || "原文件读取失败。";
  } finally {
    loading.value = false;
  }
}

async function renderFile(type, buffer) {
  const normalizedType = String(type).toLowerCase();
  if (normalizedType === "pdf") {
    viewerType.value = "pdf";
    objectUrl.value = URL.createObjectURL(new Blob([buffer], { type: "application/pdf" }));
    return;
  }

  if (["md", "markdown"].includes(normalizedType)) {
    viewerType.value = "markdown";
    textContent.value = new TextDecoder("utf-8").decode(buffer);
    return;
  }

  if (normalizedType === "docx") {
    viewerType.value = "docx";
    const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
    renderedHtml.value = DOMPurify.sanitize(result.value);
    if (result.messages.length) {
      ElMessage.info("Word 文档已转换为网页排版，个别复杂样式可能有所简化。");
    }
    return;
  }

  if (normalizedType === "txt") {
    viewerType.value = "text";
    textContent.value = new TextDecoder("utf-8").decode(buffer);
    return;
  }

  viewerType.value = "unsupported";
}

function resetViewer() {
  revokeObjectUrl();
  viewerType.value = "";
  renderedHtml.value = "";
  textContent.value = "";
  fileBuffer.value = null;
}

function revokeObjectUrl() {
  if (objectUrl.value) {
    URL.revokeObjectURL(objectUrl.value);
    objectUrl.value = "";
  }
}

function downloadFile() {
  if (!fileBuffer.value || !document.value) return;
  const url = URL.createObjectURL(new Blob([fileBuffer.value]));
  const link = window.document.createElement("a");
  link.href = url;
  link.download = document.value.file_name;
  link.click();
  URL.revokeObjectURL(url);
}

function openChunks() {
  if (document.value) {
    router.push({ name: "document-detail", params: { documentId: document.value.id } });
  }
}

function typeLabel(type) { return ({ md: "Markdown", markdown: "Markdown", txt: "TXT", pdf: "PDF", docx: "Word" })[type] || String(type).toUpperCase(); }
function statusText(status) { return ({ pending: "等待中", processing: "处理中", completed: "已完成", failed: "失败" })[status] || status || "未知"; }
function statusType(status) { return ({ pending: "info", processing: "warning", completed: "success", failed: "danger" })[status] || "info"; }
function formatSize(size) {
  if (!size) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<style scoped>
.viewer-view { min-height: 100vh; padding: 16px 0 56px; }
.page { display: grid; gap: 18px; width: min(1180px, calc(100% - 32px)); margin: 44px auto 0; }
.viewer-head, .head-actions { display: flex; align-items: center; }
.viewer-head { justify-content: space-between; gap: 20px; }
.viewer-head h1 { margin: 12px 0 7px; color: var(--cm-heading); font-size: 30px; overflow-wrap: anywhere; }
.viewer-head p { margin: 0; color: var(--cm-muted); }
.head-actions { gap: 10px; flex: 0 0 auto; }
.viewer-card { min-height: 620px; overflow: hidden; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.pdf-viewer { display: block; width: 100%; height: 78vh; min-height: 620px; border: 0; background: #fff; }
.rendered-content, .text-viewer { width: min(900px, calc(100% - 48px)); margin: 0 auto; padding: 42px 0 64px; }
.text-viewer { color: var(--cm-text); font: 16px/1.9 "SFMono-Regular", Consolas, "Liberation Mono", monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.rendered-content { color: var(--cm-text); font-size: 16px; line-height: 1.85; }
.rendered-content :deep(h1), .rendered-content :deep(h2), .rendered-content :deep(h3) { margin: 1.5em 0 .7em; color: var(--cm-heading); line-height: 1.35; }
.rendered-content :deep(h1) { padding-bottom: .35em; border-bottom: 1px solid var(--cm-border); font-size: 2em; }
.rendered-content :deep(h2) { font-size: 1.5em; }
.rendered-content :deep(p), .rendered-content :deep(li) { line-height: 1.85; }
.rendered-content :deep(a) { color: var(--cm-primary); text-decoration: underline; }
.rendered-content :deep(blockquote) { margin-left: 0; padding: 4px 18px; border-left: 4px solid var(--cm-primary); color: var(--cm-muted); background: var(--cm-surface-soft); }
.rendered-content :deep(pre) { overflow: auto; padding: 16px; border-radius: var(--cm-radius); background: #111827; color: #e5e7eb; }
.rendered-content :deep(code) { padding: .15em .35em; border-radius: 4px; background: var(--cm-primary-soft); font-family: "SFMono-Regular", Consolas, monospace; }
.rendered-content :deep(pre code) { padding: 0; background: transparent; }
.rendered-content :deep(table) { width: 100%; border-collapse: collapse; }
.rendered-content :deep(th), .rendered-content :deep(td) { padding: 10px 12px; border: 1px solid var(--cm-border); text-align: left; }
.rendered-content :deep(img) { max-width: 100%; }
.docx-body :deep(table) { margin: 18px 0; }
@media (max-width: 700px) { .viewer-view { padding-top: 8px; } .page { width: min(100% - 20px, 1180px); margin-top: 32px; } .viewer-head { align-items: stretch; flex-direction: column; } .head-actions { flex-wrap: wrap; } .rendered-content, .text-viewer { width: calc(100% - 30px); padding-top: 24px; } }
</style>

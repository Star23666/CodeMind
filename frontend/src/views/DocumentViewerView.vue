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
        <section v-if="viewerType === 'pdf'" class="pdf-viewer" aria-label="PDF 文档预览">
          <el-alert
            v-if="pdfLoadError"
            :title="pdfLoadError"
            type="warning"
            show-icon
            :closable="false"
          >
            <template #default>
              <el-button link type="primary" :disabled="!fileBuffer" @click="downloadFile">下载原文件查看</el-button>
            </template>
          </el-alert>
          <div v-else class="pdf-pages">
            <figure v-for="page in pdfPages" :key="page" class="pdf-page">
              <figcaption>第 {{ page }} 页</figcaption>
              <canvas :ref="(element) => registerPdfCanvas(page, element)" :aria-label="`PDF 第 ${page} 页`" />
            </figure>
          </div>
        </section>

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
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Download } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";
import DOMPurify from "dompurify";
import * as mammoth from "mammoth";
import { ElMessage } from "element-plus";
import { getDocument as loadPdfDocument, GlobalWorkerOptions } from "pdfjs-dist/build/pdf.mjs";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
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
const fileBuffer = ref(null);
const pdfPages = ref([]);
const pdfLoadError = ref("");
const pdfCanvasRefs = new Map();
let pdfDocument = null;
let pdfRenderVersion = 0;

GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

onMounted(checkHealth);
watch(() => route.params.documentId, loadDocument, { immediate: true });
onBeforeUnmount(resetPdfRenderer);

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
    await renderPdf(buffer);
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
  resetPdfRenderer();
  viewerType.value = "";
  renderedHtml.value = "";
  textContent.value = "";
  fileBuffer.value = null;
}

function registerPdfCanvas(pageNumber, element) {
  if (element) {
    pdfCanvasRefs.set(pageNumber, element);
  } else {
    pdfCanvasRefs.delete(pageNumber);
  }
}

async function renderPdf(buffer) {
  const renderVersion = ++pdfRenderVersion;
  pdfLoadError.value = "";
  try {
    const task = loadPdfDocument({ data: new Uint8Array(buffer.slice(0)) });
    const loadedDocument = await task.promise;
    if (renderVersion !== pdfRenderVersion) {
      loadedDocument.destroy();
      return;
    }

    pdfDocument = loadedDocument;
    pdfPages.value = Array.from({ length: loadedDocument.numPages }, (_, index) => index + 1);
    await nextTick();

    for (const pageNumber of pdfPages.value) {
      if (renderVersion !== pdfRenderVersion) return;
      const page = await loadedDocument.getPage(pageNumber);
      const canvas = pdfCanvasRefs.get(pageNumber);
      if (!canvas) continue;
      const baseViewport = page.getViewport({ scale: 1 });
      const targetWidth = Math.min(1200, Math.max(640, window.innerWidth - 96));
      const scale = Math.min(1.8, Math.max(1, targetWidth / baseViewport.width));
      const viewport = page.getViewport({ scale });
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("浏览器不支持 PDF 画布渲染。");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvasContext: context, viewport }).promise;

      if (pageNumber % 3 === 0) {
        await new Promise((resolve) => window.requestAnimationFrame(resolve));
      }
    }
  } catch (renderError) {
    if (renderVersion !== pdfRenderVersion) return;
    pdfPages.value = [];
    pdfLoadError.value = "PDF 在线预览失败，请下载原文件后查看。";
    ElMessage.warning(renderError?.message || "PDF 在线预览失败。");
  }
}

function resetPdfRenderer() {
  pdfRenderVersion += 1;
  pdfPages.value = [];
  pdfLoadError.value = "";
  pdfCanvasRefs.clear();
  if (pdfDocument) {
    pdfDocument.destroy();
    pdfDocument = null;
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
.pdf-viewer { min-height: 620px; padding: 20px; background: #edf1f6; }
.pdf-pages { display: grid; gap: 20px; justify-items: center; }
.pdf-page { display: grid; gap: 8px; width: min(100%, 1200px); margin: 0; color: var(--cm-muted); font-size: 13px; }
.pdf-page figcaption { padding-left: 2px; }
.pdf-page canvas { display: block; width: 100%; height: auto; border: 1px solid rgba(24, 45, 78, 0.12); background: #fff; box-shadow: 0 8px 22px rgba(24, 45, 78, 0.12); }
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

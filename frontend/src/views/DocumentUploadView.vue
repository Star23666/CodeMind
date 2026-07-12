<template>
  <div class="document-upload-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <el-alert
        v-if="!userStore.isLoggedIn"
        title="当前为游客浏览模式"
        description="你可以浏览页面；上传文件或进入私人文档库时会先跳转到登录页。"
        type="info"
        show-icon
        :closable="false"
        class="guest-alert"
      />

      <section class="page-head">
        <div>
          <el-tag effect="plain">我的资料</el-tag>
          <h1>文档上传</h1>
          <p>选择知识库并上传资料，系统会自动解析、切分并建立向量索引。</p>
        </div>
      </section>

      <section class="upload-layout">
        <aside class="side-stack">
          <KnowledgeBasePanel
            v-model="knowledgeBaseId"
            :bases="knowledgeBases"
            :loaded="knowledgeLoaded"
          />
        </aside>

        <div class="main-stack">
          <UploadPanel :knowledge-base-id="knowledgeBaseId" @uploaded="afterUpload" />

          <button class="library-entry" type="button" @click="openLibrary">
            <span class="entry-icon"><el-icon><FolderOpened /></el-icon></span>
            <span class="entry-copy">
              <small>文档管理</small>
              <strong>查看我的文档库</strong>
              <span>按文件名关键词、文件类型和所属知识库筛选，查看、重建或删除文档。</span>
            </span>
            <el-icon class="entry-arrow"><ArrowRight /></el-icon>
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { ArrowRight, FolderOpened } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { getDocument } from "../api/documents";
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
const processingTimers = new Map();

onMounted(async () => {
  checkHealth();
  if (!userStore.isLoggedIn) {
    knowledgeLoaded.value = true;
    return;
  }
  await loadKnowledgeBases();
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
    knowledgeBaseId.value = knowledgeBases.value[0]?.id ?? null;
  } catch (error) {
    knowledgeBases.value = [];
    knowledgeBaseId.value = null;
    ElMessage.error(error.message);
  } finally {
    knowledgeLoaded.value = true;
  }
}

function afterUpload(document) {
  scheduleProcessingCheck(document.id);
}

function scheduleProcessingCheck(documentId, attempt = 0) {
  const timer = window.setTimeout(async () => {
    try {
      const latest = await getDocument(documentId);
      if (latest.parse_status === "failed") {
        processingTimers.delete(documentId);
        ElMessage.error(latest.error_message || "文档处理失败，请前往文档库查看。");
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
        ElMessage.info("文档仍在后台处理，可前往文档库查看进度。");
      }
    } catch {
      if (attempt < 29) {
        scheduleProcessingCheck(documentId, attempt + 1);
      } else {
        processingTimers.delete(documentId);
        ElMessage.info("暂时无法读取处理状态，可前往文档库稍后查看。");
      }
    }
  }, 2000);
  processingTimers.set(documentId, timer);
}

function openLibrary() {
  router.push({ name: "document-library" });
}
</script>

<style scoped>
.document-upload-view { min-height: 100vh; padding: 16px 0 56px; }
.page { width: min(1180px, calc(100% - 32px)); margin: 44px auto 0; }
.guest-alert { margin-bottom: 20px; }
.page-head, .library-entry { display: flex; align-items: center; }
.page-head { justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.page-head h1 { margin: 12px 0 8px; color: var(--cm-heading); font-size: 34px; }
.page-head p { margin: 0; color: var(--cm-muted); line-height: 1.7; }
.upload-layout { display: grid; grid-template-columns: minmax(280px, .82fr) minmax(0, 1.18fr); gap: 20px; align-items: start; }
.side-stack, .main-stack { display: grid; gap: 20px; }
.library-entry { width: 100%; gap: 16px; padding: 22px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); color: inherit; background: linear-gradient(135deg, var(--cm-surface), var(--cm-primary-soft)); box-shadow: var(--cm-shadow); text-align: left; cursor: pointer; transition: transform .18s ease, border-color .18s ease; }
.library-entry:hover { transform: translateY(-2px); border-color: var(--cm-primary); }
.entry-icon { display: grid; width: 52px; height: 52px; flex: 0 0 auto; place-items: center; border-radius: var(--cm-radius); color: #fff; background: linear-gradient(135deg, var(--cm-primary), #38bdf8); font-size: 26px; }
.entry-copy { display: grid; min-width: 0; flex: 1; gap: 5px; }
.entry-copy small { color: var(--cm-primary); font-weight: 800; }
.entry-copy strong { color: var(--cm-heading); font-size: 21px; }
.entry-copy span { color: var(--cm-muted); line-height: 1.6; }
.entry-arrow { color: var(--cm-primary); font-size: 22px; }
@media (max-width: 980px) { .upload-layout { grid-template-columns: 1fr; } }
@media (max-width: 640px) { .document-upload-view { padding-top: 8px; } .page { width: min(100% - 20px, 1180px); margin-top: 32px; } .page-head { align-items: stretch; flex-direction: column; } }
</style>

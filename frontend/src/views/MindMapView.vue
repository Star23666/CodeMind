<template>
  <div class="mind-map-view">
    <AppHeader :health-online="healthOnline" />

    <main class="map-page">
      <header class="page-intro">
        <div>
          <p class="eyebrow">KNOWLEDGE ATLAS</p>
          <h1>把资料展开成一张可核对的知识地图</h1>
          <p class="intro-copy">
            每个节点都连接真实文档片段。先看结构，再沿着来源回到原文。
          </p>
        </div>
        <div class="intro-mark" aria-hidden="true">
          <span>MAP</span>
          <strong>{{ mapData?.node_count || "—" }}</strong>
          <small>节点</small>
        </div>
      </header>

      <section class="map-controls" aria-label="思维导图生成设置">
        <label>
          <span>知识库</span>
          <el-select
            v-model="knowledgeBaseId"
            placeholder="选择知识库"
            :disabled="loadingBases"
            @change="handleKnowledgeBaseChange"
          >
            <el-option
              v-for="base in knowledgeBases"
              :key="base.id"
              :label="base.name"
              :value="base.id"
            />
          </el-select>
        </label>

        <label>
          <span>资料范围</span>
          <el-select v-model="documentId" placeholder="整个知识库" clearable>
            <el-option label="整个知识库" :value="null" />
            <el-option
              v-for="document in completedDocuments"
              :key="document.id"
              :label="document.file_name"
              :value="document.id"
            />
          </el-select>
        </label>

        <label class="depth-control">
          <span>结构深度</span>
          <el-segmented v-model="maxDepth" :options="depthOptions" />
        </label>

        <el-button
          class="generate-button"
          type="primary"
          :loading="generating"
          :disabled="!knowledgeBaseId"
          @click="generate"
        >
          {{ mapData ? "重新生成" : "生成知识地图" }}
        </el-button>
      </section>

      <section v-if="histories.length" class="history-bar" aria-label="历史知识地图">
        <label>
          <span>历史知识地图</span>
          <el-select
            v-model="activeHistoryId"
            placeholder="选择一张已保存的地图打开"
            @change="openHistory"
          >
            <el-option
              v-for="item in histories"
              :key="item.id"
              :value="item.id"
              :label="`${item.title} · ${formatTime(item.updated_at)}`"
            />
          </el-select>
        </label>
      </section>

      <p v-if="loadError" class="state-message error-state">{{ loadError }}</p>

      <section v-if="generationJob && generating" class="generation-status" aria-live="polite">
        <div class="status-copy">
          <span>{{ stageLabel }}</span>
          <strong>{{ generationJob.message }}</strong>
          <small>已等待 {{ elapsedSeconds }} 秒 · 可切换到其他页面，返回后进度和计时会自动接续</small>
        </div>
        <el-progress
          :percentage="generationJob.progress"
          :stroke-width="10"
          :status="generationJob.status === 'failed' ? 'exception' : undefined"
        />
        <div class="stage-track" aria-label="生成阶段">
          <span
            v-for="stage in stageSteps"
            :key="stage.key"
            :class="stageClass(stage.key)"
          >
            <i></i>{{ stage.label }}
          </span>
        </div>
      </section>

      <section v-if="mapData" class="map-meta" aria-live="polite">
        <span class="mode-chip">LLM 已分析</span>
        <span>{{ mapData.node_count }} 个知识节点</span>
        <span>{{ selectedScopeName }}</span>
        <p>{{ mapData.message }}</p>
      </section>

      <section v-if="mapData" class="map-actions" aria-label="导图文件操作">
        <el-input v-model="searchTerm" clearable placeholder="搜索并定位知识节点" />
        <el-button type="primary" :loading="saving" @click="saveCurrent">保存到历史</el-button>
        <el-dropdown @command="exportMap">
          <el-button>导出 <span class="el-icon--right">⌄</span></el-button>
          <template #dropdown><el-dropdown-menu>
            <el-dropdown-item command="png">PNG 图片</el-dropdown-item>
            <el-dropdown-item command="svg">SVG 矢量图</el-dropdown-item>
            <el-dropdown-item command="json">JSON 可恢复数据</el-dropdown-item>
            <el-dropdown-item command="md">Markdown 大纲</el-dropdown-item>
          </el-dropdown-menu></template>
        </el-dropdown>
        <el-button type="danger" plain :disabled="!activeHistoryId" @click="removeHistory">删除版本</el-button>
      </section>

      <section v-if="mapData" class="atlas-workspace">
        <MindMapCanvas ref="canvasRef" :root="mapData.root" :search-term="searchTerm" @select="selectNode" />

        <aside ref="evidenceRef" class="evidence-panel">
          <div class="evidence-kicker">
            <span>SELECTED NODE</span>
            <i></i>
          </div>

          <template v-if="selectedNode">
            <p class="node-depth">第 {{ selectedNode.depth + 1 }} 层</p>
            <h2>{{ selectedNode.title }}</h2>
            <p class="node-summary">
              {{ selectedNode.summary || "该节点用于组织下级知识点，可继续展开查看。" }}
            </p>
            <el-button plain :loading="expandingNode" :disabled="!selectedNode.sources?.length" @click="expandSelectedNode">
              AI 展开这个分支
            </el-button>

            <section class="node-question">
              <div>
                <strong>问这个知识点</strong>
                <span>{{ hasOwnSources ? "回答只使用该节点绑定的原文" : "回答使用下方检索到的相关资料" }}</span>
              </div>
              <el-input
                v-model="nodeQuestion"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                maxlength="500"
                show-word-limit
                :placeholder="`例如：${selectedNode.title} 最容易混淆的地方是什么？`"
                :disabled="!questionChunkIds.length"
                @keydown.ctrl.enter="askNode"
              />
              <el-button
                type="primary"
                :loading="askingNode"
                :disabled="!questionChunkIds.length || !nodeQuestion.trim()"
                @click="askNode"
              >
                针对性提问
              </el-button>
              <p v-if="!questionChunkIds.length" class="question-hint">
                正在为该节点检索可用资料，稍候即可提问。
              </p>
              <div v-if="nodeAnswer" class="node-answer">
                <span>LLM 回答</span>
                <p>{{ nodeAnswer.answer }}</p>
                <div>
                  <RouterLink
                    v-for="source in nodeAnswer.sources"
                    :key="source.chunk_id"
                    :to="source.jump_url"
                  >
                    来源：{{ source.file_name }} · 片段 {{ source.chunk_index + 1 }}
                  </RouterLink>
                </div>
              </div>
            </section>

            <div class="source-heading">
              <strong>原文依据</strong>
              <span>{{ selectedNode.sources?.length || 0 }}</span>
            </div>

            <div v-if="selectedNode.sources?.length" class="source-cards">
              <article v-for="source in selectedNode.sources" :key="source.chunk_id">
                <div>
                  <strong>{{ source.file_name }}</strong>
                  <span>
                    片段 {{ source.chunk_index + 1 }}
                    <template v-if="source.page_no"> · 第 {{ source.page_no }} 页</template>
                  </span>
                </div>
                <p>{{ source.source_text }}</p>
                <RouterLink :to="source.jump_url">查看完整原文 →</RouterLink>
              </article>
            </div>

            <el-empty v-else :image-size="60" description="该节点没有直接绑定原文，可参考下方检索到的相关资料" />

            <div class="source-heading related-heading">
              <strong>知识库相关资料</strong>
              <span v-if="relatedLoading" class="related-spinner">检索中…</span>
              <span v-else>{{ relatedSources.length }}</span>
            </div>

            <div v-if="relatedSources.length" class="source-cards related">
              <article v-for="source in relatedSources" :key="`rel-${source.chunk_id}`">
                <div>
                  <strong>{{ source.file_name }}</strong>
                  <span>
                    片段 {{ source.chunk_index + 1 }}
                    <template v-if="source.page_no"> · 第 {{ source.page_no }} 页</template>
                    <template v-if="source.score != null"> · 相关度 {{ Math.round(source.score * 100) }}%</template>
                  </span>
                </div>
                <p>{{ source.source_text }}</p>
                <RouterLink :to="source.jump_url">查看完整原文 →</RouterLink>
              </article>
            </div>
            <p v-else-if="relatedLoading" class="related-hint">正在从整个知识库检索与该节点相关的资料…</p>
            <p v-else class="related-hint">{{ relatedError || "暂无检索到的相关资料。" }}</p>
          </template>
        </aside>
      </section>

      <section v-else class="empty-atlas">
        <div class="constellation" aria-hidden="true">
          <i class="point one"></i>
          <i class="point two"></i>
          <i class="point three"></i>
          <i class="point four"></i>
          <span class="line a"></span>
          <span class="line b"></span>
          <span class="line c"></span>
        </div>
        <div>
          <p>画布等待资料</p>
          <h2>选择知识库，生成第一张知识地图</h2>
          <span>只有已完成解析的文档会进入导图。</span>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listDocuments } from "../api/documents";
import { listKnowledgeBases } from "../api/knowledgeBases";
import {
  askMindMapNode, createMindMapHistory, createMindMapJob, deleteMindMapHistory,
  expandMindMapNode, getMindMapHistory, getMindMapJob, listMindMapHistories, updateMindMapHistory,
} from "../api/mindMaps";
import { searchKnowledge } from "../api/search";
import MindMapCanvas from "../components/mindmap/MindMapCanvas.vue";
import AppHeader from "../components/layout/AppHeader.vue";

const route = useRoute();
const router = useRouter();
const knowledgeBases = ref([]);
const documents = ref([]);
const knowledgeBaseId = ref(null);
const documentId = ref(null);
const maxDepth = ref(3);
const mapData = ref(null);
const selectedNode = ref(null);
const loadingBases = ref(false);
const generating = ref(false);
const generationJob = ref(null);
const elapsedSeconds = ref(0);
const nodeQuestion = ref("");
const nodeAnswer = ref(null);
const askingNode = ref(false);
const loadError = ref("");
const canvasRef = ref(null);
const evidenceRef = ref(null);
const searchTerm = ref("");
const histories = ref([]);
const activeHistoryId = ref(null);
const saving = ref(false);
const expandingNode = ref(false);
const healthOnline = ref(false);
const relatedLoading = ref(false);
const relatedSources = ref([]);
const relatedError = ref("");
// 节点标题 -> 检索结果缓存，避免同一节点反复点击时重复请求。
const relatedCache = new Map();
let pollTimer = null;
let elapsedTimer = null;
let pollAttempt = 0;
let trackingVersion = 0;
const stageSteps = [
  { key: "queued", label: "排队" },
  { key: "collecting", label: "读取资料" },
  { key: "preparing", label: "整理上下文" },
  { key: "extracting", label: "分批提炼" },
  { key: "merging", label: "合并结构" },
  { key: "validating", label: "校验来源" },
  { key: "assembling", label: "组装画布" },
];
const depthOptions = [
  { label: "简洁", value: 2 },
  { label: "标准", value: 3 },
  { label: "深入", value: 4 },
];

const completedDocuments = computed(() =>
  documents.value.filter((document) => document.parse_status === "completed"),
);

const selectedScopeName = computed(() => {
  if (documentId.value) {
    return completedDocuments.value.find((item) => item.id === documentId.value)?.file_name || "指定文档";
  }
  return knowledgeBases.value.find((item) => item.id === knowledgeBaseId.value)?.name || "整个知识库";
});
const stageLabel = computed(() => {
  const current = stageSteps.find((stage) => stage.key === generationJob.value?.stage);
  return current?.label || "正在处理";
});

// 节点自带原文时优先用自带来源；否则回退到实时检索到的相关资料，
// 让没有直接来源的“章节类”节点也能提问。
const hasOwnSources = computed(() => Boolean(selectedNode.value?.sources?.length));
const questionChunkIds = computed(() => {
  const own = selectedNode.value?.sources?.map((source) => source.chunk_id) || [];
  if (own.length) return own.slice(0, 8);
  return relatedSources.value.map((source) => source.chunk_id).slice(0, 8);
});

onMounted(() => {
  checkHealth();
  loadInitialData();
});
onBeforeUnmount(stopTracking);

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

async function loadInitialData() {
  loadingBases.value = true;
  loadError.value = "";
  try {
    knowledgeBases.value = await listKnowledgeBases();
    const requestedId = Number(route.query.knowledge_base_id);
    const requestedBase = knowledgeBases.value.find((item) => item.id === requestedId);
    knowledgeBaseId.value = requestedBase?.id || knowledgeBases.value[0]?.id || null;
    if (knowledgeBaseId.value) {
      await loadDocuments();
      await loadHistories();
      await resumeActiveJob();
    }
  } catch (error) {
    loadError.value = error.message;
  } finally {
    loadingBases.value = false;
  }
}

async function loadDocuments() {
  documentId.value = null;
  documents.value = [];
  if (!knowledgeBaseId.value) return;
  try {
    documents.value = await listDocuments({ knowledge_base_id: knowledgeBaseId.value });
  } catch (error) {
    loadError.value = error.message;
  }
}

async function handleKnowledgeBaseChange() {
  mapData.value = null;
  selectedNode.value = null;
  activeHistoryId.value = null;
  relatedSources.value = [];
  relatedError.value = "";
  relatedCache.clear();
  stopTracking();
  generating.value = false;
  generationJob.value = null;
  loadError.value = "";
  await router.replace({
    name: "mind-map",
    query: { knowledge_base_id: knowledgeBaseId.value },
  });
  await loadDocuments();
  await loadHistories();
  await resumeActiveJob();
}

async function loadHistories() {
  histories.value = knowledgeBaseId.value ? await listMindMapHistories(knowledgeBaseId.value) : [];
}

async function openHistory(historyId) {
  if (!historyId) return;
  try {
    const history = await getMindMapHistory(historyId);
    mapData.value = history.result;
    activeHistoryId.value = history.id;
    relatedCache.clear();
    selectNode(mapData.value.root);
  } catch (error) {
    ElMessage.error(`打开历史版本失败：${error.message}`);
  }
}

async function saveCurrent() {
  if (!mapData.value) {
    ElMessage.warning("请先生成或打开一张知识地图");
    return;
  }
  saving.value = true;
  try {
    const viewState = canvasRef.value?.getViewState() || {};
    if (activeHistoryId.value) {
      await updateMindMapHistory(activeHistoryId.value, {
        title: mapData.value.root.title,
        root: mapData.value.root,
        view_state: viewState,
      });
      ElMessage.success("已更新当前历史版本");
    } else {
      const created = await createMindMapHistory({
        knowledge_base_id: knowledgeBaseId.value,
        document_id: documentId.value || null,
        title: mapData.value.root.title,
        generation_mode: mapData.value.generation_mode || "ai",
        root: mapData.value.root,
        view_state: viewState,
      });
      activeHistoryId.value = created.id;
      mapData.value.history_id = created.id;
      ElMessage.success("已保存为新的历史版本");
    }
    await loadHistories();
  } catch (error) {
    ElMessage.error(`保存失败：${error.message}`);
  } finally {
    saving.value = false;
  }
}

async function removeHistory() {
  await deleteMindMapHistory(activeHistoryId.value);
  activeHistoryId.value = null;
  await loadHistories();
  ElMessage.success("历史版本已删除");
}

function download(content, type, extension) {
  const url = typeof content === "string" && content.startsWith("data:")
    ? content : URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = `${mapData.value.root.title}.${extension}`; anchor.click();
  if (!url.startsWith("data:")) URL.revokeObjectURL(url);
}

function toMarkdown(node, depth = 0) {
  return `${"  ".repeat(depth)}- ${node.title}${node.summary ? `：${node.summary}` : ""}\n${node.children.map((child) => toMarkdown(child, depth + 1)).join("")}`;
}

function toSvg(root) {
  const rows = [];
  function walk(node, depth = 0) { rows.push({ node, depth }); node.children.forEach((child) => walk(child, depth + 1)); }
  walk(root); const width = 1100; const height = Math.max(160, rows.length * 44 + 60);
  const escaped = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#07111f"/>${rows.map(({node,depth}, i) => `<circle cx="${50 + depth * 180}" cy="${45 + i * 44}" r="5" fill="#38bdf8"/><text x="${66 + depth * 180}" y="${51 + i * 44}" fill="#e8f8ff" font-family="Microsoft YaHei,sans-serif" font-size="16">${escaped(node.title)}</text>`).join("")}</svg>`;
}

function exportMap(format) {
  if (format === "png") download(canvasRef.value?.exportPng(), "image/png", "png");
  if (format === "svg") download(toSvg(mapData.value.root), "image/svg+xml", "svg");
  if (format === "json") download(JSON.stringify(mapData.value, null, 2), "application/json", "json");
  if (format === "md") download(`# ${mapData.value.root.title}\n\n${toMarkdown(mapData.value.root)}`, "text/markdown", "md");
}

function formatTime(value) { return value ? new Date(value).toLocaleString("zh-CN") : ""; }

async function generate() {
  if (!knowledgeBaseId.value) return;
  if (mapData.value) {
    try {
      await ElMessageBox.confirm(
        "重新生成会覆盖当前正在查看的知识地图（已保存的历史版本不受影响）。确定继续吗？",
        "重新生成确认",
        { confirmButtonText: "重新生成", cancelButtonText: "取消", type: "warning" },
      );
    } catch {
      return;
    }
  }
  generating.value = true;
  loadError.value = "";
  nodeAnswer.value = null;
  try {
    generationJob.value = await createMindMapJob({
      knowledge_base_id: knowledgeBaseId.value,
      document_id: documentId.value || null,
      max_depth: maxDepth.value,
      max_nodes: 28,
    });
    sessionStorage.setItem(activeJobKey(), generationJob.value.job_id);
    sessionStorage.setItem(startedAtKey(), String(Date.now()));
    startTracking();
  } catch (error) {
    loadError.value = error.message;
    generating.value = false;
  }
}

function selectNode(node) {
  selectedNode.value = node;
  nodeQuestion.value = "";
  nodeAnswer.value = null;
  fetchRelated(node);
  scrollToDetail();
}

// 点击节点后，用“标题 + 简介”去整个知识库检索相关片段，作为节点自带原文之外的补充。
async function fetchRelated(node) {
  relatedError.value = "";
  relatedSources.value = [];
  if (!node || !knowledgeBaseId.value) return;
  const query = [node.title, node.summary].filter(Boolean).join(" ").trim();
  if (!query) return;
  const cacheKey = `${knowledgeBaseId.value}:${node.id}`;
  if (relatedCache.has(cacheKey)) {
    relatedSources.value = relatedCache.get(cacheKey);
    return;
  }
  relatedLoading.value = true;
  try {
    const data = await searchKnowledge({
      knowledge_base_id: knowledgeBaseId.value,
      query,
      top_k: 6,
    });
    const results = data.results || [];
    relatedCache.set(cacheKey, results);
    // 用户可能已经切到别的节点，只有仍停留在当前节点时才写入，避免结果错位。
    if (selectedNode.value?.id === node.id) {
      relatedSources.value = results;
      if (!results.length) relatedError.value = data.message || "没有检索到相关资料。";
    }
  } catch (error) {
    if (selectedNode.value?.id === node.id) relatedError.value = error.message;
  } finally {
    relatedLoading.value = false;
  }
}

// 小屏（右侧详情栏堆到下方）时，点节点后自动滚到详情，避免用户以为“点了没反应”。
function scrollToDetail() {
  if (window.innerWidth > 1080) return;
  nextTick(() => {
    evidenceRef.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

async function askNode() {
  const question = nodeQuestion.value.trim();
  const chunkIds = questionChunkIds.value;
  if (!question || !chunkIds.length) return;
  askingNode.value = true;
  try {
    nodeAnswer.value = await askMindMapNode({
      knowledge_base_id: knowledgeBaseId.value,
      node_title: selectedNode.value.title,
      question,
      source_chunk_ids: chunkIds,
    });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    askingNode.value = false;
  }
}

async function expandSelectedNode() {
  if (!selectedNode.value?.sources?.length) return;
  expandingNode.value = true;
  try {
    const expanded = await expandMindMapNode({
      knowledge_base_id: knowledgeBaseId.value, node_title: selectedNode.value.title,
      node_summary: selectedNode.value.summary || "", child_count: 4,
      source_chunk_ids: selectedNode.value.sources.map((source) => source.chunk_id).slice(0, 8),
    });
    // 后端展开接口返回的子节点 id 从 mind-node-0 起重新编号，会与主树已有节点 id 撞车，
    // G6 画布遇到重复 id 会渲染失败、导致整张导图消失。这里按选中节点重新编号，保证全树唯一。
    selectedNode.value.children = relabelBranch(
      expanded.children || [],
      selectedNode.value.id,
      selectedNode.value.depth,
    );
    mapData.value.node_count = countNodes(mapData.value.root);
    ElMessage.success("已根据原文展开该分支，确认后请保存当前版本");
  } catch (error) { ElMessage.error(error.message); }
  finally { expandingNode.value = false; }
}

function countNodes(node) { return 1 + node.children.reduce((total, child) => total + countNodes(child), 0); }

// 递归重编号展开得到的分支：以父节点 id 作前缀加 "-e序号"，避开主树的纯数字路径 id，
// 同时把 depth 接续到父节点之下，保证画布层级配色正确。
function relabelBranch(nodes, parentId, parentDepth) {
  return nodes.map((node, index) => {
    const id = `${parentId}-e${index}`;
    return {
      ...node,
      id,
      depth: parentDepth + 1,
      children: relabelBranch(node.children || [], id, parentDepth + 1),
    };
  });
}

function activeJobKey() {
  return `codemind_mind_map_job_${knowledgeBaseId.value}`;
}

function startedAtKey() {
  return `codemind_mind_map_started_${knowledgeBaseId.value}`;
}

function clearActiveJob() {
  sessionStorage.removeItem(activeJobKey());
  sessionStorage.removeItem(startedAtKey());
}

async function resumeActiveJob() {
  const jobId = sessionStorage.getItem(activeJobKey());
  if (!jobId) return;
  try {
    generationJob.value = await getMindMapJob(jobId);
    if (generationJob.value.status === "completed") {
      applyCompletedJob();
    } else if (generationJob.value.status === "failed") {
      loadError.value = generationJob.value.error_message || "知识地图生成失败。";
      clearActiveJob();
      generating.value = false;
    } else {
      generating.value = true;
      startTracking();
    }
  } catch {
    clearActiveJob();
    generating.value = false;
  }
}

function startTracking() {
  stopTracking();
  generating.value = true;
  pollAttempt = 0;
  const version = trackingVersion;
  // 以任务真实开始时刻为基准计算已等待时间，切走再回来也能接续显示、不归零。
  const startedAt = Number(sessionStorage.getItem(startedAtKey())) || Date.now();
  const tick = () => {
    elapsedSeconds.value = Math.max(0, Math.round((Date.now() - startedAt) / 1000));
  };
  tick();
  elapsedTimer = window.setInterval(tick, 1000);
  schedulePoll(300, version);
}

function nextPollDelay() {
  if (pollAttempt < 10) return 1500;
  if (pollAttempt < 30) return 3000;
  return 5000;
}

function schedulePoll(delay = nextPollDelay(), version = trackingVersion) {
  window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(() => pollJob(version), delay);
}

async function pollJob(version) {
  if (version !== trackingVersion) return;
  const jobId = generationJob.value?.job_id;
  if (!jobId) return;
  try {
    const latestJob = await getMindMapJob(jobId);
    // 切换知识库或开始了新任务后，丢弃旧请求迟到的响应，避免状态串线。
    if (version !== trackingVersion || generationJob.value?.job_id !== jobId) return;
    generationJob.value = latestJob;
    pollAttempt += 1;
    if (loadError.value.startsWith("无法读取生成进度：")) loadError.value = "";
    if (generationJob.value.status === "completed") {
      applyCompletedJob();
      return;
    }
    if (generationJob.value.status === "failed") {
      loadError.value = generationJob.value.error_message || "知识地图生成失败。";
      clearActiveJob();
      stopTracking();
      generating.value = false;
      return;
    }
    schedulePoll(nextPollDelay(), version);
  } catch (error) {
    if (version !== trackingVersion) return;
    loadError.value = `无法读取生成进度：${error.message}`;
    pollAttempt += 1;
    schedulePoll(Math.max(3000, nextPollDelay()), version);
  }
}

function applyCompletedJob() {
  if (!generationJob.value?.result?.root) {
    loadError.value = "生成任务已结束，但没有返回有效的知识地图，请重新生成。";
    clearActiveJob();
    stopTracking();
    generating.value = false;
    return;
  }
  mapData.value = generationJob.value.result;
  activeHistoryId.value = mapData.value.history_id;
  relatedCache.clear();
  selectNode(mapData.value.root);
  clearActiveJob();
  stopTracking();
  generating.value = false;
  // 生成时后端已自动存了一份历史，这里刷新清单，让新地图立刻出现在历史下拉框里。
  loadHistories().catch((error) => ElMessage.warning(`历史列表刷新失败：${error.message}`));
  ElMessage.success("知识地图已生成");
}

function stopTracking() {
  trackingVersion += 1;
  window.clearTimeout(pollTimer);
  window.clearInterval(elapsedTimer);
  pollTimer = null;
  elapsedTimer = null;
}

function stageClass(stageKey) {
  const order = stageSteps.map((stage) => stage.key);
  const currentIndex = order.indexOf(generationJob.value?.stage);
  const stageIndex = order.indexOf(stageKey);
  return {
    active: stageIndex === currentIndex,
    done: currentIndex > stageIndex || generationJob.value?.status === "completed",
  };
}
</script>

<style scoped>
.mind-map-view {
  min-height: 100vh;
  padding: 16px 0 64px;
}

.map-page {
  display: grid;
  gap: 18px;
  width: min(1440px, calc(100% - 32px));
  margin: 42px auto 0;
}

.page-intro {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 32px;
  padding: 12px 4px 18px;
}

.eyebrow,
.evidence-kicker span {
  margin: 0 0 10px;
  color: var(--cm-primary);
  font-family: Consolas, "Microsoft YaHei", monospace;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
}

.page-intro h1 {
  max-width: 760px;
  margin: 0;
  color: var(--cm-heading);
  font-size: clamp(32px, 4.3vw, 62px);
  font-weight: 780;
  letter-spacing: -0.045em;
  line-height: 1.04;
}

.intro-copy {
  max-width: 620px;
  margin: 18px 0 0;
  color: var(--cm-muted);
  font-size: 16px;
  line-height: 1.75;
}

.intro-mark {
  display: grid;
  min-width: 118px;
  padding-left: 20px;
  border-left: 1px solid var(--cm-border);
  color: var(--cm-muted);
  justify-items: end;
}

.intro-mark span,
.intro-mark small {
  font-family: Consolas, monospace;
  font-size: 11px;
  letter-spacing: 0.12em;
}

.intro-mark strong {
  color: var(--cm-heading);
  font-size: 46px;
  line-height: 1.1;
}

.map-controls {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(220px, 1.2fr) auto auto;
  align-items: end;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--cm-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--cm-surface) 92%, transparent);
  box-shadow: 0 12px 34px rgba(15, 29, 53, 0.07);
  backdrop-filter: blur(14px);
}

.map-controls label {
  display: grid;
  min-width: 0;
  gap: 7px;
}

.map-controls label > span {
  color: var(--cm-muted);
  font-size: 12px;
  font-weight: 700;
}

.generate-button {
  min-height: 40px;
  padding-inline: 22px;
}

.map-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 18px;
  color: var(--cm-muted);
  font-size: 13px;
}

.map-actions {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto auto;
  gap: 10px;
  align-items: center;
  padding: 12px;
  border: 1px solid var(--cm-border);
  border-radius: 12px;
  background: var(--cm-surface);
}

.history-bar {
  display: grid;
  grid-template-columns: minmax(0, 440px);
  padding: 0 4px;
}

.history-bar label {
  display: grid;
  gap: 7px;
}

.history-bar label > span {
  color: var(--cm-muted);
  font-size: 12px;
  font-weight: 700;
}

.map-meta p {
  min-width: 260px;
  margin: 0 0 0 auto;
  text-align: right;
}

.mode-chip {
  border-radius: 999px;
  padding: 5px 10px;
  color: #1e40af;
  background: #dbeafe;
  font-weight: 800;
}

.mode-chip.fallback {
  color: #92400e;
  background: #fef3c7;
}

.generation-status {
  display: grid;
  gap: 15px;
  padding: 18px 20px;
  border: 1px solid color-mix(in srgb, var(--cm-primary) 30%, var(--cm-border));
  border-radius: 12px;
  background: color-mix(in srgb, var(--cm-primary-soft) 55%, var(--cm-surface));
}

.status-copy {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
}

.status-copy > span {
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--cm-primary);
  background: var(--cm-surface);
  font-size: 12px;
  font-weight: 800;
}

.status-copy strong { color: var(--cm-heading); }
.status-copy small { color: var(--cm-muted); }

.stage-track {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 8px;
}

.stage-track span {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--cm-muted);
  font-size: 11px;
}

.stage-track i {
  width: 8px;
  height: 8px;
  border: 2px solid var(--cm-border);
  border-radius: 50%;
  background: var(--cm-surface);
}

.stage-track span.active {
  color: var(--cm-primary);
  font-weight: 800;
}

.stage-track span.active i {
  border-color: var(--cm-primary);
  box-shadow: 0 0 0 4px var(--cm-primary-soft);
}

.stage-track span.done i {
  border-color: var(--cm-success);
  background: var(--cm-success);
}

.atlas-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: stretch;
}

.evidence-panel {
  position: relative;
  max-height: 650px;
  overflow: auto;
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: 14px;
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.evidence-panel::before {
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 112px;
  background: linear-gradient(var(--cm-primary), #22d3ee, transparent);
  content: "";
}

.evidence-kicker {
  display: flex;
  align-items: center;
  gap: 10px;
}

.evidence-kicker span { margin: 0; }

.evidence-kicker i {
  height: 1px;
  flex: 1;
  background: var(--cm-border);
}

.node-depth {
  margin: 26px 0 7px;
  color: var(--cm-muted);
  font-size: 12px;
}

.evidence-panel h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 26px;
  line-height: 1.25;
}

.node-summary {
  margin: 15px 0 24px;
  color: var(--cm-text);
  line-height: 1.78;
}

.node-question {
  display: grid;
  gap: 11px;
  margin: 0 0 24px;
  padding: 15px;
  border: 1px solid color-mix(in srgb, var(--cm-primary) 22%, var(--cm-border));
  border-radius: 10px;
  background: var(--cm-primary-soft);
}

.node-question > div:first-child {
  display: grid;
  gap: 3px;
}

.node-question strong { color: var(--cm-heading); }
.node-question > div:first-child span {
  color: var(--cm-muted);
  font-size: 12px;
}

.question-hint {
  margin: 0;
  color: var(--cm-muted);
  font-size: 12px;
}

.node-answer {
  display: grid;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--cm-border);
}

.node-answer > span {
  color: var(--cm-primary);
  font-size: 12px;
  font-weight: 800;
}

.node-answer p {
  margin: 0;
  color: var(--cm-text);
  line-height: 1.75;
  white-space: pre-wrap;
}

.node-answer > div {
  display: grid;
  gap: 5px;
}

.node-answer a {
  color: var(--cm-primary);
  font-size: 12px;
  font-weight: 700;
}

.source-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 18px;
  border-top: 1px solid var(--cm-border);
}

.source-heading span {
  display: grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border-radius: 50%;
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
  font-size: 12px;
  font-weight: 800;
}

.related-heading {
  margin-top: 22px;
}

.related-heading .related-spinner {
  width: auto;
  height: auto;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
}

.source-cards {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}

.source-cards article {
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: 10px;
  background: var(--cm-surface-soft);
}

.source-cards.related article {
  border-color: color-mix(in srgb, var(--cm-primary) 26%, var(--cm-border));
  background: color-mix(in srgb, var(--cm-primary-soft) 32%, var(--cm-surface));
}

.source-cards article > div {
  display: grid;
  gap: 4px;
}

.source-cards strong {
  overflow: hidden;
  color: var(--cm-heading);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-cards span {
  color: var(--cm-muted);
  font-size: 12px;
}

.source-cards p {
  display: -webkit-box;
  margin: 12px 0;
  overflow: hidden;
  color: var(--cm-text);
  font-size: 13px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
}

.source-cards a {
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.related-hint {
  margin: 12px 0 0;
  color: var(--cm-muted);
  font-size: 13px;
  line-height: 1.6;
}

.empty-atlas {
  position: relative;
  display: grid;
  min-height: 480px;
  overflow: hidden;
  place-items: center;
  border: 1px solid rgba(37, 99, 235, 0.16);
  border-radius: 14px;
  background: color-mix(in srgb, var(--cm-surface) 72%, transparent);
  text-align: center;
}

.empty-atlas > div:last-child {
  position: relative;
  z-index: 2;
}

.empty-atlas p {
  margin: 0 0 8px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

.empty-atlas h2 {
  margin: 0 0 10px;
  color: var(--cm-heading);
  font-size: clamp(24px, 4vw, 38px);
}

.empty-atlas span { color: var(--cm-muted); }

.constellation {
  position: absolute;
  inset: 0;
  opacity: 0.42;
}

.point,
.line { position: absolute; }

.point {
  width: 12px;
  height: 12px;
  border: 3px solid color-mix(in srgb, var(--cm-primary) 45%, transparent);
  border-radius: 50%;
  background: var(--cm-surface);
}

.point.one { top: 22%; left: 18%; }
.point.two { top: 30%; right: 22%; }
.point.three { bottom: 22%; left: 28%; }
.point.four { right: 17%; bottom: 17%; }

.line {
  width: 38%;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--cm-primary), transparent);
  transform-origin: left;
}

.line.a { top: 25%; left: 19%; transform: rotate(8deg); }
.line.b { top: 34%; left: 28%; transform: rotate(62deg); }
.line.c { right: 16%; bottom: 22%; transform: rotate(-16deg); }

.state-message {
  margin: 0;
  padding: 12px 14px;
  border-radius: 8px;
}

.error-state {
  color: var(--cm-danger);
  background: color-mix(in srgb, var(--cm-danger) 10%, var(--cm-surface));
}

@media (max-width: 1080px) {
  .map-controls {
    grid-template-columns: 1fr 1fr;
  }

  .atlas-workspace {
    grid-template-columns: 1fr;
  }

  .evidence-panel {
    max-height: none;
  }
  .map-actions { grid-template-columns: 1fr 1fr auto; }
}

@media (max-width: 680px) {
  .mind-map-view { padding-top: 8px; }

  .map-page {
    width: min(100% - 20px, 1440px);
    margin-top: 30px;
  }

  .page-intro {
    grid-template-columns: 1fr;
  }

  .intro-mark { display: none; }

  .map-controls {
    grid-template-columns: 1fr;
  }
  .map-actions { grid-template-columns: 1fr; }

  .status-copy {
    grid-template-columns: 1fr;
  }

  .stage-track {
    grid-template-columns: repeat(2, 1fr);
  }

  .map-meta p {
    width: 100%;
    margin-left: 0;
    text-align: left;
  }
}
</style>

import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { getHealth } from "../api/health";
import { listDocuments } from "../api/documents";
import { listKnowledgeBases } from "../api/knowledgeBases";
import {
  askMindMapNode,
  createMindMapHistory,
  createMindMapJob,
  deleteMindMapHistory,
  expandMindMapNode,
  getMindMapHistory,
  getMindMapJob,
  listMindMapHistories,
  updateMindMapHistory,
} from "../api/mindMaps";
import { searchKnowledge } from "../api/search";

const STAGE_STEPS = [
  { key: "queued", label: "排队", detail: "正在等待生成资源" },
  { key: "collecting", label: "读取资料", detail: "定位本次地图需要使用的资料片段" },
  { key: "preparing", label: "整理上下文", detail: "清理重复信息并建立资料上下文" },
  { key: "extracting", label: "提炼主题", detail: "从资料中分批提取主题、概念和记忆点" },
  { key: "merging", label: "组织分支", detail: "合并相近主题并整理父子层级" },
  { key: "validating", label: "核对原文", detail: "校验每个知识点能否回到真实原文" },
  { key: "assembling", label: "排布画布", detail: "确定节点顺序、间距和初始视图" },
];

const DEPTH_OPTIONS = [
  { label: "简洁", value: 2 },
  { label: "标准", value: 3 },
  { label: "深入", value: 4 },
];

export function useMindMapWorkspace() {
  const route = useRoute();
  const router = useRouter();
  const knowledgeBases = ref([]);
  const documents = ref([]);
  const knowledgeBaseId = ref(null);
  const loadedKnowledgeBaseId = ref(null);
  const documentId = ref(null);
  const maxDepth = ref(3);
  const mapData = ref(null);
  const selectedNode = ref(null);
  const loadingBases = ref(false);
  const loadingDocuments = ref(false);
  const generating = ref(false);
  const generationJob = ref(null);
  const generationTarget = ref(null);
  const generationConnectionIssue = ref("");
  const mapConstructionRevision = ref(0);
  const elapsedSeconds = ref(0);
  const nodeQuestion = ref("");
  const nodeAnswer = ref(null);
  const askingNode = ref(false);
  const loadError = ref("");
  const canvasRef = ref(null);
  const evidenceRef = ref(null);
  const searchTerm = ref("");
  const searchStatus = ref({ count: 0, index: -1 });
  const histories = ref([]);
  const activeHistoryId = ref(null);
  const selectedHistoryId = ref(null);
  const historyViewState = ref({});
  const saving = ref(false);
  const expandingNode = ref(false);
  const healthOnline = ref(false);
  const relatedLoading = ref(false);
  const relatedSources = ref([]);
  const relatedError = ref("");
  const masteredNodeIds = ref(new Set());
  const isDirty = ref(false);
  const relatedCache = new Map();
  let relatedRequestVersion = 0;
  let pollTimer = null;
  let elapsedTimer = null;
  let pollAttempt = 0;
  let trackingVersion = 0;

  const completedDocuments = computed(() =>
    documents.value.filter((document) => document.parse_status === "completed"),
  );
  const canGenerate = computed(() => Boolean(knowledgeBaseId.value && completedDocuments.value.length));
  const generationGuidance = computed(() => {
    if (loadingBases.value || loadingDocuments.value) return null;
    if (!knowledgeBaseId.value) {
      return { message: "还没有可用的知识库，请先创建一个知识库。", to: "/me", action: "创建知识库 →" };
    }
    if (!documents.value.length) {
      return { message: "这个知识库还没有文档，请先上传并完成解析。", to: "/documents", action: "上传文档 →" };
    }
    if (!completedDocuments.value.length) {
      const isProcessing = documents.value.some((document) =>
        ["pending", "processing"].includes(document.parse_status),
      );
      return isProcessing
        ? { message: "文档仍在解析中，完成后即可生成知识地图。", to: "/library", action: "查看解析进度 →" }
        : { message: "当前文档没有成功完成解析，请检查失败原因或重新解析。", to: "/library", action: "检查文档状态 →" };
    }
    return null;
  });
  const generationBlockReason = computed(() => generationGuidance.value?.message || "");

  const selectedScopeName = computed(() => {
    if (!mapData.value) return "";
    if (mapData.value.document_id) {
      return documents.value.find((item) => item.id === mapData.value.document_id)?.file_name || "指定文档";
    }
    return knowledgeBases.value.find((item) => item.id === mapData.value.knowledge_base_id)?.name || "整个知识库";
  });
  const stageLabel = computed(() => {
    const current = STAGE_STEPS.find((stage) => stage.key === generationJob.value?.stage);
    return current?.label || "正在处理";
  });
  const stageDetail = computed(() => {
    const current = STAGE_STEPS.find((stage) => stage.key === generationJob.value?.stage);
    return current?.detail || "正在建立知识结构";
  });
  const stagePosition = computed(() => {
    const currentIndex = STAGE_STEPS.findIndex((stage) => stage.key === generationJob.value?.stage);
    return {
      current: currentIndex >= 0 ? currentIndex + 1 : 1,
      total: STAGE_STEPS.length,
    };
  });
  const generationHeartbeatAge = computed(() => {
    // elapsedSeconds 每秒变化，用它带动这个状态在没有新轮询结果时继续更新。
    elapsedSeconds.value;
    const value = generationJob.value?.updated_at || generationJob.value?.created_at;
    const timestamp = value ? new Date(value).getTime() : NaN;
    return Number.isFinite(timestamp) ? Math.max(0, Math.round((Date.now() - timestamp) / 1000)) : 0;
  });
  const generationStalled = computed(() =>
    generating.value
    && generationJob.value?.status === "processing"
    && generationHeartbeatAge.value >= 90,
  );
  const hasOwnSources = computed(() => Boolean(selectedNode.value?.sources?.length));
  const questionChunkIds = computed(() => {
    const own = selectedNode.value?.sources?.map((source) => source.chunk_id) || [];
    if (own.length) return own.slice(0, 8);
    return relatedSources.value.map((source) => source.chunk_id).slice(0, 8);
  });

  const allMapNodes = computed(() => {
    if (!mapData.value?.root) return [];
    const nodes = [];
    const walk = (node) => {
      nodes.push(node);
      node.children?.forEach(walk);
    };
    walk(mapData.value.root);
    return nodes;
  });
  const learnableNodes = computed(() => allMapNodes.value.filter((node) => node.depth > 0));
  const masteredCount = computed(() =>
    learnableNodes.value.filter((node) => masteredNodeIds.value.has(node.id)).length,
  );
  const masteredNodeIdList = computed(() => [...masteredNodeIds.value]);
  const masteryProgress = computed(() =>
    learnableNodes.value.length ? Math.round((masteredCount.value / learnableNodes.value.length) * 100) : 0,
  );
  const nextLearningNode = computed(() => {
    const unmastered = learnableNodes.value.filter((node) => !masteredNodeIds.value.has(node.id));
    return unmastered.find((node) => !node.children?.length) || unmastered[0] || null;
  });
  const mapStats = computed(() => {
    const nodes = allMapNodes.value;
    const learnable = learnableNodes.value;
    const evidenced = learnable.filter((node) => node.sources?.length).length;
    return {
      maxDepth: nodes.length ? Math.max(...nodes.map((node) => Number(node.depth || 0))) + 1 : 0,
      leafCount: nodes.filter((node) => !node.children?.length).length,
      evidenceCoverage: learnable.length ? Math.round((evidenced / learnable.length) * 100) : 0,
    };
  });
  const selectedPath = computed(() => {
    if (!mapData.value?.root || !selectedNode.value) return [];
    return findNodePath(mapData.value.root, selectedNode.value.id) || [];
  });
  const selectedNodeTypeLabel = computed(() => ({
    overview: "知识总览",
    chapter: "学习章节",
    concept: "核心概念",
    detail: "知识细节",
  }[selectedNode.value?.node_type] || "知识节点"));
  const isSelectedMastered = computed(() =>
    Boolean(selectedNode.value && masteredNodeIds.value.has(selectedNode.value.id)),
  );
  const selectedLearningTip = computed(() => {
    if (selectedNode.value?.learning_tip) return selectedNode.value.learning_tip;
    if (selectedNode.value?.children?.length) return "先用一句话复述本节点，再依次学习下方子知识点。";
    return "合上原文尝试复述定义，并举一个例子检验是否真正理解。";
  });
  const saveButtonLabel = computed(() => {
    if (!activeHistoryId.value) return "保存为版本";
    return isDirty.value ? "保存修改" : "已保存";
  });
  const canSave = computed(() => Boolean(mapData.value && (!activeHistoryId.value || isDirty.value)));
  const searchResultLabel = computed(() => {
    if (!searchTerm.value.trim()) return "";
    if (!searchStatus.value.count) return "未找到";
    return `${searchStatus.value.index + 1} / ${searchStatus.value.count}`;
  });

  onMounted(() => {
    checkHealth();
    loadInitialData();
    window.addEventListener("beforeunload", handleBeforeUnload);
  });
  onBeforeUnmount(() => {
    stopTracking();
    window.removeEventListener("beforeunload", handleBeforeUnload);
  });
  onBeforeRouteLeave(async () => {
    if (!isDirty.value) return true;
    return confirmDiscardChanges("离开当前页面");
  });

  function handleBeforeUnload(event) {
    if (!isDirty.value) return;
    event.preventDefault();
    event.returnValue = "";
  }

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
      loadedKnowledgeBaseId.value = knowledgeBaseId.value;
      if (knowledgeBaseId.value) {
        await Promise.all([loadDocuments(), loadHistories()]);
        await resumeActiveJob();
        await openLatestHistoryWhenIdle();
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
    loadingDocuments.value = true;
    try {
      documents.value = await listDocuments({ knowledge_base_id: knowledgeBaseId.value });
    } catch (error) {
      loadError.value = error.message;
    } finally {
      loadingDocuments.value = false;
    }
  }

  async function handleKnowledgeBaseChange() {
    const previousId = loadedKnowledgeBaseId.value;
    if (!(await confirmDiscardChanges("切换知识库"))) {
      knowledgeBaseId.value = previousId;
      return;
    }
    resetWorkspace();
    loadedKnowledgeBaseId.value = knowledgeBaseId.value;
    await router.replace({
      name: "mind-map",
      query: knowledgeBaseId.value ? { knowledge_base_id: knowledgeBaseId.value } : {},
    });
    await Promise.all([loadDocuments(), loadHistories()]);
    await resumeActiveJob();
    await openLatestHistoryWhenIdle();
  }

  function resetWorkspace() {
    mapData.value = null;
    selectedNode.value = null;
    activeHistoryId.value = null;
    selectedHistoryId.value = null;
    historyViewState.value = {};
    masteredNodeIds.value = new Set();
    isDirty.value = false;
    searchTerm.value = "";
    searchStatus.value = { count: 0, index: -1 };
    clearRelatedState();
    stopTracking();
    generating.value = false;
    generationJob.value = null;
    generationTarget.value = null;
    generationConnectionIssue.value = "";
    loadError.value = "";
  }

  async function loadHistories() {
    try {
      histories.value = knowledgeBaseId.value ? await listMindMapHistories(knowledgeBaseId.value) : [];
    } catch (error) {
      histories.value = [];
      ElMessage.warning(`历史版本读取失败：${error.message}`);
    }
  }

  async function openLatestHistoryWhenIdle() {
    if (generating.value || mapData.value || !histories.value.length) return;
    await openHistory(histories.value[0].id, { skipGuard: true });
  }

  async function openHistory(historyId, options = {}) {
    if (!historyId) return;
    const previousId = activeHistoryId.value;
    if (!options.skipGuard && historyId !== previousId && !(await confirmDiscardChanges("打开其他历史版本"))) {
      selectedHistoryId.value = previousId;
      return;
    }
    try {
      const history = await getMindMapHistory(historyId);
      if (!history.result?.root) throw new Error("历史版本缺少有效地图数据");
      mapData.value = history.result;
      activeHistoryId.value = history.id;
      selectedHistoryId.value = history.id;
      historyViewState.value = history.view_state || {};
      documentId.value = history.document_id || null;
      loadMastery();
      clearRelatedState();
      const preferredNode = findNodeById(
        mapData.value.root,
        historyViewState.value.selected_node_id,
      ) || mapData.value.root;
      selectNode(preferredNode, { scroll: false });
      isDirty.value = false;
    } catch (error) {
      selectedHistoryId.value = previousId;
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
      const viewState = canvasRef.value?.getViewState() || historyViewState.value || {};
      historyViewState.value = viewState;
      if (activeHistoryId.value) {
        await updateMindMapHistory(activeHistoryId.value, {
          title: mapData.value.root.title,
          root: mapData.value.root,
          view_state: viewState,
        });
        ElMessage.success("地图修改已保存");
      } else {
        const created = await createMindMapHistory({
          knowledge_base_id: mapData.value.knowledge_base_id || knowledgeBaseId.value,
          document_id: mapData.value.document_id || null,
          title: mapData.value.root.title,
          generation_mode: mapData.value.generation_mode || "ai",
          root: mapData.value.root,
          view_state: viewState,
        });
        activeHistoryId.value = created.id;
        selectedHistoryId.value = created.id;
        mapData.value = { ...mapData.value, history_id: created.id };
        ElMessage.success("已保存为历史版本");
      }
      isDirty.value = false;
      saveMastery();
      await loadHistories();
    } catch (error) {
      ElMessage.error(`保存失败：${error.message}`);
    } finally {
      saving.value = false;
    }
  }

  async function removeHistory() {
    if (!activeHistoryId.value) return;
    try {
      await ElMessageBox.confirm(
        isDirty.value
          ? "当前版本还有未保存调整。删除后，这些调整和历史版本都会丢失。"
          : "删除后无法恢复这张历史地图，确定继续吗？",
        "删除历史版本",
        { confirmButtonText: "删除版本", cancelButtonText: "取消", type: "warning" },
      );
    } catch {
      return;
    }
    try {
      await deleteMindMapHistory(activeHistoryId.value);
      isDirty.value = false;
      await loadHistories();
      if (histories.value.length) {
        await openHistory(histories.value[0].id, { skipGuard: true });
      } else {
        resetWorkspace();
      }
      ElMessage.success("历史版本已删除");
    } catch (error) {
      ElMessage.error(`删除失败：${error.message}`);
    }
  }

  async function generate() {
    if (!canGenerate.value) {
      ElMessage.warning(generationBlockReason.value || "请先选择可用的知识库和资料");
      return;
    }
    if (mapData.value) {
      try {
        await ElMessageBox.confirm(
          isDirty.value
            ? "当前地图还有未保存调整。新地图生成完成后会替换当前画布，确定继续吗？"
            : "新地图生成完成后会替换当前画布；当前历史版本仍会保留。",
          "重新生成知识地图",
          { confirmButtonText: "开始生成", cancelButtonText: "取消", type: "warning" },
        );
      } catch {
        return;
      }
    }
    generating.value = true;
    loadError.value = "";
    generationConnectionIssue.value = "";
    nodeAnswer.value = null;
    try {
      generationTarget.value = createGenerationTarget();
      sessionStorage.setItem(targetKey(), JSON.stringify(generationTarget.value));
      generationJob.value = await createMindMapJob({
        knowledge_base_id: knowledgeBaseId.value,
        document_id: documentId.value || null,
        max_depth: maxDepth.value,
        max_nodes: generationTarget.value.maxNodes,
      });
      sessionStorage.setItem(activeJobKey(), generationJob.value.job_id);
      sessionStorage.setItem(startedAtKey(), String(Date.now()));
      startTracking();
    } catch (error) {
      loadError.value = error.message;
      generating.value = false;
    }
  }

  function selectNode(node, options = {}) {
    if (!node) return;
    selectedNode.value = node;
    nodeQuestion.value = "";
    nodeAnswer.value = null;
    fetchRelated(node);
    if (options.scroll !== false) scrollToDetail();
  }

  async function focusLearningNode(node) {
    if (!node) return;
    if (canvasRef.value?.focusNode) {
      await canvasRef.value.focusNode(node.id);
    } else {
      selectNode(node);
    }
  }

  function handleCanvasViewChange(viewState) {
    historyViewState.value = viewState;
    isDirty.value = true;
  }

  function handleSearchStatus(status) {
    searchStatus.value = status;
  }

  function stepSearch(direction) {
    canvasRef.value?.stepSearch(direction);
  }

  function masteryStorageKey() {
    if (!mapData.value?.root) return "";
    const identity = activeHistoryId.value
      || mapData.value.history_id
      || `${mapData.value.knowledge_base_id}-${mapData.value.document_id || "all"}-${mapData.value.root.id}`;
    return `codemind_mind_map_mastery_${identity}`;
  }

  function loadMastery() {
    const key = masteryStorageKey();
    if (!key) {
      masteredNodeIds.value = new Set();
      return;
    }
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "[]");
      const validIds = new Set(learnableNodes.value.map((node) => node.id));
      masteredNodeIds.value = new Set(saved.filter((id) => validIds.has(id)));
    } catch {
      masteredNodeIds.value = new Set();
    }
  }

  function saveMastery() {
    const key = masteryStorageKey();
    if (key) localStorage.setItem(key, JSON.stringify([...masteredNodeIds.value]));
  }

  function toggleSelectedMastery() {
    if (!selectedNode.value || selectedNode.value.depth === 0) return;
    const next = new Set(masteredNodeIds.value);
    if (next.has(selectedNode.value.id)) next.delete(selectedNode.value.id);
    else next.add(selectedNode.value.id);
    masteredNodeIds.value = next;
    saveMastery();
  }

  async function fetchRelated(node) {
    const requestVersion = ++relatedRequestVersion;
    relatedError.value = "";
    relatedSources.value = [];
    relatedLoading.value = false;
    if (!node || !knowledgeBaseId.value) return;
    const query = [node.title, node.summary].filter(Boolean).join(" ").trim();
    if (!query) return;
    const cacheKey = `${knowledgeBaseId.value}:${mapData.value?.history_id || "draft"}:${node.id}`;
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
      if (requestVersion === relatedRequestVersion && selectedNode.value?.id === node.id) {
        relatedSources.value = results;
        if (!results.length) relatedError.value = data.message || "没有检索到相关资料。";
      }
    } catch (error) {
      if (requestVersion === relatedRequestVersion && selectedNode.value?.id === node.id) {
        relatedError.value = error.message;
      }
    } finally {
      if (requestVersion === relatedRequestVersion) relatedLoading.value = false;
    }
  }

  function clearRelatedState() {
    relatedRequestVersion += 1;
    relatedCache.clear();
    relatedLoading.value = false;
    relatedSources.value = [];
    relatedError.value = "";
  }

  function scrollToDetail() {
    if (window.innerWidth > 1080) return;
    nextTick(() => evidenceRef.value?.scrollIntoView?.());
  }

  async function askNode() {
    const question = nodeQuestion.value.trim();
    const chunkIds = questionChunkIds.value;
    const targetNodeId = selectedNode.value?.id;
    if (!question || !chunkIds.length || !targetNodeId) return;
    askingNode.value = true;
    try {
      const answer = await askMindMapNode({
        knowledge_base_id: knowledgeBaseId.value,
        node_title: selectedNode.value.title,
        question,
        source_chunk_ids: chunkIds,
      });
      if (selectedNode.value?.id === targetNodeId) nodeAnswer.value = answer;
    } catch (error) {
      ElMessage.error(error.message);
    } finally {
      askingNode.value = false;
    }
  }

  async function expandSelectedNode() {
    if (!selectedNode.value?.sources?.length) return;
    const targetNode = selectedNode.value;
    expandingNode.value = true;
    try {
      const expanded = await expandMindMapNode({
        knowledge_base_id: knowledgeBaseId.value,
        node_title: targetNode.title,
        node_summary: targetNode.summary || "",
        child_count: 4,
        source_chunk_ids: targetNode.sources.map((source) => source.chunk_id).slice(0, 8),
      });
      const children = relabelBranch(expanded.children || [], targetNode.id, targetNode.depth);
      const nextRoot = replaceNode(mapData.value.root, targetNode.id, (node) => ({ ...node, children }));
      mapData.value = {
        ...mapData.value,
        root: nextRoot,
        node_count: countNodes(nextRoot),
      };
      selectedNode.value = findNodeById(nextRoot, targetNode.id) || nextRoot;
      historyViewState.value = {
        ...historyViewState.value,
        selected_node_id: targetNode.id,
      };
      isDirty.value = true;
      ElMessage.success("分支已展开并保留当前焦点，请保存修改");
    } catch (error) {
      ElMessage.error(error.message);
    } finally {
      expandingNode.value = false;
    }
  }

  function countNodes(node) {
    return 1 + (node.children || []).reduce((total, child) => total + countNodes(child), 0);
  }

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

  function replaceNode(node, targetId, updater) {
    if (node.id === targetId) return updater(node);
    return {
      ...node,
      children: (node.children || []).map((child) => replaceNode(child, targetId, updater)),
    };
  }

  function findNodeById(node, nodeId) {
    if (!node || !nodeId) return null;
    if (node.id === nodeId) return node;
    for (const child of node.children || []) {
      const match = findNodeById(child, nodeId);
      if (match) return match;
    }
    return null;
  }

  function findNodePath(node, targetId, path = []) {
    const nextPath = [...path, node];
    if (node.id === targetId) return nextPath;
    for (const child of node.children || []) {
      const match = findNodePath(child, targetId, nextPath);
      if (match) return match;
    }
    return null;
  }

  function activeJobKey() {
    return `codemind_mind_map_job_${knowledgeBaseId.value}`;
  }

  function startedAtKey() {
    return `codemind_mind_map_started_${knowledgeBaseId.value}`;
  }

  function targetKey() {
    return `codemind_mind_map_target_${knowledgeBaseId.value}`;
  }

  function createGenerationTarget() {
    const selectedDocument = documents.value.find((item) => item.id === documentId.value);
    const selectedBase = knowledgeBases.value.find((item) => item.id === knowledgeBaseId.value);
    return {
      knowledgeBaseId: knowledgeBaseId.value,
      documentId: documentId.value || null,
      scopeName: selectedDocument?.file_name || selectedBase?.name || "当前知识库",
      depth: maxDepth.value,
      maxNodes: maxDepth.value >= 4 ? 48 : maxDepth.value === 3 ? 38 : 26,
      startedAt: Date.now(),
    };
  }

  function restoreGenerationTarget() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(targetKey()) || "null");
      if (!saved || saved.knowledgeBaseId !== knowledgeBaseId.value) return;
      generationTarget.value = saved;
      if (!saved.documentId || completedDocuments.value.some((item) => item.id === saved.documentId)) {
        documentId.value = saved.documentId || null;
      }
      if (DEPTH_OPTIONS.some((option) => option.value === saved.depth)) maxDepth.value = saved.depth;
    } catch {
      generationTarget.value = null;
    }
  }

  function clearActiveJob(preserveTarget = false) {
    sessionStorage.removeItem(activeJobKey());
    sessionStorage.removeItem(startedAtKey());
    if (!preserveTarget) sessionStorage.removeItem(targetKey());
  }

  async function resumeActiveJob() {
    restoreGenerationTarget();
    const jobId = sessionStorage.getItem(activeJobKey());
    if (!jobId) return;
    try {
      generationJob.value = await getMindMapJob(jobId);
      if (generationJob.value.status === "completed") {
        applyCompletedJob();
      } else if (generationJob.value.status === "failed") {
        loadError.value = generationJob.value.error_message || "知识地图生成失败。";
        clearActiveJob(true);
        generating.value = false;
      } else {
        generating.value = true;
        startTracking();
      }
    } catch (error) {
      clearActiveJob(true);
      generating.value = false;
      loadError.value = `无法恢复上次生成任务：${error.message || "请确认后端服务已启动且网络可用"}`;
    }
  }

  function startTracking() {
    stopTracking();
    generating.value = true;
    pollAttempt = 0;
    const version = trackingVersion;
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
      if (version !== trackingVersion || generationJob.value?.job_id !== jobId) return;
      generationJob.value = latestJob;
      generationConnectionIssue.value = "";
      pollAttempt += 1;
      if (generationJob.value.status === "completed") {
        applyCompletedJob();
        return;
      }
      if (generationJob.value.status === "failed") {
        loadError.value = generationJob.value.error_message || "知识地图生成失败。";
        clearActiveJob(true);
        stopTracking();
        generating.value = false;
        return;
      }
      schedulePoll(nextPollDelay(), version);
    } catch (error) {
      if (version !== trackingVersion) return;
      generationConnectionIssue.value = `暂时无法读取最新进度：${error.message}。正在自动重连。`;
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
    mapConstructionRevision.value += 1;
    activeHistoryId.value = mapData.value.history_id;
    selectedHistoryId.value = mapData.value.history_id;
    historyViewState.value = {};
    loadMastery();
    clearRelatedState();
    selectNode(mapData.value.root, { scroll: false });
    isDirty.value = false;
    clearActiveJob();
    generationTarget.value = null;
    generationConnectionIssue.value = "";
    stopTracking();
    generating.value = false;
    loadHistories().catch((error) => ElMessage.warning(`历史列表刷新失败：${error.message}`));
    ElMessage.success("知识地图已生成并自动保存");
  }

  function stopTracking() {
    trackingVersion += 1;
    window.clearTimeout(pollTimer);
    window.clearInterval(elapsedTimer);
    pollTimer = null;
    elapsedTimer = null;
  }

  function stageClass(stageKey) {
    const order = STAGE_STEPS.map((stage) => stage.key);
    const currentIndex = order.indexOf(generationJob.value?.stage);
    const stageIndex = order.indexOf(stageKey);
    return {
      active: stageIndex === currentIndex,
      done: currentIndex > stageIndex || generationJob.value?.status === "completed",
    };
  }

  async function confirmDiscardChanges(action) {
    if (!isDirty.value) return true;
    try {
      await ElMessageBox.confirm(
        `当前地图还有未保存调整，${action}会丢失这些调整。`,
        "未保存的地图调整",
        { confirmButtonText: "放弃调整", cancelButtonText: "继续编辑", type: "warning" },
      );
      return true;
    } catch {
      return false;
    }
  }

  function download(content, type, extension) {
    if (!content) {
      ElMessage.warning("当前内容暂时无法导出");
      return;
    }
    const url = typeof content === "string" && content.startsWith("data:")
      ? content
      : URL.createObjectURL(new Blob([content], { type }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${mapData.value.root.title}.${extension}`;
    anchor.click();
    anchor.remove();
    if (!url.startsWith("data:")) URL.revokeObjectURL(url);
  }

  function toMarkdown(node, depth = 0) {
    const indent = "  ".repeat(depth);
    const points = (node.key_points || []).map((point) => `${indent}  - 记忆点：${point}\n`).join("");
    const tip = node.learning_tip ? `${indent}  - 学习建议：${node.learning_tip}\n` : "";
    const children = (node.children || []).map((child) => toMarkdown(child, depth + 1)).join("");
    return `${indent}- ${node.title}${node.summary ? `：${node.summary}` : ""}\n${points}${tip}${children}`;
  }

  function toSvg(root) {
    const rows = [];
    const walk = (node, depth = 0) => {
      rows.push({ node, depth });
      (node.children || []).forEach((child) => walk(child, depth + 1));
    };
    walk(root);
    const width = 1100;
    const height = Math.max(160, rows.length * 44 + 60);
    const escaped = (value) => String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[char]));
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#f7f9fc"/>${rows.map(({ node, depth }, index) => `<circle cx="${50 + depth * 180}" cy="${45 + index * 44}" r="5" fill="#2f5ee5"/><text x="${66 + depth * 180}" y="${51 + index * 44}" fill="#172033" font-family="Microsoft YaHei,sans-serif" font-size="16">${escaped(node.title)}</text>`).join("")}</svg>`;
  }

  function exportMap(format) {
    if (!mapData.value) return;
    if (format === "png") download(canvasRef.value?.exportPng(), "image/png", "png");
    if (format === "svg") download(toSvg(mapData.value.root), "image/svg+xml", "svg");
    if (format === "json") download(JSON.stringify(mapData.value, null, 2), "application/json", "json");
    if (format === "md") download(`# ${mapData.value.root.title}\n\n${toMarkdown(mapData.value.root)}`, "text/markdown", "md");
  }

  function formatTime(value) {
    return value ? new Date(value).toLocaleString("zh-CN") : "";
  }

  return {
    activeHistoryId,
    askNode,
    askingNode,
    canGenerate,
    canSave,
    canvasRef,
    completedDocuments,
    depthOptions: DEPTH_OPTIONS,
    documentId,
    elapsedSeconds,
    evidenceRef,
    expandingNode,
    expandSelectedNode,
    exportMap,
    focusLearningNode,
    formatTime,
    generate,
    generationBlockReason,
    generationGuidance,
    generationConnectionIssue,
    generationStalled,
    generationTarget,
    generationJob,
    generating,
    handleCanvasViewChange,
    handleKnowledgeBaseChange,
    handleSearchStatus,
    hasOwnSources,
    healthOnline,
    histories,
    historyViewState,
    isDirty,
    isSelectedMastered,
    knowledgeBaseId,
    knowledgeBases,
    learnableNodes,
    loadingBases,
    loadingDocuments,
    loadError,
    mapData,
    mapConstructionRevision,
    mapStats,
    masteredCount,
    masteredNodeIdList,
    masteryProgress,
    maxDepth,
    nextLearningNode,
    nodeAnswer,
    nodeQuestion,
    openHistory,
    questionChunkIds,
    relatedError,
    relatedLoading,
    relatedSources,
    removeHistory,
    saveButtonLabel,
    saveCurrent,
    saving,
    searchResultLabel,
    searchStatus,
    searchTerm,
    selectNode,
    selectedHistoryId,
    selectedLearningTip,
    selectedNode,
    selectedNodeTypeLabel,
    selectedPath,
    selectedScopeName,
    stageClass,
    stageDetail,
    stageLabel,
    stagePosition,
    stageSteps: STAGE_STEPS,
    stepSearch,
    toggleSelectedMastery,
  };
}

<template>
  <div class="mind-map-view" :class="{ 'zen-mode': zenMode }">
    <AppHeader v-if="!zenMode" :health-online="healthOnline" />

    <main class="map-page">
      <header v-if="!mapData && !zenMode" class="page-heading">
        <div>
          <p class="utility-label">KNOWLEDGE WORKSPACE</p>
          <h1>知识地图</h1>
          <p>把资料整理成一张能聚焦分支、核对原文并持续学习的知识画布。</p>
        </div>
      </header>

      <section
        v-if="!mapData && histories.length && !generating && !generationJob"
        class="history-library"
        aria-label="全部已生成知识地图"
      >
        <header>
          <div>
            <span>全部知识地图</span>
            <h2>选择一张地图继续学习</h2>
            <p>这里汇总所有知识库的地图，不受当前知识库选择限制。</p>
          </div>
          <strong>{{ filteredHistories.length }} / {{ histories.length }} 张</strong>
        </header>
        <div class="history-filters" aria-label="筛选知识地图">
          <el-input
            v-model="historySearch"
            clearable
            placeholder="搜索地图标题或知识库"
            aria-label="搜索知识地图"
          />
          <el-select
            v-model="historyKnowledgeBaseFilter"
            clearable
            placeholder="全部知识库"
            aria-label="按知识库筛选"
          >
            <el-option
              v-for="base in knowledgeBases"
              :key="base.id"
              :label="base.name"
              :value="base.id"
            />
          </el-select>
        </div>
        <div class="history-shelf">
          <button
            v-for="item in filteredHistories"
            :key="item.id"
            type="button"
            :class="{ opening: openingHistoryId === item.id }"
            :disabled="Boolean(openingHistoryId)"
            :aria-label="`打开${historyKnowledgeBaseName(item)}中的${item.title}`"
            @click="openHistory(item.id)"
          >
            <span class="history-route" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="history-meta">
              <b>{{ historyKnowledgeBaseName(item) }}</b>
              <time>{{ formatTime(item.updated_at) }}</time>
            </span>
            <strong>{{ item.title }}</strong>
            <small>{{ item.node_count }} 个知识节点</small>
            <em>{{ openingHistoryId === item.id ? "正在打开…" : "打开地图 →" }}</em>
          </button>
          <p v-if="!filteredHistories.length" class="history-filter-empty">
            没有匹配的知识地图，请调整搜索词或知识库筛选。
          </p>
        </div>
      </section>

      <section ref="setupRef" v-if="!mapData || setupOpen" class="control-deck" aria-label="知识地图生成设置">
        <div class="control-deck-heading">
          <div>
            <span>{{ mapData ? "生成另一张地图" : histories.length ? "新建知识地图" : "生成范围" }}</span>
            <p>选择知识库、资料范围和结构深度；新地图完成前，当前内容仍可继续浏览。</p>
          </div>
          <div class="control-deck-actions">
            <span v-if="generating" class="working-badge"><i></i>正在构造</span>
            <button v-if="mapData" type="button" aria-label="收起生成设置" @click="setupOpen = false">×</button>
          </div>
        </div>

        <div class="control-grid">
          <label>
            <span>知识库</span>
            <el-select
              v-model="knowledgeBaseId"
              placeholder="选择知识库"
              :disabled="loadingBases || generating"
              @change="handleKnowledgeBaseChange"
            >
              <KnowledgeBaseOptions :bases="knowledgeBases" />
            </el-select>
          </label>

          <label>
            <span>资料范围</span>
            <el-select
              v-model="documentId"
              placeholder="整个知识库"
              clearable
              :disabled="loadingDocuments || generating"
            >
              <el-option label="整个知识库" value="" />
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
            <el-segmented v-model="maxDepth" :options="depthOptions" :disabled="generating" />
          </label>

          <el-button
            class="generate-button"
            type="primary"
            :loading="generating"
            :disabled="!canGenerate"
            @click="generate"
          >{{ mapData ? "开始生成新地图" : "生成知识地图" }}</el-button>
        </div>

        <p v-if="generationBlockReason" class="control-guidance">
          {{ generationBlockReason }}
          <RouterLink :to="generationGuidance.to">{{ generationGuidance.action }}</RouterLink>
        </p>
      </section>

      <p v-if="loadError" class="state-message error-state">{{ loadError }}</p>

      <section
        v-if="mapData && generationJob && (generating || generationJob.status === 'failed')"
        class="generation-ribbon"
        :class="{ failed: generationJob.status === 'failed' }"
        aria-live="polite"
      >
        <div class="ribbon-stage">
          <i></i>
          <div>
            <span>{{ generationJob.status === "failed" ? "新版本构造失败" : `新版构造中 · ${stageLabel}` }}</span>
            <strong>{{ generationJob.message || loadError }}</strong>
          </div>
        </div>
        <div class="ribbon-progress" aria-label="新版本构造进度">
          <span :style="{ width: generationJob.progress + '%' }"></span>
        </div>
        <b>{{ generationJob.progress }}%</b>
        <small v-if="generationConnectionIssue">{{ generationConnectionIssue }}</small>
        <small v-else-if="generationStalled">进度暂未更新，请确认后端服务仍在运行；任务可能仍在继续。</small>
        <div class="ribbon-actions">
          <button
            v-if="generating"
            type="button"
            :disabled="cancellingGeneration"
            @click="cancelGeneration"
          >{{ cancellingGeneration ? "正在取消…" : "取消生成" }}</button>
          <button v-if="generationJob.status === 'failed'" type="button" @click="generate">按原设置重试</button>
        </div>
      </section>

      <template v-if="mapData">
        <header class="map-document-bar">
          <div class="document-leading">
            <button
              v-if="!zenMode"
              type="button"
              class="rail-toggle"
              :class="{ active: outlineOpen }"
              :aria-pressed="outlineOpen"
              @click="outlineOpen = !outlineOpen"
            >大纲</button>
            <div class="document-title">
              <span class="map-status" :class="{ dirty: isDirty }"><i></i>{{ isDirty ? "未保存" : "已保存" }}</span>
              <strong>{{ mapData.root.title }}</strong>
              <small>{{ selectedScopeName }} · {{ mapData.node_count }} 个节点</small>
            </div>
          </div>

          <div class="node-search">
            <el-input
              ref="searchInputRef"
              v-model="searchTerm"
              clearable
              :placeholder="focusRootId ? '搜索当前分支' : '搜索标题、摘要或记忆点'"
              @keydown.enter.exact="stepSearch(1)"
              @keydown.shift.enter="stepSearch(-1)"
            />
            <span class="search-count">{{ searchResultLabel }}</span>
            <button type="button" aria-label="上一个搜索结果" :disabled="searchStatus.count < 2" @click="stepSearch(-1)">↑</button>
            <button type="button" aria-label="下一个搜索结果" :disabled="searchStatus.count < 2" @click="stepSearch(1)">↓</button>
          </div>

          <div class="document-actions" aria-label="地图文件操作">
            <button
              type="button"
              class="new-map-action"
              :disabled="generating"
              @click="openGenerationSetup"
            ><i aria-hidden="true">＋</i><span>生成另一张</span></button>
            <button type="button" class="plain-action history-action" @click="returnToHistoryList">
              地图列表 {{ histories.length }}
            </button>
            <button
              type="button"
              class="plain-action"
              :class="{ active: inspectorOpen }"
              :aria-pressed="inspectorOpen"
              @click="inspectorOpen = !inspectorOpen"
            >详情</button>
            <el-button size="small" type="primary" :loading="saving" :disabled="!canSave" @click="saveCurrent">
              {{ saveButtonLabel }}
            </el-button>
            <el-dropdown :disabled="Boolean(exportingFormat)" @command="exportMap">
              <el-button size="small" :loading="Boolean(exportingFormat)">导出⌄</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="png-overall">PNG 完整地图</el-dropdown-item>
                  <el-dropdown-item command="png-viewport">PNG 当前视图</el-dropdown-item>
                  <el-dropdown-item command="svg">SVG 大纲</el-dropdown-item>
                  <el-dropdown-item command="json">JSON 可恢复数据</el-dropdown-item>
                  <el-dropdown-item command="md">Markdown 大纲</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-dropdown @command="handleDocumentCommand">
              <button type="button" class="more-action" aria-label="更多地图操作">•••</button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="setup">生成另一张地图</el-dropdown-item>
                  <el-dropdown-item command="zen">{{ zenMode ? "退出专注模式" : "进入专注模式" }}</el-dropdown-item>
                  <el-dropdown-item command="delete" divided :disabled="!activeHistoryId || generating || saving">删除当前版本</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-popover placement="bottom-end" :width="260" trigger="click">
              <template #reference><button type="button" class="shortcut-action" aria-label="查看快捷键">?</button></template>
              <div class="shortcut-list">
                <strong>快捷键</strong>
                <span><kbd>Ctrl F</kbd> 搜索节点</span>
                <span><kbd>Ctrl 0</kbd> 回到中心主题</span>
                <span><kbd>F</kbd> 聚焦选中分支</span>
                <span><kbd>Z</kbd> 专注模式</span>
                <span><kbd>Esc</kbd> 返回上一层视图</span>
              </div>
            </el-popover>
          </div>
        </header>

        <section v-if="!zenMode" class="learning-strip">
          <div class="learning-progress">
            <span>本机学习进度</span>
            <strong>{{ masteryProgress }}%</strong>
            <div aria-hidden="true"><i :style="{ width: masteryProgress + '%' }"></i></div>
          </div>
          <dl>
            <div><dt>层级</dt><dd>{{ mapStats.maxDepth }}</dd></div>
            <div><dt>原文覆盖</dt><dd>{{ mapStats.evidenceCoverage }}%</dd></div>
            <div><dt>已掌握</dt><dd>{{ masteredCount }}/{{ learnableNodes.length }}</dd></div>
          </dl>
          <button
            v-if="nextLearningNode || selectedNode?.depth > 0"
            type="button"
            class="continue-learning"
            :aria-label="nextLearningNode ? `继续学习${nextLearningNode.title}` : '确认当前知识点掌握状态'"
            @click="continueLearning"
          >
            <span>继续学习</span>
            <strong>{{ nextLearningNode?.title || "确认当前掌握状态" }}</strong><i>→</i>
          </button>
          <Transition name="learning-feedback">
            <div
              v-if="learningFeedback"
              class="learning-feedback"
              :class="learningFeedback.tone"
              role="status"
              aria-live="polite"
            >
              <i aria-hidden="true">{{ learningFeedback.symbol }}</i>
              <div><strong>{{ learningFeedback.title }}</strong><span>{{ learningFeedback.detail }}</span></div>
            </div>
          </Transition>
        </section>

        <section
          class="atlas-workspace"
          :class="{
            'has-navigator': outlineOpen && !zenMode,
            'has-inspector': inspectorOpen,
            immersive: zenMode,
          }"
        >
          <aside v-if="outlineOpen && !zenMode" class="map-navigator" aria-label="知识地图大纲">
            <header>
              <div><span>地图导航</span><strong>{{ filteredOutlineNodes.length }} 个节点</strong></div>
              <button type="button" aria-label="收起地图大纲" @click="outlineOpen = false">×</button>
            </header>
            <div class="navigator-filters" role="group" aria-label="大纲筛选">
              <button
                v-for="item in outlineFilterOptions"
                :key="item.value"
                type="button"
                :class="{ active: outlineFilter === item.value }"
                @click="outlineFilter = item.value"
              >{{ item.label }}</button>
            </div>
            <nav class="outline-tree">
              <button
                v-for="item in filteredOutlineNodes"
                :key="item.node.id"
                type="button"
                :class="{
                  selected: selectedNode?.id === item.node.id,
                  mastered: item.mastered,
                  'focus-root': focusRootId === item.node.id,
                }"
                :style="{ '--outline-depth': Math.min(item.depth, 4) }"
                @click="selectOutlineNode(item.node)"
              >
                <i></i>
                <span>{{ item.node.title }}</span>
                <small v-if="item.mastered">✓</small>
                <small v-else-if="item.sourceCount">文</small>
              </button>
              <p v-if="!filteredOutlineNodes.length">当前筛选下没有节点。</p>
            </nav>
            <footer><span><i class="mastered-key"></i>已掌握</span><span><i class="source-key"></i>有原文</span></footer>
          </aside>

          <div class="canvas-stage">
            <nav v-if="focusPath.length" class="focus-trail" aria-label="当前聚焦分支">
              <button type="button" @click="exitBranchFocus">完整地图</button>
              <template v-for="node in focusPath" :key="node.id">
                <i>›</i>
                <button type="button" @click="setFocusFromBreadcrumb(node)">{{ node.title }}</button>
              </template>
              <button type="button" class="exit-focus" @click="exitBranchFocus">退出聚焦</button>
            </nav>

            <div v-if="selectedNode" class="selection-bar" aria-label="选中节点快捷操作">
              <div><span>{{ selectedNodeTypeLabel }}</span><strong>{{ selectedNode.title }}</strong></div>
              <button
                type="button"
                :disabled="!selectedNode.children?.length"
                :aria-pressed="selectedIsFocusRoot"
                @click="toggleBranchFocus(selectedNode)"
              >
                {{ selectedIsFocusRoot ? "退出聚焦" : "聚焦分支" }} <kbd>F</kbd>
              </button>
              <button
                type="button"
                :disabled="!selectedNode.children?.length"
                :aria-expanded="selectedNode.children?.length ? !selectedBranchCollapsed : undefined"
                @click="toggleSelectedBranch"
              >
                {{ selectedBranchCollapsed ? "展开分支" : "收起分支" }}
              </button>
              <button
                v-if="selectedNode.depth > 0"
                type="button"
                :class="{ mastered: isSelectedMastered }"
                :aria-pressed="isSelectedMastered"
                @click="toggleMasteryWithFeedback"
              >
                {{ isSelectedMastered ? "已掌握 ✓" : "标记掌握" }}
              </button>
              <button type="button" @click="openInspector">查看原文</button>
            </div>

            <MindMapCanvas
              ref="canvasRef"
              :root="mapData.root"
              :search-term="searchTerm"
              :view-state="historyViewState"
              :selected-node-id="selectedNode?.id || ''"
              :focus-root-id="focusRootId"
              :mastered-node-ids="masteredNodeIdList"
              :density="layoutDensity"
              :display-mode="displayMode"
              :construction-revision="mapConstructionRevision"
              :immersive="zenMode"
              @select="selectNode"
              @branch-state-change="handleBranchStateChange"
              @view-change="handleCanvasViewChange"
              @search-change="handleSearchStatus"
              @density-change="changeDensity"
              @display-mode-change="changeDisplayMode"
              @toggle-zen="toggleZenMode"
            />
          </div>

          <MindMapInspector
            v-if="inspectorOpen"
            ref="evidenceRef"
            v-model:node-question="nodeQuestion"
            closable
            :selected-node="selectedNode"
            :selected-path="selectedPath"
            :selected-node-type-label="selectedNodeTypeLabel"
            :selected-learning-tip="selectedLearningTip"
            :is-selected-mastered="isSelectedMastered"
            :has-own-sources="hasOwnSources"
            :question-chunk-count="questionChunkIds.length"
            :node-answer="nodeAnswer"
            :asking-node="askingNode"
            :expanding-node="expandingNode"
            :related-loading="relatedLoading"
            :related-sources="relatedSources"
            :related-error="relatedError"
            @close="inspectorOpen = false"
            @focus="openLearningNode"
            @toggle-mastery="toggleMasteryWithFeedback"
            @expand="expandSelectedNode"
            @ask="askNode"
            @request-related="fetchRelated"
          />
        </section>
      </template>

      <section v-else-if="!histories.length || generating || generationJob" class="empty-atlas" :class="{ constructing: generating }">
        <div class="empty-map-mark" aria-hidden="true">
          <span class="map-node root-node"></span>
          <span class="map-node node-a"></span>
          <span class="map-node node-b"></span>
          <span class="map-node node-c"></span>
          <i class="route route-a"></i>
          <i class="route route-b"></i>
          <i class="route route-c"></i>
        </div>

        <div v-if="generationJob && (generating || generationJob.status === 'failed')" class="construction-copy">
          <span>{{ generationJob.status === "failed" ? "构造中断" : `${stagePosition.current} / ${stagePosition.total} · ${stageLabel}` }}</span>
          <h2>{{ generationJob.message || loadError }}</h2>
          <p>{{ generationJob.status === "failed" ? "检查后端服务、模型配置和网络后，可以按原设置重试。" : stageDetail }}</p>
          <div class="construction-progress">
            <i :style="{ width: generationJob.progress + '%' }"></i>
          </div>
          <div class="stage-track" aria-label="地图构造阶段">
            <span v-for="stage in stageSteps" :key="stage.key" :class="stageClass(stage.key)"><i></i>{{ stage.label }}</span>
          </div>
          <small v-if="generationConnectionIssue" class="connection-note">{{ generationConnectionIssue }}</small>
          <small v-else-if="generationStalled" class="connection-note">进度已较久没有更新，请确认后端服务仍在运行。</small>
          <small v-else>已等待 {{ elapsedSeconds }} 秒；离开页面后任务仍会继续</small>
          <el-button v-if="generationJob.status === 'failed'" type="primary" @click="generate">按原设置重试</el-button>
          <el-button
            v-else
            plain
            :loading="cancellingGeneration"
            @click="cancelGeneration"
          >取消本次生成</el-button>
        </div>

        <div v-else class="empty-copy">
          <span>{{ generating ? "正在建立生成任务" : "画布准备就绪" }}</span>
          <h2>{{ generating ? "正在为你读取资料" : "从一组资料开始建立地图" }}</h2>
          <p v-if="generating">任务建立后，这里会显示每一步真实构造进度。</p>
          <p v-else>选择知识库、资料范围和结构深度，然后生成第一张可核对原文的知识地图。</p>
          <ol v-if="!generating">
            <li><b>1</b>选择资料</li><li><b>2</b>构造枝架</li><li><b>3</b>沿路径学习</li>
          </ol>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import AppHeader from "../components/layout/AppHeader.vue";
import KnowledgeBaseOptions from "../components/knowledge/KnowledgeBaseOptions.vue";
import MindMapCanvas from "../components/mindmap/MindMapCanvas.vue";
import MindMapInspector from "../components/mindmap/MindMapInspector.vue";
import { useMindMapWorkspace } from "../composables/useMindMapWorkspace";
import { filterMindMapHistories } from "../utils/mindMapState";

const {
  activeHistoryId,
  askNode,
  askingNode,
  canGenerate,
  canSave,
  cancelGeneration,
  cancellingGeneration,
  canvasRef,
  completedDocuments,
  depthOptions,
  documentId,
  elapsedSeconds,
  evidenceRef,
  expandingNode,
  expandSelectedNode,
  exportMap,
  exportingFormat,
  fetchRelated,
  focusLearningNode,
  formatTime,
  generate,
  generationBlockReason,
  generationConnectionIssue,
  generationGuidance,
  generationJob,
  generationStalled,
  generating,
  handleCanvasViewChange,
  handleKnowledgeBaseChange,
  handleSearchStatus,
  hasOwnSources,
  healthOnline,
  histories,
  historyKnowledgeBaseName,
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
  openingHistoryId,
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
  setNodeMastery,
  selectedLearningTip,
  selectedNode,
  selectedNodeTypeLabel,
  selectedPath,
  selectedScopeName,
  showHistoryList,
  stageClass,
  stageDetail,
  stageLabel,
  stagePosition,
  stageSteps,
  stepSearch,
} = useMindMapWorkspace();

const setupOpen = ref(false);
const setupRef = ref(null);
const outlineOpen = ref(typeof window === "undefined" || window.innerWidth >= 1320);
const inspectorOpen = ref(typeof window === "undefined" || window.innerWidth >= 980);
const zenMode = ref(false);
const outlineFilter = ref("all");
const focusRootId = ref("");
const layoutDensity = ref("comfortable");
const displayMode = ref("detail");
const selectedBranchCollapsed = ref(false);
const learningFeedback = ref(null);
const historySearch = ref("");
const historyKnowledgeBaseFilter = ref("");
const searchInputRef = ref(null);
let inspectorBeforeZen = true;
let learningFeedbackTimer = null;

const outlineFilterOptions = [
  { label: "全部", value: "all" },
  { label: "未掌握", value: "unmastered" },
  { label: "有原文", value: "evidence" },
];

const filteredHistories = computed(() => filterMindMapHistories(histories.value, {
  query: historySearch.value,
  knowledgeBaseId: historyKnowledgeBaseFilter.value,
  knowledgeBases: knowledgeBases.value,
}));

const outlineNodes = computed(() => {
  if (!mapData.value?.root) return [];
  const rows = [];
  const mastered = new Set(masteredNodeIdList.value);
  const walk = (node, depth = 0) => {
    rows.push({
      node,
      depth,
      mastered: mastered.has(node.id),
      sourceCount: node.sources?.length || 0,
    });
    node.children?.forEach((child) => walk(child, depth + 1));
  };
  walk(mapData.value.root);
  return rows;
});

const filteredOutlineNodes = computed(() => {
  const term = searchTerm.value.trim().toLowerCase();
  return outlineNodes.value.filter((item) => {
    if (outlineFilter.value === "unmastered" && (item.mastered || item.node.depth === 0)) return false;
    if (outlineFilter.value === "evidence" && !item.sourceCount) return false;
    if (!term) return true;
    return [item.node.title, item.node.summary, ...(item.node.key_points || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(term);
  });
});

const focusPath = computed(() => {
  if (!focusRootId.value || !mapData.value?.root) return [];
  return (findNodePath(mapData.value.root, focusRootId.value) || []).slice(1);
});
const selectedIsFocusRoot = computed(() => Boolean(
  focusRootId.value && selectedNode.value?.id === focusRootId.value,
));

function findNode(node, nodeId) {
  if (!node || !nodeId) return null;
  if (node.id === nodeId) return node;
  for (const child of node.children || []) {
    const match = findNode(child, nodeId);
    if (match) return match;
  }
  return null;
}

function findNodePath(node, nodeId, path = []) {
  if (!node) return null;
  const nextPath = [...path, node];
  if (node.id === nodeId) return nextPath;
  for (const child of node.children || []) {
    const match = findNodePath(child, nodeId, nextPath);
    if (match) return match;
  }
  return null;
}

function commitViewPreference(patch) {
  const current = canvasRef.value?.getViewState?.() || historyViewState.value || {};
  handleCanvasViewChange({ ...current, ...patch });
}

function enterBranchFocus(node = selectedNode.value) {
  if (!node?.children?.length) return;
  focusRootId.value = node.id;
  commitViewPreference({ focus_root_id: node.id });
}

function exitBranchFocus() {
  if (!focusRootId.value) return;
  focusRootId.value = "";
  commitViewPreference({ focus_root_id: "" });
}

function setFocusFromBreadcrumb(node) {
  if (!node || node.id === mapData.value?.root?.id) exitBranchFocus();
  else enterBranchFocus(node);
}

function isInsideFocusedBranch(nodeId) {
  if (!focusRootId.value) return true;
  const branch = findNode(mapData.value?.root, focusRootId.value);
  return Boolean(findNode(branch, nodeId));
}

async function selectOutlineNode(node) {
  if (!node) return;
  await openLearningNode(node);
}

async function openLearningNode(node) {
  if (!node) return;
  if (!isInsideFocusedBranch(node.id)) exitBranchFocus();
  await nextTick();
  await focusLearningNode(node);
}

function toggleBranchFocus(node = selectedNode.value) {
  if (node?.id && node.id === focusRootId.value) exitBranchFocus();
  else enterBranchFocus(node);
}

function showLearningFeedback(node, mastered) {
  window.clearTimeout(learningFeedbackTimer);
  const completed = mastered && masteryProgress.value === 100;
  learningFeedback.value = mastered
    ? {
      tone: "success",
      symbol: completed ? "★" : "✓",
      title: completed ? "本轮学习完成" : `已掌握“${node.title}”`,
      detail: completed
        ? `${learnableNodes.value.length} 个知识点已全部掌握`
        : `本机学习进度已更新为 ${masteryProgress.value}%`,
    }
    : {
      tone: "review",
      symbol: "↻",
      title: `已将“${node.title}”加入复习`,
      detail: "继续学习时会再次回到这个知识点",
    };
  learningFeedbackTimer = window.setTimeout(() => {
    learningFeedback.value = null;
  }, 3200);
}

function toggleMasteryWithFeedback() {
  const node = selectedNode.value;
  if (!node || node.depth === 0) return;
  const mastered = !isSelectedMastered.value;
  setNodeMastery(node, mastered);
  showLearningFeedback(node, mastered);
}

async function continueLearning() {
  const current = selectedNode.value;
  let mastered = null;
  if (current?.depth > 0) {
    mastered = false;
    try {
      await ElMessageBox.confirm(
        `“${current.title}”是否已经掌握？`,
        "继续学习",
        {
          confirmButtonText: "已掌握",
          cancelButtonText: "还需复习",
          distinguishCancelAndClose: true,
          closeOnClickModal: false,
          type: "info",
        },
      );
      mastered = true;
    } catch (action) {
      if (action !== "cancel") return;
    }
    setNodeMastery(current, mastered);
    showLearningFeedback(current, mastered);
  }

  await nextTick();
  const target = nextLearningNode.value;
  if (!target) {
    if (mastered === true) ElMessage.success("本轮学习已完成，所有知识点都已掌握。");
    else ElMessage.info("当前知识点已保留为待复习，本轮没有其他未掌握章节。");
    return;
  }
  await openLearningNode(target);
}

function changeDensity(value) {
  layoutDensity.value = value === "compact" ? "compact" : "comfortable";
  commitViewPreference({ layout_density: layoutDensity.value });
}

function changeDisplayMode(value) {
  displayMode.value = value === "title" ? "title" : "detail";
  commitViewPreference({ display_mode: displayMode.value });
}

function handleBranchStateChange(state) {
  if (state?.nodeId !== selectedNode.value?.id) return;
  selectedBranchCollapsed.value = Boolean(state.collapsed);
}

async function toggleSelectedBranch() {
  await canvasRef.value?.toggleSelectedBranch?.();
}

async function openGenerationSetup() {
  if (generating.value) return;
  if (zenMode.value) toggleZenMode(false);
  setupOpen.value = true;
  await nextTick();
  setupRef.value?.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "start",
  });
}

async function returnToHistoryList() {
  if (!(await showHistoryList())) return;
  zenMode.value = false;
  focusRootId.value = "";
  setupOpen.value = false;
}

async function openInspector() {
  inspectorOpen.value = true;
  await nextTick();
  evidenceRef.value?.showSources?.();
  if (window.innerWidth <= 980) evidenceRef.value?.scrollIntoView?.();
}

function toggleZenMode(force) {
  const next = typeof force === "boolean" ? force : !zenMode.value;
  if (next === zenMode.value) return;
  if (next) {
    inspectorBeforeZen = inspectorOpen.value;
    inspectorOpen.value = false;
    zenMode.value = true;
  } else {
    zenMode.value = false;
    inspectorOpen.value = inspectorBeforeZen;
  }
}

function handleDocumentCommand(command) {
  if (command === "setup") openGenerationSetup();
  if (command === "zen") toggleZenMode();
  if (command === "delete") removeHistory();
}

function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

function handleGlobalKeydown(event) {
  if (!mapData.value) return;
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && key === "f") {
    event.preventDefault();
    searchInputRef.value?.focus?.();
    return;
  }
  if (isEditableTarget(event.target)) return;
  if (event.repeat && ["f", "z"].includes(key)) return;

  if (key === "escape") {
    if (focusRootId.value) exitBranchFocus();
    else if (zenMode.value) toggleZenMode(false);
    return;
  }
  if ((event.ctrlKey || event.metaKey) && key === "0") {
    event.preventDefault();
    canvasRef.value?.centerRoot?.();
    return;
  }
  if (key === "f") {
    event.preventDefault();
    toggleBranchFocus();
  } else if (key === "z") {
    event.preventDefault();
    toggleZenMode();
  } else if (["+", "="].includes(event.key)) {
    event.preventDefault();
    canvasRef.value?.zoom?.(1.2);
  } else if (event.key === "-") {
    event.preventDefault();
    canvasRef.value?.zoom?.(0.82);
  }
}

watch(historyViewState, (state) => {
  const root = mapData.value?.root;
  const savedFocus = findNode(root, state?.focus_root_id)?.children?.length ? state.focus_root_id : "";
  focusRootId.value = savedFocus;
  layoutDensity.value = state?.layout_density === "compact" ? "compact" : "comfortable";
  displayMode.value = state?.display_mode === "title" ? "title" : "detail";
});

watch(() => mapData.value?.root?.id, () => {
  setupOpen.value = false;
  outlineFilter.value = "all";
  selectedBranchCollapsed.value = false;
  if (!mapData.value) {
    focusRootId.value = "";
    zenMode.value = false;
  }
});

onMounted(() => window.addEventListener("keydown", handleGlobalKeydown));
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  window.clearTimeout(learningFeedbackTimer);
});
</script>

<style scoped>
.mind-map-view {
  --atlas-cobalt: #2f5ee5;
  --atlas-teal: #168c8c;
  --atlas-amber: #d9912b;
  min-height: 100vh;
  padding: 16px 0 64px;
}

.map-page {
  display: grid;
  gap: 16px;
  width: min(1540px, calc(100% - 32px));
  margin: 34px auto 0;
}

.page-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 32px;
  padding: 8px 4px 12px;
}

.utility-label {
  margin: 0 0 7px;
  color: var(--atlas-cobalt);
  font-family: "DIN Alternate", Consolas, "Microsoft YaHei", monospace;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.13em;
}

.page-heading h1 {
  margin: 0;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(34px, 4vw, 52px);
  letter-spacing: -0.035em;
  line-height: 1.08;
}

.page-heading > div:first-child > p:last-child {
  max-width: 600px;
  margin: 11px 0 0;
  color: var(--cm-muted);
  font-size: 14px;
  line-height: 1.7;
}

.map-snapshot {
  display: grid;
  min-width: 126px;
  padding-left: 20px;
  border-left: 1px solid var(--cm-border);
  justify-items: end;
}

.map-snapshot span,
.map-snapshot small {
  color: var(--cm-muted);
  font-size: 10px;
  letter-spacing: 0.08em;
}

.map-snapshot strong {
  color: var(--cm-heading);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 38px;
  line-height: 1.1;
}

.control-deck {
  padding: 16px 18px;
  border: 1px solid var(--cm-border);
  border-radius: 16px;
  background: color-mix(in srgb, var(--cm-surface) 94%, transparent);
  box-shadow: 0 14px 38px rgba(28, 50, 84, 0.08);
  backdrop-filter: blur(14px);
}

.control-deck-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 13px;
}

.control-deck-heading > div {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.control-deck-heading span {
  color: var(--cm-heading);
  font-size: 13px;
  font-weight: 800;
}

.control-deck-heading p {
  margin: 0;
  color: var(--cm-muted);
  font-size: 11px;
}

.working-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--atlas-cobalt) !important;
  font-size: 11px !important;
}

.working-badge i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--atlas-cobalt);
  box-shadow: 0 0 0 5px var(--cm-primary-soft);
  animation: pulse 1.6s ease-in-out infinite;
}

.control-grid {
  display: grid;
  grid-template-columns: minmax(170px, 0.8fr) minmax(220px, 1.1fr) auto minmax(240px, 1.15fr) auto;
  align-items: end;
  gap: 12px;
}

.control-grid label {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.control-grid label > span {
  color: var(--cm-muted);
  font-size: 11px;
  font-weight: 700;
}

.generate-button {
  min-height: 40px;
  padding-inline: 21px;
}

.control-guidance {
  margin: 12px 0 0;
  color: var(--cm-warning);
  font-size: 12px;
}

.control-guidance a {
  margin-left: 8px;
  color: var(--atlas-cobalt);
  font-weight: 800;
}

.generation-status {
  display: grid;
  gap: 13px;
  padding: 16px 18px;
  border: 1px solid color-mix(in srgb, var(--atlas-cobalt) 28%, var(--cm-border));
  border-radius: 14px;
  background: color-mix(in srgb, var(--cm-primary-soft) 45%, var(--cm-surface));
}

.status-copy {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 13px;
}

.status-copy > span {
  padding: 5px 9px;
  border-radius: 999px;
  color: var(--atlas-cobalt);
  background: var(--cm-surface);
  font-size: 11px;
  font-weight: 800;
}

.status-copy > div { display: grid; gap: 3px; }
.status-copy strong { color: var(--cm-heading); }
.status-copy small { color: var(--cm-muted); font-size: 11px; }
.status-copy b {
  color: var(--atlas-cobalt);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 22px;
}

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
  font-size: 10px;
}

.stage-track i {
  width: 7px;
  height: 7px;
  border: 2px solid var(--cm-border);
  border-radius: 50%;
  background: var(--cm-surface);
}

.stage-track span.active { color: var(--atlas-cobalt); font-weight: 800; }
.stage-track span.active i {
  border-color: var(--atlas-cobalt);
  box-shadow: 0 0 0 4px var(--cm-primary-soft);
}
.stage-track span.done i { border-color: var(--cm-success); background: var(--cm-success); }

.map-command-center {
  overflow: hidden;
  border: 1px solid var(--cm-border);
  border-radius: 18px;
  background: var(--cm-surface);
  box-shadow: 0 16px 44px rgba(28, 50, 84, 0.08);
}

.map-identity {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 20px 16px;
}

.map-identity > div:first-child { min-width: 0; }
.map-identity h2 {
  margin: 7px 0 4px;
  overflow: hidden;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(22px, 2.3vw, 31px);
  line-height: 1.22;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-identity p {
  margin: 0;
  color: var(--cm-muted);
  font-size: 12px;
}

.map-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--cm-success);
  font-size: 10px;
  font-weight: 800;
}

.map-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.map-status.dirty { color: var(--atlas-amber); }
.file-actions { display: flex; gap: 8px; flex: 0 0 auto; }

.learning-route {
  display: grid;
  grid-template-columns: minmax(160px, 0.65fr) minmax(420px, 1.7fr) minmax(220px, 0.75fr);
  align-items: center;
  gap: 20px;
  padding: 14px 20px;
  border-top: 1px solid var(--cm-border);
  border-bottom: 1px solid var(--cm-border);
  background: color-mix(in srgb, var(--cm-surface-soft) 84%, var(--cm-primary-soft));
}

.progress-copy {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 4px 10px;
}

.progress-copy span { color: var(--cm-muted); font-size: 11px; }
.progress-copy strong {
  color: var(--atlas-cobalt);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 20px;
}

.progress-copy > div {
  grid-column: 1 / -1;
  height: 4px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--cm-border);
}

.progress-copy i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--atlas-cobalt), var(--atlas-teal));
  transition: width 0.25s ease;
}

.learning-route dl {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin: 0;
}

.learning-route dl > div {
  display: flex;
  align-items: baseline;
  gap: 6px;
  justify-content: center;
  border-right: 1px solid var(--cm-border);
}

.learning-route dl > div:last-child { border-right: 0; }
.learning-route dt { color: var(--cm-muted); font-size: 10px; }
.learning-route dd {
  margin: 0;
  color: var(--cm-heading);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 16px;
  font-weight: 800;
}

.continue-learning {
  position: relative;
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 10px 38px 10px 12px;
  border: 1px solid var(--cm-border);
  border-radius: 10px;
  color: inherit;
  background: var(--cm-surface);
  text-align: left;
  cursor: pointer;
}

.continue-learning span { color: var(--cm-muted); font-size: 10px; }
.continue-learning strong {
  overflow: hidden;
  color: var(--cm-heading);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.continue-learning i {
  position: absolute;
  top: 50%;
  right: 13px;
  color: var(--atlas-cobalt);
  font-size: 18px;
  font-style: normal;
  transform: translateY(-50%);
}
.continue-learning:hover,
.continue-learning:focus-visible { border-color: var(--atlas-cobalt); outline: none; }

.map-search-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 11px 20px;
}

.node-search {
  display: grid;
  grid-template-columns: minmax(240px, 380px) auto 32px 32px;
  align-items: center;
  gap: 6px;
}

.search-count {
  min-width: 48px;
  color: var(--cm-muted);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 11px;
  text-align: center;
}

.node-search button {
  width: 32px;
  height: 32px;
  padding: 0;
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  color: var(--cm-text);
  background: var(--cm-surface-soft);
  cursor: pointer;
}
.node-search button:disabled { opacity: 0.35; cursor: not-allowed; }
.node-search button:not(:disabled):hover { border-color: var(--atlas-cobalt); color: var(--atlas-cobalt); }
.map-search-row > p { margin: 0; color: var(--cm-muted); font-size: 10px; }

.atlas-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 390px);
  gap: 16px;
  align-items: stretch;
}

.history-library {
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: 16px;
  background: var(--cm-surface);
  box-shadow: 0 14px 38px rgba(28, 50, 84, 0.06);
}

.history-library > header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--cm-border);
}

.history-library > header span {
  color: var(--atlas-cobalt);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.history-library > header h2 {
  margin: 5px 0 4px;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", serif;
  font-size: clamp(22px, 2.4vw, 32px);
}

.history-library > header p { margin: 0; color: var(--cm-muted); font-size: 12px; }
.history-library > header > strong {
  color: var(--atlas-cobalt);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 24px;
  white-space: nowrap;
}

.history-filters {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) minmax(180px, 260px);
  gap: 10px;
}

.history-shelf {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr));
  gap: 12px;
}

.history-filter-empty {
  grid-column: 1 / -1;
  margin: 8px 0;
  padding: 28px;
  border: 1px dashed var(--cm-border);
  border-radius: 12px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  text-align: center;
}

.history-shelf > button {
  position: relative;
  display: grid;
  min-height: 154px;
  padding: 15px 16px 14px 54px;
  overflow: hidden;
  border: 1px solid var(--cm-border);
  border-radius: 12px;
  color: var(--cm-text);
  background: color-mix(in srgb, var(--cm-surface-soft) 72%, var(--cm-surface));
  text-align: left;
  cursor: pointer;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.history-shelf > button:not(:disabled):hover,
.history-shelf > button:not(:disabled):focus-visible {
  border-color: color-mix(in srgb, var(--atlas-cobalt) 48%, var(--cm-border));
  box-shadow: 0 12px 28px rgba(47, 94, 229, 0.11);
  transform: translateY(-2px);
}

.history-shelf > button:focus-visible { outline: 3px solid color-mix(in srgb, var(--atlas-cobalt) 22%, transparent); }
.history-shelf > button:disabled { cursor: wait; opacity: 0.62; }
.history-shelf > button.opening { border-color: color-mix(in srgb, var(--atlas-cobalt) 48%, var(--cm-border)); opacity: 1; }
.history-meta { display: flex; min-width: 0; justify-content: space-between; gap: 10px; }
.history-meta b { overflow: hidden; color: var(--atlas-cobalt); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.history-meta time { color: var(--cm-muted); font-size: 9px; white-space: nowrap; }
.history-shelf > button > strong {
  align-self: end;
  overflow: hidden;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", serif;
  font-size: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-shelf > button > small { color: var(--cm-muted); font-size: 10px; }
.history-shelf > button > em { align-self: end; color: var(--atlas-cobalt); font-size: 11px; font-style: normal; font-weight: 800; }
.history-route { position: absolute; top: 18px; bottom: 18px; left: 20px; width: 20px; }
.history-route::before { position: absolute; top: 8px; bottom: 8px; left: 6px; width: 1px; background: color-mix(in srgb, var(--atlas-cobalt) 38%, var(--cm-border)); content: ""; }
.history-route i { position: absolute; left: 2px; z-index: 1; width: 9px; height: 9px; border: 2px solid var(--cm-surface); border-radius: 50%; background: var(--atlas-cobalt); }
.history-route i:nth-child(1) { top: 4px; }
.history-route i:nth-child(2) { top: calc(50% - 4px); background: var(--atlas-teal); }
.history-route i:nth-child(3) { bottom: 4px; background: var(--atlas-amber); }

.empty-atlas {
  position: relative;
  display: grid;
  min-height: 520px;
  overflow: hidden;
  place-items: center;
  border: 1px solid var(--cm-border);
  border-radius: 18px;
  background:
    radial-gradient(circle at 50% 45%, color-mix(in srgb, var(--cm-primary-soft) 72%, transparent), transparent 34%),
    var(--cm-surface);
  text-align: center;
}

.empty-copy {
  position: relative;
  z-index: 2;
  max-width: 640px;
  padding: 32px;
}

.empty-copy > span {
  color: var(--atlas-cobalt);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.09em;
}

.empty-copy h2 {
  margin: 8px 0 10px;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", serif;
  font-size: clamp(26px, 3vw, 38px);
}

.empty-copy p { margin: 0; color: var(--cm-muted); line-height: 1.7; }
.empty-copy ol {
  display: flex;
  justify-content: center;
  gap: 22px;
  margin: 26px 0 0;
  padding: 0;
  color: var(--cm-muted);
  font-size: 12px;
  list-style: none;
}
.empty-copy li { display: flex; align-items: center; gap: 7px; }
.empty-copy b {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 50%;
  color: var(--atlas-cobalt);
  background: var(--cm-primary-soft);
  font-family: Consolas, monospace;
  font-size: 10px;
}

.empty-map-mark {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 720px;
  height: 360px;
  opacity: 0.34;
  transform: translate(-50%, -50%);
}

.map-node,
.route { position: absolute; }
.map-node {
  z-index: 2;
  width: 26px;
  height: 18px;
  border: 2px solid var(--atlas-cobalt);
  border-radius: 6px;
  background: var(--cm-surface);
}
.root-node { top: 171px; left: 347px; width: 34px; height: 24px; background: var(--atlas-cobalt); }
.node-a { top: 58px; left: 92px; border-color: var(--atlas-teal); }
.node-b { top: 54px; right: 84px; border-color: var(--atlas-amber); }
.node-c { right: 52px; bottom: 56px; border-color: #7457c6; }
.route {
  z-index: 1;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--atlas-cobalt));
  transform-origin: right center;
}
.route-a { top: 124px; left: 111px; width: 258px; transform: rotate(24deg); }
.route-b { top: 124px; right: 103px; width: 265px; transform: rotate(-24deg); }
.route-c { right: 70px; bottom: 117px; width: 306px; transform: rotate(25deg); }

.state-message {
  margin: 0;
  padding: 12px 14px;
  border-radius: 10px;
}
.error-state {
  color: var(--cm-danger);
  background: color-mix(in srgb, var(--cm-danger) 9%, var(--cm-surface));
}

@keyframes pulse {
  0%, 100% { opacity: 0.6; transform: scale(0.86); }
  50% { opacity: 1; transform: scale(1); }
}

@media (max-width: 1250px) {
  .control-grid {
    grid-template-columns: 1fr 1.2fr auto auto;
  }
  .history-control { grid-column: 1 / 3; }
  .generate-button { grid-column: 4; grid-row: 1; }
  .learning-route { grid-template-columns: 180px 1fr; }
  .continue-learning { grid-column: 1 / -1; }
}

@media (max-width: 1080px) {
  .atlas-workspace { grid-template-columns: 1fr; }
  .learning-route { grid-template-columns: 1fr; }
  .learning-route dl > div { justify-content: flex-start; }
  .continue-learning { grid-column: auto; }
  .map-search-row { align-items: flex-start; flex-direction: column; }
}

@media (max-width: 760px) {
  .mind-map-view { padding-top: 8px; }
  .map-page {
    width: min(100% - 20px, 1540px);
    margin-top: 26px;
  }
  .page-heading { grid-template-columns: 1fr; }
  .map-snapshot { display: none; }
  .control-deck { padding: 14px; }
  .control-deck-heading > div { display: grid; gap: 3px; }
  .control-grid { grid-template-columns: 1fr; }
  .history-control,
  .generate-button { grid-column: auto; grid-row: auto; }
  .status-copy { grid-template-columns: 1fr auto; }
  .status-copy > span { grid-column: 1 / -1; justify-self: start; }
  .stage-track { grid-template-columns: repeat(2, 1fr); }
  .map-identity { align-items: flex-start; flex-direction: column; }
  .file-actions { width: 100%; flex-wrap: wrap; }
  .learning-route dl { grid-template-columns: 1fr 1fr; gap: 11px 0; }
  .learning-route dl > div:nth-child(2) { border-right: 0; }
  .node-search {
    width: 100%;
    grid-template-columns: minmax(0, 1fr) auto 32px 32px;
  }
  .empty-copy ol { align-items: flex-start; flex-direction: column; width: max-content; margin-inline: auto; }
  .history-library { padding: 16px; }
  .history-library > header { align-items: flex-start; flex-direction: column; gap: 8px; }
  .history-filters { grid-template-columns: 1fr; }
  .history-shelf { grid-template-columns: 1fr; }
}

/* XMind 式画布优先工作区：地图生成后只保留紧凑文档栏，把空间让给画布。 */
.mind-map-view {
  min-height: 100vh;
  padding: 12px 0 44px;
}

.map-page {
  gap: 12px;
  width: min(1600px, calc(100% - 24px));
  margin-top: 24px;
}

.page-heading { padding-block: 8px 4px; }
.page-heading h1 { font-size: clamp(34px, 4vw, 50px); }

.control-deck {
  scroll-margin-top: 76px;
  padding: 15px 17px;
  border-radius: 13px;
  box-shadow: 0 10px 30px rgba(28, 50, 84, 0.07);
}

.control-deck-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.control-deck-actions > button,
.map-navigator header > button {
  display: grid;
  width: 30px;
  height: 30px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 7px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  font-size: 18px;
  cursor: pointer;
}

.generation-ribbon {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(180px, 0.65fr) auto auto;
  align-items: center;
  gap: 10px 16px;
  padding: 10px 13px;
  border: 1px solid color-mix(in srgb, var(--atlas-cobalt) 28%, var(--cm-border));
  border-radius: 11px;
  background: color-mix(in srgb, var(--cm-primary-soft) 50%, var(--cm-surface));
}

.generation-ribbon.failed {
  border-color: color-mix(in srgb, var(--cm-danger) 36%, var(--cm-border));
  background: color-mix(in srgb, var(--cm-danger) 7%, var(--cm-surface));
}

.ribbon-stage {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.ribbon-stage > i {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--atlas-cobalt);
  box-shadow: 0 0 0 5px var(--cm-primary-soft);
  animation: pulse 1.4s ease-in-out infinite;
}

.failed .ribbon-stage > i { background: var(--cm-danger); box-shadow: none; animation: none; }
.ribbon-stage > div { display: grid; min-width: 0; gap: 2px; }
.ribbon-stage span { color: var(--atlas-cobalt); font-size: 10px; font-weight: 800; }
.ribbon-stage strong { overflow: hidden; color: var(--cm-heading); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.ribbon-progress { height: 4px; overflow: hidden; border-radius: 999px; background: var(--cm-border); }
.ribbon-progress span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--atlas-cobalt), var(--atlas-teal)); }
.generation-ribbon > b { color: var(--atlas-cobalt); font-family: "DIN Alternate", Consolas, monospace; font-size: 15px; }
.generation-ribbon > small { grid-column: 1 / 4; color: var(--cm-warning); font-size: 10px; }
.ribbon-actions {
  display: flex;
  justify-self: end;
  gap: 10px;
}
.ribbon-actions button {
  border: 0;
  color: var(--atlas-cobalt);
  background: transparent;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}
.ribbon-actions button:disabled { cursor: wait; opacity: 0.55; }

.map-document-bar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  grid-template-columns: minmax(270px, 1fr) minmax(250px, 430px) auto;
  min-height: 58px;
  align-items: center;
  gap: 14px;
  padding: 8px 10px;
  border: 1px solid var(--cm-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--cm-surface) 94%, transparent);
  box-shadow: 0 8px 24px rgba(28, 50, 84, 0.08);
  backdrop-filter: blur(16px);
}

.document-leading,
.document-actions,
.node-search {
  display: flex;
  min-width: 0;
  align-items: center;
}

.document-leading { gap: 10px; }
.rail-toggle,
.plain-action,
.more-action,
.shortcut-action {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.rail-toggle.active,
.plain-action.active {
  border-color: color-mix(in srgb, var(--atlas-cobalt) 34%, var(--cm-border));
  color: var(--atlas-cobalt);
  background: var(--cm-primary-soft);
}

.document-title {
  display: grid;
  min-width: 0;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline;
  gap: 2px 8px;
}

.document-title strong {
  overflow: hidden;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-title small {
  grid-column: 1 / -1;
  overflow: hidden;
  color: var(--cm-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-status { align-self: center; }
.node-search { display: grid; grid-template-columns: minmax(0, 1fr) auto 30px 30px; gap: 5px; }
.node-search :deep(.el-input__wrapper) { min-height: 34px; border-radius: 8px; box-shadow: 0 0 0 1px var(--cm-border) inset; }
.node-search > button {
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid var(--cm-border);
  border-radius: 7px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  cursor: pointer;
}
.node-search > button:disabled { opacity: 0.35; cursor: not-allowed; }

.document-actions { justify-content: flex-end; gap: 6px; }
.new-map-action {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  gap: 7px;
  padding: 0 12px 0 7px;
  border: 1px solid #244ac0;
  border-radius: 9px;
  color: #fff;
  background: linear-gradient(135deg, var(--atlas-cobalt), #244ac0);
  box-shadow: 0 7px 18px rgba(47, 94, 229, 0.24);
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
  cursor: pointer;
  transition: box-shadow 160ms ease, transform 160ms ease;
}
.new-map-action i {
  display: grid;
  width: 22px;
  height: 22px;
  place-items: center;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.16);
  font-size: 16px;
  font-style: normal;
  line-height: 1;
}
.new-map-action:not(:disabled):hover,
.new-map-action:not(:disabled):focus-visible {
  box-shadow: 0 9px 24px rgba(47, 94, 229, 0.32);
  outline: none;
  transform: translateY(-1px);
}
.new-map-action:focus-visible { outline: 3px solid color-mix(in srgb, var(--atlas-cobalt) 24%, transparent); outline-offset: 2px; }
.new-map-action:disabled { opacity: 0.55; cursor: not-allowed; }
.history-action { white-space: nowrap; }
.history-action:disabled { opacity: 0.55; cursor: not-allowed; }
.more-action,
.shortcut-action { width: 34px; padding: 0; letter-spacing: 0.05em; }
.shortcut-list { display: grid; gap: 9px; color: var(--cm-text); }
.shortcut-list strong { color: var(--cm-heading); }
.shortcut-list span { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: 12px; }
kbd {
  padding: 2px 5px;
  border: 1px solid var(--cm-border);
  border-bottom-width: 2px;
  border-radius: 5px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 9px;
}

.learning-strip {
  display: grid;
  grid-template-columns: minmax(190px, 0.65fr) minmax(320px, 1.2fr) minmax(220px, 0.75fr);
  align-items: center;
  gap: 16px;
  padding: 9px 12px;
  border: 1px solid var(--cm-border);
  border-radius: 11px;
  background: color-mix(in srgb, var(--cm-surface-soft) 82%, var(--cm-primary-soft));
}

.learning-progress {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 3px 9px;
}
.learning-progress span { color: var(--cm-muted); font-size: 10px; }
.learning-progress strong { color: var(--atlas-cobalt); font-family: "DIN Alternate", Consolas, monospace; font-size: 16px; }
.learning-progress > div { grid-column: 1 / -1; height: 3px; overflow: hidden; border-radius: 99px; background: var(--cm-border); }
.learning-progress i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--atlas-cobalt), var(--atlas-teal)); transition: width 360ms ease; }
.learning-strip dl { display: grid; grid-template-columns: repeat(3, 1fr); margin: 0; }
.learning-strip dl > div { display: flex; justify-content: center; gap: 6px; border-right: 1px solid var(--cm-border); }
.learning-strip dl > div:last-child { border-right: 0; }
.learning-strip dt { color: var(--cm-muted); font-size: 10px; }
.learning-strip dd { margin: 0; color: var(--cm-heading); font-family: "DIN Alternate", Consolas, monospace; font-size: 13px; font-weight: 800; }

.learning-strip .continue-learning { min-height: 38px; padding-block: 7px; }
.learning-feedback {
  display: flex;
  min-height: 42px;
  grid-column: 1 / -1;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid color-mix(in srgb, var(--atlas-teal) 36%, var(--cm-border));
  border-radius: 10px;
  color: var(--cm-text);
  background: color-mix(in srgb, var(--atlas-teal) 8%, var(--cm-surface));
}
.learning-feedback.review {
  border-color: color-mix(in srgb, var(--atlas-amber) 38%, var(--cm-border));
  background: color-mix(in srgb, var(--atlas-amber) 8%, var(--cm-surface));
}
.learning-feedback > i {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  background: var(--atlas-teal);
  font-size: 15px;
  font-style: normal;
  font-weight: 900;
}
.learning-feedback.review > i { background: var(--atlas-amber); }
.learning-feedback > div { display: grid; min-width: 0; gap: 2px; }
.learning-feedback strong { overflow: hidden; color: var(--cm-heading); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.learning-feedback span { color: var(--cm-muted); font-size: 10px; }
.learning-feedback-enter-active,
.learning-feedback-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.learning-feedback-enter-from,
.learning-feedback-leave-to { opacity: 0; transform: translateY(-5px); }

.atlas-workspace {
  position: relative;
  display: grid;
  min-width: 0;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  align-items: stretch;
}

.atlas-workspace.has-navigator { grid-template-columns: 244px minmax(0, 1fr); }
.atlas-workspace.has-inspector { grid-template-columns: minmax(0, 1fr) minmax(340px, 380px); }
.atlas-workspace.has-navigator.has-inspector { grid-template-columns: 244px minmax(0, 1fr) minmax(340px, 380px); }

.map-navigator {
  display: grid;
  height: clamp(650px, calc(100vh - 214px), 860px);
  min-width: 0;
  overflow: hidden;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  border: 1px solid var(--cm-border);
  border-radius: 14px;
  background: var(--cm-surface);
  box-shadow: 0 14px 38px rgba(28, 50, 84, 0.08);
}

.map-navigator > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 14px 13px 10px;
}
.map-navigator header > div { display: grid; gap: 2px; }
.map-navigator header span { color: var(--atlas-cobalt); font-size: 10px; font-weight: 800; letter-spacing: 0.08em; }
.map-navigator header strong { color: var(--cm-heading); font-size: 13px; }

.navigator-filters {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3px;
  margin: 0 10px 9px;
  padding: 3px;
  border: 1px solid var(--cm-border);
  border-radius: 9px;
  background: var(--cm-surface-soft);
}
.navigator-filters button {
  min-height: 28px;
  border: 0;
  border-radius: 6px;
  color: var(--cm-muted);
  background: transparent;
  font-size: 10px;
  cursor: pointer;
}
.navigator-filters button.active { color: var(--atlas-cobalt); background: var(--cm-surface); box-shadow: 0 3px 10px rgba(28, 50, 84, 0.08); }

.outline-tree {
  min-height: 0;
  padding: 3px 8px 12px;
  overflow: auto;
  scrollbar-color: color-mix(in srgb, var(--cm-muted) 35%, transparent) transparent;
}
.outline-tree > button {
  display: grid;
  width: 100%;
  min-height: 34px;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  padding: 5px 8px 5px calc(9px + var(--outline-depth) * 14px);
  border: 0;
  border-radius: 7px;
  color: var(--cm-text);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.outline-tree > button:hover { background: var(--cm-surface-soft); }
.outline-tree > button.selected { color: var(--atlas-cobalt); background: var(--cm-primary-soft); font-weight: 700; }
.outline-tree > button.focus-root { box-shadow: inset 3px 0 0 var(--atlas-amber); }
.outline-tree > button > i { width: 7px; height: 7px; border: 1px solid var(--atlas-cobalt); border-radius: 2px; }
.outline-tree > button.mastered > i { border-color: var(--atlas-teal); background: var(--atlas-teal); }
.outline-tree > button span { overflow: hidden; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.outline-tree > button small { display: grid; width: 17px; height: 17px; place-items: center; border-radius: 5px; color: var(--atlas-teal); background: color-mix(in srgb, var(--atlas-teal) 10%, var(--cm-surface)); font-size: 9px; font-weight: 900; }
.outline-tree > p { margin: 28px 12px; color: var(--cm-muted); font-size: 11px; text-align: center; }
.map-navigator > footer { display: flex; gap: 12px; padding: 9px 12px; border-top: 1px solid var(--cm-border); color: var(--cm-muted); font-size: 9px; }
.map-navigator footer span { display: flex; align-items: center; gap: 5px; }
.map-navigator footer i { width: 7px; height: 7px; border-radius: 2px; }
.mastered-key { background: var(--atlas-teal); }
.source-key { border: 1px solid var(--atlas-amber); background: color-mix(in srgb, var(--atlas-amber) 14%, transparent); }

.canvas-stage { position: relative; min-width: 0; }
.selection-bar,
.focus-trail {
  position: absolute;
  z-index: 9;
  display: flex;
  align-items: center;
  border: 1px solid color-mix(in srgb, var(--atlas-cobalt) 22%, var(--cm-border));
  background: color-mix(in srgb, var(--cm-surface) 92%, transparent);
  box-shadow: 0 8px 24px rgba(35, 54, 84, 0.12);
  backdrop-filter: blur(16px);
}

.selection-bar {
  top: 16px;
  right: 16px;
  max-width: calc(100% - 310px);
  gap: 4px;
  padding: 5px;
  border-radius: 10px;
}
.selection-bar > div { display: grid; min-width: 105px; max-width: 190px; gap: 1px; padding: 0 7px; }
.selection-bar > div span { color: var(--atlas-cobalt); font-size: 8px; font-weight: 800; letter-spacing: 0.06em; }
.selection-bar > div strong { overflow: hidden; color: var(--cm-heading); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.selection-bar > button,
.focus-trail button {
  min-height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  color: var(--cm-muted);
  background: transparent;
  font-size: 10px;
  white-space: nowrap;
  cursor: pointer;
}
.selection-bar > button:hover,
.selection-bar > button:focus-visible,
.focus-trail button:hover,
.focus-trail button:focus-visible { color: var(--atlas-cobalt); background: var(--cm-primary-soft); outline: none; }
.selection-bar > button:disabled { opacity: 0.35; cursor: not-allowed; }
.selection-bar > button.mastered { color: var(--atlas-teal); background: color-mix(in srgb, var(--atlas-teal) 10%, transparent); }
.selection-bar kbd { margin-left: 3px; }

.focus-trail {
  top: 72px;
  left: 16px;
  max-width: calc(100% - 32px);
  padding: 3px 5px;
  overflow-x: auto;
  border-radius: 9px;
}
.focus-trail i { color: var(--cm-border); font-style: normal; }
.focus-trail .exit-focus { margin-left: 3px; color: var(--atlas-amber); background: color-mix(in srgb, var(--atlas-amber) 9%, transparent); }

.atlas-workspace :deep(.map-inspector) {
  height: clamp(650px, calc(100vh - 214px), 860px);
  max-height: none;
  border-radius: 14px;
  box-shadow: 0 14px 38px rgba(28, 50, 84, 0.08);
}

.empty-atlas {
  min-height: clamp(560px, calc(100vh - 330px), 760px);
  border-radius: 14px;
  box-shadow: 0 14px 38px rgba(28, 50, 84, 0.06);
}
.construction-copy {
  position: relative;
  z-index: 3;
  display: grid;
  width: min(820px, calc(100% - 48px));
  gap: 12px;
  padding: 28px;
  border: 1px solid color-mix(in srgb, var(--atlas-cobalt) 26%, var(--cm-border));
  border-radius: 14px;
  background: color-mix(in srgb, var(--cm-surface) 94%, transparent);
  box-shadow: 0 18px 52px rgba(28, 50, 84, 0.12);
  backdrop-filter: blur(18px);
}
.construction-copy > span { color: var(--atlas-cobalt); font-size: 10px; font-weight: 800; letter-spacing: 0.08em; }
.construction-copy h2 { margin: 0; color: var(--cm-heading); font-family: "Source Han Serif SC", "Songti SC", serif; font-size: clamp(22px, 3vw, 34px); }
.construction-copy > p { margin: 0; color: var(--cm-muted); line-height: 1.65; }
.construction-copy > small { color: var(--cm-muted); font-size: 10px; }
.construction-copy > .connection-note { color: var(--cm-warning); }
.construction-progress { height: 6px; overflow: hidden; border-radius: 999px; background: var(--cm-border); }
.construction-progress > i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--atlas-cobalt), var(--atlas-teal)); transition: width 0.35s ease; }
.construction-copy .stage-track { grid-template-columns: repeat(7, 1fr); }
.construction-copy .stage-track span { justify-content: center; }
.constructing .route { animation: routeGrow 1.5s ease-in-out infinite alternate; }
.constructing .map-node { animation: nodeBreathe 1.5s ease-in-out infinite; }
.constructing .node-a { animation-delay: 0.18s; }
.constructing .node-b { animation-delay: 0.34s; }
.constructing .node-c { animation-delay: 0.5s; }

@keyframes routeGrow {
  from { opacity: 0.25; transform: scaleX(0.55); }
  to { opacity: 0.85; transform: scaleX(1); }
}
@keyframes nodeBreathe {
  0%, 100% { opacity: 0.46; }
  50% { opacity: 1; box-shadow: 0 0 0 7px var(--cm-primary-soft); }
}

.zen-mode {
  height: 100vh;
  padding: 0;
  overflow: hidden;
  background: var(--cm-bg);
}
.zen-mode .map-page { width: 100%; height: 100vh; margin: 0; gap: 0; }
.zen-mode .map-document-bar { min-height: 58px; border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
.zen-mode .new-map-action { display: none; }
.zen-mode .document-title > span,
.zen-mode .document-title > small { display: none; }
.zen-mode .document-title { grid-template-columns: minmax(0, 1fr); }
.zen-mode .atlas-workspace { display: block; height: calc(100vh - 58px); }
.zen-mode .canvas-stage { height: 100%; }
.zen-mode .atlas-workspace :deep(.map-inspector) {
  position: absolute;
  top: 14px;
  right: 14px;
  bottom: 14px;
  z-index: 18;
  width: min(390px, calc(100% - 28px));
  height: auto;
  background: color-mix(in srgb, var(--cm-surface) 96%, transparent);
  box-shadow: 0 24px 70px rgba(18, 31, 52, 0.22);
}

.rail-toggle:focus-visible,
.plain-action:focus-visible,
.more-action:focus-visible,
.shortcut-action:focus-visible,
.node-search > button:focus-visible,
.navigator-filters button:focus-visible,
.outline-tree > button:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--atlas-cobalt) 24%, transparent);
  outline-offset: 2px;
}

@media (max-width: 1380px) {
  .map-document-bar { grid-template-columns: minmax(240px, 1fr) minmax(220px, 360px) auto; }
  .document-actions .plain-action { display: none; }
  .selection-bar { top: 72px; max-width: calc(100% - 32px); }
  .focus-trail { top: 122px; }
}

@media (max-width: 1280px) {
  .atlas-workspace.has-navigator { grid-template-columns: minmax(0, 1fr); }
  .atlas-workspace.has-navigator.has-inspector { grid-template-columns: minmax(0, 1fr) minmax(330px, 360px); }
  .map-navigator {
    position: absolute;
    top: 12px;
    bottom: 12px;
    left: 12px;
    z-index: 14;
    width: 244px;
    height: auto;
    box-shadow: 0 24px 70px rgba(18, 31, 52, 0.2);
  }
  .map-document-bar { grid-template-columns: minmax(240px, 1fr) minmax(230px, 330px); }
  .document-actions {
    grid-column: 1 / -1;
    display: flex;
    justify-content: flex-end;
  }
}

@media (max-width: 980px) {
  .map-page { width: min(100% - 16px, 1600px); }
  .map-document-bar { grid-template-columns: 1fr; }
  .node-search { grid-row: 2; }
  .atlas-workspace.has-inspector,
  .atlas-workspace.has-navigator.has-inspector { grid-template-columns: minmax(0, 1fr); }
  .atlas-workspace :deep(.map-inspector) {
    position: absolute;
    top: 12px;
    right: 12px;
    bottom: 12px;
    z-index: 16;
    width: min(390px, calc(100% - 24px));
    height: auto;
    background: var(--cm-surface);
    box-shadow: 0 24px 70px rgba(18, 31, 52, 0.22);
  }
  .learning-strip { grid-template-columns: 1fr 1.4fr; }
  .learning-strip .continue-learning { grid-column: 1 / -1; }
}

@media (max-width: 720px) {
  .mind-map-view { padding-top: 6px; }
  .mind-map-view.zen-mode { padding-top: 0; }
  .map-page { margin-top: 16px; }
  .control-grid,
  .learning-strip { grid-template-columns: 1fr; }
  .learning-strip dl { margin-block: 4px; }
  .map-document-bar { position: relative; }
  .document-title small { display: none; }
  .selection-bar { top: 62px; right: 10px; left: 10px; max-width: none; overflow-x: auto; }
  .selection-bar > div { display: none; }
  .focus-trail { top: 108px; right: 10px; left: 10px; max-width: none; }
  .map-navigator { top: 8px; bottom: 8px; left: 8px; width: min(260px, calc(100% - 16px)); }
  .construction-copy { width: calc(100% - 24px); padding: 20px 16px; }
  .construction-copy .stage-track { grid-template-columns: repeat(2, 1fr); }
  .generation-ribbon { grid-template-columns: 1fr auto; }
  .ribbon-progress { grid-column: 1 / -1; }
  .generation-ribbon > small { grid-column: 1 / -1; }
  .ribbon-actions { grid-column: 1 / -1; justify-self: start; }
  .zen-mode .map-document-bar { min-height: 106px; }
  .zen-mode .atlas-workspace { height: calc(100vh - 106px); }
}

@media (prefers-reduced-motion: reduce) {
  .ribbon-stage > i,
  .constructing .route,
  .constructing .map-node { animation: none; }
  .construction-progress > i,
  .history-shelf > button,
  .learning-progress i,
  .new-map-action,
  .learning-feedback-enter-active,
  .learning-feedback-leave-active { transition: none; }
  .history-shelf > button:not(:disabled):hover,
  .history-shelf > button:not(:disabled):focus-visible,
  .new-map-action:not(:disabled):hover,
  .new-map-action:not(:disabled):focus-visible { transform: none; }
}
</style>

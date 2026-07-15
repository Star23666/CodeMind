<template>
  <section class="map-shell" :class="{ immersive, revealing: isRevealing, preparing: isPreparingReveal }">
    <div class="canvas-topbar">
      <div class="canvas-title" aria-hidden="true">
        <span>{{ focusRootId ? "聚焦分支" : "知识画布" }}</span>
        <strong>{{ activeRoot.title }}</strong>
        <small>{{ visibleNodeCount }} / {{ nodeCount }} 个节点</small>
      </div>
      <div v-if="isRevealing" class="construction-indicator" aria-live="polite">
        <i></i>
        <span>正在展开第 {{ revealDepth }} 层知识枝架</span>
      </div>
    </div>

    <div
      ref="canvasHost"
      class="canvas-host"
      role="region"
      tabindex="0"
      :aria-label="activeRoot.title + ' 知识地图。可拖动画布、滚轮缩放，单击节点查看完整学习路径，双击节点展开或收起。'"
    ></div>

    <div class="canvas-legend" aria-hidden="true">
      <span><i class="root-dot"></i>主题</span>
      <span><i class="branch-dot"></i>章节</span>
      <span><i class="leaf-dot"></i>知识点</span>
      <span><i class="mastery-dot">✓</i>已掌握</span>
      <span><i class="source-dot">文</i>有原文</span>
    </div>

    <div class="canvas-navigation" aria-label="知识画布工具">
      <div class="tool-group" aria-label="视图定位">
        <el-tooltip content="回到中心主题（Ctrl+0）" placement="top">
          <button type="button" aria-label="回到当前中心主题" @click="centerRoot">
            <el-icon><Aim /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="适应全部节点" placement="top">
          <button type="button" aria-label="让全部节点适应画布" @click="fitView">全图</button>
        </el-tooltip>
        <el-tooltip content="重新自动排列" placement="top">
          <button type="button" aria-label="重新自动排列知识地图" @click="reflow">
            <el-icon><Refresh /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <i class="tool-divider" aria-hidden="true"></i>

      <div class="tool-group" aria-label="编辑视图">
        <el-tooltip :content="layoutLocked ? '解锁节点拖拽' : '锁定节点位置'" placement="top">
          <button
            type="button"
            :aria-label="layoutLocked ? '解锁节点拖拽' : '锁定节点位置'"
            :class="{ active: layoutLocked }"
            @click="layoutLocked = !layoutLocked"
          >
            <el-icon><Lock v-if="layoutLocked" /><Unlock v-else /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="撤销节点移动" placement="top">
          <button type="button" aria-label="撤销节点移动" :disabled="undoStack.length < 2" @click="undo">
            <el-icon><Back /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="重做节点移动" placement="top">
          <button type="button" aria-label="重做节点移动" :disabled="!redoStack.length" @click="redo">
            <el-icon><Right /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <i class="tool-divider" aria-hidden="true"></i>

      <div class="tool-group zoom-tools" aria-label="缩放工具">
        <button type="button" aria-label="缩小知识地图" @click="zoom(0.82)">
          <el-icon><ZoomOut /></el-icon>
        </button>
        <span class="zoom-badge" aria-live="polite">{{ zoomLevel }}%</span>
        <button type="button" aria-label="放大知识地图" @click="zoom(1.2)">
          <el-icon><ZoomIn /></el-icon>
        </button>
      </div>

      <i class="tool-divider" aria-hidden="true"></i>

      <div class="tool-group view-mode-tools" aria-label="呈现方式">
        <button type="button" @click="$emit('density-change', density === 'compact' ? 'comfortable' : 'compact')">
          {{ density === "compact" ? "舒展" : "紧凑" }}
        </button>
        <button type="button" @click="$emit('display-mode-change', displayMode === 'detail' ? 'title' : 'detail')">
          {{ displayMode === "detail" ? "仅标题" : "看摘要" }}
        </button>
        <el-tooltip content="专注模式（Z）" placement="top">
          <button type="button" aria-label="切换专注模式" :class="{ active: immersive }" @click="$emit('toggle-zen')">
            <el-icon><FullScreen /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Graph } from "@antv/g6";
import {
  Aim,
  Back,
  FullScreen,
  Lock,
  Refresh,
  Right,
  Unlock,
  ZoomIn,
  ZoomOut,
} from "@element-plus/icons-vue";
import { useTheme } from "../../composables/useTheme";

const props = defineProps({
  root: {
    type: Object,
    required: true,
  },
  searchTerm: { type: String, default: "" },
  viewState: { type: Object, default: () => ({}) },
  selectedNodeId: { type: String, default: "" },
  focusRootId: { type: String, default: "" },
  masteredNodeIds: { type: Array, default: () => [] },
  density: { type: String, default: "comfortable" },
  displayMode: { type: String, default: "detail" },
  constructionRevision: { type: Number, default: 0 },
  immersive: { type: Boolean, default: false },
});

const emit = defineEmits([
  "select",
  "view-change",
  "search-change",
  "density-change",
  "display-mode-change",
  "toggle-zen",
]);
const { isDark } = useTheme();
const GRAPH_PADDING = 66;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 2.4;
const VIEW_STATE_VERSION = 2;
const canvasHost = ref(null);
const layoutLocked = ref(false);
const selectedNodeId = ref("");
const zoomLevel = ref(100);
const undoStack = ref([]);
const redoStack = ref([]);
const isRevealing = ref(false);
const isPreparingReveal = ref(false);
const revealDepth = ref(1);
const collapsedNodeIds = new Set();
let graph = null;
let resizeObserver = null;
let resizeFrame = 0;
let resizeRevision = 0;
let resizePending = false;
let resizeNeedsFit = false;
let isGraphReady = false;
let nodeLookup = new Map();
let parentLookup = new Map();
let edgeLookup = new Map();
let searchMatchIds = [];
let searchIndex = -1;
let renderVersion = 0;
let isRestoring = false;
let presentedConstructionRevision = 0;
let focusSnapshot = null;

const masteredIdSet = computed(() => new Set(props.masteredNodeIds));
const activeRoot = computed(() => findTreeNode(props.root, props.focusRootId) || props.root);

const selectedHasChildren = computed(() => {
  const node = nodeLookup.get(selectedNodeId.value);
  return Boolean(node?.children?.length);
});
const nodeCount = computed(() => {
  const count = (node) => 1 + (node.children || []).reduce((sum, child) => sum + count(child), 0);
  return props.root ? count(props.root) : 0;
});
const visibleNodeCount = computed(() => {
  const count = (node) => 1 + (node.children || []).reduce((sum, child) => sum + count(child), 0);
  return activeRoot.value ? count(activeRoot.value) : 0;
});

const lightRootPalette = {
  fill: "#2f5ee5",
  deepFill: "#2f5ee5",
  stroke: "#244ac0",
  label: "#ffffff",
  glow: "rgba(47, 94, 229, 0.22)",
};
const darkRootPalette = {
  fill: "#4169d8",
  deepFill: "#4169d8",
  stroke: "#8eabff",
  label: "#ffffff",
  glow: "rgba(78, 118, 229, 0.34)",
};
const lightBranchPalettes = [
  { fill: "#eaf0ff", deepFill: "#ffffff", stroke: "#4c70d8", label: "#172033", glow: "rgba(76, 112, 216, 0.12)" },
  { fill: "#e7f6f5", deepFill: "#ffffff", stroke: "#168c8c", label: "#172033", glow: "rgba(22, 140, 140, 0.12)" },
  { fill: "#fff4e5", deepFill: "#ffffff", stroke: "#c27b24", label: "#172033", glow: "rgba(194, 123, 36, 0.12)" },
  { fill: "#f1edff", deepFill: "#ffffff", stroke: "#7457c6", label: "#172033", glow: "rgba(116, 87, 198, 0.12)" },
  { fill: "#fbeceb", deepFill: "#ffffff", stroke: "#c55757", label: "#172033", glow: "rgba(197, 87, 87, 0.12)" },
];
const darkBranchPalettes = [
  { fill: "#223459", deepFill: "#18243a", stroke: "#7798f2", label: "#edf3ff", glow: "rgba(119, 152, 242, 0.18)" },
  { fill: "#173e43", deepFill: "#172c34", stroke: "#49b8b5", label: "#ecfffe", glow: "rgba(73, 184, 181, 0.18)" },
  { fill: "#49371f", deepFill: "#312a22", stroke: "#d8a04f", label: "#fff8ea", glow: "rgba(216, 160, 79, 0.18)" },
  { fill: "#352b52", deepFill: "#25233a", stroke: "#9b83dd", label: "#f7f3ff", glow: "rgba(155, 131, 221, 0.18)" },
  { fill: "#482a34", deepFill: "#32232c", stroke: "#d27b7b", label: "#fff2f2", glow: "rgba(210, 123, 123, 0.18)" },
];

function findTreeNode(node, nodeId) {
  if (!node || !nodeId) return null;
  if (node.id === nodeId) return node;
  for (const child of node.children || []) {
    const match = findTreeNode(child, nodeId);
    if (match) return match;
  }
  return null;
}

function flattenTree(root) {
  const nodes = [];
  const edges = [];
  nodeLookup = new Map();
  parentLookup = new Map();
  edgeLookup = new Map();

  function visit(node, parentId = null, branchIndex = -1, visualDepth = 0) {
    nodeLookup.set(node.id, node);
    if (parentId) parentLookup.set(node.id, parentId);
    nodes.push({
      id: node.id,
      data: {
        title: node.title,
        summary: node.summary || "",
        depth: visualDepth,
        originalDepth: node.depth,
        sourceCount: node.sources?.length || 0,
        childCount: node.children?.length || 0,
        nodeType: node.node_type || "concept",
        branchIndex,
        mastered: masteredIdSet.value.has(node.id),
      },
    });

    if (parentId) {
      const edgeId = "edge-" + parentId + "-" + node.id;
      const edge = {
        id: edgeId,
        source: parentId,
        target: node.id,
        data: { depth: visualDepth, branchIndex },
      };
      edges.push(edge);
      edgeLookup.set(edgeId, edge);
    }

    node.children?.forEach((child, index) => {
      visit(child, node.id, visualDepth === 0 ? index : branchIndex, visualDepth + 1);
    });
  }

  visit(root);
  return { nodes, edges };
}

function paletteFor(datum) {
  const depth = Number(datum?.data?.depth || 0);
  if (depth === 0) return isDark.value ? darkRootPalette : lightRootPalette;
  const palettes = isDark.value ? darkBranchPalettes : lightBranchPalettes;
  const index = Math.max(0, Number(datum?.data?.branchIndex || 0));
  const palette = palettes[index % palettes.length];
  return {
    ...palette,
    fill: depth === 1 ? palette.fill : palette.deepFill,
  };
}

function truncateLabel(value, length = 20) {
  const text = String(value || "");
  return text.length > length ? text.slice(0, length) + "…" : text;
}

function nodeLabel(datum) {
  const depth = Number(datum.data?.depth || 0);
  const title = truncateLabel(datum.data?.title, depth === 0 ? 22 : 18);
  if (depth === 0) return title + "\n" + (datum.data?.childCount || 0) + " 个学习分支";
  if (props.displayMode === "title") return title;
  const summary = truncateLabel(datum.data?.summary, 20);
  const detail = summary || (datum.data?.sourceCount || 0) + " 条原文依据";
  return title + "\n" + detail;
}

function layoutOptions(nodeFilter) {
  const compact = props.density === "compact";
  return {
    type: "mindmap",
    direction: "H",
    ...(nodeFilter ? { nodeFilter } : {}),
    getWidth: (datum) => nodeSize(datum)[0],
    getHeight: (datum) => nodeSize(datum)[1],
    getHGap: () => compact ? 72 : 104,
    getVGap: () => compact ? 17 : 30,
  };
}

function nodeSize(datum) {
  const depth = Number(datum.data?.depth || 0);
  const compact = props.density === "compact";
  const titleOnly = props.displayMode === "title";
  if (depth === 0) return compact ? [222, titleOnly ? 58 : 72] : [252, titleOnly ? 66 : 88];
  if (depth === 1) return compact ? [196, titleOnly ? 46 : 60] : [230, titleOnly ? 54 : 78];
  return compact ? [180, titleOnly ? 42 : 56] : [212, titleOnly ? 50 : 70];
}

function nodeBadges(datum) {
  if (Number(datum.data?.depth || 0) === 0) return [];
  const badges = [];
  if (datum.data?.mastered) {
    badges.push({
      text: "✓",
      placement: "right-top",
      backgroundFill: isDark.value ? "#2b8f80" : "#168c8c",
      backgroundStroke: isDark.value ? "#7bd8ca" : "#ffffff",
      fill: "#ffffff",
      fontSize: 10,
      fontWeight: 800,
      padding: [2, 5],
    });
  }
  if (Number(datum.data?.sourceCount || 0) > 0) {
    badges.push({
      text: "文",
      placement: "right-bottom",
      backgroundFill: isDark.value ? "#4a3a24" : "#fff2d8",
      backgroundStroke: isDark.value ? "#d8a04f" : "#d9912b",
      fill: isDark.value ? "#ffd99b" : "#9b5d10",
      fontSize: 9,
      fontWeight: 800,
      padding: [2, 5],
    });
  }
  return badges;
}

async function renderGraph() {
  const version = ++renderVersion;
  isGraphReady = false;
  await nextTick();
  if (!canvasHost.value || !props.root) return;

  graph?.destroy();
  const renderRoot = props.root;
  const data = flattenTree(renderRoot);
  const shouldReveal = props.constructionRevision > 0
    && props.constructionRevision !== presentedConstructionRevision
    && data.nodes.length <= 120
    && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  isPreparingReveal.value = shouldReveal;
  const nextGraph = new Graph({
    container: canvasHost.value,
    data,
    padding: GRAPH_PADDING,
    animation: shouldReveal ? { duration: 220, easing: "ease-out" } : false,
    zoomRange: [MIN_ZOOM, MAX_ZOOM],
    layout: layoutOptions(),
    node: {
      type: "rect",
      style: {
        size: nodeSize,
        radius: (datum) => Number(datum.data?.depth || 0) === 0 ? 18 : 12,
        fill: (datum) => paletteFor(datum).fill,
        stroke: (datum) => paletteFor(datum).stroke,
        lineWidth: (datum) => Number(datum.data?.depth || 0) === 0 ? 2.2 : 1.4,
        shadowColor: (datum) => paletteFor(datum).glow,
        shadowBlur: (datum) => Number(datum.data?.depth || 0) === 0 ? 18 : 8,
        cursor: "pointer",
        labelText: nodeLabel,
        labelPlacement: "center",
        labelFill: (datum) => paletteFor(datum).label,
        labelFontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
        labelFontSize: (datum) => Number(datum.data?.depth || 0) === 0 ? 15 : 12,
        labelFontWeight: (datum) => Number(datum.data?.depth || 0) <= 1 ? 700 : 600,
        labelLineHeight: 18,
        labelMaxWidth: 192,
        badges: nodeBadges,
      },
      animation: shouldReveal ? { show: "fade", hide: "fade", enter: "fade" } : false,
      state: {
        selected: {
          stroke: "#d97706",
          lineWidth: 3,
          shadowColor: "rgba(217, 119, 6, 0.28)",
          shadowBlur: 16,
        },
        path: {
          lineWidth: 2.5,
          shadowColor: "rgba(47, 94, 229, 0.2)",
          shadowBlur: 12,
        },
        searchMatch: {
          stroke: "#d9912b",
          lineWidth: 2.5,
          lineDash: [5, 3],
        },
        dimmed: {
          opacity: 0.22,
        },
      },
    },
    edge: {
      type: "cubic-horizontal",
      style: {
        stroke: (datum) => paletteFor(datum).stroke,
        lineWidth: (datum) => Number(datum.data?.depth || 1) === 1 ? 2.3 : 1.5,
        opacity: 0.7,
      },
      animation: shouldReveal ? { show: "path-in", hide: "path-out", enter: "fade" } : false,
      state: {
        path: {
          stroke: "#2f5ee5",
          lineWidth: 3,
          opacity: 1,
          shadowColor: "rgba(47, 94, 229, 0.2)",
          shadowBlur: 8,
        },
        dimmed: {
          opacity: 0.1,
        },
      },
    },
    behaviors: [
      {
        type: "drag-canvas",
        onFinish: notifyViewChange,
      },
      {
        type: "zoom-canvas",
        sensitivity: 1.05,
        onFinish: () => {
          updateZoomLevel();
          notifyViewChange();
        },
      },
      {
        type: "drag-element",
        enable: () => !layoutLocked.value,
        onFinish: () => rememberLayout(true),
      },
      {
        type: "collapse-expand",
        trigger: "dblclick",
        animation: true,
        align: true,
        onCollapse: (id) => {
          collapsedNodeIds.add(id);
          notifyViewChange();
        },
        onExpand: (id) => {
          collapsedNodeIds.delete(id);
          notifyViewChange();
        },
      },
    ],
  });

  graph = nextGraph;
  await graph.render();
  if (version !== renderVersion || graph !== nextGraph) {
    nextGraph.destroy();
    return;
  }

  if (shouldReveal) {
    const initialVisibility = {};
    data.nodes.forEach((node) => {
      initialVisibility[node.id] = Number(node.data?.depth || 0) === 0 ? "visible" : "hidden";
    });
    data.edges.forEach((edge) => { initialVisibility[edge.id] = "hidden"; });
    await graph.setElementVisibility(initialVisibility, false);
  }
  isPreparingReveal.value = false;

  graph.on("node:click", (event) => {
    selectNodeById(event.target.id, false, true);
  });
  if (shouldReveal) {
    presentedConstructionRevision = props.constructionRevision;
    await revealConstruction(data, version);
  }
  const recoveredViewState = await restoreViewState(props.viewState || {});
  rememberLayout(false);
  const preferredNodeId = props.selectedNodeId
    || props.viewState?.selected_node_id
    || activeRoot.value.id;
  await selectNodeById(nodeLookup.has(preferredNodeId) ? preferredNodeId : activeRoot.value.id, false);
  if (props.focusRootId) await applyFocusMode(props.focusRootId, { initial: true });
  if (props.searchTerm) await updateSearch(props.searchTerm);
  isGraphReady = true;
  if (resizePending) scheduleCanvasResize();
  if (recoveredViewState) notifyViewChange();
}

function waitForReveal(delay) {
  return new Promise((resolve) => window.setTimeout(resolve, delay));
}

async function revealConstruction(data, version) {
  if (!graph) return;
  const maxDepth = Math.max(0, ...data.nodes.map((node) => Number(node.data?.depth || 0)));
  if (!maxDepth || data.nodes.length > 120) return;
  isRevealing.value = true;
  try {
    for (let depth = 1; depth <= maxDepth; depth += 1) {
      if (!graph || version !== renderVersion) return;
      revealDepth.value = depth + 1;
      const edgeIds = data.edges
        .filter((edge) => Number(edge.data?.depth || 0) === depth)
        .map((edge) => edge.id);
      const nodeIds = data.nodes
        .filter((node) => Number(node.data?.depth || 0) === depth)
        .map((node) => node.id);
      if (edgeIds.length) await graph.showElement(edgeIds, true);
      if (nodeIds.length) await graph.showElement(nodeIds, true);
      await waitForReveal(95);
    }
  } finally {
    if (version === renderVersion) isRevealing.value = false;
  }
}

function currentLayout() {
  return graph?.getNodeData().map((node) => ({
    id: node.id,
    style: { x: node.style?.x, y: node.style?.y },
  })) || [];
}

function descendantIds(nodeId) {
  const ids = new Set();
  const walk = (node) => {
    if (!node) return;
    ids.add(node.id);
    node.children?.forEach(walk);
  };
  walk(nodeLookup.get(nodeId));
  return ids;
}

function fullVisibility() {
  const visibility = {};
  nodeLookup.forEach((_, id) => { visibility[id] = "visible"; });
  edgeLookup.forEach((_, id) => { visibility[id] = "visible"; });
  return visibility;
}

function currentViewportCenter() {
  if (!graph) return [0, 0];
  const [width, height] = graph.getSize();
  return graph.getCanvasByViewport([width / 2, height / 2]).slice(0, 2);
}

async function centerCanvasPoint(point, animation = false) {
  if (!graph || !Array.isArray(point) || point.length < 2) return;
  const [canvasWidth, canvasHeight] = graph.getSize();
  const viewportPosition = graph.getViewportByCanvas(point);
  const offset = [
    canvasWidth / 2 - viewportPosition[0],
    canvasHeight / 2 - viewportPosition[1],
  ];
  if (offset.every(Number.isFinite)) await graph.translateBy(offset, animation);
}

async function fitNodeIds(nodeIds, animation = false) {
  if (!graph) return;
  const targetGraph = graph;
  const dataById = new Map(targetGraph.getNodeData().map((node) => [node.id, node]));
  const bounds = {
    minX: Number.POSITIVE_INFINITY,
    minY: Number.POSITIVE_INFINITY,
    maxX: Number.NEGATIVE_INFINITY,
    maxY: Number.NEGATIVE_INFINITY,
  };
  const validNodeIds = [];

  nodeIds.forEach((nodeId) => {
    const datum = dataById.get(nodeId);
    const position = targetGraph.getElementPosition(nodeId);
    if (targetGraph.getElementVisibility(nodeId) === "hidden") return;
    if (!datum || !Number.isFinite(position?.[0]) || !Number.isFinite(position?.[1])) return;
    const [width, height] = nodeSize(datum);
    bounds.minX = Math.min(bounds.minX, position[0] - width / 2);
    bounds.minY = Math.min(bounds.minY, position[1] - height / 2);
    bounds.maxX = Math.max(bounds.maxX, position[0] + width / 2);
    bounds.maxY = Math.max(bounds.maxY, position[1] + height / 2);
    validNodeIds.push(nodeId);
  });

  if (!validNodeIds.length) return;
  const [canvasWidth, canvasHeight] = targetGraph.getSize();
  const contentWidth = Math.max(bounds.maxX - bounds.minX, 1);
  const contentHeight = Math.max(bounds.maxY - bounds.minY, 1);
  const availableWidth = Math.max(canvasWidth - GRAPH_PADDING * 2, 1);
  const availableHeight = Math.max(canvasHeight - GRAPH_PADDING * 2, 1);
  const zoom = Math.min(
    MAX_ZOOM,
    Math.max(MIN_ZOOM, Math.min(availableWidth / contentWidth, availableHeight / contentHeight)),
  );
  const contentCenter = [
    (bounds.minX + bounds.maxX) / 2,
    (bounds.minY + bounds.maxY) / 2,
  ];

  await targetGraph.zoomTo(zoom, animation);
  if (graph !== targetGraph) return;
  await centerCanvasPoint(contentCenter, animation);
}

async function fitCurrentView(animation = false) {
  if (!graph) return;
  const nodeIds = props.focusRootId && nodeLookup.has(props.focusRootId)
    ? [...descendantIds(props.focusRootId)]
    : [...nodeLookup.keys()];
  await fitNodeIds(nodeIds, animation);
}

async function applyFocusMode(nodeId, options = {}) {
  if (!graph) return;
  const validNodeId = nodeLookup.has(nodeId) ? nodeId : "";

  if (!validNodeId) {
    graph.setLayout(layoutOptions());
    await graph.setElementVisibility(fullVisibility(), false);
    if (focusSnapshot?.positions?.length) {
      graph.updateNodeData(focusSnapshot.positions);
      await graph.draw();
    }
    if (Number.isFinite(focusSnapshot?.zoom)) await graph.zoomTo(focusSnapshot.zoom, false);
    if (Array.isArray(focusSnapshot?.viewportCenter)) {
      await centerCanvasPoint(focusSnapshot.viewportCenter, false);
    }
    focusSnapshot = null;
    updateZoomLevel();
    await applyVisualStates();
    if (!options.initial) notifyViewChange();
    return;
  }

  if (!focusSnapshot) {
    focusSnapshot = {
      positions: currentLayout(),
      zoom: graph.getZoom() || 1,
      viewportCenter: currentViewportCenter(),
    };
  } else if (focusSnapshot.positions?.length) {
    await graph.setElementVisibility(fullVisibility(), false);
    graph.updateNodeData(focusSnapshot.positions);
    await graph.draw();
  }

  const visibleNodes = descendantIds(validNodeId);
  const visibility = {};
  nodeLookup.forEach((_, id) => { visibility[id] = visibleNodes.has(id) ? "visible" : "hidden"; });
  edgeLookup.forEach((edge, id) => {
    visibility[id] = visibleNodes.has(edge.source) && visibleNodes.has(edge.target) ? "visible" : "hidden";
  });
  await graph.setElementVisibility(visibility, false);
  graph.setLayout(layoutOptions((node) => visibleNodes.has(node.id)));
  await graph.layout();
  await fitNodeIds(
    [...visibleNodes],
    options.initial ? false : { duration: 240, easing: "ease-out" },
  );
  updateZoomLevel();
  await selectNodeById(validNodeId, false);
  if (!options.initial) notifyViewChange();
}

function rememberLayout(shouldNotify = false) {
  const snapshot = currentLayout();
  if (!snapshot.length) return;
  const previous = undoStack.value.at(-1);
  if (previous && JSON.stringify(previous) === JSON.stringify(snapshot)) return;
  undoStack.value = [...undoStack.value.slice(-19), snapshot];
  redoStack.value = [];
  if (shouldNotify) notifyViewChange();
}

async function applyLayout(snapshot, shouldNotify = true) {
  if (!graph) return;
  graph.updateNodeData(snapshot);
  await graph.draw();
  if (shouldNotify) notifyViewChange();
}

async function undo() {
  if (undoStack.value.length < 2) return;
  redoStack.value.push(undoStack.value.pop());
  await applyLayout(undoStack.value.at(-1));
}

async function redo() {
  const snapshot = redoStack.value.pop();
  if (!snapshot) return;
  undoStack.value.push(snapshot);
  await applyLayout(snapshot);
}

function pathTo(nodeId) {
  const ids = [];
  let currentId = nodeId;
  while (currentId) {
    ids.unshift(currentId);
    currentId = parentLookup.get(currentId);
  }
  return ids;
}

async function applyVisualStates() {
  if (!graph) return;
  const selectedPath = new Set(pathTo(selectedNodeId.value));
  const searchMatches = new Set(searchMatchIds);
  const shouldDim = selectedNodeId.value && selectedNodeId.value !== props.root.id;
  const states = {};

  nodeLookup.forEach((node, id) => {
    const nodeStates = [];
    if (id === selectedNodeId.value) nodeStates.push("selected");
    else if (selectedPath.has(id) && shouldDim) nodeStates.push("path");
    if (searchMatches.has(id)) nodeStates.push("searchMatch");
    if (shouldDim && !selectedPath.has(id) && !searchMatches.has(id)) nodeStates.push("dimmed");
    states[id] = nodeStates;
  });

  edgeLookup.forEach((edge, id) => {
    const isPathEdge = selectedPath.has(edge.source) && selectedPath.has(edge.target);
    states[id] = shouldDim ? (isPathEdge ? ["path"] : ["dimmed"]) : [];
  });

  await graph.setElementState(states, false);
}

async function selectNodeById(nodeId, shouldFocus = false, shouldNotify = false) {
  if (!graph || !nodeLookup.has(nodeId)) return;
  selectedNodeId.value = nodeId;
  await applyVisualStates();
  if (shouldFocus) await graph.focusElement(nodeId, { duration: 320 });
  emit("select", nodeLookup.get(nodeId));
  if (shouldNotify) notifyViewChange();
}

async function updateSearch(value) {
  if (!graph) return;
  const term = value?.trim().toLowerCase();
  if (!term) {
    searchMatchIds = [];
    searchIndex = -1;
    emit("search-change", { count: 0, index: -1 });
    await applyVisualStates();
    return;
  }

  const visibleIds = props.focusRootId ? descendantIds(props.focusRootId) : null;
  searchMatchIds = [...nodeLookup.values()]
    .filter((node) => !visibleIds || visibleIds.has(node.id))
    .filter((node) => [node.title, node.summary, ...(node.key_points || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(term))
    .map((node) => node.id);
  searchIndex = searchMatchIds.length ? 0 : -1;
  emit("search-change", { count: searchMatchIds.length, index: searchIndex });
  if (searchIndex >= 0) await selectNodeById(searchMatchIds[searchIndex], true);
  else await applyVisualStates();
}

async function stepSearch(direction = 1) {
  if (!searchMatchIds.length) return;
  searchIndex = (searchIndex + direction + searchMatchIds.length) % searchMatchIds.length;
  emit("search-change", { count: searchMatchIds.length, index: searchIndex });
  await selectNodeById(searchMatchIds[searchIndex], true);
}

async function focusNode(nodeId) {
  await selectNodeById(nodeId, true, true);
}

async function updateLearningSignals() {
  if (!graph) return;
  const updates = graph.getNodeData().map((node) => ({
    id: node.id,
    data: {
      ...node.data,
      mastered: masteredIdSet.value.has(node.id),
    },
  }));
  graph.updateNodeData(updates);
  await graph.draw();
  await applyVisualStates();
}

async function applyPresentationOptions() {
  if (!graph) return;
  if (props.focusRootId) {
    await graph.setElementVisibility(fullVisibility(), false);
    focusSnapshot = null;
  }
  graph.setLayout(layoutOptions());
  await graph.layout();
  await graph.draw();
  undoStack.value = [];
  redoStack.value = [];
  rememberLayout(false);
  if (props.focusRootId) await applyFocusMode(props.focusRootId, { initial: true });
  else await fitCurrentView({ duration: 240, easing: "ease-out" });
  updateZoomLevel();
  notifyViewChange();
}

async function restoreViewState(state) {
  if (!graph) return false;
  isRestoring = true;
  collapsedNodeIds.clear();
  let recovered = false;
  try {
    for (const nodeId of state.collapsed_node_ids || []) {
      if (!nodeLookup.get(nodeId)?.children?.length) continue;
      await graph.collapseElement(nodeId, { animation: false, align: false });
      collapsedNodeIds.add(nodeId);
    }

    const positions = (state.positions || []).filter((item) =>
      nodeLookup.has(item.id)
      && Number.isFinite(item.style?.x)
      && Number.isFinite(item.style?.y),
    );
    if (positions.length) {
      graph.updateNodeData(positions);
      await graph.draw();
    }

    if (Number.isFinite(state.zoom)) {
      await graph.zoomTo(Math.min(2.4, Math.max(0.25, state.zoom)), false);
    }
    if (Array.isArray(state.viewport_position) && state.viewport_position.length >= 2) {
      if (Number(state.view_state_version || 0) >= VIEW_STATE_VERSION) {
        await centerCanvasPoint(state.viewport_position, false);
      } else {
        await graph.translateTo(state.viewport_position, false);
      }
    } else if (!positions.length) {
      await fitCurrentView();
    }

    if (!hasNodeInViewport()) {
      await fitCurrentView();
      recovered = true;
    }
    if (!hasNodeInViewport()) {
      graph.setLayout(layoutOptions());
      await graph.layout();
      await graph.draw();
      await fitCurrentView();
    }
    updateZoomLevel();
  } finally {
    isRestoring = false;
  }
  return recovered;
}

function hasNodeInViewport() {
  if (!graph) return false;
  const [canvasWidth, canvasHeight] = graph.getSize();
  const zoom = graph.getZoom() || 1;
  return graph.getNodeData().some((node) => {
    if (graph.getElementVisibility(node.id) === "hidden") return false;
    const position = graph.getElementPosition(node.id);
    if (!Number.isFinite(position?.[0]) || !Number.isFinite(position?.[1])) return false;
    const viewportPosition = graph.getViewportByCanvas(position);
    if (!Number.isFinite(viewportPosition?.[0]) || !Number.isFinite(viewportPosition?.[1])) return false;
    const [width, height] = nodeSize(node);
    const halfWidth = width * zoom / 2;
    const halfHeight = height * zoom / 2;
    return viewportPosition[0] + halfWidth >= 0
      && viewportPosition[0] - halfWidth <= canvasWidth
      && viewportPosition[1] + halfHeight >= 0
      && viewportPosition[1] - halfHeight <= canvasHeight;
  });
}

function exportPng() {
  return canvasHost.value?.querySelector("canvas")?.toDataURL("image/png") || "";
}

function getViewState() {
  return {
    view_state_version: VIEW_STATE_VERSION,
    positions: focusSnapshot?.positions || currentLayout(),
    collapsed_node_ids: [...collapsedNodeIds],
    zoom: focusSnapshot?.zoom || graph?.getZoom() || 1,
    viewport_position: focusSnapshot?.viewportCenter || currentViewportCenter(),
    selected_node_id: selectedNodeId.value,
    focus_root_id: props.focusRootId || "",
    layout_density: props.density,
    display_mode: props.displayMode,
  };
}

function notifyViewChange() {
  if (!graph || isRestoring) return;
  emit("view-change", getViewState());
}

function updateZoomLevel() {
  zoomLevel.value = Math.round((graph?.getZoom() || 1) * 100);
}

defineExpose({
  centerRoot,
  exportPng,
  fitView,
  focusNode,
  getViewState,
  reflow,
  stepSearch,
  toggleSelectedBranch,
  zoom,
});

async function zoom(ratio) {
  if (!graph) return;
  await graph.zoomBy(ratio);
  updateZoomLevel();
  notifyViewChange();
}

async function fitView() {
  if (!graph) return;
  await fitCurrentView();
  updateZoomLevel();
  notifyViewChange();
}

async function centerRoot() {
  if (!graph || !activeRoot.value?.id) return;
  await graph.focusElement(activeRoot.value.id, { duration: 260, easing: "ease-out" });
  updateZoomLevel();
  notifyViewChange();
}

async function reflow() {
  if (!graph) return;
  collapsedNodeIds.clear();
  const focusedIds = props.focusRootId && nodeLookup.has(props.focusRootId)
    ? descendantIds(props.focusRootId)
    : null;
  graph.setLayout(layoutOptions(focusedIds ? (node) => focusedIds.has(node.id) : undefined));
  await graph.layout();
  await fitCurrentView();
  undoStack.value = [];
  redoStack.value = [];
  rememberLayout(false);
  updateZoomLevel();
  notifyViewChange();
}

async function toggleSelectedBranch() {
  if (!graph || !selectedHasChildren.value) return;
  const nodeId = selectedNodeId.value;
  if (collapsedNodeIds.has(nodeId)) {
    await graph.expandElement(nodeId, { animation: true, align: true });
    collapsedNodeIds.delete(nodeId);
  } else {
    await graph.collapseElement(nodeId, { animation: true, align: true });
    collapsedNodeIds.add(nodeId);
  }
  notifyViewChange();
}

function scheduleCanvasResize(shouldFit = false) {
  resizePending = true;
  resizeNeedsFit = resizeNeedsFit || shouldFit;
  const revision = ++resizeRevision;
  if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = window.requestAnimationFrame(async () => {
      resizeFrame = 0;
      if (revision !== resizeRevision) return;
      if (!isGraphReady || !graph || !canvasHost.value) return;
      const targetGraph = graph;
      const fitAfterResize = resizeNeedsFit;
      resizePending = false;
      resizeNeedsFit = false;
      const { width, height } = canvasHost.value.getBoundingClientRect();
      targetGraph.resize(Math.max(width, 320), Math.max(height, 520));
      if (revision !== resizeRevision || graph !== targetGraph) return;
      if (fitAfterResize) {
        await fitCurrentView();
        if (revision === resizeRevision && graph === targetGraph) updateZoomLevel();
      }
    });
  });
}

onMounted(() => {
  resizeObserver = new ResizeObserver(() => scheduleCanvasResize());
  if (canvasHost.value) resizeObserver.observe(canvasHost.value);
  renderGraph();
});

watch(() => props.root, () => renderGraph());
watch(() => props.searchTerm, updateSearch);
watch(() => props.selectedNodeId, (nodeId) => {
  if (nodeId && nodeId !== selectedNodeId.value) selectNodeById(nodeId);
});
watch(isDark, () => renderGraph());
watch(() => props.immersive, async () => {
  await nextTick();
  scheduleCanvasResize(true);
});
watch(() => props.focusRootId, (nodeId) => applyFocusMode(nodeId));
watch(() => props.masteredNodeIds, updateLearningSignals, { deep: true });
watch([() => props.density, () => props.displayMode], applyPresentationOptions);

onBeforeUnmount(() => {
  renderVersion += 1;
  resizeRevision += 1;
  isGraphReady = false;
  resizePending = false;
  resizeNeedsFit = false;
  if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
  resizeObserver?.disconnect();
  isRevealing.value = false;
  isPreparingReveal.value = false;
  graph?.destroy();
  graph = null;
});
</script>

<style scoped>
.map-shell {
  --canvas-bg: #f7f9fc;
  --canvas-grid: rgba(51, 76, 112, 0.105);
  --canvas-ink: #172033;
  --canvas-muted: #6f7f94;
  --canvas-panel: rgba(255, 255, 255, 0.92);
  position: relative;
  height: clamp(650px, calc(100vh - 214px), 860px);
  min-width: 0;
  min-height: 650px;
  overflow: hidden;
  border: 1px solid #d8e0ea;
  border-radius: 14px;
  background-color: var(--canvas-bg);
  background-image:
    radial-gradient(circle, var(--canvas-grid) 1px, transparent 1.2px),
    linear-gradient(135deg, rgba(47, 94, 229, 0.026), transparent 38%);
  background-size: 24px 24px, auto;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.54),
    0 14px 38px rgba(28, 50, 84, 0.09);
}

.map-shell.immersive {
  height: calc(100vh - 58px);
  min-height: calc(100vh - 58px);
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

:global(:root[data-theme="dark"] .map-shell) {
  --canvas-bg: #101a2a;
  --canvas-grid: rgba(171, 190, 219, 0.105);
  --canvas-ink: #edf3ff;
  --canvas-muted: #9aa9bc;
  --canvas-panel: rgba(18, 30, 48, 0.9);
  border-color: #30415d;
  background-image:
    radial-gradient(circle, var(--canvas-grid) 1px, transparent 1.2px),
    linear-gradient(135deg, rgba(74, 112, 216, 0.08), transparent 40%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.025), 0 18px 50px rgba(0, 0, 0, 0.25);
}

.canvas-host {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  outline: none;
  transition: opacity 0.12s ease;
}

.map-shell.preparing .canvas-host { opacity: 0; }

.canvas-host:focus-visible {
  box-shadow: inset 0 0 0 3px rgba(47, 94, 229, 0.22);
}

.canvas-topbar {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 14px;
  pointer-events: none;
}

.canvas-title,
.construction-indicator,
.canvas-legend,
.canvas-navigation {
  border: 1px solid rgba(121, 139, 165, 0.22);
  background: var(--canvas-panel);
  box-shadow: 0 8px 24px rgba(35, 54, 84, 0.11);
  backdrop-filter: blur(16px);
}

.canvas-title {
  display: grid;
  gap: 2px;
  max-width: 260px;
  padding: 9px 12px;
  border-radius: 10px;
}

.canvas-title span {
  color: #2f5ee5;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.canvas-title strong {
  overflow: hidden;
  color: var(--canvas-ink);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.canvas-title small {
  color: var(--canvas-muted);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 10px;
}

.construction-indicator {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 9px 12px;
  border-radius: 10px;
  color: var(--canvas-ink);
  font-size: 11px;
}

.construction-indicator i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2f5ee5;
  box-shadow: 0 0 0 5px rgba(47, 94, 229, 0.12);
  animation: constructionPulse 1.15s ease-in-out infinite;
}

.canvas-navigation {
  position: absolute;
  right: 16px;
  bottom: 14px;
  z-index: 5;
  display: flex;
  max-width: calc(100% - 32px);
  align-items: center;
  gap: 5px;
  padding: 5px;
  overflow-x: auto;
  border-radius: 11px;
}

.tool-group {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
}

.tool-divider {
  flex: 0 0 auto;
  width: 1px;
  height: 22px;
  margin-inline: 2px;
  background: rgba(121, 139, 165, 0.24);
}

.canvas-navigation button {
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 8px;
  color: var(--canvas-muted);
  background: transparent;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}

.canvas-navigation button:hover,
.canvas-navigation button:focus-visible {
  color: #2f5ee5;
  background: rgba(47, 94, 229, 0.1);
  outline: none;
}

.canvas-navigation button:active { transform: translateY(1px); }
.canvas-navigation button.active {
  color: #b66d10;
  background: rgba(217, 145, 43, 0.13);
}
.canvas-navigation button:disabled { opacity: 0.32; cursor: not-allowed; }

.view-mode-tools button { width: auto; padding-inline: 9px; }
.view-mode-tools button:last-child { width: 34px; padding: 0; }

.zoom-badge {
  min-width: 42px;
  padding-inline: 3px;
  color: var(--canvas-ink);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 10px;
  text-align: center;
}

.canvas-legend {
  position: absolute;
  left: 18px;
  bottom: 16px;
  z-index: 4;
  display: flex;
  gap: 13px;
  padding: 8px 11px;
  border-radius: 10px;
  color: var(--canvas-muted);
  font-size: 11px;
}

.canvas-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.canvas-legend i {
  display: grid;
  width: 8px;
  height: 8px;
  place-items: center;
  border-radius: 3px;
  font-size: 7px;
  font-style: normal;
  font-weight: 900;
}

.root-dot { background: #2f5ee5; }
.branch-dot { background: #168c8c; }
.leaf-dot { border: 1px solid #c27b24; background: transparent; }
.mastery-dot { color: #fff; background: #168c8c; }
.source-dot { color: #8d5610; background: #fff2d8; box-shadow: inset 0 0 0 1px #d9912b; }

@keyframes constructionPulse {
  0%, 100% { opacity: 0.55; transform: scale(0.82); }
  50% { opacity: 1; transform: scale(1); }
}

@media (max-width: 1120px) {
  .canvas-legend span:nth-child(-n + 3) { display: none; }
}

@media (max-width: 760px) {
  .map-shell {
    height: 620px;
    min-height: 620px;
  }

  .canvas-topbar { top: 12px; left: 12px; }
  .canvas-title { display: none; }
  .canvas-legend { display: none; }
  .canvas-navigation { right: 10px; bottom: 10px; max-width: calc(100% - 20px); }
  .view-mode-tools { order: -1; }
  .view-mode-tools button:not(:last-child) { display: none; }
}

@media (max-width: 720px) {
  .map-shell.immersive {
    height: calc(100vh - 106px);
    min-height: calc(100vh - 106px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .canvas-host,
  .canvas-navigation button { transition: none; }
  .construction-indicator i { animation: none; }
}
</style>

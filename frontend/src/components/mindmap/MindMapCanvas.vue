<template>
  <section ref="shell" class="map-shell">
    <div class="canvas-toolbar" aria-label="导图画布工具">
      <el-tooltip content="放大" placement="bottom">
        <button type="button" aria-label="放大导图" @click="zoom(1.2)">
          <el-icon><ZoomIn /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="缩小" placement="bottom">
        <button type="button" aria-label="缩小导图" @click="zoom(0.82)">
          <el-icon><ZoomOut /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="适应画布" placement="bottom">
        <button type="button" aria-label="让导图适应画布" @click="fitView">
          <el-icon><Aim /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="自动整理" placement="bottom">
        <button type="button" aria-label="重新自动排列导图" @click="reflow">
          <el-icon><Refresh /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="撤销移动" placement="bottom">
        <button type="button" :disabled="undoStack.length < 2" @click="undo"><el-icon><Back /></el-icon></button>
      </el-tooltip>
      <el-tooltip content="重做移动" placement="bottom">
        <button type="button" :disabled="!redoStack.length" @click="redo"><el-icon><Right /></el-icon></button>
      </el-tooltip>
      <el-tooltip :content="layoutLocked ? '解锁节点拖拽' : '锁定节点位置'" placement="bottom">
        <button
          type="button"
          :aria-label="layoutLocked ? '解锁节点拖拽' : '锁定节点位置'"
          :class="{ active: layoutLocked }"
          @click="layoutLocked = !layoutLocked"
        >
          <el-icon><Lock v-if="layoutLocked" /><Unlock v-else /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="折叠或展开选中分支" placement="bottom">
        <button
          type="button"
          aria-label="折叠或展开选中分支"
          :disabled="!selectedHasChildren"
          @click="toggleSelectedBranch"
        >
          <el-icon><Fold /></el-icon>
        </button>
      </el-tooltip>
      <el-tooltip content="全屏" placement="bottom">
        <button type="button" aria-label="全屏查看导图" @click="toggleFullscreen">
          <el-icon><FullScreen /></el-icon>
        </button>
      </el-tooltip>
    </div>

    <div class="canvas-legend" aria-hidden="true">
      <span><i class="root-dot"></i>主题</span>
      <span><i class="branch-dot"></i>章节</span>
      <span><i class="leaf-dot"></i>要点</span>
    </div>

    <div
      ref="canvasHost"
      class="canvas-host"
      role="img"
      :aria-label="`${root.title} 思维导图。可拖动画布、滚轮缩放，单击节点查看来源，双击节点展开或收起。`"
    ></div>

    <p class="canvas-hint">拖动画布或节点 · 滚轮缩放 · 单击查看依据 · 双击折叠分支</p>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Graph } from "@antv/g6";
import { Aim, Back, Fold, FullScreen, Lock, Refresh, Right, Unlock, ZoomIn, ZoomOut } from "@element-plus/icons-vue";

const props = defineProps({
  root: {
    type: Object,
    required: true,
  },
  searchTerm: { type: String, default: "" },
});

const emit = defineEmits(["select"]);
const shell = ref(null);
const canvasHost = ref(null);
const layoutLocked = ref(false);
const selectedNodeId = ref("");
const collapsedNodeIds = new Set();
const undoStack = ref([]);
const redoStack = ref([]);
let graph = null;
let resizeObserver = null;
let nodeLookup = new Map();
const selectedHasChildren = computed(() => {
  const node = nodeLookup.get(selectedNodeId.value);
  return Boolean(node?.children?.length);
});

const depthPalette = [
  { fill: "#1d4ed8", stroke: "#93c5fd", label: "#ffffff" },
  { fill: "#12385a", stroke: "#38bdf8", label: "#e8f8ff" },
  { fill: "#172554", stroke: "#818cf8", label: "#eef2ff" },
  { fill: "#22233f", stroke: "#a78bfa", label: "#f5f3ff" },
  { fill: "#2b2035", stroke: "#f0abfc", label: "#fdf4ff" },
];

function flattenTree(root) {
  const nodes = [];
  const edges = [];
  nodeLookup = new Map();

  function visit(node, parentId = null) {
    nodeLookup.set(node.id, node);
    nodes.push({
      id: node.id,
      data: {
        title: node.title,
        depth: node.depth,
        sourceCount: node.sources?.length || 0,
      },
    });

    if (parentId) {
      edges.push({
        id: `edge-${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        data: { depth: node.depth },
      });
    }

    node.children?.forEach((child) => visit(child, node.id));
  }

  visit(root);
  return { nodes, edges };
}

function paletteFor(datum) {
  const depth = Number(datum?.data?.depth || 0);
  return depthPalette[Math.min(depth, depthPalette.length - 1)];
}

function truncateLabel(value) {
  const text = String(value || "");
  return text.length > 20 ? `${text.slice(0, 20)}…` : text;
}

async function renderGraph() {
  await nextTick();
  if (!canvasHost.value || !props.root) return;

  graph?.destroy();
  const data = flattenTree(props.root);

  graph = new Graph({
    container: canvasHost.value,
    data,
    padding: 56,
    animation: false,
    layout: {
      type: "mindmap",
      direction: "H",
      getWidth: () => 184,
      getHeight: () => 52,
      getHGap: () => 86,
      getVGap: () => 22,
    },
    node: {
      type: "rect",
      style: {
        size: (datum) => (Number(datum.data?.depth || 0) === 0 ? [210, 62] : [184, 52]),
        radius: (datum) => (Number(datum.data?.depth || 0) === 0 ? 18 : 11),
        fill: (datum) => paletteFor(datum).fill,
        stroke: (datum) => paletteFor(datum).stroke,
        lineWidth: (datum) => (Number(datum.data?.depth || 0) === 0 ? 2.4 : 1.4),
        shadowColor: "rgba(56, 189, 248, 0.24)",
        shadowBlur: (datum) => (Number(datum.data?.depth || 0) === 0 ? 22 : 8),
        cursor: "pointer",
        labelText: (datum) => truncateLabel(datum.data?.title),
        labelPlacement: "center",
        labelFill: (datum) => paletteFor(datum).label,
        labelFontFamily: 'Inter, "Microsoft YaHei", sans-serif',
        labelFontSize: (datum) => (Number(datum.data?.depth || 0) === 0 ? 16 : 13),
        labelFontWeight: (datum) => (Number(datum.data?.depth || 0) <= 1 ? 700 : 600),
        labelMaxWidth: 156,
      },
      state: {
        selected: {
          stroke: "#facc15",
          lineWidth: 3,
          shadowColor: "rgba(250, 204, 21, 0.55)",
          shadowBlur: 18,
        },
        related: {
          stroke: "#67e8f9",
          lineWidth: 2,
        },
        dimmed: {
          opacity: 0.26,
        },
      },
    },
    edge: {
      type: "cubic-horizontal",
      style: {
        stroke: (datum) => depthPalette[Math.min(Number(datum.data?.depth || 1), 4)].stroke,
        lineWidth: 1.5,
        opacity: 0.66,
      },
      state: {
        related: {
          stroke: "#67e8f9",
          lineWidth: 2.6,
          opacity: 1,
        },
        dimmed: {
          opacity: 0.12,
        },
      },
    },
    behaviors: [
      "drag-canvas",
      { type: "zoom-canvas", sensitivity: 1.1 },
      {
        type: "click-select",
        state: "selected",
        neighborState: "related",
        unselectedState: "dimmed",
        degree: 1,
        animation: false,
        onClick: (event) => {
          if (event.targetType === "node") {
            selectedNodeId.value = event.target.id;
            const node = nodeLookup.get(event.target.id);
            if (node) emit("select", node);
          }
        },
      },
      {
        type: "drag-element",
        enable: () => !layoutLocked.value,
      },
      {
        type: "collapse-expand",
        trigger: "dblclick",
        animation: true,
        align: true,
      },
    ],
  });

  await graph.render();
  await graph.fitView();
  graph.on("node:dragend", rememberLayout);
  rememberLayout();
  selectedNodeId.value = props.root.id;
  emit("select", props.root);
}

function currentLayout() {
  return graph?.getNodeData().map((node) => ({ id: node.id, style: { x: node.style?.x, y: node.style?.y } })) || [];
}

function rememberLayout() {
  const snapshot = currentLayout();
  if (!snapshot.length) return;
  undoStack.value = [...undoStack.value.slice(-19), snapshot];
  redoStack.value = [];
}

async function applyLayout(snapshot) {
  graph.updateNodeData(snapshot);
  await graph.draw();
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

async function focusSearch(value) {
  if (!graph || !value?.trim()) return;
  const term = value.trim().toLowerCase();
  const match = [...nodeLookup.values()].find((node) => node.title.toLowerCase().includes(term));
  if (!match) return;
  selectedNodeId.value = match.id;
  await graph.setElementState(match.id, ["selected"]);
  await graph.focusElement(match.id, { duration: 350 });
  emit("select", match);
}

function exportPng() {
  return canvasHost.value?.querySelector("canvas")?.toDataURL("image/png") || "";
}

function getViewState() {
  return { positions: currentLayout(), collapsed_node_ids: [...collapsedNodeIds] };
}

defineExpose({ exportPng, getViewState, focusSearch });

async function zoom(ratio) {
  if (graph) await graph.zoomBy(ratio);
}

async function fitView() {
  if (graph) await graph.fitView();
}

async function reflow() {
  if (!graph) return;
  collapsedNodeIds.clear();
  await graph.layout();
  await graph.fitView();
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
}

async function toggleFullscreen() {
  if (!shell.value) return;
  if (document.fullscreenElement) {
    await document.exitFullscreen();
  } else {
    await shell.value.requestFullscreen();
  }
}

onMounted(() => {
  resizeObserver = new ResizeObserver((entries) => {
    const entry = entries[0];
    if (!graph || !entry) return;
    const { width, height } = entry.contentRect;
    graph.resize(Math.max(width, 320), Math.max(height, 420));
  });
  if (canvasHost.value) resizeObserver.observe(canvasHost.value);
  renderGraph();
});

watch(() => props.root, renderGraph, { deep: true });
watch(() => props.searchTerm, focusSearch);

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  graph?.destroy();
});
</script>

<style scoped>
.map-shell {
  position: relative;
  min-width: 0;
  min-height: 650px;
  overflow: hidden;
  border: 1px solid rgba(125, 211, 252, 0.2);
  border-radius: 14px;
  background:
    linear-gradient(rgba(56, 189, 248, 0.055) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.055) 1px, transparent 1px),
    radial-gradient(circle at 50% 45%, rgba(29, 78, 216, 0.22), transparent 46%),
    #07111f;
  background-size: 32px 32px, 32px 32px, auto, auto;
  box-shadow: inset 0 0 90px rgba(3, 7, 18, 0.72);
}

.map-shell:fullscreen {
  width: 100vw;
  height: 100vh;
  min-height: 100vh;
  border: 0;
  border-radius: 0;
}

.canvas-host {
  width: 100%;
  height: 650px;
  outline: none;
}

.map-shell:fullscreen .canvas-host {
  height: 100vh;
}

.canvas-toolbar,
.canvas-legend {
  position: absolute;
  z-index: 4;
  display: flex;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(7, 17, 31, 0.82);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(14px);
}

.canvas-toolbar {
  top: 16px;
  left: 16px;
  gap: 4px;
  padding: 5px;
  border-radius: 11px;
}

.canvas-toolbar button {
  display: grid;
  width: 34px;
  height: 34px;
  padding: 0;
  place-items: center;
  border: 0;
  border-radius: 8px;
  color: #bfdbfe;
  background: transparent;
  cursor: pointer;
  transition: color 0.18s ease, background 0.18s ease;
}

.canvas-toolbar button:hover,
.canvas-toolbar button:focus-visible {
  color: #ffffff;
  background: rgba(59, 130, 246, 0.28);
  outline: none;
}

.canvas-toolbar button.active {
  color: #facc15;
  background: rgba(250, 204, 21, 0.12);
}

.canvas-toolbar button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.canvas-legend {
  top: 18px;
  right: 18px;
  gap: 14px;
  padding: 9px 12px;
  border-radius: 999px;
  color: #b7c7db;
  font-size: 12px;
}

.canvas-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.canvas-legend i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.root-dot { background: #60a5fa; }
.branch-dot { background: #38bdf8; }
.leaf-dot { background: #a78bfa; }

.canvas-hint {
  position: absolute;
  right: 18px;
  bottom: 14px;
  z-index: 4;
  margin: 0;
  color: #7f94ad;
  font-family: Consolas, "Microsoft YaHei", monospace;
  font-size: 11px;
  letter-spacing: 0.04em;
}

@media (max-width: 720px) {
  .map-shell,
  .canvas-host {
    min-height: 540px;
    height: 540px;
  }

  .canvas-legend {
    display: none;
  }

  .canvas-hint {
    left: 16px;
    right: auto;
    max-width: calc(100% - 32px);
  }
}
</style>

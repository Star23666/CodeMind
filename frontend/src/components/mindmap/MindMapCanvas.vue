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
      <span><i class="branch-dot"></i>学习分支</span>
      <span><i class="leaf-dot"></i>知识细节</span>
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

const rootPalette = {
  fill: "#123f88",
  deepFill: "#123f88",
  stroke: "#93c5fd",
  label: "#ffffff",
  glow: "rgba(37, 99, 235, 0.48)",
};
const branchPalettes = [
  { fill: "#0d4a61", deepFill: "#102f43", stroke: "#22d3ee", label: "#ecfeff", glow: "rgba(34, 211, 238, 0.32)" },
  { fill: "#3c3270", deepFill: "#26284f", stroke: "#a78bfa", label: "#f5f3ff", glow: "rgba(167, 139, 250, 0.32)" },
  { fill: "#66451d", deepFill: "#3e321f", stroke: "#f4c95d", label: "#fffbea", glow: "rgba(244, 201, 93, 0.3)" },
  { fill: "#174f46", deepFill: "#173932", stroke: "#5eead4", label: "#ecfdf5", glow: "rgba(94, 234, 212, 0.28)" },
  { fill: "#633046", deepFill: "#412638", stroke: "#f9a8d4", label: "#fff1f7", glow: "rgba(249, 168, 212, 0.28)" },
];

function flattenTree(root) {
  const nodes = [];
  const edges = [];
  nodeLookup = new Map();

  function visit(node, parentId = null, branchIndex = -1) {
    nodeLookup.set(node.id, node);
    nodes.push({
      id: node.id,
      data: {
        title: node.title,
        summary: node.summary || "",
        depth: node.depth,
        sourceCount: node.sources?.length || 0,
        childCount: node.children?.length || 0,
        nodeType: node.node_type || "concept",
        branchIndex,
      },
    });

    if (parentId) {
      edges.push({
        id: `edge-${parentId}-${node.id}`,
        source: parentId,
        target: node.id,
        data: { depth: node.depth, branchIndex },
      });
    }

    node.children?.forEach((child, index) => {
      visit(child, node.id, Number(node.depth || 0) === 0 ? index : branchIndex);
    });
  }

  visit(root);
  return { nodes, edges };
}

function paletteFor(datum) {
  const depth = Number(datum?.data?.depth || 0);
  if (depth === 0) return rootPalette;
  const index = Math.max(0, Number(datum?.data?.branchIndex || 0));
  const palette = branchPalettes[index % branchPalettes.length];
  return {
    ...palette,
    fill: depth === 1 ? palette.fill : palette.deepFill,
  };
}

function truncateLabel(value, length = 20) {
  const text = String(value || "");
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function nodeLabel(datum) {
  const depth = Number(datum.data?.depth || 0);
  const title = truncateLabel(datum.data?.title, depth === 0 ? 22 : 18);
  if (depth === 0) return `${title}\n${datum.data?.childCount || 0} 个学习分支`;
  const summary = truncateLabel(datum.data?.summary, 20);
  const detail = summary || `${datum.data?.sourceCount || 0} 条原文依据`;
  return `${title}\n${detail}`;
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
      getWidth: () => 228,
      getHeight: () => 76,
      getHGap: () => 108,
      getVGap: () => 28,
    },
    node: {
      type: "rect",
      style: {
        size: (datum) => {
          const depth = Number(datum.data?.depth || 0);
          if (depth === 0) return [252, 88];
          if (depth === 1) return [232, 78];
          return [214, 70];
        },
        radius: (datum) => (Number(datum.data?.depth || 0) === 0 ? 24 : Number(datum.data?.depth || 0) === 1 ? 16 : 11),
        fill: (datum) => paletteFor(datum).fill,
        stroke: (datum) => paletteFor(datum).stroke,
        lineWidth: (datum) => (Number(datum.data?.depth || 0) === 0 ? 2.4 : 1.4),
        shadowColor: (datum) => paletteFor(datum).glow,
        shadowBlur: (datum) => (Number(datum.data?.depth || 0) === 0 ? 28 : 12),
        cursor: "pointer",
        labelText: nodeLabel,
        labelPlacement: "center",
        labelFill: (datum) => paletteFor(datum).label,
        labelFontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
        labelFontSize: (datum) => (Number(datum.data?.depth || 0) === 0 ? 15 : 12),
        labelFontWeight: (datum) => (Number(datum.data?.depth || 0) <= 1 ? 700 : 600),
        labelLineHeight: 18,
        labelMaxWidth: 194,
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
        stroke: (datum) => paletteFor(datum).stroke,
        lineWidth: (datum) => (Number(datum.data?.depth || 1) === 1 ? 2.4 : 1.5),
        opacity: 0.72,
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
  const match = [...nodeLookup.values()].find((node) =>
    [node.title, node.summary, ...(node.key_points || [])]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(term),
  );
  if (!match) return;
  await focusNode(match.id);
}

async function focusNode(nodeId) {
  if (!graph) return;
  const node = nodeLookup.get(nodeId);
  if (!node) return;
  selectedNodeId.value = nodeId;
  await graph.setElementState(nodeId, ["selected"]);
  await graph.focusElement(nodeId, { duration: 350 });
  emit("select", node);
}

function exportPng() {
  return canvasHost.value?.querySelector("canvas")?.toDataURL("image/png") || "";
}

function getViewState() {
  return { positions: currentLayout(), collapsed_node_ids: [...collapsedNodeIds] };
}

defineExpose({ exportPng, getViewState, focusSearch, focusNode });

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
  border-radius: 18px;
  background:
    linear-gradient(rgba(125, 211, 252, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(125, 211, 252, 0.04) 1px, transparent 1px),
    radial-gradient(circle at 44% 42%, rgba(37, 99, 235, 0.2), transparent 38%),
    linear-gradient(145deg, #0a1a31, #07111f 58%, #09172a);
  background-size: 36px 36px, 36px 36px, auto, auto;
  box-shadow:
    inset 0 0 110px rgba(3, 7, 18, 0.74),
    0 22px 50px rgba(8, 20, 38, 0.2);
}

.map-shell::before,
.map-shell::after {
  position: absolute;
  z-index: 0;
  pointer-events: none;
  content: "";
}

.map-shell::before {
  inset: 0;
  opacity: 0.62;
  background-image:
    radial-gradient(circle, rgba(226, 245, 255, 0.7) 0 1px, transparent 1.4px),
    radial-gradient(circle, rgba(125, 211, 252, 0.45) 0 1px, transparent 1.5px);
  background-position: 12px 18px, 74px 92px;
  background-size: 118px 118px, 164px 164px;
}

.map-shell::after {
  width: 520px;
  height: 520px;
  top: 50%;
  left: 43%;
  border: 1px solid rgba(147, 197, 253, 0.08);
  border-radius: 50%;
  box-shadow:
    0 0 0 86px rgba(147, 197, 253, 0.035),
    0 0 0 172px rgba(147, 197, 253, 0.022);
  transform: translate(-50%, -50%);
}

.map-shell:fullscreen {
  width: 100vw;
  height: 100vh;
  min-height: 100vh;
  border: 0;
  border-radius: 0;
}

.canvas-host {
  position: relative;
  z-index: 1;
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
  color: #c4d5e9;
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

.root-dot { background: #93c5fd; }
.branch-dot { background: linear-gradient(90deg, #22d3ee, #a78bfa); }
.leaf-dot { background: #f4c95d; }

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

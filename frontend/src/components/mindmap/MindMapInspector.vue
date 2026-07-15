<template>
  <aside ref="panel" class="map-inspector" aria-label="当前知识节点详情">
    <template v-if="selectedNode">
      <header class="inspector-header">
        <div class="inspector-identity">
          <span class="node-kind">{{ selectedNodeTypeLabel }}</span>
          <p>第 {{ selectedNode.depth + 1 }} 层</p>
        </div>
        <div class="inspector-actions">
          <button
            v-if="selectedNode.depth > 0"
            type="button"
            class="mastery-toggle"
            :class="{ mastered: isSelectedMastered }"
            :aria-pressed="isSelectedMastered"
            @click="$emit('toggle-mastery')"
          >
            {{ isSelectedMastered ? "已掌握 ✓" : "标记已掌握" }}
          </button>
          <button
            v-if="closable"
            type="button"
            class="inspector-close"
            aria-label="关闭节点详情"
            title="关闭节点详情"
            @click="$emit('close')"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5.5 5.5 14.5 14.5M14.5 5.5 5.5 14.5" />
            </svg>
          </button>
        </div>
      </header>

      <nav class="node-breadcrumb" aria-label="当前知识路径">
        <button
          v-for="node in selectedPath"
          :key="node.id"
          type="button"
          @click="$emit('focus', node)"
        >{{ node.title }}</button>
      </nav>

      <h2>{{ selectedNode.title }}</h2>

      <div class="inspector-tabs" role="tablist" aria-label="节点详情分类">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          role="tab"
          :aria-selected="activeTab === tab.key"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.key === 'sources'">{{ sourceCount }}</span>
        </button>
      </div>

      <div v-if="activeTab === 'understand'" class="tab-panel understand-panel" role="tabpanel">
        <section>
          <span class="section-caption">核心理解</span>
          <p class="node-summary">
            {{ selectedNode.summary || "该节点用于组织下级知识点，可继续展开查看。" }}
          </p>
        </section>

        <section v-if="selectedNode.key_points?.length" class="key-points">
          <span class="section-caption">关键记忆点</span>
          <ul>
            <li v-for="point in selectedNode.key_points" :key="point">{{ point }}</li>
          </ul>
        </section>

        <section class="learning-tip">
          <span>下一步</span>
          <p>{{ selectedLearningTip }}</p>
        </section>

        <section v-if="selectedNode.children?.length" class="child-navigation">
          <span class="section-caption">继续深入</span>
          <div>
            <button
              v-for="child in selectedNode.children"
              :key="child.id"
              type="button"
              @click="$emit('focus', child)"
            >{{ child.title }} <i>→</i></button>
          </div>
        </section>

        <el-button
          class="expand-button"
          plain
          :loading="expandingNode"
          :disabled="!selectedNode.sources?.length"
          @click="$emit('expand')"
        >
          AI 展开这个分支
        </el-button>
        <p v-if="!selectedNode.sources?.length" class="action-note">该节点没有直接原文，暂时不能继续扩展。</p>
      </div>

      <div v-else-if="activeTab === 'sources'" class="tab-panel" role="tabpanel">
        <section class="source-section">
          <div class="source-heading">
            <div>
              <strong>节点原文</strong>
              <span>生成地图时绑定的直接依据</span>
            </div>
            <b>{{ selectedNode.sources?.length || 0 }}</b>
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
          <p v-else class="empty-copy">该节点没有直接绑定原文，可查看下方知识库补充资料。</p>
        </section>

        <section class="source-section related-section">
          <div class="source-heading">
            <div>
              <strong>知识库补充</strong>
              <span>根据当前节点实时检索</span>
            </div>
            <b v-if="relatedLoading" class="loading-count">…</b>
            <b v-else>{{ relatedSources.length }}</b>
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
          <p v-else-if="relatedLoading" class="empty-copy">正在检索与该节点相关的资料…</p>
          <p v-else class="empty-copy">{{ relatedError || "暂无检索到的相关资料。" }}</p>
        </section>
      </div>

      <div v-else class="tab-panel question-panel" role="tabpanel">
        <div class="question-intro">
          <span class="section-caption">针对当前节点</span>
          <p>{{ hasOwnSources ? "回答只使用该节点绑定的原文。" : "回答使用检索到的知识库相关资料。" }}</p>
        </div>
        <el-input
          :model-value="nodeQuestion"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          maxlength="500"
          show-word-limit
          :placeholder="`例如：${selectedNode.title} 最容易混淆的地方是什么？`"
          :disabled="!questionChunkCount"
          @update:model-value="$emit('update:nodeQuestion', $event)"
          @keydown.ctrl.enter="$emit('ask')"
        />
        <el-button
          type="primary"
          :loading="askingNode"
          :disabled="!questionChunkCount || !nodeQuestion.trim()"
          @click="$emit('ask')"
        >针对性提问</el-button>
        <p v-if="!questionChunkCount" class="action-note">正在准备可引用的资料，稍候即可提问。</p>

        <section v-if="nodeAnswer" class="node-answer">
          <span>基于原文的回答</span>
          <p>{{ nodeAnswer.answer }}</p>
          <div>
            <RouterLink
              v-for="source in nodeAnswer.sources"
              :key="source.chunk_id"
              :to="source.jump_url"
            >来源：{{ source.file_name }} · 片段 {{ source.chunk_index + 1 }}</RouterLink>
          </div>
        </section>
      </div>
    </template>
  </aside>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  selectedNode: { type: Object, default: null },
  closable: { type: Boolean, default: false },
  selectedPath: { type: Array, default: () => [] },
  selectedNodeTypeLabel: { type: String, default: "知识节点" },
  selectedLearningTip: { type: String, default: "" },
  isSelectedMastered: { type: Boolean, default: false },
  hasOwnSources: { type: Boolean, default: false },
  questionChunkCount: { type: Number, default: 0 },
  nodeQuestion: { type: String, default: "" },
  nodeAnswer: { type: Object, default: null },
  askingNode: { type: Boolean, default: false },
  expandingNode: { type: Boolean, default: false },
  relatedLoading: { type: Boolean, default: false },
  relatedSources: { type: Array, default: () => [] },
  relatedError: { type: String, default: "" },
});

defineEmits(["focus", "toggle-mastery", "expand", "ask", "update:nodeQuestion", "close"]);

const panel = ref(null);
const activeTab = ref("understand");
const tabs = [
  { key: "understand", label: "理解" },
  { key: "sources", label: "原文" },
  { key: "question", label: "提问" },
];
const sourceCount = computed(() =>
  (props.selectedNode?.sources?.length || 0) + props.relatedSources.length,
);

function scrollIntoView() {
  panel.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

defineExpose({ scrollIntoView });
</script>

<style scoped>
.map-inspector {
  --inspector-accent: #2f5ee5;
  position: relative;
  min-width: 0;
  height: 100%;
  max-height: 720px;
  overflow: auto;
  border: 1px solid var(--cm-border);
  border-radius: 18px;
  background: var(--cm-surface);
  box-shadow: 0 18px 48px rgba(28, 50, 84, 0.1);
  scrollbar-color: color-mix(in srgb, var(--cm-muted) 42%, transparent) transparent;
}

.map-inspector::before {
  position: sticky;
  top: 0;
  z-index: 4;
  display: block;
  width: 100%;
  height: 3px;
  background: linear-gradient(90deg, #2f5ee5, #168c8c 56%, #d9912b);
  content: "";
}

.inspector-header,
.node-breadcrumb,
.map-inspector h2,
.inspector-tabs,
.tab-panel {
  margin-inline: 22px;
}

.inspector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding-top: 20px;
}

.inspector-identity {
  display: flex;
  align-items: center;
  gap: 8px;
}

.inspector-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.node-kind {
  color: var(--inspector-accent);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.inspector-header p {
  margin: 0;
  color: var(--cm-muted);
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 11px;
}

.mastery-toggle {
  padding: 6px 10px;
  border: 1px solid var(--cm-border);
  border-radius: 999px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
}

.mastery-toggle.mastered {
  border-color: color-mix(in srgb, var(--cm-success) 46%, var(--cm-border));
  color: var(--cm-success);
  background: color-mix(in srgb, var(--cm-success) 9%, var(--cm-surface));
}

.inspector-close {
  display: grid;
  width: 32px;
  height: 32px;
  padding: 0;
  place-items: center;
  border: 1px solid var(--cm-border);
  border-radius: 9px;
  color: var(--cm-muted);
  background: var(--cm-surface-soft);
  cursor: pointer;
  transition:
    border-color 150ms ease,
    color 150ms ease,
    background-color 150ms ease;
}

.inspector-close svg {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-width: 1.7;
}

.inspector-close:hover {
  border-color: color-mix(in srgb, var(--inspector-accent) 40%, var(--cm-border));
  color: var(--cm-heading);
  background: color-mix(in srgb, var(--inspector-accent) 7%, var(--cm-surface));
}

.node-breadcrumb {
  display: flex;
  gap: 6px;
  margin-top: 18px;
  margin-bottom: 10px;
  overflow-x: auto;
}

.node-breadcrumb button {
  position: relative;
  flex: 0 0 auto;
  padding: 0 14px 0 0;
  border: 0;
  color: var(--cm-muted);
  background: transparent;
  font-size: 11px;
  cursor: pointer;
}

.node-breadcrumb button::after {
  position: absolute;
  right: 4px;
  color: var(--cm-border);
  content: "/";
}

.node-breadcrumb button:last-child {
  color: var(--inspector-accent);
  font-weight: 800;
}

.node-breadcrumb button:last-child::after { display: none; }

.map-inspector h2 {
  margin-top: 0;
  margin-bottom: 18px;
  color: var(--cm-heading);
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: 27px;
  line-height: 1.28;
}

.inspector-tabs {
  position: sticky;
  top: 3px;
  z-index: 3;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  padding: 4px;
  border: 1px solid var(--cm-border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--cm-surface) 92%, transparent);
  backdrop-filter: blur(12px);
}

.inspector-tabs button {
  display: flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 0;
  border-radius: 8px;
  color: var(--cm-muted);
  background: transparent;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.inspector-tabs button.active {
  color: var(--cm-heading);
  background: var(--cm-surface-soft);
  box-shadow: 0 4px 14px rgba(30, 50, 80, 0.09);
}

.inspector-tabs span {
  display: grid;
  min-width: 18px;
  height: 18px;
  padding-inline: 4px;
  place-items: center;
  border-radius: 999px;
  color: var(--inspector-accent);
  background: var(--cm-primary-soft);
  font-size: 10px;
}

.tab-panel {
  padding: 22px 0 28px;
}

.section-caption {
  display: block;
  color: var(--inspector-accent);
  font-family: "DIN Alternate", Consolas, "Microsoft YaHei", monospace;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
}

.node-summary {
  margin: 8px 0 22px;
  color: var(--cm-text);
  line-height: 1.78;
}

.key-points { margin-bottom: 20px; }
.key-points ul {
  display: grid;
  gap: 10px;
  margin: 11px 0 0;
  padding: 0;
  list-style: none;
}

.key-points li {
  position: relative;
  padding-left: 19px;
  color: var(--cm-text);
  font-size: 13px;
  line-height: 1.65;
}

.key-points li::before {
  position: absolute;
  top: 0.7em;
  left: 2px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--inspector-accent);
  box-shadow: 0 0 0 4px var(--cm-primary-soft);
  content: "";
}

.learning-tip {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  margin-bottom: 22px;
  padding: 13px 14px;
  border: 1px solid color-mix(in srgb, #d9912b 34%, var(--cm-border));
  border-radius: 11px;
  background: color-mix(in srgb, #d9912b 8%, var(--cm-surface));
}

.learning-tip span {
  color: #a26316;
  font-size: 11px;
  font-weight: 800;
  white-space: nowrap;
}

.learning-tip p {
  margin: 0;
  color: var(--cm-text);
  font-size: 12px;
  line-height: 1.6;
}

.child-navigation { margin-bottom: 20px; }
.child-navigation > div {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 10px;
}

.child-navigation button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 9px;
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  color: var(--cm-text);
  background: var(--cm-surface-soft);
  font-size: 11px;
  cursor: pointer;
}

.child-navigation button:hover,
.child-navigation button:focus-visible {
  border-color: var(--inspector-accent);
  color: var(--inspector-accent);
  outline: none;
}

.child-navigation i { color: var(--inspector-accent); font-style: normal; }
.expand-button { width: 100%; }
.action-note,
.empty-copy {
  margin: 10px 0 0;
  color: var(--cm-muted);
  font-size: 12px;
  line-height: 1.6;
}

.source-section + .source-section {
  margin-top: 28px;
  padding-top: 24px;
  border-top: 1px solid var(--cm-border);
}

.source-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.source-heading > div { display: grid; gap: 3px; }
.source-heading strong { color: var(--cm-heading); }
.source-heading span { color: var(--cm-muted); font-size: 11px; }
.source-heading b {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 50%;
  color: var(--inspector-accent);
  background: var(--cm-primary-soft);
  font-size: 12px;
}

.source-cards {
  display: grid;
  gap: 11px;
  margin-top: 14px;
}

.source-cards article {
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: 11px;
  background: var(--cm-surface-soft);
}

.source-cards.related article {
  border-color: color-mix(in srgb, var(--inspector-accent) 23%, var(--cm-border));
}

.source-cards article > div { display: grid; gap: 4px; }
.source-cards strong {
  overflow: hidden;
  color: var(--cm-heading);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-cards span { color: var(--cm-muted); font-size: 11px; }
.source-cards p {
  display: -webkit-box;
  margin: 11px 0;
  overflow: hidden;
  color: var(--cm-text);
  font-size: 13px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
}

.source-cards a,
.node-answer a {
  color: var(--inspector-accent);
  font-size: 12px;
  font-weight: 800;
}

.question-panel { display: grid; gap: 14px; }
.question-intro p { margin: 6px 0 0; color: var(--cm-muted); font-size: 12px; }
.node-answer {
  display: grid;
  gap: 10px;
  margin-top: 4px;
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--inspector-accent) 24%, var(--cm-border));
  border-radius: 12px;
  background: var(--cm-primary-soft);
}

.node-answer > span {
  color: var(--inspector-accent);
  font-size: 11px;
  font-weight: 800;
}

.node-answer p {
  margin: 0;
  color: var(--cm-text);
  line-height: 1.75;
  white-space: pre-wrap;
}

.node-answer > div { display: grid; gap: 6px; }

button:focus-visible {
  outline: 3px solid color-mix(in srgb, var(--inspector-accent) 26%, transparent);
  outline-offset: 2px;
}

@media (max-width: 1080px) {
  .map-inspector { max-height: none; }
}

@media (max-width: 560px) {
  .inspector-header,
  .node-breadcrumb,
  .map-inspector h2,
  .inspector-tabs,
  .tab-panel {
    margin-inline: 16px;
  }

  .inspector-header {
    align-items: flex-start;
    gap: 10px;
  }

  .inspector-actions { gap: 6px; }

  .mastery-toggle {
    max-width: 116px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

@media (prefers-reduced-motion: reduce) {
  .inspector-close { transition: none; }
}
</style>

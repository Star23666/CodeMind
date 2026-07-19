<template>
  <section class="source-list" id="sources">
    <div class="section-head">
      <h3>来源片段</h3>
      <span>{{ sources.length }} 条</span>
    </div>

    <el-empty v-if="!sources.length" description="暂无来源，提问后会显示检索片段。" />

    <article v-for="(source, index) in sources" v-else :key="sourceKey(source, index)" class="source-item">
      <div class="rank">来源 {{ index + 1 }}</div>
      <div class="content">
        <div class="meta">
          <strong>{{ source.file_name || "未命名文档" }}</strong>
          <el-tag size="small" effect="plain">
            {{ formatScore(source.score) }}
          </el-tag>
        </div>
        <MarkdownContent
          v-if="isMarkdownSource(source)"
          class="source-text markdown-source"
          :class="{ collapsed: !isExpanded(source, index) }"
          :content="source.source_text"
          @click="toggleExpanded(source, index)"
        />
        <p
          v-else
          class="source-text"
          :class="{ collapsed: !isExpanded(source, index) }"
          @click="toggleExpanded(source, index)"
        >
          {{ source.source_text }}
        </p>
        <div class="footer">
          <span>chunk {{ source.chunk_index ?? "-" }}</span>
          <span v-if="source.page_no">第 {{ source.page_no }} 页</span>
          <el-button link type="primary" @click="toggleExpanded(source, index)">
            {{ isExpanded(source, index) ? "收起" : "展开全文" }}
          </el-button>
          <RouterLink v-if="hasSourceTarget(source)" :to="sourceTo(source)">查看片段</RouterLink>
          <span v-else class="source-unavailable">原文已删除</span>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { ref } from "vue";
import MarkdownContent from "../common/MarkdownContent.vue";

defineProps({
  sources: {
    type: Array,
    default: () => [],
  },
});

const expandedSources = ref(new Set());

function sourceKey(source, index) {
  return source.chunk_id ?? `${source.document_id ?? "snapshot"}-${source.chunk_index ?? index}-${index}`;
}

function isExpanded(source, index) {
  return expandedSources.value.has(sourceKey(source, index));
}

function toggleExpanded(source, index) {
  const key = sourceKey(source, index);
  const next = new Set(expandedSources.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  expandedSources.value = next;
}

function sourceTo(source) {
  if (source.jump_url) {
    return source.jump_url;
  }

  if (source.document_id && source.chunk_id) {
    return {
      name: "document-chunk",
      params: {
        documentId: source.document_id,
        chunkId: source.chunk_id,
      },
    };
  }

  return null;
}

function hasSourceTarget(source) {
  return Boolean(
    source.jump_url ||
      (source.document_id !== null &&
        source.document_id !== undefined &&
        source.chunk_id !== null &&
        source.chunk_id !== undefined),
  );
}

function formatScore(score) {
  if (score === null || score === undefined) {
    return "相关度未知";
  }
  return `相关度 ${Number(score).toFixed(3)}`;
}

function isMarkdownSource(source) {
  return /\.md(?:own)?$/i.test(source.file_name || "");
}
</script>

<style scoped>
.source-list {
  display: grid;
  gap: 12px;
}

.section-head,
.meta,
.footer {
  display: flex;
  align-items: center;
}

.section-head {
  justify-content: space-between;
}

h3 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 18px;
}

.section-head span,
.footer {
  color: var(--cm-muted);
  font-size: 13px;
}

.source-item {
  display: grid;
  grid-template-columns: 76px 1fr;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.rank {
  display: grid;
  height: 36px;
  place-items: center;
  border-radius: var(--cm-radius);
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
  font-size: 13px;
  font-weight: 800;
}

.content {
  min-width: 0;
}

.meta {
  justify-content: space-between;
  gap: 12px;
}

.meta strong {
  overflow: hidden;
  color: var(--cm-heading);
  text-overflow: ellipsis;
  white-space: nowrap;
}

p {
  margin: 10px 0;
  color: var(--cm-text);
  line-height: 1.7;
}

.source-text {
  cursor: pointer;
}

.source-text.collapsed {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.markdown-source {
  width: 100%;
  margin: 10px 0;
  color: var(--cm-text);
  line-height: 1.7;
}

.markdown-source.collapsed {
  display: block;
  max-height: 5.1em;
  overflow: hidden;
}

.footer .el-button {
  height: auto;
  padding: 0;
  font-size: 13px;
  font-weight: 700;
}

.footer {
  flex-wrap: wrap;
  gap: 10px;
}

.footer a {
  color: var(--cm-primary);
  font-weight: 700;
}

.source-unavailable {
  color: var(--cm-muted);
  font-weight: 700;
}

@media (max-width: 560px) {
  .source-item {
    grid-template-columns: 1fr;
  }

  .rank {
    width: fit-content;
    padding: 0 12px;
  }
}
</style>

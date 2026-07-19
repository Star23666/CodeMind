<template>
  <section class="answer-card" :class="{ error }">
    <div class="answer-head">
      <div>
        <span>{{ error ? "提示" : "AI 回答" }}</span>
        <strong>{{ status }}</strong>
      </div>
      <el-tag v-if="qaRecordId" type="info" effect="plain">#{{ qaRecordId }}</el-tag>
    </div>

    <el-skeleton v-if="loading && !answer" :rows="4" animated />

    <template v-else>
      <MarkdownContent
        class="answer-text"
        :content="answer"
        fallback="提交问题后，这里会显示回答。"
        :citation-targets="citationTargets"
      />
      <div v-if="sourceArticles.length" class="source-articles">
        <span class="source-articles__label">来源文章</span>
        <span
          v-for="article in sourceArticles"
          :key="article.key"
          class="source-article"
        >
          {{ article.fileName }}
          <small>{{ article.knowledgeBaseName }}</small>
        </span>
      </div>
      <FeedbackPanel v-if="qaRecordId && answer && !error" :qa-record-id="qaRecordId" />
    </template>
  </section>
</template>

<script setup>
import { computed } from "vue";
import MarkdownContent from "../common/MarkdownContent.vue";
import FeedbackPanel from "./FeedbackPanel.vue";

const props = defineProps({
  answer: {
    type: String,
    default: "",
  },
  status: {
    type: String,
    default: "等待提问",
  },
  qaRecordId: {
    type: Number,
    default: null,
  },
  sources: {
    type: Array,
    default: () => [],
  },
  knowledgeBaseName: {
    type: String,
    default: "当前知识库",
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: Boolean,
    default: false,
  },
});

const citationTargets = computed(() => props.sources.map(sourceTarget));

const sourceArticles = computed(() => {
  const seen = new Set();
  return props.sources.reduce((articles, source, index) => {
    const key = source.document_id ?? source.file_name ?? index;
    if (seen.has(key)) return articles;
    seen.add(key);
    articles.push({
      key,
      fileName: source.file_name || "未命名文档",
      knowledgeBaseName: props.knowledgeBaseName,
    });
    return articles;
  }, []);
});

function sourceTarget(source) {
  if (!source) return null;
  if (source.jump_url) return source.jump_url;
  if (source.document_id == null || source.chunk_id == null) return null;
  return {
    name: "document-chunk",
    params: {
      documentId: source.document_id,
      chunkId: source.chunk_id,
    },
  };
}
</script>

<style scoped>
.answer-card {
  display: grid;
  gap: 24px;
  padding: clamp(22px, 4vw, 38px);
  border: 1px solid rgba(153, 183, 219, 0.52);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.76);
  box-shadow:
    0 28px 80px rgba(62, 112, 168, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(24px) saturate(125%);
}

.answer-card.error {
  border-color: rgba(207, 111, 111, 0.42);
  background: rgba(255, 248, 248, 0.84);
}

.answer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.answer-head div {
  display: grid;
  gap: 4px;
}

.answer-head span {
  color: #3b76bd;
  font-family: "DIN Alternate", "Avenir Next", sans-serif;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.answer-head strong {
  color: #1c304d;
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: 20px;
  font-weight: 600;
}

.answer-text {
  margin: 0;
  color: #28394f;
  font-size: 16px;
  line-height: 1.95;
}

.source-articles {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px 12px;
  color: #74849a;
  font-size: 12px;
  line-height: 1.6;
}

.source-articles__label {
  color: #4c6481;
  font-weight: 750;
}

.source-article {
  position: relative;
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}

.source-article + .source-article::before {
  margin-right: 5px;
  color: #b5c1cf;
  content: "·";
}

.source-article small {
  color: #95a2b2;
  font-size: 11px;
}

.answer-card :deep(.feedback-panel) {
  border-top-color: rgba(166, 191, 221, 0.42);
}
</style>

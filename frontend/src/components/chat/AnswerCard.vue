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
      <SourceList v-if="sources.length" :sources="sources" />
      <FeedbackPanel v-if="qaRecordId && answer && !error" :qa-record-id="qaRecordId" />
    </template>
  </section>
</template>

<script setup>
import { computed } from "vue";
import MarkdownContent from "../common/MarkdownContent.vue";
import FeedbackPanel from "./FeedbackPanel.vue";
import SourceList from "./SourceList.vue";

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

.answer-card :deep(.feedback-panel) {
  border-top-color: rgba(166, 191, 221, 0.42);
}

.answer-card :deep(.source-list) {
  padding-top: 4px;
}
</style>

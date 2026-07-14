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
      <p class="answer-text">{{ answer || "提交问题后，这里会显示回答。" }}</p>
      <p v-if="rewrittenQuestion" class="rewritten">
        检索问题：{{ rewrittenQuestion }}
      </p>
      <SourceList :sources="sources" />
    </template>
  </section>
</template>

<script setup>
import SourceList from "./SourceList.vue";

defineProps({
  answer: {
    type: String,
    default: "",
  },
  status: {
    type: String,
    default: "等待提问",
  },
  rewrittenQuestion: {
    type: String,
    default: "",
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
</script>

<style scoped>
.answer-card {
  display: grid;
  gap: 18px;
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--cm-primary) 20%, var(--cm-border));
  border-radius: var(--cm-radius);
  background: var(--cm-primary-soft);
}

.answer-card.error {
  border-color: color-mix(in srgb, var(--cm-danger) 36%, var(--cm-border));
  background: color-mix(in srgb, var(--cm-danger) 10%, var(--cm-surface));
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
  color: var(--cm-muted);
  font-size: 13px;
  font-weight: 700;
}

.answer-head strong {
  color: var(--cm-heading);
  font-size: 18px;
}

.answer-text {
  margin: 0;
  color: var(--cm-text);
  line-height: 1.8;
  white-space: pre-wrap;
}

.rewritten {
  margin: 0;
  padding: 10px 12px;
  border: 1px dashed var(--cm-border);
  border-radius: var(--cm-radius);
  color: var(--cm-muted);
  background: var(--cm-surface);
  line-height: 1.6;
}
</style>

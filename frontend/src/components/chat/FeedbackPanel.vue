<template>
  <section class="feedback-panel">
    <div class="feedback-head">
      <div>
        <span>回答反馈</span>
        <strong>{{ feedback ? "感谢你的评价" : "这次回答有帮助吗？" }}</strong>
      </div>
      <el-tag v-if="feedback" type="success" effect="plain">已提交</el-tag>
    </div>

    <el-skeleton v-if="loading" :rows="2" animated />
    <template v-else-if="feedback">
      <el-rate :model-value="feedback.rating" disabled show-score score-template="{value} 分" />
      <p v-if="feedback.comment">{{ feedback.comment }}</p>
      <small>每条回答只能评价一次，提交后不可修改。</small>
    </template>
    <template v-else>
      <el-rate v-model="rating" :texts="ratingTexts" show-text aria-label="回答评分" />
      <el-input
        v-model="comment"
        type="textarea"
        :rows="3"
        maxlength="1000"
        show-word-limit
        placeholder="可选：说明回答哪里准确，或哪里需要改进"
      />
      <small>提交后，评分和文字说明将向管理员展示；私人知识库中的问题、回答和来源不会展示。</small>
      <el-button type="primary" plain :loading="submitting" :disabled="!rating" @click="submit">
        提交反馈
      </el-button>
    </template>
  </section>
</template>

<script setup>
import { ref, watch } from "vue";
import { getQaFeedback, submitQaFeedback } from "../../api/qaHistory";

const props = defineProps({
  qaRecordId: { type: Number, required: true },
});

const ratingTexts = ["没有帮助", "需要改进", "一般", "有帮助", "非常有帮助"];
const loading = ref(false);
const submitting = ref(false);
const feedback = ref(null);
const rating = ref(0);
const comment = ref("");

watch(
  () => props.qaRecordId,
  () => loadFeedback(),
  { immediate: true },
);

async function loadFeedback() {
  feedback.value = null;
  rating.value = 0;
  comment.value = "";
  if (!props.qaRecordId) return;
  loading.value = true;
  try {
    feedback.value = await getQaFeedback(props.qaRecordId);
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

async function submit() {
  if (!rating.value) {
    ElMessage.warning("请先选择 1 到 5 分。");
    return;
  }
  submitting.value = true;
  try {
    feedback.value = await submitQaFeedback(props.qaRecordId, {
      rating: rating.value,
      comment: comment.value.trim() || null,
    });
    ElMessage.success("反馈已提交，感谢你的帮助。");
  } catch (error) {
    if (error.status === 409) {
      await loadFeedback();
      ElMessage.info("该回答已经提交过反馈。");
      return;
    }
    ElMessage.error(error.message);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.feedback-panel { display: grid; gap: 14px; padding-top: 16px; border-top: 1px solid var(--cm-border); }
.feedback-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.feedback-head > div { display: grid; gap: 4px; }
.feedback-head span, .feedback-panel small { color: var(--cm-muted); font-size: 13px; }
.feedback-head strong { color: var(--cm-heading); }
.feedback-panel p { margin: 0; padding: 10px 12px; border-radius: var(--cm-radius); color: var(--cm-text); background: var(--cm-surface); line-height: 1.6; white-space: pre-wrap; }
.feedback-panel .el-button { justify-self: start; }
</style>

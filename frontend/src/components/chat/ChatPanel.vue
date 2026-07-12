<template>
  <section class="chat-panel" id="chat">
    <div class="panel-head">
      <div>
        <p>AI 知识库问答</p>
        <h2>围绕你的资料提问</h2>
      </div>
      <el-tag effect="plain">{{ knowledgeBaseName || "未选择知识库" }}</el-tag>
    </div>

    <el-input
      ref="questionInput"
      v-model="question"
      type="textarea"
      :autosize="{ minRows: 5, maxRows: 8 }"
      maxlength="500"
      show-word-limit
      placeholder="例如：这份资料里对项目部署流程是怎么描述的？"
      @keydown.ctrl.enter="askQuestion"
    />

    <div class="controls">
      <el-select v-model="topK" class="topk-select" aria-label="召回片段数量">
        <el-option label="Top 4 片段" :value="4" />
        <el-option label="Top 6 片段" :value="6" />
        <el-option label="Top 8 片段" :value="8" />
      </el-select>
      <el-input-number
        v-model="scoreThreshold"
        :min="-1"
        :max="1"
        :step="0.01"
        controls-position="right"
        aria-label="相似度阈值"
      />
      <el-button type="primary" :icon="Search" :loading="loading" @click="askQuestion">
        发送问题
      </el-button>
    </div>

    <AnswerCard
      :answer="answer"
      :status="answerStatus"
      :rewritten-question="rewrittenQuestion"
      :qa-record-id="qaRecordId"
      :sources="sources"
      :loading="loading"
      :error="hasError"
    />
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from "vue";
import { ElMessageBox } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import { sendChatQuestion } from "../../api/chat";
import { useUserStore } from "../../stores/user";
import AnswerCard from "./AnswerCard.vue";

const props = defineProps({
  knowledgeBaseId: {
    type: Number,
    default: null,
  },
  knowledgeBaseName: {
    type: String,
    default: "",
  },
  initialQuestion: {
    type: String,
    default: "",
  },
});

const router = useRouter();
const userStore = useUserStore();
const question = ref(props.initialQuestion);
const topK = ref(4);
const scoreThreshold = ref(0.3);
const answer = ref("");
const answerStatus = ref("等待提问");
const rewrittenQuestion = ref("");
const qaRecordId = ref(null);
const sources = ref([]);
const loading = ref(false);
const hasError = ref(false);
const questionInput = ref(null);

watch(
  () => props.initialQuestion,
  (nextQuestion) => {
    if (nextQuestion) {
      question.value = nextQuestion;
    }
  },
);

async function askQuestion() {
  if (!userStore.isLoggedIn) {
    router.push({ name: "login", query: { redirect: "/" } });
    return;
  }

  if (!props.knowledgeBaseId) {
    try {
      await ElMessageBox.confirm(
        "请先创建一个知识库，再开始提问。",
        "创建一个知识库",
        {
          confirmButtonText: "去创建",
          cancelButtonText: "取消",
          type: "warning",
        },
      );
      router.push({ name: "me" });
    } catch {
      // 用户取消后留在当前页面。
    }
    return;
  }

  const trimmedQuestion = question.value.trim();

  if (!trimmedQuestion) {
    hasError.value = true;
    answerStatus.value = "需要输入问题";
    answer.value = "请先输入一个和资料相关的问题。";
    sources.value = [];
    return;
  }

  loading.value = true;
  hasError.value = false;
  answerStatus.value = "检索与生成中";
  answer.value = "";
  rewrittenQuestion.value = "";
  qaRecordId.value = null;

  try {
    const data = await sendChatQuestion({
      knowledge_base_id: props.knowledgeBaseId,
      question: trimmedQuestion,
      top_k: topK.value,
      score_threshold: scoreThreshold.value,
      rerank_top_n: 2,
      enable_rewrite: true,
      enable_rerank: true,
    });

    answer.value = data.answer || "后端已返回响应，但没有检测到 answer 字段。";
    answerStatus.value = data.sources?.length ? "已生成带来源回答" : "资料依据不足";
    rewrittenQuestion.value = data.rewritten_question || "";
    qaRecordId.value = data.qa_record_id || null;
    sources.value = data.sources || [];
  } catch (error) {
    hasError.value = true;
    answerStatus.value = "请求失败";
    answer.value = error.message;
    sources.value = [];
  } finally {
    loading.value = false;
  }
}

async function focusQuestion() {
  await nextTick();
  questionInput.value?.focus?.();
}

function setQuestion(nextQuestion) {
  question.value = nextQuestion;
  focusQuestion();
}

defineExpose({
  focusQuestion,
  setQuestion,
});
</script>

<style scoped>
.chat-panel {
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.panel-head,
.controls {
  display: flex;
  align-items: center;
}

.panel-head {
  justify-content: space-between;
  gap: 16px;
}

.panel-head p {
  margin: 0 0 6px;
  color: var(--cm-primary);
  font-size: 13px;
  font-weight: 800;
}

h2 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 22px;
}

.controls {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
}

.topk-select {
  width: 140px;
}

@media (max-width: 700px) {
  .panel-head,
  .controls {
    align-items: stretch;
    flex-direction: column;
  }

  .topk-select {
    width: 100%;
  }
}
</style>

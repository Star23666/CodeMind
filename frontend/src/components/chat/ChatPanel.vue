<template>
  <section class="chat-experience" id="chat">
    <Transition name="screen-shift" mode="out-in" appear>
      <div v-if="viewState === 'compose'" key="compose" class="compose-stage">
        <slot name="intro" />

        <form ref="composerRef" class="composer" @submit.prevent="askQuestion">
          <label class="sr-only" for="home-question">输入你的问题</label>
          <textarea
            id="home-question"
            ref="questionInput"
            v-model="question"
            maxlength="500"
            rows="2"
            placeholder="向你的知识库提问…"
            aria-controls="recent-question-history"
            :aria-expanded="historyOpen && visibleRecentRecords.length > 0"
            @focus="openRecentHistory"
            @keydown.esc="historyOpen = false"
            @keydown.ctrl.enter.prevent="askQuestion"
          ></textarea>

          <Transition name="history-reveal">
            <section
              v-if="historyOpen && visibleRecentRecords.length"
              id="recent-question-history"
              class="recent-history"
              aria-label="最近提问"
            >
              <div class="recent-history__head">
                <span>{{ question.trim() ? "匹配历史" : "最近提问" }}</span>
                <RouterLink to="/history" @mousedown.prevent>查看完整历史</RouterLink>
              </div>
              <button
                v-for="record in visibleRecentRecords"
                :key="record.id"
                class="recent-question"
                type="button"
                @mousedown.prevent
                @click="applyHistoryQuestion(record.question)"
              >
                <span>{{ record.question }}</span>
                <small>{{ formatHistoryTime(record.created_at) }}</small>
              </button>
            </section>
          </Transition>

          <div class="composer-meta">
            <span class="character-count">{{ question.length }} / 500</span>

            <div class="composer-toolbar">
              <div class="tool-group">
                <el-dropdown
                  :disabled="!knowledgeBases.length"
                  trigger="click"
                  max-height="320"
                  @command="selectKnowledgeBase"
                >
                  <button
                    class="tool-control tool-control--knowledge"
                    type="button"
                    :disabled="!knowledgeBases.length"
                  >
                    <span>知识库</span>
                    <strong>{{ currentKnowledgeBase?.name || "请选择" }}</strong>
                    <svg viewBox="0 0 16 16" aria-hidden="true">
                      <path d="m4.5 6 3.5 3.5L11.5 6" />
                    </svg>
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu class="knowledge-menu">
                      <el-dropdown-item
                        v-for="base in knowledgeBases"
                        :key="base.id"
                        :command="base.id"
                        :class="{ 'is-current': base.id === knowledgeBaseId }"
                      >
                        <span class="dropdown-name">{{ base.name }}</span>
                        <span class="dropdown-type">
                          {{ base.visibility === "public" ? "公共" : "私人" }}
                        </span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>

                <el-dropdown trigger="click" @command="selectTopK">
                  <button class="tool-control" type="button">
                    <span>Top K</span>
                    <strong>{{ topK }}</strong>
                    <svg viewBox="0 0 16 16" aria-hidden="true">
                      <path d="m4.5 6 3.5 3.5L11.5 6" />
                    </svg>
                  </button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="value in [4, 6, 8]"
                        :key="value"
                        :command="value"
                        :class="{ 'is-current': value === topK }"
                      >
                        召回 {{ value }} 个片段
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>

                <el-popover
                  placement="bottom"
                  :width="276"
                  trigger="click"
                  popper-class="threshold-popover"
                >
                  <template #reference>
                    <button class="tool-control" type="button">
                      <span>置信度</span>
                      <strong>{{ scoreThreshold.toFixed(2) }}</strong>
                      <svg viewBox="0 0 16 16" aria-hidden="true">
                        <path d="m4.5 6 3.5 3.5L11.5 6" />
                      </svg>
                    </button>
                  </template>

                  <div class="threshold-panel">
                    <div class="threshold-heading">
                      <span>检索置信度</span>
                      <label class="threshold-input">
                        <span class="sr-only">手动输入检索置信度</span>
                        <input
                          v-model="scoreThresholdInput"
                          type="number"
                          inputmode="decimal"
                          min="0"
                          max="1"
                          step="0.01"
                          @change="commitScoreThreshold"
                          @blur="commitScoreThreshold"
                          @keydown.enter.prevent="commitScoreThreshold"
                        />
                      </label>
                    </div>
                    <el-slider
                      v-model="scoreThreshold"
                      :min="0"
                      :max="1"
                      :step="0.01"
                      :show-tooltip="false"
                      aria-label="检索置信度"
                    />
                    <p>请输入 0–1，超出范围将恢复默认值。</p>
                  </div>
                </el-popover>
              </div>

              <button
                class="send-button"
                type="submit"
                :disabled="loading"
                aria-label="发送问题"
                title="发送问题（Ctrl + Enter）"
              >
                <span v-if="loading" class="send-spinner"></span>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 18V6m0 0-5 5m5-5 5 5" />
                </svg>
              </button>
            </div>
          </div>
        </form>

        <p v-if="validationMessage" class="validation-message" role="alert">
          {{ validationMessage }}
        </p>
      </div>

      <div v-else key="result" class="result-stage">
        <header class="result-intro">
          <div class="result-copy">
            <div class="answer-kicker">
              <span class="status-dot" :class="{ active: loading }"></span>
              {{ loading ? "正在检索并组织回答" : answerStatus }}
            </div>
            <h1>{{ questionSnapshot }}</h1>
            <p>
              {{ currentKnowledgeBase?.name || "当前知识库" }}
              <span aria-hidden="true">·</span>
              Top {{ topK }}
              <span aria-hidden="true">·</span>
              置信度 {{ scoreThreshold.toFixed(2) }}
            </p>
          </div>
          <button class="ask-again" type="button" :disabled="loading" @click="returnToComposer">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M15.5 6.5A7 7 0 1 0 17 11m-1.5-4.5V3m0 3.5H12" />
            </svg>
            继续提问
          </button>
        </header>

        <AnswerCard
          :answer="answer"
          :status="answerStatus"
          :rewritten-question="rewrittenQuestion"
          :qa-record-id="qaRecordId"
          :sources="sources"
          :knowledge-base-name="currentKnowledgeBase?.name"
          :loading="loading"
          :error="hasError"
        />
      </div>
    </Transition>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { DEFAULT_SCORE_THRESHOLD, streamChatQuestion } from "../../api/chat";
import { listQaRecords } from "../../api/qaHistory";
import { useUserStore } from "../../stores/user";
import AnswerCard from "./AnswerCard.vue";

const props = defineProps({
  knowledgeBaseId: {
    type: Number,
    default: null,
  },
  knowledgeBases: {
    type: Array,
    default: () => [],
  },
  initialQuestion: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["update:knowledge-base-id"]);
const router = useRouter();
const userStore = useUserStore();
const question = ref(props.initialQuestion);
const questionSnapshot = ref("");
const topK = ref(4);
const normalizedDefaultScoreThreshold =
  Number.isFinite(Number(DEFAULT_SCORE_THRESHOLD)) &&
  Number(DEFAULT_SCORE_THRESHOLD) >= 0 &&
  Number(DEFAULT_SCORE_THRESHOLD) <= 1
    ? Number(DEFAULT_SCORE_THRESHOLD)
    : 0.45;
const scoreThreshold = ref(normalizedDefaultScoreThreshold);
const scoreThresholdInput = ref(normalizedDefaultScoreThreshold.toFixed(2));
const answer = ref("");
const answerStatus = ref("等待提问");
const rewrittenQuestion = ref("");
const qaRecordId = ref(null);
const sources = ref([]);
const loading = ref(false);
const hasError = ref(false);
const validationMessage = ref("");
const questionInput = ref(null);
const composerRef = ref(null);
const streamController = ref(null);
const viewState = ref("compose");
const historyOpen = ref(false);
const recentRecords = ref([]);
const recentHistoryLoaded = ref(false);
let suppressNextHistoryOpen = false;

const currentKnowledgeBase = computed(() =>
  props.knowledgeBases.find((base) => base.id === props.knowledgeBaseId),
);

const visibleRecentRecords = computed(() => {
  const query = question.value.trim().toLocaleLowerCase();
  if (!query) return recentRecords.value.slice(0, 5);
  return recentRecords.value
    .filter((record) => record.question.toLocaleLowerCase().includes(query))
    .slice(0, 5);
});

watch(
  () => props.initialQuestion,
  (nextQuestion) => {
    if (nextQuestion) {
      question.value = nextQuestion;
    }
  },
);

watch(question, () => {
  if (validationMessage.value) validationMessage.value = "";
});

watch(scoreThreshold, (value) => {
  scoreThresholdInput.value = Number(value).toFixed(2);
});

onMounted(() => {
  document.addEventListener("pointerdown", closeHistoryOnOutsideClick);
});

function selectKnowledgeBase(id) {
  emit("update:knowledge-base-id", id);
  validationMessage.value = "";
}

function selectTopK(value) {
  topK.value = value;
}

function commitScoreThreshold() {
  const rawValue = String(scoreThresholdInput.value ?? "").trim();
  const value = Number(rawValue);
  scoreThreshold.value =
    rawValue !== "" && Number.isFinite(value) && value >= 0 && value <= 1
      ? Math.round(value * 100) / 100
      : normalizedDefaultScoreThreshold;
  scoreThresholdInput.value = scoreThreshold.value.toFixed(2);
}

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
    validationMessage.value = "先写下你想从知识库中了解的问题。";
    await focusQuestion();
    return;
  }

  questionSnapshot.value = trimmedQuestion;
  viewState.value = "result";
  loading.value = true;
  hasError.value = false;
  validationMessage.value = "";
  answerStatus.value = "检索与生成中";
  answer.value = "";
  rewrittenQuestion.value = "";
  qaRecordId.value = null;
  sources.value = [];
  streamController.value?.abort();
  const controller = new AbortController();
  streamController.value = controller;

  try {
    await streamChatQuestion(
      {
        knowledge_base_id: props.knowledgeBaseId,
        question: trimmedQuestion,
        top_k: topK.value,
        score_threshold: scoreThreshold.value,
        rerank_top_n: 2,
        enable_rewrite: true,
        enable_rerank: true,
      },
      {
        signal: controller.signal,
        onMeta(data) {
          rewrittenQuestion.value = data.rewritten_question || "";
          sources.value = data.sources || [];
          answerStatus.value = sources.value.length ? "资料已找到，生成中" : "资料依据不足";
        },
        onToken(delta) {
          answer.value += delta;
          answerStatus.value = "流式生成中";
        },
        onDone(data) {
          answer.value = data.answer || answer.value;
          rewrittenQuestion.value = data.rewritten_question || rewrittenQuestion.value;
          qaRecordId.value = data.qa_record_id || null;
          sources.value = data.sources || sources.value;
          answerStatus.value = sources.value.length ? "已生成带来源回答" : "资料依据不足";
          loadRecentHistory({ force: true, show: false });
        },
      },
    );
  } catch (error) {
    if (error.name === "AbortError") {
      answerStatus.value = "已停止生成";
      return;
    }
    hasError.value = true;
    answerStatus.value = "请求失败";
    if (!answer.value) answer.value = error.message;
  } finally {
    if (streamController.value === controller) streamController.value = null;
    loading.value = false;
  }
}

async function returnToComposer() {
  if (loading.value) return;
  question.value = "";
  questionSnapshot.value = "";
  answer.value = "";
  rewrittenQuestion.value = "";
  qaRecordId.value = null;
  sources.value = [];
  hasError.value = false;
  answerStatus.value = "等待提问";
  viewState.value = "compose";
  await focusQuestion();
}

onBeforeUnmount(() => {
  streamController.value?.abort();
  document.removeEventListener("pointerdown", closeHistoryOnOutsideClick);
});

async function focusQuestion() {
  await nextTick();
  questionInput.value?.focus?.();
}

function setQuestion(nextQuestion) {
  question.value = nextQuestion;
  if (viewState.value !== "compose" && !loading.value) {
    viewState.value = "compose";
  }
  focusQuestion();
}

async function openRecentHistory() {
  if (suppressNextHistoryOpen) {
    suppressNextHistoryOpen = false;
    return;
  }
  if (!userStore.isLoggedIn) return;
  historyOpen.value = true;
  await loadRecentHistory();
}

async function loadRecentHistory({ force = false, show = true } = {}) {
  if (!userStore.isLoggedIn || (recentHistoryLoaded.value && !force)) return;
  try {
    recentRecords.value = await listQaRecords({ limit: 50 });
    recentHistoryLoaded.value = true;
    if (show && visibleRecentRecords.value.length) historyOpen.value = true;
  } catch {
    recentRecords.value = [];
  }
}

function applyHistoryQuestion(historyQuestion) {
  question.value = historyQuestion;
  historyOpen.value = false;
  suppressNextHistoryOpen = true;
  focusQuestion();
}

function closeHistoryOnOutsideClick(event) {
  if (!composerRef.value?.contains(event.target)) {
    historyOpen.value = false;
  }
}

function formatHistoryTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

defineExpose({
  focusQuestion,
  setQuestion,
});
</script>

<style scoped>
.chat-experience {
  width: 100%;
}

.compose-stage {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 28px;
  width: 100%;
  transform: translateY(-76px);
}

.composer {
  position: relative;
  z-index: 4;
  width: min(880px, 100%);
  overflow: visible;
  border: 1px solid rgba(149, 181, 219, 0.62);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.84);
  box-shadow:
    0 28px 80px rgba(48, 107, 175, 0.16),
    0 8px 24px rgba(72, 124, 184, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(24px) saturate(132%);
  transition:
    border-color 0.25s ease,
    box-shadow 0.25s ease;
}

.composer:focus-within {
  border-color: rgba(51, 126, 218, 0.72);
  box-shadow:
    0 32px 90px rgba(48, 107, 175, 0.2),
    0 0 0 4px rgba(51, 126, 218, 0.07);
}

textarea {
  display: block;
  width: 100%;
  height: 76px;
  min-height: 76px;
  max-height: 76px;
  overflow-y: auto;
  resize: none;
  border: 0;
  outline: 0;
  padding: 11px 22px 5px;
  color: #18283f;
  background: transparent;
  font-size: 18px;
  line-height: 1.55;
  scrollbar-color: rgba(104, 151, 204, 0.4) transparent;
  scrollbar-width: thin;
}

textarea::placeholder {
  color: #8997aa;
}

.recent-history {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  left: 0;
  z-index: 12;
  display: grid;
  gap: 1px;
  max-height: 242px;
  overflow-y: auto;
  padding: 9px;
  border: 1px solid rgba(147, 180, 218, 0.58);
  border-radius: 18px;
  background: rgba(251, 253, 255, 0.96);
  box-shadow:
    0 24px 60px rgba(45, 91, 145, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(22px) saturate(130%);
  scrollbar-color: rgba(104, 151, 204, 0.45) transparent;
  scrollbar-width: thin;
}

.recent-history__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 3px 9px 8px;
  color: #718096;
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0.06em;
}

.recent-history__head a {
  color: #5595dc;
  font-weight: 700;
  letter-spacing: 0;
}

.recent-history__head a:hover {
  color: #226ebf;
}

.recent-question {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  width: 100%;
  border: 0;
  border-radius: 11px;
  min-height: 35px;
  padding: 7px 10px;
  color: #344961;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition:
    color 0.18s ease,
    background 0.18s ease;
}

.recent-question:hover,
.recent-question:focus-visible {
  color: #1d65b5;
  background: rgba(220, 237, 255, 0.66);
  outline: none;
}

.recent-question span {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-question small {
  flex: 0 0 auto;
  color: #99a6b6;
  font-size: 10px;
}

.history-reveal-enter-active,
.history-reveal-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.history-reveal-enter-from,
.history-reveal-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.99);
}

.history-reveal-enter-active {
  transform-origin: top center;
}

.composer-meta {
  padding: 0 14px 14px;
}

.character-count {
  display: block;
  margin: 0 10px 8px;
  color: #9aa7b7;
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 11px;
  text-align: right;
}

.composer-toolbar,
.tool-group,
.tool-control,
.send-button,
.result-intro,
.ask-again,
.answer-kicker {
  display: flex;
  align-items: center;
}

.composer-toolbar {
  justify-content: space-between;
  gap: 14px;
}

.tool-group {
  min-width: 0;
  flex-wrap: wrap;
  gap: 4px;
}

.tool-control {
  max-width: 260px;
  height: 38px;
  gap: 6px;
  border: 0;
  border-radius: 12px;
  padding: 0 11px;
  color: #596a7f;
  background: transparent;
  cursor: pointer;
  transition:
    color 0.2s ease,
    background 0.2s ease;
}

.tool-control:hover,
.tool-control:focus-visible {
  color: #174f9e;
  background: rgba(48, 119, 210, 0.08);
  outline: 0;
}

.tool-control:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.tool-control span {
  font-size: 12px;
}

.tool-control strong {
  overflow: hidden;
  max-width: 136px;
  color: #1d3454;
  font-size: 12px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-control svg {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.send-button {
  width: 46px;
  height: 46px;
  flex: 0 0 auto;
  justify-content: center;
  border: 0;
  border-radius: 50%;
  color: #ffffff;
  background: linear-gradient(145deg, #2465d4, #238fe8);
  box-shadow:
    0 10px 25px rgba(32, 108, 210, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.32);
  cursor: pointer;
  transition:
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.send-button:hover:not(:disabled) {
  box-shadow:
    0 14px 30px rgba(32, 108, 210, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.32);
  transform: translateY(-2px);
}

.send-button:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}

.send-button:disabled {
  cursor: wait;
  opacity: 0.68;
}

.send-button svg {
  width: 23px;
  height: 23px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.send-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.42);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.validation-message {
  position: absolute;
  bottom: -30px;
  margin: 0;
  font-size: 12px;
}

.validation-message {
  color: #bd4b4b;
}

.threshold-panel {
  display: grid;
  gap: 15px;
  padding: 4px 2px 2px;
}

.threshold-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #596a7f;
  font-size: 13px;
}

.threshold-input input {
  width: 76px;
  border: 1px solid #d7e3f0;
  border-radius: 9px;
  outline: none;
  padding: 6px 8px;
  color: #174f9e;
  background: #f8fbff;
  font-family: "DIN Alternate", Consolas, monospace;
  font-size: 14px;
  font-weight: 750;
  text-align: center;
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.threshold-input input:focus {
  border-color: #70a8e9;
  box-shadow: 0 0 0 3px rgba(67, 137, 219, 0.1);
}

.threshold-panel p {
  margin: -4px 0 0;
  color: #8491a2;
  font-size: 11px;
  line-height: 1.6;
}

.result-stage {
  display: grid;
  gap: 22px;
  width: min(980px, 100%);
  margin: 12px auto 0;
  padding-bottom: 46px;
}

.result-intro {
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  padding: 4px 4px 0;
}

.result-copy {
  min-width: 0;
}

.answer-kicker {
  gap: 8px;
  margin-bottom: 12px;
  color: #3472be;
  font-size: 12px;
  font-weight: 750;
  letter-spacing: 0.06em;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #5f9dde;
  box-shadow: 0 0 0 5px rgba(64, 137, 218, 0.1);
}

.status-dot.active {
  animation: pulse 1.6s ease-out infinite;
}

.result-intro h1 {
  margin: 0;
  color: #10213a;
  font-family: "Source Han Serif SC", "Songti SC", "STSong", serif;
  font-size: clamp(30px, 4.4vw, 48px);
  font-weight: 600;
  letter-spacing: -0.035em;
  line-height: 1.25;
  text-wrap: balance;
}

.result-intro p {
  margin: 12px 0 0;
  color: #738197;
  font-size: 12px;
}

.result-intro p span {
  margin: 0 6px;
  color: #aab4c1;
}

.ask-again {
  flex: 0 0 auto;
  gap: 8px;
  border: 1px solid rgba(145, 177, 215, 0.58);
  border-radius: 999px;
  padding: 10px 15px;
  color: #315f96;
  background: rgba(255, 255, 255, 0.66);
  cursor: pointer;
  backdrop-filter: blur(14px);
  transition:
    background 0.2s ease,
    transform 0.2s ease;
}

.ask-again:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.92);
  transform: translateY(-1px);
}

.ask-again:disabled {
  cursor: wait;
  opacity: 0.52;
}

.ask-again svg {
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.5;
}

.screen-shift-enter-active {
  transition:
    opacity 0.55s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.screen-shift-leave-active {
  transition:
    opacity 0.34s ease,
    transform 0.34s cubic-bezier(0.4, 0, 1, 1);
}

.screen-shift-enter-from {
  opacity: 0;
  transform: translateY(72px);
}

.screen-shift-leave-to {
  opacity: 0;
  transform: translateY(-64px) scale(0.985);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  margin: -1px;
  padding: 0;
  border: 0;
  clip: rect(0, 0, 0, 0);
}

:deep(.el-dropdown-menu__item.is-current) {
  color: #1f63b7;
  background: #eef6ff;
}

:deep(.knowledge-menu .el-dropdown-menu__item) {
  display: flex;
  min-width: 240px;
  justify-content: space-between;
  gap: 16px;
}

.dropdown-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-type {
  color: #8996a8;
  font-size: 11px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(64, 137, 218, 0.34);
  }
  70% {
    box-shadow: 0 0 0 8px rgba(64, 137, 218, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(64, 137, 218, 0);
  }
}

@media (max-width: 700px) {
  .compose-stage {
    gap: 24px;
    transform: translateY(-28px);
  }

  .composer {
    border-radius: 20px;
  }

  textarea {
    height: 72px;
    min-height: 72px;
    max-height: 72px;
    padding: 10px 18px 4px;
    font-size: 16px;
  }

  .composer-meta {
    padding: 0 9px 10px;
  }

  .recent-history {
    top: calc(100% + 8px);
    max-height: 224px;
    border-radius: 15px;
  }

  .recent-question small {
    display: none;
  }

  .composer-toolbar {
    align-items: flex-end;
  }

  .tool-group {
    gap: 2px;
  }

  .tool-control {
    height: 34px;
    padding: 0 8px;
  }

  .tool-control span {
    display: none;
  }

  .tool-control strong {
    max-width: 92px;
  }

  .send-button {
    width: 42px;
    height: 42px;
  }

  .result-intro {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .screen-shift-enter-active,
  .screen-shift-leave-active {
    transition-duration: 0.01ms;
  }

  .status-dot.active,
  .send-spinner {
    animation: none;
  }
}
</style>

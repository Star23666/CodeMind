<template>
  <div class="quiz-view">
    <AppHeader :health-online="healthOnline" />

    <main class="quiz-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">PRACTICE LAB</p>
        <h1>AI 定制练习</h1>
        <p>从你有权阅读的知识库中组合资料，生成带原文依据的即时练习。</p>
      </div>
      <div v-if="session && !result" class="session-state" aria-live="polite">
        <span>{{ session.status === "ready" ? "练习进行中" : "后台生成中" }}</span>
        <strong>{{ session.progress }}%</strong>
      </div>
    </header>

    <section v-if="loadingBases" class="state-panel" aria-live="polite">
      <el-skeleton :rows="6" animated />
    </section>

    <section v-else-if="!session && !result" class="setup-layout">
      <form class="setup-form" @submit.prevent="startQuiz">
        <section class="form-section" aria-labelledby="quiz-sources-heading">
          <div class="section-heading">
            <div>
              <span>01</span>
              <h2 id="quiz-sources-heading">选择资料范围</h2>
            </div>
            <b>{{ form.knowledge_base_ids.length }}/5</b>
          </div>

          <div v-if="publicBases.length" class="base-group">
            <h3>公共知识库</h3>
            <label
              v-for="base in publicBases"
              :key="base.id"
              class="base-option public"
              :class="{ selected: form.knowledge_base_ids.includes(base.id) }"
            >
              <input
                v-model="form.knowledge_base_ids"
                type="checkbox"
                :value="base.id"
                :disabled="baseSelectionDisabled(base.id)"
              />
              <span class="base-mark">公</span>
              <span>
                <strong>{{ base.name }}</strong>
                <small>{{ base.description || "所有登录用户可读取" }}</small>
              </span>
            </label>
          </div>

          <div class="base-group">
            <h3>我的知识库</h3>
            <div v-if="privateBases.length" class="base-grid">
              <label
                v-for="base in privateBases"
                :key="base.id"
                class="base-option"
                :class="{ selected: form.knowledge_base_ids.includes(base.id) }"
              >
                <input
                  v-model="form.knowledge_base_ids"
                  type="checkbox"
                  :value="base.id"
                  :disabled="baseSelectionDisabled(base.id)"
                />
                <span class="base-mark">私</span>
                <span>
                  <strong>{{ base.name }}</strong>
                  <small>{{ base.description || "仅你本人可读取" }}</small>
                </span>
              </label>
            </div>
            <el-empty v-else description="还没有私人知识库" :image-size="64" />
          </div>
        </section>

        <section class="form-section" aria-labelledby="quiz-config-heading">
          <div class="section-heading">
            <div>
              <span>02</span>
              <h2 id="quiz-config-heading">设置练习方式</h2>
            </div>
          </div>

          <div class="config-grid">
            <label class="field-block">
              <span>题目数量</span>
              <el-input-number v-model="form.question_count" :min="5" :max="20" />
              <small>支持 5～20 题</small>
            </label>

            <fieldset class="field-block difficulty-field">
              <legend>难度</legend>
              <el-radio-group v-model="form.difficulty">
                <el-radio-button value="basic">基础</el-radio-button>
                <el-radio-button value="intermediate">进阶</el-radio-button>
                <el-radio-button value="challenge">挑战</el-radio-button>
              </el-radio-group>
            </fieldset>

            <label class="field-block topic-field">
              <span>主题关键词 <i>可选</i></span>
              <el-input
                v-model="form.topic"
                maxlength="100"
                show-word-limit
                placeholder="例如：进程调度、TCP 拥塞控制"
              />
            </label>
          </div>

          <div class="type-heading">
            <div>
              <strong>题型范围</strong>
              <small>{{ form.random_mix ? "AI 将在所选题型中随机混合" : "AI 将覆盖每种所选题型" }}</small>
            </div>
            <el-switch
              v-model="form.random_mix"
              active-text="随机混合"
              inactive-text="指定题型"
            />
          </div>
          <el-checkbox-group v-model="form.question_types" class="type-grid">
            <el-checkbox
              v-for="item in questionTypeOptions"
              :key="item.value"
              :value="item.value"
              border
            >
              <span class="type-symbol">{{ item.symbol }}</span>
              {{ item.label }}
            </el-checkbox>
          </el-checkbox-group>

          <div class="disclosure-row">
            <div>
              <strong>提交后显示解析与资料来源</strong>
              <small>正确答案始终只会在提交后返回</small>
            </div>
            <el-switch v-model="form.show_explanations_and_sources" />
          </div>
        </section>

        <div class="setup-actions">
          <p v-if="formError" role="alert">{{ formError }}</p>
          <el-button
            type="primary"
            size="large"
            native-type="submit"
            :loading="creating"
          >
            生成练习
          </el-button>
        </div>
      </form>

      <aside class="setup-summary">
        <span>本次练习</span>
        <strong>{{ form.question_count }}</strong>
        <p>道 {{ difficultyLabel(form.difficulty) }}题</p>
        <dl>
          <div><dt>知识库</dt><dd>{{ form.knowledge_base_ids.length }} 个</dd></div>
          <div><dt>题型</dt><dd>{{ form.question_types.length }} 种</dd></div>
          <div><dt>模式</dt><dd>{{ form.random_mix ? "随机混合" : "指定题型" }}</dd></div>
        </dl>
        <small>练习提交或过期后会自动清理，不会保存为历史试卷。</small>
      </aside>
    </section>

    <section v-else-if="isGenerating" class="generation-panel" aria-live="polite">
      <el-progress
        class="generation-ring"
        type="circle"
        :percentage="session.progress"
        :width="116"
        :stroke-width="10"
      />
      <p class="eyebrow">{{ stageLabel(session.stage) }}</p>
      <h2>{{ session.message }}</h2>
      <el-progress :percentage="session.progress" :show-text="false" />
      <ol class="generation-steps">
        <li :class="stepClass(18)">均衡抽取多知识库资料</li>
        <li :class="stepClass(42)">生成多种题型</li>
        <li :class="stepClass(82)">校验答案与来源</li>
        <li :class="stepClass(100)">准备作答界面</li>
      </ol>
      <p v-if="session.status === 'failed'" class="error-message" role="alert">
        {{ session.error_message || "出题失败，请稍后重试。" }}
      </p>
      <div class="generation-actions">
        <el-button v-if="session.status === 'failed'" type="primary" @click="discardAndReset">
          重新配置
        </el-button>
        <el-button v-else @click="cancelQuiz">取消生成</el-button>
      </div>
    </section>

    <section v-else-if="session?.status === 'ready' && currentQuestion" class="practice-layout">
      <aside class="question-index" aria-label="题目导航">
        <div>
          <span>作答进度</span>
          <strong>{{ answeredCount }}/{{ questions.length }}</strong>
        </div>
        <el-progress
          :percentage="Math.round((answeredCount / questions.length) * 100)"
          :show-text="false"
        />
        <nav>
          <button
            v-for="(question, index) in questions"
            :key="question.id"
            type="button"
            :class="{
              active: index === currentIndex,
              answered: isAnswered(question),
            }"
            :aria-label="`第 ${index + 1} 题${isAnswered(question) ? '，已作答' : ''}`"
            @click="currentIndex = index"
          >
            {{ index + 1 }}
          </button>
        </nav>
        <small>答案仅保存在当前页面，提交后临时会话会被清理。</small>
      </aside>

      <article class="question-card">
        <header>
          <div>
            <span>第 {{ currentIndex + 1 }} / {{ questions.length }} 题</span>
            <el-tag effect="plain">{{ questionTypeLabel(currentQuestion.question_type) }}</el-tag>
          </div>
          <small>{{ currentQuestion.source_count }} 条资料依据</small>
        </header>
        <h2>{{ currentQuestion.prompt }}</h2>

        <el-radio-group
          v-if="currentQuestion.question_type === 'single_choice'"
          v-model="answers[currentQuestion.id]"
          class="answer-options"
        >
          <el-radio
            v-for="option in currentQuestion.options"
            :key="option.id"
            :value="option.id"
            border
          >
            <b>{{ option.id }}</b>{{ option.text }}
          </el-radio>
        </el-radio-group>

        <el-checkbox-group
          v-else-if="currentQuestion.question_type === 'multiple_choice'"
          v-model="answers[currentQuestion.id]"
          class="answer-options"
        >
          <el-checkbox
            v-for="option in currentQuestion.options"
            :key="option.id"
            :value="option.id"
            border
          >
            <b>{{ option.id }}</b>{{ option.text }}
          </el-checkbox>
        </el-checkbox-group>

        <el-radio-group
          v-else-if="currentQuestion.question_type === 'true_false'"
          v-model="answers[currentQuestion.id]"
          class="judgment-options"
        >
          <el-radio :value="true" border>正确</el-radio>
          <el-radio :value="false" border>错误</el-radio>
        </el-radio-group>

        <el-input
          v-else-if="currentQuestion.question_type === 'fill_blank'"
          v-model="answers[currentQuestion.id]"
          size="large"
          maxlength="300"
          placeholder="填写答案"
          @keyup.enter="goNext"
        />

        <el-input
          v-else
          v-model="answers[currentQuestion.id]"
          type="textarea"
          :rows="7"
          maxlength="2000"
          show-word-limit
          :placeholder="
            currentQuestion.question_type === 'scenario'
              ? '结合情景写出分析过程和解决方案'
              : '用自己的语言概括答案'
          "
        />

        <footer>
          <el-button :disabled="currentIndex === 0" @click="currentIndex -= 1">
            上一题
          </el-button>
          <div>
            <el-button v-if="currentIndex < questions.length - 1" type="primary" @click="goNext">
              下一题
            </el-button>
            <el-button v-else type="primary" :loading="submitting" @click="submitQuiz">
              提交练习
            </el-button>
          </div>
        </footer>
      </article>
    </section>

    <section v-else-if="result" class="result-layout">
      <header class="completion-card">
        <p class="eyebrow">PRACTICE COMPLETE</p>
        <span class="score-caption">客观题得分</span>
        <div class="score-line">
          <strong>{{ result.score_percent ?? "—" }}</strong>
          <span v-if="result.score_percent != null">分</span>
        </div>
        <h2>{{ completionTitle }}</h2>
        <p>{{ result.message }}</p>
        <dl>
          <div><dt>自动评分</dt><dd>{{ result.correct_count }}/{{ result.auto_scored_count }}</dd></div>
          <div><dt>主观自评</dt><dd>{{ manualReviewedCount }}/{{ result.manual_review_count }}</dd></div>
          <div><dt>客观题最长连对</dt><dd>{{ longestStreak }} 题</dd></div>
        </dl>
        <el-button type="primary" size="large" @click="resetQuiz">再生成一组</el-button>
      </header>

      <div class="result-column">
        <section class="result-toolbar" aria-label="结果筛选与展开设置">
          <el-radio-group v-model="resultFilter" size="small">
            <el-radio-button value="all">全部 {{ result.results.length }}</el-radio-button>
            <el-radio-button value="incorrect">需复习 {{ reviewNeededCount }}</el-radio-button>
            <el-radio-button value="pending">待自评 {{ manualPendingCount }}</el-radio-button>
          </el-radio-group>
          <div>
            <el-button size="small" @click="expandAllResults">展开全部</el-button>
            <el-button size="small" @click="collapseAllResults">折叠全部</el-button>
          </div>
        </section>

        <el-empty v-if="!filteredResults.length" description="当前筛选下没有题目" />
        <div v-else class="result-list">
          <details
            v-for="item in filteredResults"
            :key="item.question_id"
            class="result-card"
            :class="resultClass(item)"
            :open="expandedResultIds.has(item.question_id)"
            @toggle="syncResultExpanded(item.question_id, $event)"
          >
            <summary class="result-summary">
              <div>
                <span>第 {{ item.order_no }} 题 · {{ questionTypeLabel(item.question_type) }}</span>
                <strong>{{ resultStatus(item) }}</strong>
              </div>
              <h3>{{ item.prompt }}</h3>
            </summary>
            <div class="result-body">
              <div class="answer-compare">
                <p><span>你的答案</span>{{ formatAnswer(item.submitted_answer, item.options) }}</p>
                <p v-if="item.correct_answer !== null">
                  <span>正确答案</span>{{ formatAnswer(item.correct_answer, item.options) }}
                </p>
                <p v-if="item.reference_answer">
                  <span>参考答案</span>{{ item.reference_answer }}
                </p>
              </div>
              <section v-if="item.is_correct === null" class="self-review">
                <div>
                  <strong>完成主观题自评</strong>
                  <small>请对照参考答案判断自己的回答是否覆盖了关键点。</small>
                </div>
                <el-radio-group
                  :model-value="subjectiveAssessments[item.question_id] || ''"
                  size="small"
                  @change="selfAssess(item.question_id, $event)"
                >
                  <el-radio-button value="mastered">基本掌握</el-radio-button>
                  <el-radio-button value="review">需要复习</el-radio-button>
                </el-radio-group>
              </section>
              <section v-if="item.explanation" class="explanation">
                <strong>答案解析</strong>
                <p>{{ item.explanation }}</p>
              </section>
              <details v-if="item.sources.length" class="source-details">
                <summary>查看 {{ item.sources.length }} 条资料来源</summary>
                <article v-for="source in item.sources" :key="source.source_id">
                  <div>
                    <strong>{{ source.file_name }}</strong>
                    <span>{{ source.knowledge_base_name }} · 片段 {{ source.chunk_index + 1 }}</span>
                  </div>
                  <p>{{ source.source_text }}</p>
                  <RouterLink :to="source.jump_url" target="_blank" rel="noopener noreferrer">
                    在新标签页打开原文片段 →
                  </RouterLink>
                </article>
              </details>
            </div>
          </details>
        </div>
      </div>
    </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import {
  abandonQuizSession,
  createQuizSession,
  getQuizSession,
  submitQuizSession,
} from "../api/quizzes";
import AppHeader from "../components/layout/AppHeader.vue";
import { useUserStore } from "../stores/user";

const ACTIVE_SESSION_KEY_PREFIX = "codemind_active_quiz_session";
const RESULT_STATE_KEY_PREFIX = "codemind_quiz_result";
const RESULT_STATE_VERSION = 1;
const questionTypeOptions = [
  { value: "single_choice", label: "单项选择", symbol: "A" },
  { value: "multiple_choice", label: "多项选择", symbol: "多" },
  { value: "true_false", label: "判断题", symbol: "✓" },
  { value: "fill_blank", label: "填空题", symbol: "填" },
  { value: "short_answer", label: "简答题", symbol: "答" },
  { value: "scenario", label: "情景应用", symbol: "用" },
];

const knowledgeBases = ref([]);
const loadingBases = ref(true);
const healthOnline = ref(false);
const creating = ref(false);
const submitting = ref(false);
const formError = ref("");
const session = ref(null);
const result = ref(null);
const resultFilter = ref("all");
const expandedResultIds = ref(new Set());
const currentIndex = ref(0);
const answers = reactive({});
const subjectiveAssessments = reactive({});
const userStore = useUserStore();
let pollTimer = null;
let pollFailureCount = 0;

const form = reactive({
  knowledge_base_ids: [],
  question_count: 10,
  difficulty: "intermediate",
  question_types: questionTypeOptions.map((item) => item.value),
  random_mix: true,
  topic: "",
  show_explanations_and_sources: true,
});

const publicBases = computed(() =>
  knowledgeBases.value.filter((base) => base.visibility === "public" && base.can_read),
);
const privateBases = computed(() =>
  knowledgeBases.value.filter((base) => base.visibility === "private" && base.can_read),
);
const questions = computed(() => session.value?.questions || []);
const currentQuestion = computed(() => questions.value[currentIndex.value] || null);
const isGenerating = computed(() =>
  ["queued", "processing", "failed"].includes(session.value?.status),
);
const answeredCount = computed(() =>
  questions.value.filter((question) => isAnswered(question)).length,
);
const longestStreak = computed(() => {
  let current = 0;
  let longest = 0;
  for (const item of result.value?.results || []) {
    if (item.is_correct === null) continue;
    current = item.is_correct === true ? current + 1 : 0;
    longest = Math.max(longest, current);
  }
  return longest;
});
const manualReviewedCount = computed(() =>
  (result.value?.results || []).filter(
    (item) => item.is_correct === null && subjectiveAssessments[item.question_id],
  ).length,
);
const manualPendingCount = computed(() =>
  Math.max(0, (result.value?.manual_review_count || 0) - manualReviewedCount.value),
);
const reviewNeededCount = computed(() =>
  (result.value?.results || []).filter(
    (item) => item.is_correct === false || subjectiveAssessments[item.question_id] === "review",
  ).length,
);
const filteredResults = computed(() => {
  const items = result.value?.results || [];
  if (resultFilter.value === "incorrect") {
    return items.filter(
      (item) => item.is_correct === false || subjectiveAssessments[item.question_id] === "review",
    );
  }
  if (resultFilter.value === "pending") {
    return items.filter(
      (item) => item.is_correct === null && !subjectiveAssessments[item.question_id],
    );
  }
  return items;
});
const completionTitle = computed(() => {
  const score = result.value?.score_percent;
  if (score == null) return "完成本轮练习";
  if (manualPendingCount.value > 0) return "客观题已完成，主观题待自评";
  if (reviewNeededCount.value > 0) return "已经定位到需要复习的部分";
  if (score >= 90) return "本轮练习掌握得很扎实";
  if (score >= 70) return "状态不错，继续巩固";
  return "已经定位到需要复习的部分";
});

function userScopedKey(prefix) {
  return `${prefix}:${userStore.userId || "anonymous"}`;
}

function activeSessionKey() {
  return userScopedKey(ACTIVE_SESSION_KEY_PREFIX);
}

function resultStateKey() {
  return userScopedKey(RESULT_STATE_KEY_PREFIX);
}

onMounted(async () => {
  window.addEventListener("beforeunload", handleBeforeUnload);
  checkHealth();
  try {
    knowledgeBases.value = await listKnowledgeBases();
    const restoredResult = restoreCompletedResult();
    const activeSessionId = sessionStorage.getItem(activeSessionKey());
    if (!restoredResult && activeSessionId) {
      try {
        session.value = await getQuizSession(activeSessionId);
        initializeAnswers();
        if (isGenerating.value && session.value.status !== "failed") schedulePoll();
      } catch (error) {
        if ([404, 410].includes(error.status)) {
          sessionStorage.removeItem(activeSessionKey());
        } else {
          session.value = {
            session_id: activeSessionId,
            status: "processing",
            stage: "queued",
            progress: 0,
            message: "正在重新连接未完成的出题任务。",
            error_message: null,
          };
          schedulePoll(2000);
        }
      }
    }
  } catch (error) {
    formError.value = error.message;
  } finally {
    loadingBases.value = false;
  }
});

async function checkHealth() {
  try {
    const data = await getHealth();
    healthOnline.value = data.status === "ok";
  } catch {
    healthOnline.value = false;
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", handleBeforeUnload);
  clearPoll();
});

onBeforeRouteLeave(async () => {
  if (!hasUnfinishedQuiz()) return true;
  try {
    await ElMessageBox.confirm(
      "离开后本次未完成练习会被清理，确定继续吗？",
      "离开当前练习",
      {
        confirmButtonText: "清理并离开",
        cancelButtonText: "继续作答",
        type: "warning",
      },
    );
  } catch {
    return false;
  }
  await abandonCurrentSession();
  return true;
});

function baseSelectionDisabled(baseId) {
  return form.knowledge_base_ids.length >= 5 && !form.knowledge_base_ids.includes(baseId);
}

async function startQuiz() {
  formError.value = "";
  if (!form.knowledge_base_ids.length) {
    formError.value = "请至少选择一个知识库。";
    return;
  }
  if (!form.question_types.length) {
    formError.value = "请至少选择一种题型。";
    return;
  }
  if (form.random_mix && form.question_types.length < 2) {
    formError.value = "随机混合模式至少需要选择两种题型。";
    return;
  }
  creating.value = true;
  pollFailureCount = 0;
  try {
    clearCompletedResult();
    session.value = await createQuizSession({
      ...form,
      topic: form.topic.trim() || null,
    });
    sessionStorage.setItem(activeSessionKey(), session.value.session_id);
    schedulePoll(300);
  } catch (error) {
    formError.value = error.message;
  } finally {
    creating.value = false;
  }
}

function schedulePoll(delay = 1000) {
  clearPoll();
  pollTimer = window.setTimeout(pollSession, delay);
}

async function pollSession() {
  if (!session.value?.session_id) return;
  try {
    session.value = await getQuizSession(session.value.session_id);
    pollFailureCount = 0;
    if (session.value.status === "ready") {
      initializeAnswers();
      return;
    }
    if (session.value.status !== "failed") schedulePoll();
  } catch (error) {
    if ([404, 410].includes(error.status)) {
      ElMessage.error(error.message);
      resetQuiz();
      return;
    }
    pollFailureCount += 1;
    if (pollFailureCount === 1) {
      ElMessage.warning("网络连接暂时中断，正在自动重试出题进度。");
    }
    schedulePoll(Math.min(1000 * 2 ** Math.min(pollFailureCount, 3), 8000));
  }
}

function initializeAnswers() {
  for (const key of Object.keys(answers)) delete answers[key];
  for (const question of questions.value) {
    answers[question.id] = question.question_type === "multiple_choice" ? [] : null;
  }
  currentIndex.value = 0;
  pollFailureCount = 0;
}

function isAnswered(question) {
  const value = answers[question.id];
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "boolean") return true;
  return typeof value === "string" ? value.trim().length > 0 : value != null;
}

function goNext() {
  if (currentIndex.value < questions.value.length - 1) currentIndex.value += 1;
}

async function submitQuiz() {
  const unanswered = questions.value.length - answeredCount.value;
  if (unanswered > 0) {
    try {
      await ElMessageBox.confirm(
        `还有 ${unanswered} 道题未作答，未作答的客观题会按错误计分。`,
        "确认提交",
        { confirmButtonText: "仍然提交", cancelButtonText: "继续作答", type: "warning" },
      );
    } catch {
      return;
    }
  }
  submitting.value = true;
  try {
    result.value = await submitQuizSession(session.value.session_id, {
      answers: questions.value
        .filter((question) => isAnswered(question))
        .map((question) => ({
          question_id: question.id,
          answer: answers[question.id],
        })),
    });
    sessionStorage.removeItem(activeSessionKey());
    session.value = null;
    initializeResultView();
    persistCompletedResult();
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    submitting.value = false;
  }
}

async function cancelQuiz() {
  try {
    await ElMessageBox.confirm("确定取消并清理本次出题任务吗？", "取消生成", {
      confirmButtonText: "取消任务",
      cancelButtonText: "继续等待",
      type: "warning",
    });
  } catch {
    return;
  }
  await abandonCurrentSession();
  resetQuiz();
}

async function discardAndReset() {
  await abandonCurrentSession();
  resetQuiz();
}

async function abandonCurrentSession() {
  const sessionId = session.value?.session_id;
  if (!sessionId) return;
  try {
    await abandonQuizSession(sessionId);
  } catch {
    // TTL cleanup remains the fallback if the network is unavailable.
  }
  sessionStorage.removeItem(activeSessionKey());
}

function resetQuiz() {
  clearPoll();
  pollFailureCount = 0;
  sessionStorage.removeItem(activeSessionKey());
  clearCompletedResult();
  session.value = null;
  result.value = null;
  resultFilter.value = "all";
  expandedResultIds.value = new Set();
  currentIndex.value = 0;
  for (const key of Object.keys(answers)) delete answers[key];
  for (const key of Object.keys(subjectiveAssessments)) delete subjectiveAssessments[key];
}

function initializeResultView(savedAssessments = {}) {
  for (const key of Object.keys(subjectiveAssessments)) delete subjectiveAssessments[key];
  Object.assign(subjectiveAssessments, savedAssessments);
  resultFilter.value = "all";
  const priorityIds = (result.value?.results || [])
    .filter((item) => item.is_correct !== true)
    .map((item) => item.question_id);
  if (!priorityIds.length && result.value?.results?.length) {
    priorityIds.push(result.value.results[0].question_id);
  }
  expandedResultIds.value = new Set(priorityIds);
}

function restoreCompletedResult() {
  const stored = sessionStorage.getItem(resultStateKey());
  if (!stored) return false;
  try {
    const state = JSON.parse(stored);
    if (state.version !== RESULT_STATE_VERSION || !Array.isArray(state.result?.results)) {
      clearCompletedResult();
      return false;
    }
    result.value = state.result;
    session.value = null;
    initializeResultView(state.subjective_assessments || {});
    return true;
  } catch {
    clearCompletedResult();
    return false;
  }
}

function persistCompletedResult() {
  if (!result.value) return;
  sessionStorage.setItem(
    resultStateKey(),
    JSON.stringify({
      version: RESULT_STATE_VERSION,
      result: result.value,
      subjective_assessments: { ...subjectiveAssessments },
    }),
  );
}

function clearCompletedResult() {
  sessionStorage.removeItem(resultStateKey());
}

function selfAssess(questionId, assessment) {
  subjectiveAssessments[questionId] = assessment;
  persistCompletedResult();
}

function syncResultExpanded(questionId, event) {
  const next = new Set(expandedResultIds.value);
  if (event.currentTarget.open) next.add(questionId);
  else next.delete(questionId);
  expandedResultIds.value = next;
}

function expandAllResults() {
  expandedResultIds.value = new Set(
    filteredResults.value.map((item) => item.question_id),
  );
}

function collapseAllResults() {
  expandedResultIds.value = new Set();
}

function clearPoll() {
  if (pollTimer != null) window.clearTimeout(pollTimer);
  pollTimer = null;
}

function hasUnfinishedQuiz() {
  return Boolean(session.value && !result.value && session.value.status !== "failed");
}

function handleBeforeUnload(event) {
  if (!hasUnfinishedQuiz()) return;
  event.preventDefault();
  event.returnValue = "";
}

function questionTypeLabel(value) {
  return questionTypeOptions.find((item) => item.value === value)?.label || value;
}

function difficultyLabel(value) {
  return { basic: "基础", intermediate: "进阶", challenge: "挑战" }[value] || value;
}

function stageLabel(value) {
  return {
    queued: "等待处理",
    starting: "准备资料",
    collecting: "资料抽取",
    generating: "AI 出题",
    validating: "质量校验",
    failed: "生成失败",
  }[value] || "正在处理";
}

function stepClass(threshold) {
  if (session.value.progress >= threshold) return "done";
  const previous = [0, 18, 42, 82].findLast((value) => value < threshold) || 0;
  return session.value.progress >= previous ? "active" : "";
}

function formatAnswer(value, options = []) {
  if (value === null || value === undefined || value === "") return "未作答";
  if (typeof value === "boolean") return value ? "正确" : "错误";
  const values = Array.isArray(value) ? value : [value];
  return values
    .map((item) => {
      const option = options.find((candidate) => candidate.id === item);
      return option ? `${option.id}. ${option.text}` : String(item);
    })
    .join("；");
}

function resultStatus(item) {
  if (item.is_correct === true) return "回答正确";
  if (item.is_correct === false) return "需要复习";
  if (subjectiveAssessments[item.question_id] === "mastered") return "自评已掌握";
  if (subjectiveAssessments[item.question_id] === "review") return "需要复习";
  return "待自评";
}

function resultClass(item) {
  if (item.is_correct === true) return "correct";
  if (item.is_correct === false) return "incorrect";
  if (subjectiveAssessments[item.question_id] === "mastered") return "correct";
  if (subjectiveAssessments[item.question_id] === "review") return "incorrect";
  return "review";
}
</script>

<style scoped>
.quiz-page {
  width: min(1180px, calc(100% - 32px));
  margin: 42px auto 80px;
  color: var(--cm-text);
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 28px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--cm-primary);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0;
}

.page-heading h1 {
  margin: 0;
  color: var(--cm-heading);
  font-size: 38px;
  line-height: 1.16;
}

.page-heading > div > p:last-child {
  max-width: 680px;
  margin: 10px 0 0;
  color: var(--cm-muted);
}

.session-state {
  display: grid;
  justify-items: end;
  gap: 3px;
  color: var(--cm-muted);
  font-size: 13px;
}

.session-state strong {
  color: var(--cm-heading);
  font-size: 28px;
}

.state-panel,
.generation-panel {
  max-width: 760px;
  margin: 60px auto;
  padding: 32px;
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  background: var(--cm-surface);
}

.setup-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  align-items: start;
  gap: 24px;
}

.setup-form {
  display: grid;
  gap: 20px;
}

.form-section,
.setup-summary,
.question-index,
.question-card,
.completion-card,
.result-card {
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.form-section {
  padding: 24px;
}

.section-heading,
.section-heading > div,
.type-heading,
.disclosure-row,
.question-card > header,
.question-card > footer,
.result-card > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.section-heading {
  margin-bottom: 20px;
}

.section-heading span {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
  font-size: 12px;
  font-weight: 900;
}

.section-heading h2,
.base-group h3 {
  margin: 0;
  color: var(--cm-heading);
}

.section-heading h2 { font-size: 19px; }
.section-heading b { color: var(--cm-muted); }
.base-group + .base-group { margin-top: 22px; }
.base-group h3 { margin-bottom: 10px; font-size: 14px; }

.base-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.base-option {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  min-height: 68px;
  padding: 12px;
  border: 1px solid var(--cm-border);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease;
}

.base-option.public { margin-bottom: 10px; }
.base-option.selected { border-color: var(--cm-primary); background: var(--cm-primary-soft); }
.base-option:has(input:disabled) { cursor: not-allowed; opacity: 0.5; }
.base-option input { accent-color: var(--cm-primary); }

.base-mark,
.type-symbol {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 5px;
  color: var(--cm-primary);
  background: var(--cm-primary-soft);
  font-size: 12px;
  font-weight: 900;
}

.base-option > span:last-child { display: grid; gap: 3px; min-width: 0; }
.base-option strong { color: var(--cm-heading); }
.base-option small {
  overflow: hidden;
  color: var(--cm-muted);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-grid {
  display: grid;
  grid-template-columns: 180px minmax(260px, 1fr);
  gap: 18px;
}

.field-block { display: grid; align-content: start; gap: 8px; }
.field-block > span,
.field-block legend { color: var(--cm-heading); font-size: 14px; font-weight: 800; }
.field-block i { color: var(--cm-muted); font-size: 12px; font-style: normal; font-weight: 500; }
.field-block small,
.type-heading small,
.disclosure-row small { color: var(--cm-muted); }
.difficulty-field { margin: 0; padding: 0; border: 0; }
.topic-field { grid-column: 1 / -1; }

.type-heading { margin: 24px 0 12px; }
.type-heading > div,
.disclosure-row > div { display: grid; gap: 3px; }
.type-heading strong,
.disclosure-row strong { color: var(--cm-heading); }

.type-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.type-grid :deep(.el-checkbox) {
  width: 100%;
  height: 48px;
  margin: 0;
}

.type-grid :deep(.el-checkbox__label) { display: flex; align-items: center; gap: 8px; }
.disclosure-row { margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--cm-border); }

.setup-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 18px;
}

.setup-actions p,
.error-message { margin: 0; color: var(--el-color-danger); }

.setup-summary {
  position: sticky;
  top: 118px;
  padding: 22px;
}

.setup-summary > span { color: var(--cm-muted); font-size: 13px; font-weight: 800; }
.setup-summary > strong { display: block; margin-top: 10px; color: var(--cm-heading); font-size: 56px; line-height: 1; }
.setup-summary > p { margin: 6px 0 22px; color: var(--cm-muted); }
.setup-summary dl { display: grid; gap: 0; margin: 0 0 20px; }
.setup-summary dl div { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--cm-border); }
.setup-summary dt { color: var(--cm-muted); }
.setup-summary dd { margin: 0; color: var(--cm-heading); font-weight: 800; }
.setup-summary > small { display: block; color: var(--cm-muted); line-height: 1.65; }

.generation-panel { text-align: center; }
.generation-ring {
  margin: 0 auto 22px;
}
.generation-ring :deep(.el-progress__text) { color: var(--cm-heading); font-weight: 900; }
.generation-panel h2 { margin: 0 0 24px; color: var(--cm-heading); font-size: 22px; }
.generation-steps { display: grid; gap: 8px; max-width: 440px; margin: 24px auto; padding: 0; list-style: none; text-align: left; }
.generation-steps li { padding: 10px 14px; border-left: 3px solid var(--cm-border); color: var(--cm-muted); background: var(--cm-surface-soft); }
.generation-steps li.active { border-color: var(--cm-primary); color: var(--cm-heading); }
.generation-steps li.done { border-color: var(--el-color-success); color: var(--cm-heading); }
.generation-actions { margin-top: 18px; }

.practice-layout {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  align-items: start;
  gap: 20px;
}
.question-index { position: sticky; top: 118px; padding: 18px; }
.question-index > div { display: flex; justify-content: space-between; margin-bottom: 10px; }
.question-index span,
.question-index small { color: var(--cm-muted); }
.question-index strong { color: var(--cm-heading); }
.question-index nav { display: grid; grid-template-columns: repeat(5, 1fr); gap: 7px; margin: 18px 0; }
.question-index button {
  aspect-ratio: 1;
  border: 1px solid var(--cm-border);
  border-radius: 5px;
  color: var(--cm-muted);
  background: var(--cm-surface);
  cursor: pointer;
}
.question-index button.answered { border-color: var(--el-color-success); color: var(--el-color-success); }
.question-index button.active { border-color: var(--cm-primary); color: white; background: var(--cm-primary); }
.question-index > small { display: block; line-height: 1.6; }

.question-card { min-height: 540px; padding: 28px; }
.question-card > header { padding-bottom: 18px; border-bottom: 1px solid var(--cm-border); }
.question-card > header > div { display: flex; align-items: center; gap: 10px; }
.question-card > header span,
.question-card > header small { color: var(--cm-muted); font-size: 13px; }
.question-card h2 { margin: 32px 0; color: var(--cm-heading); font-size: 23px; line-height: 1.55; }
.answer-options { display: grid; gap: 12px; }
.answer-options :deep(.el-radio),
.answer-options :deep(.el-checkbox) { width: 100%; min-height: 52px; height: auto; margin: 0; padding: 12px 16px; }
.answer-options b { display: inline-grid; width: 26px; height: 26px; margin-right: 10px; place-items: center; border-radius: 4px; background: var(--cm-surface-soft); }
.judgment-options { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.judgment-options :deep(.el-radio) { width: 100%; height: 58px; margin: 0; justify-content: center; }
.question-card > footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--cm-border); }

.result-layout { display: grid; grid-template-columns: 300px minmax(0, 1fr); align-items: start; gap: 22px; }
.completion-card { position: sticky; top: 118px; padding: 26px; text-align: center; }
.score-caption { display: block; margin-top: 18px; color: var(--cm-muted); font-size: 12px; font-weight: 800; }
.score-line { display: flex; align-items: flex-end; justify-content: center; gap: 4px; margin: 18px 0 10px; }
.score-line strong { color: var(--cm-primary); font-size: 64px; line-height: 1; }
.score-line span { padding-bottom: 8px; color: var(--cm-muted); }
.completion-card h2 { margin: 0; color: var(--cm-heading); font-size: 21px; }
.completion-card > p:not(.eyebrow) { color: var(--cm-muted); line-height: 1.6; }
.completion-card dl { display: grid; grid-template-columns: repeat(3, 1fr); margin: 22px 0; }
.completion-card dl div { display: grid; gap: 4px; }
.completion-card dt { color: var(--cm-muted); font-size: 11px; }
.completion-card dd { margin: 0; color: var(--cm-heading); font-weight: 900; }
.result-column,
.result-list { display: grid; gap: 14px; }
.result-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--cm-border);
  border-radius: 8px;
  background: var(--cm-surface);
}
.result-toolbar > div { display: flex; }
.result-card { overflow: hidden; }
.result-summary { padding: 14px 18px; cursor: pointer; background: var(--cm-surface-soft); }
.result-card[open] > .result-summary { border-bottom: 1px solid var(--cm-border); }
.result-summary > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.result-summary span { color: var(--cm-muted); font-size: 12px; }
.result-summary h3 { margin: 12px 0 0; color: var(--cm-heading); line-height: 1.55; }
.result-card.correct .result-summary strong { color: var(--el-color-success); }
.result-card.incorrect .result-summary strong { color: var(--el-color-danger); }
.result-card.review .result-summary strong { color: var(--el-color-warning); }
.result-body { padding-top: 10px; }
.answer-compare { display: grid; gap: 8px; padding: 8px 20px 18px; }
.answer-compare p { margin: 0; line-height: 1.6; }
.answer-compare span { display: inline-block; min-width: 72px; margin-right: 10px; color: var(--cm-muted); font-size: 12px; font-weight: 800; }
.explanation { margin: 0 20px 18px; padding: 14px; border-left: 3px solid var(--cm-primary); background: var(--cm-primary-soft); }
.explanation strong { color: var(--cm-heading); }
.explanation p { margin: 6px 0 0; line-height: 1.65; }
.self-review {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 0 20px 18px;
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: 6px;
  background: var(--cm-surface-soft);
}
.self-review > div { display: grid; gap: 4px; }
.self-review strong { color: var(--cm-heading); }
.self-review small { color: var(--cm-muted); line-height: 1.5; }
.source-details { margin: 0 20px 20px; border-top: 1px solid var(--cm-border); }
.source-details summary { padding: 14px 0; color: var(--cm-primary); font-weight: 800; cursor: pointer; }
.source-details article { padding: 14px; border: 1px solid var(--cm-border); border-radius: 6px; background: var(--cm-surface-soft); }
.source-details article + article { margin-top: 8px; }
.source-details article > div { display: flex; justify-content: space-between; gap: 12px; }
.source-details article span { color: var(--cm-muted); font-size: 12px; }
.source-details article p { margin: 10px 0; color: var(--cm-muted); line-height: 1.6; }
.source-details article a { color: var(--cm-primary); font-weight: 800; }

@media (max-width: 920px) {
  .setup-layout,
  .practice-layout,
  .result-layout { grid-template-columns: 1fr; }
  .setup-summary,
  .question-index,
  .completion-card { position: static; }
  .question-index nav { grid-template-columns: repeat(10, 1fr); }
}

@media (max-width: 640px) {
  .quiz-page { width: min(100% - 20px, 1180px); margin-top: 26px; }
  .page-heading { align-items: flex-start; }
  .page-heading h1 { font-size: 30px; }
  .session-state { display: none; }
  .form-section,
  .question-card { padding: 18px; }
  .base-grid,
  .config-grid,
  .type-grid,
  .judgment-options { grid-template-columns: 1fr; }
  .question-index nav { grid-template-columns: repeat(5, 1fr); }
  .question-card h2 { margin: 24px 0; font-size: 20px; }
  .result-toolbar,
  .self-review { align-items: stretch; flex-direction: column; }
  .result-toolbar > div { width: 100%; }
  .result-toolbar > div .el-button { flex: 1; }
  .result-summary > div { align-items: flex-start; }
  .source-details article > div { display: grid; }
}
</style>

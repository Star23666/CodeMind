<template>
  <main class="app-shell">
    <header class="topbar enter enter-0">
      <div class="brand">
        <span class="brand-mark">
          <el-icon><Cpu /></el-icon>
        </span>
        <span>CodeMind</span>
      </div>

      <el-segmented v-model="activeMode" :options="modeOptions" size="large" />

      <div class="top-actions">
        <el-tag type="success" effect="light" round>RAG Demo</el-tag>
        <el-button :icon="DataAnalysis" round>知识库概览</el-button>
      </div>
    </header>

    <section class="hero">
      <div class="hero-copy enter enter-1">
        <p class="eyebrow">
          <span class="status-dot"></span>
          计算机知识智能问答平台
        </p>
        <h1>把课程资料变成可追溯的 AI 助教</h1>
        <p class="description">
          上传讲义、实验文档和复习资料后，CodeMind
          会完成知识切分、语义检索与答案生成，帮助学生快速定位概念、代码思路和引用来源。
        </p>

        <div class="hero-actions">
          <el-button
            type="primary"
            size="large"
            :icon="ChatDotRound"
            @click="focusQuestion"
          >
            开始提问
          </el-button>
          <el-button size="large" :icon="UploadFilled" @click="scrollToUpload">
            上传资料
          </el-button>
        </div>

        <div class="quick-prompts" aria-label="推荐问题">
          <button
            v-for="prompt in promptExamples"
            :key="prompt"
            type="button"
            @click="usePrompt(prompt)"
          >
            {{ prompt }}
          </button>
        </div>
      </div>

      <aside class="hero-console enter enter-2" aria-label="模型运行状态">
        <div class="console-head">
          <div>
            <span class="console-label">Live Retrieval</span>
            <strong>Hybrid Search Pipeline</strong>
          </div>
          <div class="signal-bars" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>

        <div class="trace-list">
          <div
            v-for="(stage, index) in pipeline"
            :key="stage.label"
            class="trace-line"
            :style="{ '--delay': `${index * 0.16}s` }"
          >
            <div class="trace-meta">
              <span>{{ stage.label }}</span>
              <strong>{{ stage.value }}</strong>
            </div>
            <div class="trace-track">
              <span :style="{ width: stage.value }"></span>
            </div>
          </div>
        </div>

        <div class="answer-preview">
          <el-icon><Connection /></el-icon>
          <p>已就绪：支持文档上传、知识库检索、上下文增强回答与来源展示。</p>
        </div>
      </aside>
    </section>

    <section class="workspace">
      <section ref="uploadPanel" class="panel upload-panel enter enter-3">
        <div class="panel-head">
          <span class="panel-icon teal">
            <el-icon><UploadFilled /></el-icon>
          </span>
          <div>
            <h2>文档上传</h2>
            <p>把课程资料放进知识库，后端接入后会自动完成解析和向量化。</p>
          </div>
        </div>

        <el-upload
          drag
          action="/api/documents/upload"
          name="file"
          accept=".pdf,.doc,.docx,.md,.txt"
          :limit="6"
        >
          <el-icon class="upload-icon"><UploadFilled /></el-icon>
          <div class="upload-text">拖拽文件到此处，或点击选择上传</div>
          <template #tip>
            <p class="tip">
              建议上传 PDF、DOCX、Markdown 或 TXT，单次最多 6 个文件。
            </p>
          </template>
        </el-upload>

        <div class="file-types">
          <span>PDF</span>
          <span>DOCX</span>
          <span>MD</span>
          <span>TXT</span>
        </div>
      </section>

      <section class="panel ask-panel enter enter-4">
        <div class="panel-head">
          <span class="panel-icon blue">
            <el-icon><ChatDotRound /></el-icon>
          </span>
          <div>
            <h2>知识库问答</h2>
            <p>输入问题后，系统会按相关度检索片段并生成回答。</p>
          </div>
        </div>

        <el-input
          ref="questionInput"
          v-model="question"
          type="textarea"
          :autosize="{ minRows: 5, maxRows: 8 }"
          maxlength="500"
          show-word-limit
          placeholder="例如：操作系统中进程和线程有什么区别？请结合调度、资源和通信方式说明。"
        />

        <div class="ask-toolbar">
          <el-select
            v-model="topK"
            size="large"
            class="topk-select"
            aria-label="检索片段数量"
          >
            <el-option label="Top 3 片段" :value="3" />
            <el-option label="Top 5 片段" :value="5" />
            <el-option label="Top 8 片段" :value="8" />
          </el-select>
          <el-button
            type="primary"
            size="large"
            :loading="isLoading"
            :icon="Search"
            @click="askQuestion"
          >
            发送问题
          </el-button>
        </div>

        <transition name="answer">
          <div
            v-if="answer || answerStatus"
            class="answer"
            :class="{ 'is-error': hasError }"
          >
            <div class="answer-title">
              <span>{{ hasError ? "演示提示" : "AI 回答" }}</span>
              <el-tag size="small" effect="plain">{{ answerStatus }}</el-tag>
            </div>
            <p>{{ answer }}</p>
          </div>
        </transition>
      </section>

      <section class="panel metrics-panel enter enter-5">
        <div class="panel-head compact">
          <span class="panel-icon coral">
            <el-icon><TrendCharts /></el-icon>
          </span>
          <div>
            <h2>运行指标</h2>
            <p>演示状态数据，方便展示系统能力。</p>
          </div>
        </div>

        <div class="metrics-grid">
          <div
            v-for="metric in metrics"
            :key="metric.label"
            class="metric-item"
            :class="metric.tone"
          >
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <em>{{ metric.trend }}</em>
          </div>
        </div>
      </section>

      <section class="panel sources-panel enter enter-6">
        <div class="panel-head compact">
          <span class="panel-icon gold">
            <el-icon><DocumentChecked /></el-icon>
          </span>
          <div>
            <h2>来源片段</h2>
            <p>回答生成时展示可追溯依据。</p>
          </div>
        </div>

        <div class="source-list">
          <div
            v-for="source in sources"
            :key="source.title"
            class="source-item"
          >
            <span>{{ source.type }}</span>
            <div>
              <strong>{{ source.title }}</strong>
              <p>{{ source.summary }}</p>
            </div>
          </div>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup>
import { nextTick, ref } from "vue";
import {
  ChatDotRound,
  Connection,
  Cpu,
  DataAnalysis,
  DocumentChecked,
  Search,
  TrendCharts,
  UploadFilled,
} from "@element-plus/icons-vue";
import axios from "axios";

const activeMode = ref("课程问答");
const modeOptions = ["课程问答", "实验辅导", "知识复盘"];
const question = ref("");
const answer = ref("");
const answerStatus = ref("等待提问");
const hasError = ref(false);
const isLoading = ref(false);
const topK = ref(5);
const questionInput = ref(null);
const uploadPanel = ref(null);

const promptExamples = [
  "进程和线程有什么区别？",
  "数据库索引为什么能加速查询？",
  "TCP 三次握手解决了什么问题？",
];

const pipeline = [
  { label: "文档切分", value: "96%" },
  { label: "向量召回", value: "88%" },
  { label: "语义重排", value: "72%" },
  { label: "答案生成", value: "91%" },
];

const metrics = [
  { label: "已索引文档", value: "128", trend: "+18 本周", tone: "teal" },
  { label: "平均响应", value: "1.8s", trend: "低延迟", tone: "blue" },
  { label: "命中率", value: "92%", trend: "Top 5", tone: "coral" },
];

const sources = [
  {
    type: "OS",
    title: "操作系统-进程管理.pdf",
    summary: "包含进程、线程、调度状态与上下文切换说明。",
  },
  {
    type: "DB",
    title: "数据库系统概论.md",
    summary: "记录 B+ 树索引、事务隔离级别和查询优化笔记。",
  },
  {
    type: "NET",
    title: "计算机网络复习.docx",
    summary: "覆盖 TCP、拥塞控制、可靠传输和 HTTP 缓存。",
  },
];

function usePrompt(prompt) {
  question.value = prompt;
  focusQuestion();
}

async function focusQuestion() {
  await nextTick();
  questionInput.value?.focus?.();
}

function scrollToUpload() {
  uploadPanel.value?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function askQuestion() {
  const trimmedQuestion = question.value.trim();

  if (!trimmedQuestion) {
    hasError.value = true;
    answerStatus.value = "需要输入问题";
    answer.value = "请先输入一个和课程知识相关的问题。";
    return;
  }

  isLoading.value = true;
  hasError.value = false;
  answerStatus.value = "检索中";
  answer.value = "";

  try {
    const response = await axios.post("/api/chat", {
      question: trimmedQuestion,
      top_k: topK.value,
    });

    answer.value =
      response.data?.answer || "后端已返回响应，但没有检测到 answer 字段。";
    answerStatus.value = `已引用 Top ${topK.value} 片段`;
  } catch (error) {
    hasError.value = true;
    answerStatus.value = "演示模式";
    answer.value =
      "当前后端服务尚未连接，页面已保留真实请求逻辑。启动 /api/chat 后，这里会展示知识库生成的回答。";
  } finally {
    isLoading.value = false;
  }
}
</script>

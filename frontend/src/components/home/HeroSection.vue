<template>
  <section class="hero">
    <div class="copy">
      <p class="eyebrow">计算机知识智能问答平台</p>
      <h1>把课程资料变成可追溯的 AI 助教</h1>
      <p class="description">
        上传讲义、实验文档和复习资料后，CodeMind 会围绕知识库进行检索增强问答，
        并把答案依据清楚地展示给用户。
      </p>

      <div class="actions">
        <el-button type="primary" size="large" :icon="ChatDotRound" @click="$emit('focus-chat')">
          开始提问
        </el-button>
        <el-button size="large" :icon="UploadFilled" @click="$emit('focus-upload')">
          上传资料
        </el-button>
      </div>

      <div class="quick-prompts" aria-label="推荐问题">
        <button
          v-for="prompt in prompts"
          :key="prompt"
          type="button"
          @click="$emit('use-prompt', prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </div>

    <aside class="pipeline" aria-label="RAG 流程">
      <div class="pipeline-head">
        <span>RAG Pipeline</span>
        <strong>已接入 /api/chat 演示链路</strong>
      </div>
      <div class="steps">
        <div v-for="step in steps" :key="step.label" class="step">
          <span>{{ step.label }}</span>
          <strong>{{ step.value }}</strong>
        </div>
      </div>
      <p class="note">
        当前可真实调用问答接口；检索侧、历史持久化仍是后端 mock/内存实现。
      </p>
    </aside>
  </section>
</template>

<script setup>
import { ChatDotRound, UploadFilled } from "@element-plus/icons-vue";

defineEmits(["focus-chat", "focus-upload", "use-prompt"]);

const prompts = [
  "进程和线程有什么区别？",
  "RAG 为什么能提升回答可信度？",
  "知识库检索的相似度阈值有什么作用？",
];

const steps = [
  { label: "问题重写", value: "ready" },
  { label: "Mock 检索", value: "ready" },
  { label: "Prompt 组装", value: "ready" },
  { label: "LLM 降级回答", value: "ready" },
];
</script>

<style scoped>
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
  gap: 24px;
  align-items: stretch;
  padding: 54px 0 28px;
}

.copy {
  padding: 34px 0;
}

.eyebrow {
  display: inline-flex;
  margin-bottom: 14px;
  color: var(--cm-primary);
  font-weight: 800;
}

h1 {
  max-width: 760px;
  margin-bottom: 18px;
  color: var(--cm-heading);
  font-size: clamp(38px, 5vw, 62px);
  line-height: 1.06;
}

.description {
  max-width: 720px;
  margin-bottom: 26px;
  color: var(--cm-muted);
  font-size: 18px;
  line-height: 1.8;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 24px;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.quick-prompts button {
  border: 1px solid var(--cm-border);
  border-radius: 999px;
  padding: 10px 14px;
  color: var(--cm-primary);
  background: var(--cm-surface);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease;
}

.quick-prompts button:hover {
  transform: translateY(-2px);
  border-color: var(--cm-primary);
}

.pipeline {
  display: flex;
  flex-direction: column;
  min-height: 360px;
  padding: 24px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.pipeline-head {
  display: grid;
  gap: 6px;
  margin-bottom: 22px;
}

.pipeline-head span,
.note {
  color: var(--cm-muted);
}

.pipeline-head strong {
  color: var(--cm-heading);
  font-size: 21px;
}

.steps {
  display: grid;
  gap: 12px;
}

.step {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.step span {
  color: var(--cm-muted);
}

.step strong {
  color: var(--cm-success);
}

.note {
  margin: auto 0 0;
  padding-top: 20px;
  line-height: 1.7;
}

@media (max-width: 920px) {
  .hero {
    grid-template-columns: 1fr;
  }

  .copy {
    padding-bottom: 0;
  }
}

@media (max-width: 640px) {
  h1 {
    font-size: 36px;
  }

  .description {
    font-size: 16px;
  }
}
</style>

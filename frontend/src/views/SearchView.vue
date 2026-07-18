<template>
  <div class="search-view">
    <AppHeader :health-online="healthOnline" />

    <main class="page">
      <section class="page-head">
        <div>
          <el-tag effect="plain">语义检索</el-tag>
          <h1>直接查找资料片段</h1>
          <p>用自然语言搜索指定知识库，并从结果直接打开对应原文。</p>
        </div>
      </section>

      <section class="search-panel">
        <div class="search-fields">
          <label class="knowledge-field">
            <span>检索知识库</span>
            <el-select v-model="knowledgeBaseId" placeholder="请选择知识库" :disabled="loadingBases">
              <KnowledgeBaseOptions :bases="knowledgeBases" />
            </el-select>
          </label>
          <label class="query-field">
            <span>检索词</span>
            <el-input
              v-model="query"
              clearable
              maxlength="300"
              show-word-limit
              placeholder="例如：线程同步有哪些常见方式？"
              @keydown.enter="runSearch"
            />
          </label>
          <el-button type="primary" :icon="Search" :loading="loading" @click="runSearch">
            开始检索
          </el-button>
        </div>

        <el-collapse class="advanced-options">
          <el-collapse-item title="高级参数" name="advanced">
            <div class="advanced-grid">
              <label>
                <span>召回数量</span>
                <el-select v-model="topK">
                  <el-option label="Top 4" :value="4" />
                  <el-option label="Top 6" :value="6" />
                  <el-option label="Top 8" :value="8" />
                  <el-option label="Top 10" :value="10" />
                </el-select>
              </label>
              <label>
                <span>相似度阈值</span>
                <el-input-number v-model="scoreThreshold" :min="-1" :max="1" :step="0.01" />
              </label>
              <label>
                <span>精排保留</span>
                <el-input-number v-model="rerankTopN" :min="1" :max="10" />
              </label>
            </div>
          </el-collapse-item>
        </el-collapse>
      </section>

      <el-alert
        v-if="errorMessage"
        title="检索失败"
        :description="errorMessage"
        type="error"
        show-icon
        :closable="false"
      />

      <section class="results-panel" aria-live="polite">
        <div class="results-head">
          <div>
            <p>检索结果</p>
            <h2>{{ hasSearched ? `${results.length} 个相关片段` : "等待检索" }}</h2>
          </div>
          <span v-if="rewrittenQuery">检索改写：{{ rewrittenQuery }}</span>
        </div>

        <el-skeleton v-if="loading" :rows="5" animated />
        <div v-else-if="results.length" class="result-list">
          <article v-for="item in results" :key="item.chunk_id" class="result-item">
            <div class="result-meta">
              <div>
                <strong>{{ item.file_name }}</strong>
                <span>
                  片段 {{ item.chunk_index + 1 }}
                  <template v-if="item.page_no"> · 第 {{ item.page_no }} 页</template>
                </span>
              </div>
              <el-tag effect="plain">相似度 {{ formatScore(item.score) }}</el-tag>
            </div>
            <p>{{ item.source_text }}</p>
            <el-button link type="primary" @click="openSource(item)">打开原文片段</el-button>
          </article>
        </div>
        <el-empty
          v-else
          :description="emptyDescription"
          :image-size="88"
        />
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Search } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";
import { DEFAULT_SCORE_THRESHOLD } from "../api/chat";
import { getHealth } from "../api/health";
import { listKnowledgeBases } from "../api/knowledgeBases";
import { searchKnowledge } from "../api/search";
import KnowledgeBaseOptions from "../components/knowledge/KnowledgeBaseOptions.vue";
import AppHeader from "../components/layout/AppHeader.vue";
import { pickDefaultKnowledgeBase } from "../utils/knowledgeBases";

const router = useRouter();
const healthOnline = ref(false);
const loadingBases = ref(false);
const loading = ref(false);
const hasSearched = ref(false);
const knowledgeBases = ref([]);
const knowledgeBaseId = ref(null);
const query = ref("");
const topK = ref(4);
const scoreThreshold = ref(DEFAULT_SCORE_THRESHOLD);
const rerankTopN = ref(4);
const results = ref([]);
const rewrittenQuery = ref("");
const responseMessage = ref("");
const errorMessage = ref("");

const emptyDescription = computed(() => {
  if (!hasSearched.value) return "输入检索词后，这里会显示相关资料片段";
  return responseMessage.value || "没有找到达到当前相似度阈值的片段";
});

onMounted(async () => {
  checkHealth();
  loadingBases.value = true;
  try {
    knowledgeBases.value = await listKnowledgeBases();
    knowledgeBaseId.value = pickDefaultKnowledgeBase(knowledgeBases.value)?.id ?? null;
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    loadingBases.value = false;
  }
});

async function checkHealth() {
  try { healthOnline.value = (await getHealth()).status === "ok"; }
  catch { healthOnline.value = false; }
}

async function runSearch() {
  const normalizedQuery = query.value.trim();
  if (!knowledgeBaseId.value) {
    errorMessage.value = "请先选择知识库。";
    return;
  }
  if (!normalizedQuery) {
    errorMessage.value = "请输入检索词。";
    return;
  }

  loading.value = true;
  errorMessage.value = "";
  responseMessage.value = "";
  results.value = [];
  hasSearched.value = true;
  try {
    const response = await searchKnowledge({
      knowledge_base_id: knowledgeBaseId.value,
      query: normalizedQuery,
      top_k: topK.value,
      score_threshold: scoreThreshold.value,
      rerank_top_n: Math.min(rerankTopN.value, topK.value),
      enable_rewrite: true,
      enable_rerank: true,
    });
    results.value = response.results || [];
    rewrittenQuery.value = response.rewritten_query || "";
    responseMessage.value = response.message || "";
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    loading.value = false;
  }
}

function openSource(item) {
  if (item.jump_url) router.push(item.jump_url);
}

function formatScore(score) {
  return typeof score === "number" ? score.toFixed(4) : "未知";
}
</script>

<style scoped>
.search-view { min-height: 100vh; padding: 16px 0 56px; }
.page { display: grid; gap: 20px; width: min(1060px, calc(100% - 32px)); margin: 44px auto 0; }
.page-head h1 { margin: 12px 0 8px; color: var(--cm-heading); font-size: 34px; }
.page-head p { margin: 0; color: var(--cm-muted); }
.search-panel, .results-panel { display: grid; gap: 18px; padding: 22px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface); box-shadow: var(--cm-shadow); }
.search-fields { display: grid; grid-template-columns: minmax(190px, .7fr) minmax(280px, 1.6fr) auto; align-items: end; gap: 14px; }
.search-fields label, .advanced-grid label { display: grid; gap: 8px; }
.search-fields label > span, .advanced-grid label > span { color: var(--cm-heading); font-size: 13px; font-weight: 800; }
.advanced-options { border-top: 1px solid var(--cm-border); }
.advanced-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.results-head, .result-meta { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.results-head p { margin: 0 0 5px; color: var(--cm-primary); font-size: 13px; font-weight: 800; }
.results-head h2 { margin: 0; color: var(--cm-heading); }
.results-head > span { max-width: 56%; color: var(--cm-muted); font-size: 13px; line-height: 1.6; text-align: right; }
.result-list { display: grid; gap: 12px; }
.result-item { display: grid; gap: 12px; padding: 18px; border: 1px solid var(--cm-border); border-radius: var(--cm-radius); background: var(--cm-surface-soft); }
.result-meta > div { display: grid; gap: 5px; }
.result-meta strong { color: var(--cm-heading); }
.result-meta span { color: var(--cm-muted); font-size: 13px; }
.result-item p { margin: 0; color: var(--cm-text); line-height: 1.75; white-space: pre-wrap; }
.result-item .el-button { justify-self: start; }
@media (max-width: 760px) { .search-fields, .advanced-grid { grid-template-columns: 1fr; } .results-head, .result-meta { align-items: stretch; flex-direction: column; } .results-head > span { max-width: none; text-align: left; } }
@media (max-width: 640px) { .search-view { padding-top: 8px; } .page { width: min(100% - 20px, 1060px); margin-top: 32px; } }
</style>

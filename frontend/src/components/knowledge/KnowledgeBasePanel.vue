<template>
  <section class="kb-panel">
    <div class="panel-head">
      <div>
        <p>当前知识库</p>
        <div class="current-title">
          <h2>{{ currentBase?.name || "尚未选择知识库" }}</h2>
          <el-tag v-if="currentBase?.visibility === 'public'" size="small" effect="plain">公共</el-tag>
        </div>
      </div>
      <el-select v-model="model" class="kb-select" aria-label="选择知识库" placeholder="暂无知识库">
        <KnowledgeBaseOptions :bases="bases" />
      </el-select>
    </div>

    <div class="facts">
      <div>
        <span>资料范围</span>
        <strong>{{ currentBase?.visibility === "public" ? "公共协作" : "仅自己" }}</strong>
      </div>
      <div>
        <span>知识库数量</span>
        <strong>{{ bases.length }} 个</strong>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import KnowledgeBaseOptions from "./KnowledgeBaseOptions.vue";

const model = defineModel({ type: Number, default: null });

const props = defineProps({
  bases: {
    type: Array,
    default: () => [],
  },
  loaded: {
    type: Boolean,
    default: false,
  },
});

const currentBase = computed(() =>
  props.bases.find((item) => item.id === model.value),
);
</script>

<style scoped>
.kb-panel {
  display: grid;
  gap: 16px;
  padding: 22px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.panel-head {
  display: flex;
  align-items: center;
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

.current-title {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
}

.kb-select {
  width: 180px;
}

.facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.facts div {
  padding: 14px;
  border: 1px solid var(--cm-border);
  border-radius: var(--cm-radius);
  background: var(--cm-surface-soft);
}

.facts span,
.facts strong {
  display: block;
}

.facts span {
  margin-bottom: 8px;
  color: var(--cm-muted);
  font-size: 13px;
}

.facts strong {
  color: var(--cm-heading);
  font-size: 18px;
}

@media (max-width: 700px) {
  .panel-head {
    align-items: stretch;
    flex-direction: column;
  }

  .kb-select {
    width: 100%;
  }

  .facts {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <section class="kb-panel">
    <div class="panel-head">
      <div>
        <p>当前知识库</p>
        <h2>{{ currentName }}</h2>
      </div>
      <el-select v-model="model" class="kb-select" aria-label="选择知识库">
        <el-option
          v-for="base in bases"
          :key="base.id"
          :label="base.name"
          :value="base.id"
        />
        <el-option v-if="!bases.length" label="默认知识库" :value="1" />
      </el-select>
    </div>

    <div class="facts">
      <div>
        <span>接口状态</span>
        <strong>{{ loaded ? "已读取" : "未读取" }}</strong>
      </div>
      <div>
        <span>知识库数量</span>
        <strong>{{ bases.length }} 个</strong>
      </div>
      <div>
        <span>当前 ID</span>
        <strong>{{ model }}</strong>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const model = defineModel({ type: Number, default: 1 });

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

const currentName = computed(() => {
  const matched = props.bases.find((item) => item.id === model.value);
  return matched?.name || "默认知识库";
});
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

.kb-select {
  width: 180px;
}

.facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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
